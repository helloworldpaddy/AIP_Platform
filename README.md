# ADK RAG with PostgreSQL (pgvector) + Gemini

A production-grade Retrieval-Augmented Generation (RAG) system built with:

- **Google Agent Development Kit (ADK)** — agent + tool architecture
- **PostgreSQL + pgvector** — vector store (no Vertex AI RAG Engine)
- **Gemini** — embeddings (`text-embedding-004`) and generation (`gemini-2.0-flash` / `gemini-1.5-pro`)
- **AML domain extensions** — entity-aware retrieval, query expansion, risk scoring
- **Optional** — Redis cache, hybrid BM25+vector search, reranking, OpenTelemetry

## Architecture

```
┌──────────────┐   ┌──────────────────┐   ┌─────────────────────┐
│ Documents    │──▶│ Ingestion Service │──▶│ Postgres (pgvector) │
│ PDF/DOCX/TXT │   │  (chunk+embed)    │   │  documents table    │
└──────────────┘   └──────────────────┘   └─────────────────────┘
                                                    ▲
┌──────────────┐   ┌──────────────────┐   ┌─────────┴───────────┐
│ User query   │──▶│ ADK Agent        │──▶│ vector_search_tool  │
│              │   │  (Gemini)        │   │  (retrieval svc)    │
└──────────────┘   └──────────────────┘   └─────────────────────┘
                            │
                            ▼
                    Grounded answer
```

## Project Structure

```
agents/rag_agent/
    agent.py                  # ADK agent wiring
    prompts.py                # System prompt + response template
    tools/
        vector_search_tool.py # ADK tool exposed to the agent
    services/
        embedding_service.py  # Gemini embeddings (batch + async)
        retrieval_service.py  # Vector / hybrid search
        ingestion_service.py  # Chunk → embed → upsert
    db/
        postgres_client.py    # asyncpg pool + queries
        schema.sql            # Table + indexes
    config/
        settings.py           # Pydantic settings (env + YAML)
    utils/
        chunking.py           # Token-aware chunker with overlap
        text_extraction.py    # PDF/DOCX/TXT extractors
        logging_config.py     # Structured logging
        telemetry.py          # OpenTelemetry tracing
        cache.py              # Redis-backed query/embedding cache
    aml/
        entity_extractor.py   # Parties, aliases, sanctions terms
        query_expansion.py    # Synonyms + risk vocabulary
        risk_scoring.py       # Priority boosting for results
scripts/
    setup_db.py               # Enable pgvector + apply schema
    ingest.py                 # Ingest files from a directory
    query.py                  # End-to-end query runner
tests/
    test_embedding_service.py
    test_retrieval_service.py
    test_integration.py
config.yaml
.env.example
docker-compose.yml
requirements.txt
```

## Setup

### 1. Requirements

- Python 3.11+
- PostgreSQL 16+ with `pgvector` extension (use the provided `docker-compose.yml`)
- Google AI Studio API key (`GOOGLE_API_KEY`) — or a GCP project for Vertex-hosted Gemini
- (Optional) Redis for caching

### 2. Install dependencies

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Start Postgres

```bash
docker compose up -d postgres
```

### 4. Configure environment

```bash
cp .env.example .env
# edit .env: GOOGLE_API_KEY, DB credentials
```

### 5. Initialize the database

```bash
python scripts/setup_db.py
```

### 6. Ingest documents

```bash
python scripts/ingest.py --path ./data/samples --tags aml,policy
```

### 7. Query

```bash
python scripts/query.py "Who is the beneficial owner of ACME Holdings?"
```

Or run the ADK agent interactively:

```bash
adk run agents.rag_agent
```

## Configuration

All settings are externalized via `config.yaml` and/or environment variables
(env vars take precedence). See `agents/rag_agent/config/settings.py`.

Key options:

| Setting            | Default                 | Description                        |
|--------------------|-------------------------|------------------------------------|
| `embedding_model`  | `text-embedding-004`    | Gemini embedding model             |
| `generation_model` | `gemini-2.0-flash`      | Gemini chat model                  |
| `embedding_dim`    | `768`                   | Must match the embedding model     |
| `chunk_size`       | `800`                   | Tokens per chunk                   |
| `chunk_overlap`    | `100`                   | Overlap tokens                     |
| `top_k`            | `5`                     | Retrieved chunks per query         |
| `ivfflat_lists`    | `100`                   | pgvector IVFFlat index lists       |
| `hybrid_search`    | `true`                  | Combine BM25 (`tsvector`) + vector |
| `enable_rerank`    | `false`                 | Enable LLM-based reranking         |
| `cache_enabled`    | `false`                 | Redis query/embedding cache        |

## AML Extensions

The system includes an AML (Anti-Money Laundering) domain layer:

- **Entity-aware retrieval** — parties, aliases, account numbers are extracted
  from the query and used to filter/boost results via the metadata JSONB column.
- **Query expansion** — risk vocabulary (e.g. *layering*, *structuring*,
  *shell company*, *PEP*, *SDN*) expands user queries for higher recall.
- **Risk scoring** — retrieved chunks are re-scored by a weighted combination
  of vector similarity, BM25, and domain signals (sanctions keywords,
  transaction cues, jurisdictions of concern).

## Testing

```bash
pytest tests/ -v
pytest tests/test_integration.py -v -m integration  # requires running Postgres
```

## Observability

- **Logs** — structured JSON via `utils/logging_config.py`
- **Tracing** — OpenTelemetry spans around ingest, embed, retrieve, generate
- **Metrics** — retrieval latency, LLM latency, success rate, cache hit rate
- Configure the OTLP exporter via `OTEL_EXPORTER_OTLP_ENDPOINT`

## License

MIT
