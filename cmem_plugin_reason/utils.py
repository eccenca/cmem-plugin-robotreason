"""Common constants and functions"""

import json
import shlex
from collections import OrderedDict
from pathlib import Path
from secrets import token_hex
from subprocess import CompletedProcess, run
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

import validators.url
from cmem.cmempy.dp.proxy.graph import get_graph_import_tree, get_graphs_list, post_streamed
from cmem.cmempy.dp.proxy.sparql import post as post_select
from cmem.cmempy.dp.proxy.update import post as post_update
from cmem_plugin_base.dataintegration.context import ExecutionContext, PluginContext
from cmem_plugin_base.dataintegration.description import PluginParameter
from cmem_plugin_base.dataintegration.parameter.graph import GraphParameterType
from cmem_plugin_base.dataintegration.plugins import WorkflowPlugin
from cmem_plugin_base.dataintegration.types import (
    Autocompletion,
    BoolParameterType,
    IntParameterType,
    StringParameterType,
)
from cmem_plugin_base.dataintegration.utils import setup_cmempy_user_access
from defusedxml import minidom

from . import __path__

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

MAX_RAM_PERCENTAGE_DEFAULT = 20

ONTOLOGY_GRAPH_IRI_PARAMETER = PluginParameter(
    param_type=GraphParameterType(classes=["http://www.w3.org/2002/07/owl#Ontology"]),
    name="ontology_graph_iri",
    label="Ontology_graph_IRI",
    description="The IRI of the input ontology graph.",
)

MAX_RAM_PERCENTAGE_PARAMETER = PluginParameter(
    param_type=IntParameterType(),
    name="max_ram_percentage",
    label="Maximum RAM Percentage",
    description="""Maximum heap size for the reasoning process in the DI container. ⚠️ Setting the
    percentage too high may result in an out of memory error.""",
    default_value=MAX_RAM_PERCENTAGE_DEFAULT,
    advanced=True,
)

VALIDATE_PROFILES_PARAMETER = PluginParameter(
    param_type=BoolParameterType(),
    name="validate_profile",
    label="Validate OWL2 profiles",
    description="""Validate the input ontology against OWL profiles (DL, EL, QL, RL, and Full) and
    annotate the result graph.""",
    default_value=False,
)


def create_xml_catalog_file(dir_: str, graphs: dict) -> None:
    """Create XML catalog file"""
    file_name = Path(dir_) / "catalog-v001.xml"
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


def get_graphs_tree(graph_iris: tuple) -> dict:
    """Get graph import tree. Last item in tuple is output_graph_iri which is excluded"""
    graphs = {}
    for graph_iri in graph_iris[:-1]:
        if graph_iri not in graphs:
            graphs[graph_iri] = f"{token_hex(8)}.nt"
            tree = get_graph_import_tree(graph_iri)
            for value in tree["tree"].values():
                for iri in value:
                    if iri not in graphs and iri != graph_iri[-1]:
                        graphs[iri] = f"{token_hex(8)}.nt"
    return graphs


def send_result(iri: str, filepath: Path) -> None:
    """Send result"""
    res = post_streamed(
        iri,
        str(filepath),
        replace=True,
        content_type="text/turtle",
    )
    if res.status_code != 204:  # noqa: PLR2004
        raise OSError(f"Error posting result graph (status code {res.status_code}).")


def post_provenance(plugin: WorkflowPlugin, prov: dict | None) -> None:
    """Post provenance"""
    if not prov:
        return
    param_sparql = ""
    for name, iri in prov["parameters"].items():
        param_sparql += f'\n<{prov["plugin_iri"]}> <{iri}> "{plugin.__dict__[name]}" .'
    insert_query = f"""
        INSERT DATA {{
            GRAPH <{plugin.output_graph_iri}> {{
                <{plugin.output_graph_iri}> <http://purl.org/dc/terms/creator>
                    <{prov["plugin_iri"]}> .
                <{prov["plugin_iri"]}> a <{prov["plugin_type"]}>,
                    <https://vocab.eccenca.com/di/CustomTask> .
                <{prov["plugin_iri"]}> <http://www.w3.org/2000/01/rdf-schema#label>
                    "{prov['plugin_label']}" .
                {param_sparql}
            }}
        }}
    """
    post_update(query=insert_query)


def get_provenance(plugin: WorkflowPlugin, context: ExecutionContext) -> dict | None:
    """Get provenance information"""
    plugin_iri = (
        f"http://dataintegration.eccenca.com/{context.task.project_id()}/{context.task.task_id()}"
    )
    project_graph = f"http://di.eccenca.com/project/{context.task.project_id()}"

    type_query = f"""
            SELECT ?type ?label {{
                GRAPH <{project_graph}> {{
                    <{plugin_iri}> a ?type .
                    <{plugin_iri}> <http://www.w3.org/2000/01/rdf-schema#label> ?label .
                    FILTER(STRSTARTS(STR(?type), "https://vocab.eccenca.com/di/functions/"))
                }}
            }}
        """

    result = json.loads(post_select(query=type_query))

    try:
        plugin_type = result["results"]["bindings"][0]["type"]["value"]
    except IndexError:
        plugin.log.warning("Could not add provenance data to output graph.")
        return None
    plugin_label = result["results"]["bindings"][0]["label"]["value"]

    param_split = (
        plugin_type.replace(
            "https://vocab.eccenca.com/di/functions/Plugin_",
            "https://vocab.eccenca.com/di/functions/param_",
        )
        + "_"
    )

    parameter_query = f"""
        SELECT ?parameter {{
            GRAPH <{project_graph}> {{
                <{plugin_iri}> ?parameter ?o .
                FILTER(STRSTARTS(STR(?parameter), "https://vocab.eccenca.com/di/functions/param_"))
            }}
        }}
    """

    new_plugin_iri = f'{"_".join(plugin_iri.split("_")[:-1])}_{token_hex(8)}'
    result = json.loads(post_select(query=parameter_query))

    prov = {
        "plugin_iri": new_plugin_iri,
        "plugin_label": plugin_label,
        "plugin_type": plugin_type,
        "parameters": {},
    }

    for binding in result["results"]["bindings"]:
        param_iri = binding["parameter"]["value"]
        param_name = param_iri.split(param_split)[1]
        prov["parameters"][param_name] = param_iri

    return prov


