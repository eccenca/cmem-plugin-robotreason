"""Reasoning with robot plugin module"""

import re
import shlex
import unicodedata
from collections import OrderedDict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from subprocess import run
from time import time
from uuid import uuid4
from xml.etree.ElementTree import (
    Element,
    SubElement,
    tostring,
)

import validators.url
from cmem.cmempy.dp.proxy.graph import get, get_graph_import_tree, post_streamed
from cmem_plugin_base.dataintegration.context import ExecutionContext
from cmem_plugin_base.dataintegration.description import Icon, Plugin, PluginParameter
from cmem_plugin_base.dataintegration.entity import Entities
from cmem_plugin_base.dataintegration.parameter.choice import ChoiceParameterType
from cmem_plugin_base.dataintegration.parameter.graph import GraphParameterType
from cmem_plugin_base.dataintegration.plugins import WorkflowPlugin
from cmem_plugin_base.dataintegration.types import BoolParameterType, StringParameterType
from cmem_plugin_base.dataintegration.utils import setup_cmempy_user_access
from defusedxml import minidom

from . import __path__

ROBOT = Path(__path__[0]) / "bin" / "robot.jar"
REASONERS = OrderedDict(
    {
        "elk": "ELK",
        "emr": "Expression Materializing Reasoner",
        "hermit": "HermiT",
        "jfact": "JFact",
        "structural": "Structural Reasoner",
        "whelk": "Whelk",
    }
)


def convert_iri_to_filename(value: str) -> str:
    """Convert IRI to filename"""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"\.", "_", value.lower())
    value = re.sub(r"/", "_", value.lower())
    value = re.sub(r"[^\w\s-]", "", value.lower())
    value = re.sub(r"[-\s]+", "-", value).strip("-_")
    return value + ".nt"


