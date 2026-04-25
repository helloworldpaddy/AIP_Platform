// Initial constraints + indexes for the AML investigation graph.
//
// Loaded once on first boot by `cypher-shell` invoked from the
// `neo4j-init` one-shot service in docker-compose.yml.  Intentionally
// minimal — concrete relationship types accrete as the GraphProvider
// is implemented.

CREATE CONSTRAINT party_external_id_unique IF NOT EXISTS
FOR (p:Party) REQUIRE p.party_external_id IS UNIQUE;

CREATE CONSTRAINT account_external_id_unique IF NOT EXISTS
FOR (a:Account) REQUIRE a.account_external_id IS UNIQUE;

CREATE CONSTRAINT transaction_external_id_unique IF NOT EXISTS
FOR (t:Transaction) REQUIRE t.transaction_external_id IS UNIQUE;

CREATE INDEX party_name_text IF NOT EXISTS FOR (p:Party) ON (p.party_name);
CREATE INDEX transaction_timestamp IF NOT EXISTS FOR (t:Transaction) ON (t.timestamp);
