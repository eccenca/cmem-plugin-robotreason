"""Plugin tests."""

from contextlib import suppress
from pathlib import Path

import pytest
from cmem.cmempy.dp.proxy.graph import delete, get, post
from cmem.cmempy.workspace.projects.project import delete_project, make_new_project
from cmem.cmempy.workspace.projects.resources.resource import get_resource
from rdflib import DCTERMS, OWL, RDF, RDFS, Graph, URIRef
from rdflib.compare import to_isomorphic

from cmem_plugin_reason.plugin_reason import ReasonPlugin
from cmem_plugin_reason.plugin_validate import ValidatePlugin
from tests.utils import TestExecutionContext, needs_cmem

from . import __path__

UID = "e02aaed014c94e0c91bf960fed127750"
REASON_DATA_GRAPH_IRI = f"https://ns.eccenca.com/reasoning/{UID}/data/"
REASON_ONTOLOGY_GRAPH_IRI = f"https://ns.eccenca.com/reasoning/{UID}/vocab/"
REASON_RESULT_GRAPH_IRI = f"https://ns.eccenca.com/reasoning/{UID}/result/"
VALIDATE_ONTOLOGY_GRAPH_IRI = f"https://ns.eccenca.com/validateontology/{UID}/vocab/"
OUTPUT_GRAPH_IRI = f"https://ns.eccenca.com/validateontology/{UID}/output/"
MD_FILENAME = f"{UID}.md"
PROJECT_ID = f"validate_plugin_test_project_{UID}"


@pytest.fixture()
def _setup(request: pytest.FixtureRequest) -> None:
    """Set up"""
    res = post(REASON_DATA_GRAPH_IRI, Path(__path__[0]) / "dataset_owl.ttl", replace=True)
    if res.status_code != 204:  # noqa: PLR2004
        raise ValueError(f"Response {res.status_code}: {res.url}")
    res = post(REASON_ONTOLOGY_GRAPH_IRI, Path(__path__[0]) / "vocab.ttl", replace=True)
    if res.status_code != 204:  # noqa: PLR2004
        raise ValueError(f"Response {res.status_code}: {res.url}")

    with suppress(Exception):
        delete_project(PROJECT_ID)
    make_new_project(PROJECT_ID)
    res = post(
        VALIDATE_ONTOLOGY_GRAPH_IRI, Path(__path__[0]) / "test_validate_ontology.ttl", replace=True
    )
    if res.status_code != 204:  # noqa: PLR2004
        raise ValueError(f"Response {res.status_code}: {res.url}")

    request.addfinalizer(lambda: delete(REASON_DATA_GRAPH_IRI))
    request.addfinalizer(lambda: delete(REASON_ONTOLOGY_GRAPH_IRI))
    request.addfinalizer(lambda: delete(REASON_RESULT_GRAPH_IRI))
    request.addfinalizer(lambda: delete_project(PROJECT_ID))
    request.addfinalizer(lambda: delete(OUTPUT_GRAPH_IRI))
    request.addfinalizer(lambda: delete(VALIDATE_ONTOLOGY_GRAPH_IRI))  # noqa: PT021


@needs_cmem
def tests(_setup: None) -> None:  # noqa: C901
    """Tests for reason plugin"""

    def get_remote_graph(iri: str) -> Graph:
        graph = Graph().parse(
            data=get(iri, owl_imports_resolution=False).text,
            format="turtle",
        )
        graph.remove((URIRef(iri), DCTERMS.created, None))
        graph.remove((URIRef(iri), RDFS.label, None))
        graph.remove((None, RDF.type, OWL.AnnotationProperty))
        return graph

    def test_reasoner(reasoner: str, err_list: list) -> list:
        ReasonPlugin(
            data_graph_iri=REASON_DATA_GRAPH_IRI,
            ontology_graph_iri=REASON_ONTOLOGY_GRAPH_IRI,
            result_graph_iri=REASON_RESULT_GRAPH_IRI,
            reasoner=reasoner,
            sub_class=False,
            class_assertion=True,
            property_assertion=True,
        ).execute((), context=TestExecutionContext())

        result = get_remote_graph(REASON_RESULT_GRAPH_IRI)
        test = Graph().parse(Path(__path__[0]) / f"test_{reasoner}.ttl", format="turtle")
        if to_isomorphic(result) != to_isomorphic(test):
            err_list.append(reasoner)
        return err_list

    def test_validate(errors: str) -> str:
        result = ValidatePlugin(
            ontology_graph_iri=VALIDATE_ONTOLOGY_GRAPH_IRI,
            produce_graph=True,
            output_graph_iri=OUTPUT_GRAPH_IRI,
            write_md=True,
            md_filename=MD_FILENAME,
        ).execute((), context=TestExecutionContext(PROJECT_ID))

        val_errors = ""
        md_test = (Path(__path__[0]) / "test_validate.md").read_text()

        if md_test != next(iter(result.entities)).values[0][0]:  # type: ignore[union-attr]
            val_errors += "Entities output error. "

        if md_test != get_resource(PROJECT_ID, MD_FILENAME).decode():
            val_errors += "Markdown file error. "

        output_graph = get_remote_graph(OUTPUT_GRAPH_IRI)
        test = Graph().parse(Path(__path__[0]) / "test_validate_output.ttl", format="turtle")
        if to_isomorphic(output_graph) != to_isomorphic(test):
            val_errors += "Output graph error. "

        if val_errors:
            errors += "Validate: " + val_errors
        return errors

    errors_list: list[str] = []
    reasoners = ["elk", "emr", "hermit", "jfact", "structural", "whelk"]
    for reasoner in reasoners:
        errors_list = test_reasoner(reasoner, errors_list)

    errors = ""
    if errors_list:
        errors += f"Reason: test failed for reasoners {', '.join(errors_list)}. "

    errors = test_validate(errors)

    if errors:
        raise AssertionError(errors[:-1])
