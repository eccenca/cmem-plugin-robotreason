"""Reasoning workflow plugin module"""

from collections.abc import Sequence
from datetime import UTC, datetime
from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
from warnings import simplefilter

import validators.url
from cmem.cmempy.dp.proxy.graph import get
from cmem_plugin_base.dataintegration.context import ExecutionContext, ExecutionReport
from cmem_plugin_base.dataintegration.description import Icon, Plugin, PluginParameter
from cmem_plugin_base.dataintegration.entity import Entities, EntityPath, EntitySchema
from cmem_plugin_base.dataintegration.parameter.choice import ChoiceParameterType
from cmem_plugin_base.dataintegration.parameter.graph import GraphParameterType
from cmem_plugin_base.dataintegration.plugins import WorkflowPlugin
from cmem_plugin_base.dataintegration.ports import FixedNumberOfInputs, FixedSchemaPort
from cmem_plugin_base.dataintegration.types import BoolParameterType
from cmem_plugin_base.dataintegration.utils import setup_cmempy_user_access
from urllib3.exceptions import InsecureRequestWarning

from cmem_plugin_reason.utils import (
    MAX_RAM_PERCENTAGE_DEFAULT,
    MAX_RAM_PERCENTAGE_PARAMETER,
    ONTOLOGY_GRAPH_IRI_PARAMETER,
    OUTPUT_GRAPH_IRI_PARAMETER,
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
simplefilter("ignore", category=InsecureRequestWarning)


@Plugin(
    label="Reason",
    icon=Icon(file_name="fluent--brain-circuit-24-regular.svg", package=__package__),
    description="Performs OWL reasoning.",
    documentation="""A task performing OWL reasoning. With an OWL ontology and a data graph as input
    the reasoning result is written to a specified graph. The following reasoners are supported:
    ELK, Expression Materializing Reasoner, HermiT, JFact, Structural Reasoner and Whelk.""",
    parameters=[
        ONTOLOGY_GRAPH_IRI_PARAMETER,
        OUTPUT_GRAPH_IRI_PARAMETER,
        VALIDATE_PROFILES_PARAMETER,
        MAX_RAM_PERCENTAGE_PARAMETER,
        PluginParameter(
            param_type=ChoiceParameterType(REASONERS),
            name="reasoner",
            label="Reasoner",
            description="Reasoner option. Additionally, select axiom generators below.",
            default_value="",
        ),
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
            description="",
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
            name="input_profiles",
            label="Process valid OWL profiles from input",
            description="""If the "validate OWL profiles" parameter is enabled, the valid profiles
            and ontology IRI is taken from the input (paths "profile" and "ontology") instead of
            running the validation in the plugin.""",
            default_value=False,
            advanced=True,
        ),
    ],
)
class ReasonPlugin(WorkflowPlugin):
    """Reason plugin"""

    def __init__(  # noqa: PLR0913, C901
        self,
        data_graph_iri: str = "",
        ontology_graph_iri: str = "",
        output_graph_iri: str = "",
        reasoner: str = "",
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
        validate_profile: bool = False,
        input_profiles: bool = False,
        max_ram_percentage: int = MAX_RAM_PERCENTAGE_DEFAULT,
    ) -> None:
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
        if not validators.url(data_graph_iri):
            errors += 'Invalid IRI for parameter "Data graph IRI". '
        if not validators.url(ontology_graph_iri):
            errors += 'Invalid IRI for parameter "Ontology graph IRI". '
        if not validators.url(output_graph_iri):
            errors += 'Invalid IRI for parameter "Result graph IRI". '
        if output_graph_iri and output_graph_iri == data_graph_iri:
            errors += "Result graph IRI cannot be the same as the data graph IRI. "
        if output_graph_iri and output_graph_iri == ontology_graph_iri:
            errors += "Result graph IRI cannot be the same as the ontology graph IRI. "
        if reasoner not in REASONERS:
            errors += 'Invalid value for parameter "Reasoner". '
        if True not in self.axioms.values():
            errors += "No axiom generator selected. "
        if max_ram_percentage not in range(1, 101):
            errors += 'Invalid value for parameter "Maximum RAM Percentage". '
        if errors:
            raise ValueError(errors[:-1])
        self.sub_class = sub_class
        self.equivalent_class = equivalent_class
        self.disjoint_classes = disjoint_classes
        self.data_property_characteristic = data_property_characteristic
        self.equivalent_data_properties = equivalent_data_properties
        self.sub_data_property = sub_data_property
        self.class_assertion = class_assertion
        self.property_assertion = property_assertion
        self.equivalent_object_property = equivalent_object_property
        self.inverse_object_properties = inverse_object_properties
        self.object_property_characteristic = object_property_characteristic
        self.sub_object_property = sub_object_property
        self.object_property_range = object_property_range
        self.object_property_domain = object_property_domain
        self.data_graph_iri = data_graph_iri
        self.ontology_graph_iri = ontology_graph_iri
        self.output_graph_iri = output_graph_iri
        self.reasoner = reasoner
        self.validate_profile = validate_profile
        self.input_profiles = input_profiles
        self.max_ram_percentage = max_ram_percentage

        if validate_profile and input_profiles:
            self.input_ports = FixedNumberOfInputs([FixedSchemaPort(self.generate_input_schema())])
        else:
            self.input_ports = FixedNumberOfInputs([])
        self.output_port = None

    def generate_input_schema(self) -> EntitySchema:
        """Generate the output schema."""
        return EntitySchema(
            type_uri="validate",
            paths=[EntityPath("profile"), EntityPath("ontology")],
        )

    def get_graphs(self, graphs: dict, context: ExecutionContext) -> None:
        """Get graphs from CMEM"""
        for iri, filename in graphs.items():
            self.log.info(f"Fetching graph {iri}.")
            with (Path(self.temp) / filename).open("w", encoding="utf-8") as file:
                setup_cmempy_user_access(context.user)
                for line in get(iri).text.splitlines():
                    if line != (
                        f"<{iri}> <http://www.w3.org/2002/07/owl#imports> "
                        f"<{self.output_graph_iri}> ."
                    ):
                        file.write(line + "\n")
                if iri == self.data_graph_iri:
                    file.write(
                        f"<{iri}> <http://www.w3.org/2002/07/owl#imports> "
                        f"<{self.ontology_graph_iri}> ."
                    )

    def reason(self, graphs: dict) -> None:
        """Reason"""
        axioms = " ".join(k for k, v in self.axioms.items() if v)
        data_location = f"{self.temp}/{graphs[self.data_graph_iri]}"
        utctime = str(datetime.fromtimestamp(int(time()), tz=UTC))[:-6].replace(" ", "T") + "Z"
        cmd = (
            f'reason --input "{data_location}" '
            f"--reasoner {self.reasoner} "
            f'--axiom-generators "{axioms}" '
            f"--include-indirect true "
            f"--exclude-duplicate-axioms true "
            f"--exclude-owl-thing true "
            f"--exclude-tautologies all "
            f"--exclude-external-entities "
            f"reduce --reasoner {self.reasoner} "
            f'unmerge --input "{data_location}" '
            f'annotate --ontology-iri "{self.output_graph_iri}" '
            f"--remove-annotations "
            f'--language-annotation rdfs:label "Eccenca Reasoning Result {utctime}" en '
            f"--language-annotation rdfs:comment "
            f'"Reasoning result set of <{self.data_graph_iri}> and '
            f'<{self.ontology_graph_iri}>" en '
            f'--link-annotation dc:source "{self.data_graph_iri}" '
            f'--link-annotation dc:source "{self.ontology_graph_iri}" '
            f'--typed-annotation dc:created "{utctime}" xsd:dateTime '
            f'--output "{self.temp}/result.ttl"'
        )
        response = robot(cmd, self.max_ram_percentage)
        if response.returncode != 0:
            if response.stdout:
                raise OSError(response.stdout.decode())
            if response.stderr:
                raise OSError(response.stderr.decode())
            raise OSError("ROBOT error")

    def post_valid_profiles(self, inputs: Sequence[Entities], graphs: dict) -> None:
        """Post valid profiles. Optionally get valid profiles from input."""
        if self.input_profiles:
            values = next(inputs[0].entities).values
            paths = [p.path for p in inputs[0].schema.paths]
            valid_profiles = values[paths.index("profile")]
        else:
            valid_profiles = validate_profiles(self, graphs)
        post_profiles(self, valid_profiles)

    def _execute(self, inputs: Sequence[Entities], context: ExecutionContext) -> None:
        """`Execute plugin"""
        setup_cmempy_user_access(context.user)
        graphs = get_graphs_tree(
            (self.data_graph_iri, self.ontology_graph_iri, self.output_graph_iri)
        )
        self.get_graphs(graphs, context)
        create_xml_catalog_file(self.temp, graphs)
        self.reason(graphs)
        setup_cmempy_user_access(context.user)
        send_result(self.output_graph_iri, Path(self.temp) / "result.ttl")
        if self.validate_profile:
            self.post_valid_profiles(inputs, graphs)
        post_provenance(self, get_provenance(self, context))

        context.report.update(
            ExecutionReport(
                operation="reason",
                operation_desc="ontology and data graph processed.",
                entity_count=1,
            )
        )

    def execute(self, inputs: Sequence[Entities], context: ExecutionContext) -> None:
        """Validate input, execute plugin with temporary directory"""
        context.report.update(
            ExecutionReport(
                operation="reason",
                operation_desc="ontologies and data graphs processed.",
            )
        )
        if self.input_profiles:
            errors = ""
            values = next(inputs[0].entities).values
            paths = [p.path for p in inputs[0].schema.paths]
            if not inputs:
                raise OSError(
                    'Input entities needed if "Process valid OWL profiles from input" is enabled'
                )
            if "profile" not in paths:
                errors += 'No value for "profile" given on input. '
            if "ontology" not in paths:
                errors += 'No value for "ontology" given on input. '
            self.ontology_graph_iri = values[paths.index("ontology")][0]
            if not validators.url(self.ontology_graph_iri):
                errors += 'Invalid IRI for parameter "Ontology graph IRI". '
            if self.ontology_graph_iri == self.data_graph_iri:
                errors += "Ontology graph IRI cannot be the same as the data graph IRI. "
            if self.ontology_graph_iri == self.output_graph_iri:
                errors += "Ontology graph IRI cannot be the same as the output graph IRI. "
            if errors:
                raise ValueError(errors[:-1])

        with TemporaryDirectory() as self.temp:
            self._execute(inputs, context)
