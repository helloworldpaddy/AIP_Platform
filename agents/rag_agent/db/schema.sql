-- ADK RAG schema. Safe to re-run.
-- Embedding dimension is templated as {embedding_dim} and substituted by setup_db.py.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS documents (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id  TEXT NOT NULL,          -- logical parent document id
    chunk_index  INT  NOT NULL,          -- chunk order within parent
    source       TEXT NOT NULL,          -- origin file path / URI
    content      TEXT NOT NULL,
    embedding    VECTOR({embedding_dim}),
    metadata     JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    tsv          TSVECTOR
                 GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);

-- Vector similarity (cosine) index.
-- IVFFlat requires ANALYZE after first bulk load for optimal performance.
CREATE INDEX IF NOT EXISTS documents_embedding_ivfflat
    ON documents USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = {ivfflat_lists});

-- Metadata JSONB index for fast filtering.
CREATE INDEX IF NOT EXISTS documents_metadata_gin
    ON documents USING gin (metadata);

-- Lexical search index for hybrid retrieval.
CREATE INDEX IF NOT EXISTS documents_tsv_gin
    ON documents USING gin (tsv);

-- Trigram index for fuzzy entity lookups (aliases, typos).
CREATE INDEX IF NOT EXISTS documents_content_trgm
    ON documents USING gin (content gin_trgm_ops);

CREATE INDEX IF NOT EXISTS documents_document_id_idx
    ON documents (document_id);

CREATE INDEX IF NOT EXISTS documents_created_at_idx
    ON documents (created_at DESC);

-- Utility: update updated_at on every row modification.
CREATE OR REPLACE FUNCTION documents_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS documents_updated_at ON documents;
CREATE TRIGGER documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION documents_set_updated_at();
