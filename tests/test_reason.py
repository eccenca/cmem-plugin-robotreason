"""Plugin tests."""

from pathlib import Path

import pytest
from cmem.cmempy.dp.proxy.graph import delete, get, post
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


@pytest.fixture()
def _setup_reason(request: pytest.FixtureRequest) -> None:
    """Set up"""
    res = post(REASON_DATA_GRAPH_IRI, Path(__path__[0]) / "dataset_owl.ttl", replace=True)
    if res.status_code != 204:  # noqa: PLR2004
        raise ValueError(f"Response {res.status_code}: {res.url}")
    res = post(REASON_ONTOLOGY_GRAPH_IRI, Path(__path__[0]) / "vocab.ttl", replace=True)
    if res.status_code != 204:  # noqa: PLR2004
        raise ValueError(f"Response {res.status_code}: {res.url}")

    request.addfinalizer(lambda: delete(REASON_DATA_GRAPH_IRI))
    request.addfinalizer(lambda: delete(REASON_ONTOLOGY_GRAPH_IRI))
    request.addfinalizer(lambda: delete(REASON_RESULT_GRAPH_IRI))  # noqa: PT021


@pytest.fixture()
def _setup_validate(request: pytest.FixtureRequest) -> None:
    """Set up"""
    res = post(VALIDATE_ONTOLOGY_GRAPH_IRI, Path(__path__[0]) / "test_validate.ttl", replace=True)
    if res.status_code != 204:  # noqa: PLR2004
        raise ValueError(f"Response {res.status_code}: {res.url}")

    request.addfinalizer(lambda: delete(VALIDATE_ONTOLOGY_GRAPH_IRI))  # noqa: PT021


@needs_cmem
def tests_reason(_setup_reason: None) -> None:
    """Tests for reason plugin"""

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

        result = Graph().parse(
            data=get(REASON_RESULT_GRAPH_IRI, owl_imports_resolution=False).text,
            format="turtle",
        )
        result.remove((URIRef(REASON_RESULT_GRAPH_IRI), DCTERMS.created, None))
        result.remove((URIRef(REASON_RESULT_GRAPH_IRI), RDFS.label, None))
        result.remove((None, RDF.type, OWL.AnnotationProperty))

        test = Graph().parse(Path(__path__[0]) / f"test_{reasoner}.ttl", format="turtle")
        if to_isomorphic(result) != to_isomorphic(test):
            err_list.append(reasoner)
        return err_list

    errors: list[str] = []
    reasoners = ["elk", "emr", "hermit", "jfact", "structural", "whelk"]
    for reasoner in reasoners:
        errors = test_reasoner(reasoner, errors)

    if errors:
        raise AssertionError(f"Test failed for reasoners: {', '.join(errors)}")


@needs_cmem
def tests_validate(_setup_validate: None) -> None:
    """Tests for validate plugin"""
    ValidatePlugin(
        ontology_graph_iri=VALIDATE_ONTOLOGY_GRAPH_IRI,
    ).execute((), context=TestExecutionContext())
