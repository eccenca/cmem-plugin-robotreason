"""Common functions"""

import re
import unicodedata
from collections import OrderedDict
from pathlib import Path
from xml.etree.ElementTree import (
    Element,
    SubElement,
    tostring,
)

from cmem.cmempy.dp.proxy.graph import get_graph_import_tree, post_streamed
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


def create_xml_catalog_file(temp: str, graphs: dict) -> None:
    """Create XML catalog file"""
    file_name = Path(temp) / "catalog-v001.xml"
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
    """Get graph import tree"""
    graphs = {}
    for graph_iri in graph_iris:
        if graph_iri not in graphs:
            graphs[graph_iri] = convert_iri_to_filename(graph_iri)
            tree = get_graph_import_tree(graph_iri)
            for value in tree["tree"].values():
                for iri in value:
                    if iri not in graphs:
                        graphs[iri] = convert_iri_to_filename(iri)
    return graphs


def send_result(iri: str, filepath: Path) -> None:
    """Send result"""
    post_streamed(
        iri,
        str(filepath),
        replace=True,
        content_type="text/turtle",
    )
