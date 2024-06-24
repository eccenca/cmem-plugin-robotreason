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

ROBOT = Path(__path__[0]) / "bin" / "robot"


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
    description="Given a data and an ontology graph, this task performs reasoning " "using ROBOT.",
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
            name="result_iri",
            label="Result graph IRI",
            description="The IRI of the output graph for the reasoning result. "
            "WARNING: existing graph will be overwritten!",
        ),
        PluginParameter(
            param_type=ChoiceParameterType(
                OrderedDict(
                    {
                        "elk": "ELK",
                        "emr": "Expression Materializing Reasoner",
                        "hermit": "HermiT",
                        "jfact": "JFact",
                        "structural": "Structural Reasoner",
                        "whelk": "Whelk",
                    }
                )
            ),
            name="reasoner",
            label="Reasoner",
            description="Reasoner option.",
            default_value="elk",
        ),
        PluginParameter(
            param_type=BoolParameterType(),
            name="sub_class",
            label="SubClass",
            description="Generated Axioms",
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
            name="disjoint_class",
            label="Disjoint_Class",
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
            description="",
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
        result_iri: str = "",
        reasoner: str = "elk",
        sub_class: bool = True,
        equivalent_class: bool = False,
        disjoint_class: bool = False,
        data_property_characteristic: bool = False,
        equivalent_data_properties: bool = False,
        sub_data_property: bool = False,
        class_assertion: bool = False,
        property_assertion: bool = False,
        equivalent_object_property: bool = False,
        inverse_object_properties: bool = False,
        object_property_characteristic: bool = False,
        sub_object_property: bool = False,
        object_property_range: bool = False,
        object_property_domain: bool = False,
    ) -> None:
        """Init"""
        self.data_graph_iri = data_graph_iri
        self.ontology_graph_iri = ontology_graph_iri
        self.result_iri = result_iri
        self.reasoner = reasoner
        self.temp = f"robot_{uuid4().hex}"
        self.sub_class = sub_class
        self.equivalent_class = equivalent_class
        self.disjoint_class = disjoint_class
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

    def get_graphs(self, graphs: dict) -> None:
        """Get graphs from CMEM"""
        if not Path(self.temp).exists():
            Path(self.temp).mkdir(parents=True)
        for graph in graphs:
            with (Path(self.temp) / graphs[graph]).open("w", encoding="utf-8") as file:
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

    def set_axioms(self) -> str:
        """Set asserted axioms"""
        axioms_dict = {
            "sub_class": "SubClass",
            "equivalent_class": "EquivalentClass",
            "disjoint_class": "DisjointClass",
            "data_property_characteristic": "DataPropertyCharacteristic",
            "equivalent_data_properties": "EquivalentDataProperties",
            "sub_data_property": "SubDataProperty",
            "class_assertion": "ClassAssertion",
            "property_assertion": "PropertyAssertion",
            "equivalent_object_property": "EquivalentObjectProperty",
            "inverse_object_properties": "InverseObjectProperties",
            "object_property_characteristic": "ObjectPropertyCharacteristic",
            "sub_object_property": "SubObjectProperty",
            "object_property_range": "ObjectPropertyRange",
            "object_property_domain": "ObjectPropertyDomain",
        }

        axioms = " ".join(v for k, v in axioms_dict.items() if self.__dict__[k])

        if not axioms:
            raise ValueError("No axioms selected.")

        return axioms

    def reason(self, graphs: dict) -> None:
        """Reason"""
        inputs = f'--input "{self.temp}/{graphs[self.data_graph_iri]}"'
        utctime = str(datetime.fromtimestamp(int(time()), tz=UTC))[:-6].replace(" ", "T") + "Z"
        cmd = (
            f"{ROBOT} merge {inputs} --collapse-import-closure false "
            f"reason --reasoner {self.reasoner} "
            f'--axiom-generators "{self.set_axioms()}" '
            f"--include-indirect true "
            f"--exclude-duplicate-axioms true "
            f"--exclude-owl-thing true "
            f"--exclude-tautologies all "
            f"--exclude-external-entities "
            f"reduce --reasoner {self.reasoner} "
            f"unmerge {inputs} "
            f'annotate --ontology-iri "{self.result_iri}" '
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
        run(shlex.split(cmd), check=False)  # noqa: S603

    def send_result(self) -> None:
        """Send result"""
        post_streamed(
            self.result_iri,
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
        self.get_graphs(graphs)
        self.create_xml_catalog_file(graphs)
        self.reason(graphs)
        self.send_result()
        self.clean_up(graphs)