def robot(cmd: str, max_ram_percentage: int) -> CompletedProcess:
    """Run robot.jar"""
    jar = Path(__path__[0]) / "bin" / "robot.jar"
    cmd = f"java -XX:MaxRAMPercentage={max_ram_percentage} -jar {jar} {cmd}"
    return run(shlex.split(cmd), check=False, capture_output=True)  # noqa: S603


def validate_profiles(plugin: WorkflowPlugin, graphs: dict) -> list:
    """Validate OWL2 profiles"""
    ontology_location = f"{plugin.temp}/{graphs[plugin.ontology_graph_iri]}"
    valid_profiles = []
    for profile in ("Full", "DL", "EL", "QL", "RL"):
        plugin.log.info(f"Validating {profile} profile.")
        cmd = f"validate-profile --profile {profile} --input {ontology_location}"
        response = robot(cmd, plugin.max_ram_percentage)
        if response.stdout.endswith(b"[Ontology and imports closure in profile]\n\n"):
            valid_profiles.append(profile)
        elif profile == "Full":
            break
    return valid_profiles


def post_profiles(plugin: WorkflowPlugin, valid_profiles: list) -> None:
    """Validate OWL2 profiles"""
    if valid_profiles:
        profiles = '", "'.join(valid_profiles)
        query = f"""
            INSERT DATA {{
                GRAPH <{plugin.output_graph_iri}> {{
                    <{plugin.ontology_graph_iri}>
                        <https://vocab.eccenca.com/plugin/reason/profile> "{profiles}" .
                }}
            }}
        """
        post_update(query=query)


class GraphParameterTypeNew(StringParameterType):
    """Knowledge Graph parameter type."""

    allow_only_autocompleted_values: bool = False
    autocomplete_value_with_labels: bool = True
    classes: set[str] | None = None

    def __init__(  # noqa: PLR0913
        self,
        show_di_graphs: bool = False,
        show_system_graphs: bool = False,
        show_graphs_without_class: bool = False,
        classes: list[str] | None = None,
        allow_only_autocompleted_values: bool = True,
    ):
        """Knowledge Graph parameter type.

        :param show_di_graphs: show DI project graphs
        :param show_system_graphs: show system graphs such as shape and query catalogs
        :param classes: allowed classes of the shown graphs
            - if None -> defaults to di:Dataset and void:Dataset
        :param allow_only_autocompleted_values: allow entering new graph URLs
        """
        self.show_di_graphs = show_di_graphs
        self.show_system_graphs = show_system_graphs
        self.show_graphs_without_class = show_graphs_without_class
        self.allow_only_autocompleted_values = allow_only_autocompleted_values
        if classes:
            self.classes = set(classes)
        else:
            self.classes = {
                "https://vocab.eccenca.com/di/Dataset",
                "http://rdfs.org/ns/void#Dataset",
            }

    def autocomplete(  # noqa: C901
        self,
        query_terms: list[str],
        depend_on_parameter_values: list[Any],  # noqa: ARG002
        context: PluginContext,
    ) -> list[Autocompletion]:
        """Autocomplete"""
        setup_cmempy_user_access(context=context.user)
        graphs = get_graphs_list()
        result = []
        for _ in graphs:
            iri = _["iri"]
            title = _["label"]["title"]
            label = f"{title} ({iri})"
            assigned_classes = set(_["assignedClasses"])
            # ignore DI project graphs
            if self.show_di_graphs is False and _["diProjectGraph"]:
                continue
            # ignore system resource graphs
            if self.show_system_graphs is False and _["systemResource"]:
                continue
            # show graphs without assigned classes only if explicitly wanted
            if not assigned_classes:
                if self.show_graphs_without_class:
                    result.append(Autocompletion(value=iri, label=label))
                continue
            # ignore graphs which do not match the requested classes
            if (
                self.classes
                and assigned_classes
                and not self.classes.intersection(assigned_classes)
            ):
                continue
            str_match = True
            for term in query_terms:
                if term.lower() not in label.lower():
                    str_match = False
                    break
            if str_match:
                result.append(Autocompletion(value=iri, label=label))
        if not result and len(query_terms) == 1 and validators.url(query_terms[0]):
            result.append(
                Autocompletion(value=query_terms[0], label=f"new graph: {query_terms[0]}")
            )

        result.sort(key=lambda x: x.label)
        return list(set(result))