@Plugin(
    label="Reasoning with ROBOT",
    icon=Icon(file_name="obofoundry.png", package=__package__),
    description="Given a data and an ontology graph, this task performs reasoning using ROBOT.",
    documentation="""A task performing reasoning using ROBOT (ROBOT is an OBO Tool).
    It takes an OWL ontology and a data graph as inputs and writes the reasoning result
    to a specified graph. The following reasoner options are supported: ELK, Expression
    Materializing Reasoner, HermiT, JFact, Structural Reasoner and Whelk.""",
    parameters=[
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
            param_type=GraphParameterType(classes=["http://www.w3.org/2002/07/owl#Ontology"]),
            name="ontology_graph_iri",
            label="Ontology_graph_IRI",
            description="The IRI of the input ontology graph.",
        ),
        PluginParameter(
            param_type=StringParameterType(),
            name="result_graph_iri",
            label="Result graph IRI",
            description="The IRI of the output graph for the reasoning result. "
            "WARNING: existing graph will be overwritten!",
        ),
        PluginParameter(
            param_type=ChoiceParameterType(REASONERS),
            name="reasoner",
            label="Reasoner",
            description="Reasoner option.",
            default_value="elk",
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="sub_class",
            label="SubClass",
            description="",
            default_value=True,
            advanced=True,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="equivalent_class",
            label="EquivalentClass",
            description="",
            default_value=False,
            advanced=True,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="disjoint_classes",
            label="DisjointClasses",
            description="",
            default_value=False,
            advanced=True,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="data_property_characteristic",
            label="DataPropertyCharacteristic",
            description="",
            default_value=False,
            advanced=True,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="equivalent_data_properties",
            label="EquivalentDataProperties",
            description="",
            default_value=False,
            advanced=True,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="sub_data_property",
            label="SubDataProperty",
            description="",
            default_value=False,
            advanced=True,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="class_assertion",
            label="ClassAssertion",
            description="Generated Axioms",
            default_value=False,
            advanced=True,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="property_assertion",
            label="PropertyAssertion",
            description="",
            default_value=False,
            advanced=True,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="equivalent_object_property",
            label="EquivalentObjectProperty",
            description="",
            default_value=False,
            advanced=True,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="inverse_object_properties",
            label="InverseObjectProperties",
            description="",
            default_value=False,
            advanced=True,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="object_property_characteristic",
            label="ObjectPropertyCharacteristic",
            description="",
            default_value=False,
            advanced=True,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="sub_object_property",
            label="SubObjectProperty",
            description="",
            default_value=False,
            advanced=True,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="object_property_range",
            label="ObjectPropertyRange",
            description="",
            default_value=False,
            advanced=True,
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="object_property_domain",
            label="ObjectPropertyDomain",
            description="",
            default_value=False,
            advanced=True,
        ),
    ],
)
class RobotReasonPlugin(WorkflowPlugin):
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
        if result_graph_iri == data_graph_iri:
            errors += "Result graph IRI cannot be the same as the data graph IRI. "
        if result_graph_iri == ontology_graph_iri:
            errors += "Result graph IRI cannot be the same as the ontology graph IRI. "
        if reasoner not in REASONERS:
            errors += "Invalid value for parameter Reasoner. "
        not_bool = sorted([k for k, v in self.axioms.items() if not isinstance(v, bool)])
        if not_bool:
            errors += f"Invalid value for parameters: {', '.join(not_bool)}. "
        if True not in self.axioms.values():
            errors += "No axiom generator selected. "
        if errors:
            raise ValueError(errors[:-1])

        self.data_graph_iri = data_graph_iri
        self.ontology_graph_iri = ontology_graph_iri
        self.result_graph_iri = result_graph_iri
        self.reasoner = reasoner
        self.temp = f"robot_{uuid4().hex}"

    def create_xml_catalog_file(self, graphs: dict) -> None:
        """Create XML catalog file"""
        file_name = Path(self.temp) / "catalog-v001.xml"
        catalog = Element("catalog")
        catalog.set("prefer", "public")
        catalog.set("xmlns", "urn:oasis:names:tc:entity:xmlns:xml:catalog")
        for i, graph in enumerate(graphs):
            uri = SubElement(catalog, "uri")
            uri.set("id", f"id{i}")
            uri.set("name", graph)
            uri.set("uri", graphs[graph])
        reparsed = minidom.parseString(tostring(catalog, "utf-8")).toxml()
        with Path(file_name).open("w", encoding="utf-8") as file:
            file.truncate(0)
            file.write(reparsed)

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

    def get_graphs_tree(self) -> dict:
        """Get graph import tree"""
        graphs = {}
        for graph_iri in (self.data_graph_iri, self.ontology_graph_iri):
            if graph_iri not in graphs:
                graphs[graph_iri] = convert_iri_to_filename(graph_iri)
                tree = get_graph_import_tree(graph_iri)
                for value in tree["tree"].values():
                    for iri in value:
                        if iri not in graphs:
                            graphs[iri] = convert_iri_to_filename(iri)
        return graphs

    def reason(self, graphs: dict) -> None:
        """Reason"""
        axioms = " ".join(k for k, v in self.axioms.items() if v)
        data_location = f"{self.temp}/{graphs[self.data_graph_iri]}"
        utctime = str(datetime.fromtimestamp(int(time()), tz=UTC))[:-6].replace(" ", "T") + "Z"
        cmd = (
            f'java -XX:MaxRAMPercentage=15 -jar {ROBOT} merge --input "{data_location}" '
            "--collapse-import-closure false "
            f"reason --reasoner {self.reasoner} "
            f'--axiom-generators "{axioms}" '
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
            f'"cmem-plugin-robotreason ({self.reasoner})" en '
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

    def send_result(self) -> None:
        """Send result"""
        post_streamed(
            self.result_graph_iri,
            str(Path(self.temp) / "result.ttl"),
            replace=True,
            content_type="text/turtle",
        )

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
        graphs = self.get_graphs_tree()
        self.get_graphs(graphs, context)
        self.create_xml_catalog_file(graphs)
        self.reason(graphs)
        setup_cmempy_user_access(context.user)
        self.send_result()
        self.clean_up(graphs)
