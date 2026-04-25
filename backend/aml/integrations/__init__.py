"""External integrations: Neo4j, KYC providers, web search adapters.

Each module here implements one of the `Provider` protocols declared in
`backend/aml/agents/tools/data_tools.py`.  Wiring (instantiating the client
+ calling `set_*_provider`) happens once at FastAPI startup.
"""
