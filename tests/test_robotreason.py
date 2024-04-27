"""Plugin tests."""

from pathlib import Path

import pytest
from cmem.cmempy.dp.proxy.graph import delete, get, post
from rdflib import DCTERMS, OWL, RDF, RDFS, Graph, URIRef

from cmem_plugin_robotreason.workflow import RobotReasonPlugin
from tests.utils import TestExecutionContext, needs_cmem

from . import __path__

UID = "e02aaed014c94e0c91bf960fed127750"
DATA_GRAPH_IRI = f"https://ns.eccenca.com/reasoning/{UID}/data/"
ONTOLOGY_GRAPH_IRI = f"https://ns.eccenca.com/reasoning/{UID}/vocab/"
RESULT_GRAPH_IRI = f"https://ns.eccenca.com/reasoning/{UID}/result/"


@pytest.fixture()
def _setup(request: pytest.FixtureRequest) -> None:
    """Set up"""
    res = post(DATA_GRAPH_IRI, Path(__path__[0]) / "dataset_owl.ttl", replace=True)
    if res.status_code != 204:  # noqa: PLR2004
        raise ValueError(f"Response {res.status_code}: {res.url}")
    res = post(ONTOLOGY_GRAPH_IRI, Path(__path__[0]) / "vocab.ttl", replace=True)
    if res.status_code != 204:  # noqa: PLR2004
        raise ValueError(f"Response {res.status_code}: {res.url}")

    request.addfinalizer(lambda: delete(DATA_GRAPH_IRI))
    request.addfinalizer(lambda: delete(ONTOLOGY_GRAPH_IRI))
    request.addfinalizer(lambda: delete(RESULT_GRAPH_IRI))  # noqa: PT021


@needs_cmem
def tests(_setup: None) -> None:
    """Tests"""

    def test_reasoner(reasoner: str) -> None:
        RobotReasonPlugin(
            data_graph_iri=DATA_GRAPH_IRI,
            ontology_graph_iri=ONTOLOGY_GRAPH_IRI,
            result_iri=RESULT_GRAPH_IRI,
            reasoner=reasoner,
        ).execute((), context=TestExecutionContext())

        result = Graph().parse(
            data=get(RESULT_GRAPH_IRI, owl_imports_resolution=False).text,
            format="turtle",
        )
        result.remove((URIRef(RESULT_GRAPH_IRI), DCTERMS.created, None))
        result.remove((URIRef(RESULT_GRAPH_IRI), RDFS.label, None))
        result.remove((None, RDF.type, OWL.AnnotationProperty))

        test = Graph().parse(Path(__path__[0]) / f"test_{reasoner}.ttl", format="turtle")
        for triple in result:
            assert triple in test

        for triple in test:
            assert triple in result

    reasoners = ["elk", "hermit", "jfact", "structural", "whelk"]
    for reasoner in reasoners:
        test_reasoner(reasoner)
