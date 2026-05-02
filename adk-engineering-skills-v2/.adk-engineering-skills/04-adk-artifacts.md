# ADK Artifacts Skill

Use ADK artifacts for generated and retrieved files.

Use artifacts for:

- Investigation reports
- Case narratives
- Evidence bundles
- JSON outputs
- PDF reports
- CSV transaction summaries
- Screenshots
- Audit files

Rules:

1. Do not store large reports only in session state.
2. Store generated investigation output as artifacts.
3. Include artifact metadata:
   - case_id
   - generated_by_agent
   - generation_timestamp
   - source_references
   - version
4. Keep evidence artifacts separate from final narrative artifacts.
