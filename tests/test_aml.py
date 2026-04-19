from agents.rag_agent.aml.entity_extractor import EntityExtractor
from agents.rag_agent.aml.query_expansion import QueryExpander
from agents.rag_agent.aml.risk_scoring import RiskScorer
from agents.rag_agent.services.retrieval_service import RetrievedChunk


def test_entity_extractor_finds_named_entities():
    ex = EntityExtractor()
    entities = ex.extract('Who owns "ACME Holdings" and account 12345678?')
    assert any("ACME" in e for e in entities)
    assert "12345678" in entities


def test_entity_extractor_skips_stopwords():
    ex = EntityExtractor()
    entities = ex.extract("Who signed this?")
    assert "Who" not in entities


def test_query_expansion_adds_synonyms():
    expander = QueryExpander()
    out = expander.expand("Who is the beneficial owner of ACME?")
    assert "UBO" in out


def test_query_expansion_is_noop_without_triggers():
    expander = QueryExpander()
    out = expander.expand("What is the weather today?")
    assert out == "What is the weather today?"


def test_risk_scorer_boosts_sanctions_hits():
    # Realistic scenario: candidates come back with similar vector scores,
    # so the AML keyword signal is what re-orders them.
    scorer = RiskScorer()
    chunks = [
        RetrievedChunk(
            id="filler", document_id="d0", chunk_index=0, source="z.txt",
            content="some filler paragraph with no signals.",
            metadata={}, score=0.60,
        ),
        RetrievedChunk(
            id="a", document_id="d1", chunk_index=0, source="x.txt",
            content="unrelated paragraph about office supplies.",
            metadata={}, score=0.82,
        ),
        RetrievedChunk(
            id="b", document_id="d2", chunk_index=0, source="y.txt",
            content=(
                "This person appears on the OFAC SDN list (sanction). "
                "Shell company structuring and layering indicators present."
            ),
            metadata={}, score=0.80,
        ),
    ]
    rescored = scorer.rescore("sanctions check", chunks)
    assert rescored[0].id == "b"
