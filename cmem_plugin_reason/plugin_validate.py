"""Ontology consistency validation workflow plugin module"""

from datetime import UTC, datetime
from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time

import validators.url
from cmem.cmempy.dp.proxy.graph import get
from cmem.cmempy.workspace.projects.resources.resource import create_resource
from cmem_plugin_base.dataintegration.context import ExecutionContext
from cmem_plugin_base.dataintegration.description import Icon, Plugin, PluginParameter
from cmem_plugin_base.dataintegration.entity import (
    Entities,
    Entity,
    EntityPath,
    EntitySchema,
)
from cmem_plugin_base.dataintegration.plugins import WorkflowPlugin
from cmem_plugin_base.dataintegration.types import BoolParameterType, StringParameterType
from cmem_plugin_base.dataintegration.utils import setup_cmempy_user_access
from pathvalidate import is_valid_filename

from cmem_plugin_reason.utils import (
    MAX_RAM_PERCENTAGE_DEFAULT,
    MAX_RAM_PERCENTAGE_PARAMETER,
    ONTOLOGY_GRAPH_IRI_PARAMETER,
    REASONER_PARAMETER,
    REASONERS,
    VALIDATE_PROFILES_PARAMETER,
    create_xml_catalog_file,
    get_graphs_tree,
    get_provenance,
    post_profiles,
    post_provenance,
    robot,
    send_result,
    validate_profiles,
)

environ["SSL_VERIFY"] = "false"


