"""Reasoning workflow plugin module"""

import shlex
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from subprocess import run
from time import time
from uuid import uuid4

import validators.url
from cmem.cmempy.dp.proxy.graph import get
from cmem_plugin_base.dataintegration.context import ExecutionContext
from cmem_plugin_base.dataintegration.description import Icon, Plugin, PluginParameter
from cmem_plugin_base.dataintegration.entity import Entities
from cmem_plugin_base.dataintegration.parameter.graph import GraphParameterType
from cmem_plugin_base.dataintegration.plugins import WorkflowPlugin
from cmem_plugin_base.dataintegration.types import BoolParameterType, StringParameterType
from cmem_plugin_base.dataintegration.utils import setup_cmempy_user_access

from cmem_plugin_reason.utils import (
    MAX_RAM_PERCENTAGE_DEFAULT,
    MAX_RAM_PERCENTAGE_PARAMETER,
    ONTOLOGY_GRAPH_IRI_PARAMETER,
    REASONER_PARAMETER,
    REASONERS,
    ROBOT,
    create_xml_catalog_file,
    get_graphs_tree,
    send_result,
)


@Plugin(
    label="Reason",
    icon=Icon(file_name="obofoundry.png", package=__package__),
    description="Given a data and an ontology graph, this task performs reasoning using ROBOT.",
    documentation="""A task performing reasoning using ROBOT (ROBOT is an OBO Tool).
    It takes an OWL ontology and a data graph as inputs and writes the reasoning result
    to a specified graph. The following reasoner options are supported: ELK, Expression
    Materializing Reasoner, HermiT, JFact, Structural Reasoner and Whelk.""",
    parameters=[
        REASONER_PARAMETER,
        ONTOLOGY_GRAPH_IRI_PARAMETER,
        MAX_RAM_PERCENTAGE_PARAMETER,
        PluginParameter(
            param_type=GraphParameterType(
                classes=[
                    "http://www.w3.org/2002/07/owl#Ontology",
                    "https://vocab.eccenca.com/di/Dataset",
                    "http://rdfs.org/ns/void#Dataset",
                ]
            ),
            name="data_graph_iri",
            label="Data graph IRI",
            description="The IRI of the input data graph.",
        ),
        PluginParameter(
            param_type=StringParameterType(),
            name="result_graph_iri",
            label="Result graph IRI",
            description="The IRI of the output graph for the reasoning result. ⚠️ Existing graph "
            "will be overwritten.",
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="sub_class",
            label="SubClass",
            description="",
            default_value=True,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="equivalent_class",
            label="EquivalentClass",
            description="",
            default_value=False,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="disjoint_classes",
            label="DisjointClasses",
            description="",
            default_value=False,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="data_property_characteristic",
            label="DataPropertyCharacteristic",
            description="",
            default_value=False,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="equivalent_data_properties",
            label="EquivalentDataProperties",
            description="",
            default_value=False,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="sub_data_property",
            label="SubDataProperty",
            description="",
            default_value=False,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="class_assertion",
            label="ClassAssertion",
            description="Generated Axioms",
            default_value=False,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="property_assertion",
            label="PropertyAssertion",
            description="",
            default_value=False,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="equivalent_object_property",
            label="EquivalentObjectProperty",
            description="",
            default_value=False,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="inverse_object_properties",
            label="InverseObjectProperties",
            description="",
            default_value=False,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="object_property_characteristic",
            label="ObjectPropertyCharacteristic",
            description="",
            default_value=False,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="sub_object_property",
            label="SubObjectProperty",
            description="",
            default_value=False,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="object_property_range",
            label="ObjectPropertyRange",
            description="",
            default_value=False,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="object_property_domain",
            label="ObjectPropertyDomain",
            description="",
            default_value=False,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="annotate_inferred_axioms",
            label="Annnotate inferred subclass axioms",
            description="Annotate inferred subclass axioms. ⚠️ This parameter can only be enabled "
            "if the only enabled axiom generator is SubClass.",
            default_value=False,
            advanced=True,
        ),
    ],
)
class ReasonPlugin(WorkflowPlugin):
    """Robot reasoning plugin"""

    def __init__(  # noqa: PLR0913
        self,
        data_graph_iri: str = "",
        ontology_graph_iri: str = "",
        result_graph_iri: str = "",
        reasoner: str = "elk",
        class_assertion: bool = False,
        data_property_characteristic: bool = False,
        disjoint_classes: bool = False,
        equivalent_class: bool = False,
        equivalent_data_properties: bool = False,
        equivalent_object_property: bool = False,
        inverse_object_properties: bool = False,
        object_property_characteristic: bool = False,
        object_property_domain: bool = False,
        object_property_range: bool = False,
        property_assertion: bool = False,
        sub_class: bool = True,
        sub_data_property: bool = False,
        sub_object_property: bool = False,
        annotate_inferred_axioms: bool = False,
        max_ram_percentage: int = MAX_RAM_PERCENTAGE_DEFAULT,
    ) -> None:
        """Init"""
        self.axioms = {
            "SubClass": sub_class,
            "EquivalentClass": equivalent_class,
            "DisjointClasses": disjoint_classes,
            "DataPropertyCharacteristic": data_property_characteristic,
            "EquivalentDataProperties": equivalent_data_properties,
            "SubDataProperty": sub_data_property,
            "ClassAssertion": class_assertion,
            "PropertyAssertion": property_assertion,
            "EquivalentObjectProperty": equivalent_object_property,
            "InverseObjectProperties": inverse_object_properties,
            "ObjectPropertyCharacteristic": object_property_characteristic,
            "SubObjectProperty": sub_object_property,
            "ObjectPropertyRange": object_property_range,
            "ObjectPropertyDomain": object_property_domain,
        }

        errors = ""
        iris = {
            "Data graph IRI": data_graph_iri,
            "Ontology graph IRI": ontology_graph_iri,
            "Result graph IRI": result_graph_iri,
        }
        not_iri = sorted([k for k, v in iris.items() if not validators.url(v)])
        if not_iri:
            errors += f"Invalid IRI for parameters: {', '.join(not_iri)}. "
        if result_graph_iri and result_graph_iri == data_graph_iri:
            errors += "Result graph IRI cannot be the same as the data graph IRI. "
        if result_graph_iri and result_graph_iri == ontology_graph_iri:
            errors += "Result graph IRI cannot be the same as the ontology graph IRI. "
        if reasoner not in REASONERS:
            errors += 'Invalid value for parameter "Reasoner". '
        if True not in self.axioms.values():
            errors += "No axiom generator selected. "
        if annotate_inferred_axioms and [k for k, v in self.axioms.items() if v] != ["SubClass"]:
            errors += (
                'Parameter "Annnotate inferred subclass axioms" can only be enabled if the only '
                "enabled axiom generator is SubClass. "
            )
        if max_ram_percentage not in range(1, 101):
            errors += 'Invalid value for parameter "Maximum RAM Percentage". '
        if errors:
            raise ValueError(errors[:-1])

        self.data_graph_iri = data_graph_iri
        self.ontology_graph_iri = ontology_graph_iri
        self.result_graph_iri = result_graph_iri
        self.reasoner = reasoner
        self.annotate_inferred_axioms = str(annotate_inferred_axioms).lower()
        self.max_ram_percentage = max_ram_percentage
        self.temp = f"reason_{uuid4().hex}"

    def get_graphs(self, graphs: dict, context: ExecutionContext) -> None:
        """Get graphs from CMEM"""
        if not Path(self.temp).exists():
            Path(self.temp).mkdir(parents=True)
        for graph in graphs:
            with (Path(self.temp) / graphs[graph]).open("w", encoding="utf-8") as file:
                setup_cmempy_user_access(context.user)
                file.write(get(graph).text)
                if graph == self.data_graph_iri:
                    file.write(
                        f"\n<{graph}> "
                        f"<http://www.w3.org/2002/07/owl#imports> <{self.ontology_graph_iri}> ."
                    )

    def reason(self, graphs: dict) -> None:
        """Reason"""
        axioms = " ".join(k for k, v in self.axioms.items() if v)
        data_location = f"{self.temp}/{graphs[self.data_graph_iri]}"
        utctime = str(datetime.fromtimestamp(int(time()), tz=UTC))[:-6].replace(" ", "T") + "Z"
        cmd = (
            f"java -XX:MaxRAMPercentage={self.max_ram_percentage} -jar {ROBOT} "
            f'merge --input "{data_location}" '
            "--collapse-import-closure false "
            f"reason --reasoner {self.reasoner} "
            f'--axiom-generators "{axioms}" '
            f"--annotate-inferred-axioms {self.annotate_inferred_axioms} "
            f"--include-indirect true "
            f"--exclude-duplicate-axioms true "
            f"--exclude-owl-thing true "
            f"--exclude-tautologies all "
            f"--exclude-external-entities "
            f"reduce --reasoner {self.reasoner} "
            f'unmerge --input "{data_location}" '
            f'annotate --ontology-iri "{self.result_graph_iri}" '
            f"--remove-annotations "
            f'--language-annotation rdfs:label "Eccenca Reasoning Result {utctime}" en '
            f"--language-annotation rdfs:comment "
            f'"Reasoning result set of <{self.data_graph_iri}> and '
            f'<{self.ontology_graph_iri}>" en '
            f"--language-annotation prov:wasGeneratedBy "
            f'"cmem-plugin-reason ({self.reasoner})" en '
            f'--link-annotation prov:wasDerivedFrom "{self.data_graph_iri}" '
            f"--link-annotation prov:wasDerivedFrom "
            f'"{self.ontology_graph_iri}" '
            f'--typed-annotation dc:created "{utctime}" xsd:dateTime '
            f'--output "{self.temp}/result.ttl"'
        )
        response = run(shlex.split(cmd), check=False, capture_output=True)  # noqa: S603
        if response.returncode != 0:
            if response.stdout:
                raise OSError(response.stdout.decode())
            if response.stderr:
                raise OSError(response.stderr.decode())
            raise OSError("ROBOT error")

    def clean_up(self, graphs: dict) -> None:
        """Remove temporary files"""
        files = ["catalog-v001.xml", "result.ttl"]
        files += list(graphs.values())
        for file in files:
            try:
                (Path(self.temp) / file).unlink()
            except (OSError, FileNotFoundError) as err:
                self.log.warning(f"Cannot remove file {file} ({err})")
        try:
            Path(self.temp).rmdir()
        except (OSError, FileNotFoundError) as err:
            self.log.warning(f"Cannot remove directory {self.temp} ({err})")

    def execute(self, inputs: Sequence[Entities], context: ExecutionContext) -> None:  # noqa: ARG002
        """Execute plugin"""
        setup_cmempy_user_access(context.user)
        graphs = get_graphs_tree((self.data_graph_iri, self.ontology_graph_iri))
        self.get_graphs(graphs, context)
        create_xml_catalog_file(self.temp, graphs)
        self.reason(graphs)
        setup_cmempy_user_access(context.user)
        send_result(self.result_graph_iri, Path(self.temp) / "result.ttl")
        self.clean_up(graphs)
