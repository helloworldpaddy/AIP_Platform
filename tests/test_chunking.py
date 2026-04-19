from agents.rag_agent.utils.chunking import TextChunker


def test_short_text_produces_single_chunk():
    chunker = TextChunker(chunk_size=1000, chunk_overlap=100)
    chunks = chunker.chunk("Hello world.")
    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].content == "Hello world."


def test_long_text_chunks_with_overlap():
    chunker = TextChunker(chunk_size=50, chunk_overlap=10)
    text = " ".join([f"sentence {i}." for i in range(200)])
    chunks = chunker.chunk(text)
    assert len(chunks) > 1
    # Adjacent chunks should share some content because of overlap.
    overlap = set(chunks[0].content.split()) & set(chunks[1].content.split())
    assert overlap, "expected overlap between consecutive chunks"


def test_indexes_are_sequential():
    chunker = TextChunker(chunk_size=50, chunk_overlap=10)
    text = " ".join([f"s{i}" for i in range(500)])
    chunks = chunker.chunk(text)
    assert [c.index for c in chunks] == list(range(len(chunks)))