@Plugin(
    label="Validate OWL consistency",
    description="Validates the consistency of an OWL ontology.",
    documentation="""A task validating the consistency of an OWL ontology and generating an
    explanation if inconsistencies are found. The explanation can be written to the project as a
    Markdown file and/or to a specified graph. The Markdown string is also provided as an output
    entity using the path "text". The following reasoners are supported: ELK, Expression
    Materializing Reasoner, HermiT, JFact, Structural Reasoner and Whelk.""",
    icon=Icon(file_name="file-icons--owl.svg", package=__package__),
    parameters=[
        REASONER_PARAMETER,
        ONTOLOGY_GRAPH_IRI_PARAMETER,
        MAX_RAM_PERCENTAGE_PARAMETER,
        VALIDATE_PROFILES_PARAMETER,
        PluginParameter(
            param_type=BoolParameterType(),
            name="write_md",
            label="Write Markdown explanation file",
            description="Write Markdown file with explanation to project.",
            default_value=False,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="produce_graph",
            label="Produce output graph",
            description="Produce explanation graph.",
            default_value=False,
        ),
        PluginParameter(
            param_type=StringParameterType(),
            name="output_graph_iri",
            label="Output graph IRI",
            description="The IRI of the output graph for the inconsistency validation. ⚠️ Existing "
            "graphs will be overwritten.",
        ),
        PluginParameter(
            param_type=StringParameterType(),
            name="md_filename",
            label="Output filename",
            description="The filename of the Markdown file with the explanation of "
            "inconsistencies.⚠️ Existing files will be overwritten.",
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="stop_at_inconsistencies",
            label="Stop at inconsistencies",
            description="Raise an error if inconsistencies are found. If enabled, the plugin does "
            "not output entities.",
            default_value=False,
        ),
    ],
)
class ValidatePlugin(WorkflowPlugin):
    """Validate plugin"""

    def __init__(  # noqa: PLR0913
        self,
        ontology_graph_iri: str = "",
        reasoner: str = "elk",
        produce_graph: bool = False,
        output_graph_iri: str = "",
        write_md: bool = False,
        md_filename: str = "",
        validate_profile: bool = False,
        stop_at_inconsistencies: bool = False,
        max_ram_percentage: int = MAX_RAM_PERCENTAGE_DEFAULT,
    ) -> None:
        errors = ""
        if not validators.url(ontology_graph_iri):
            errors += 'Invalid IRI for parameter "Ontology graph IRI." '
        if produce_graph and not validators.url(output_graph_iri):
            errors += 'Invalid IRI for parameter "Output graph IRI". '
        if produce_graph and output_graph_iri == ontology_graph_iri:
            errors += "Output graph IRI cannot be the same as the Ontology graph IRI. "
        if reasoner not in REASONERS:
            errors += 'Invalid value for parameter "Reasoner". '
        if write_md and not is_valid_filename(md_filename):
            errors += 'Invalid filename for parameter "Output filename". '
        if max_ram_percentage not in range(1, 101):
            errors += 'Invalid value for parameter "Maximum RAM Percentage". '
        if errors:
            raise ValueError(errors[:-1])
        self.ontology_graph_iri = ontology_graph_iri
        self.reasoner = reasoner
        self.produce_graph = produce_graph
        self.output_graph_iri = output_graph_iri
        self.write_md = write_md
        self.stop_at_inconsistencies = stop_at_inconsistencies
        self.md_filename = md_filename if write_md else "mdfile.md"
        self.validate_profile = validate_profile
        self.max_ram_percentage = max_ram_percentage

    def get_graphs(self, graphs: dict, context: ExecutionContext) -> None:
        """Get graphs from CMEM"""
        for graph in graphs:
            self.log.info(f"Fetching graph {graph}.")
            with (Path(self.temp) / graphs[graph]).open("w", encoding="utf-8") as file:
                setup_cmempy_user_access(context.user)
                file.write(get(graph).text)

    def explain(self, graphs: dict) -> None:
        """Reason"""
        data_location = f"{self.temp}/{graphs[self.ontology_graph_iri]}"
        utctime = str(datetime.fromtimestamp(int(time()), tz=UTC))[:-6].replace(" ", "T") + "Z"

        cmd = (
            f'merge --input "{data_location}" '
            f"explain --reasoner {self.reasoner} -M inconsistency "
            f'--explanation "{self.temp}/{self.md_filename}"'
        )

        if self.produce_graph:
            cmd += (
                f' annotate --ontology-iri "{self.output_graph_iri}" '
                f'--language-annotation rdfs:label "Ontology Validation Result {utctime}" en '
                f"--language-annotation rdfs:comment "
                f'"Ontology validation of <{self.ontology_graph_iri}>" en '
                f'--link-annotation dc:source "{self.ontology_graph_iri}" '
                f'--typed-annotation dc:created "{utctime}" xsd:dateTime '
                f'--output "{self.temp}/output.ttl"'
            )

        response = robot(cmd, self.max_ram_percentage)
        if response.returncode != 0:
            if response.stdout:
                raise OSError(response.stdout.decode())
            if response.stderr:
                raise OSError(response.stderr.decode())
            raise OSError("ROBOT error")

    def make_resource(self, context: ExecutionContext) -> None:
        """Make MD resource in project"""
        create_resource(
            project_name=context.task.project_id(),
            resource_name=self.md_filename,
            file_resource=(Path(self.temp) / self.md_filename).open("r"),
            replace=True,
        )

    def add_profiles(self, valid_profiles: list) -> list:
        """Add profile validation result to output"""
        with (Path(self.temp) / self.md_filename).open("a") as mdfile:
            mdfile.write("\n\n\n# Valid Profiles:\n")
            if valid_profiles:
                profiles_str = "\n- ".join(valid_profiles)
                mdfile.write(f"- {profiles_str}\n")
        if self.produce_graph:
            post_profiles(self, valid_profiles)
        return valid_profiles

    def make_entities(self, text: str, valid_profiles: list) -> Entities:
        """Make entities"""
        values = [[text], [self.ontology_graph_iri]]
        paths = [EntityPath(path="markdown"), EntityPath(path="ontology")]
        if self.validate_profile:
            values.append(valid_profiles)
            paths.append(EntityPath(path="profile"))
        entities = [
            Entity(
                uri="https://eccenca.com/plugin_validateontology/result",
                values=values,
            ),
        ]
        schema = EntitySchema(
            type_uri="https://eccenca.com/plugin_validateontology/type",
            paths=paths,
        )
        return Entities(entities=entities, schema=schema)

    def _execute(self, context: ExecutionContext) -> Entities:
        """Run the workflow operator."""
        setup_cmempy_user_access(context.user)
        graphs = get_graphs_tree((self.ontology_graph_iri,))
        self.get_graphs(graphs, context)
        create_xml_catalog_file(self.temp, graphs)
        self.explain(graphs)

        if self.produce_graph:
            setup_cmempy_user_access(context.user)
            send_result(self.output_graph_iri, Path(self.temp) / "output.ttl")
            setup_cmempy_user_access(context.user)
            post_provenance(self, get_provenance(self, context))

        valid_profiles = (
            self.add_profiles(validate_profiles(self, graphs)) if self.validate_profile else []
        )

        if self.write_md:
            setup_cmempy_user_access(context.user)
            self.make_resource(context)

        text = (Path(self.temp) / self.md_filename).read_text()

        if self.stop_at_inconsistencies and text != "No explanations found.":
            raise RuntimeError("Inconsistencies found in Ontology.")

        return self.make_entities(text, valid_profiles)

    def execute(self, inputs: tuple, context: ExecutionContext) -> Entities:  # noqa: ARG002
        """Remove temp files on error"""
        with TemporaryDirectory() as self.temp:
            return self._execute(context)
