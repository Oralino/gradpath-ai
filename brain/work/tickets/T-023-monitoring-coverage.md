# T-023: nothing indexed on metrics, monitoring and alerting
Found in the owner's local test of the preparation plan (2026-11-21), twice. Sources in
`../../../knowledge_base/source_manifest.csv`; corpus decisions in T-009.

- **Type:** change
- **Status:** done
- **Opened:** 2026-11-21 · **Closed:** 2026-11-21
- **GitHub Issue:** none

## Summary
The sample posting asks for production debugging with logs and metrics, and prefers monitoring
and alerting. In both test plans the roadmap step cited only the Twelve-Factor App (logs as event
streams) and said metrics are not covered by the provided material. That is accurate: the index
has nothing on metrics or alerting. Monitoring is a common new-grad backend requirement.

## Cause
The one monitoring source, Google SRE Book "Monitoring Distributed Systems"
(`be-google-sre-monitoring`), is `link_only`: its licence is CC BY-NC-ND 4.0 (no derivatives),
so by the owner's decision of 2026-11-17 it is cited by URL and not chunked. Retrieval can't find
what isn't indexed. (A first reading in the session blamed retrieval; the manifest shows it is a
corpus gap by design.)

## Decision
Owner, 2026-11-21: option (a), add both openly licensed sources (rejected for now: showing
`link_only` sources as further reading, and leaving the gap as is).
- `devops-prometheus-monitoring`: Prometheus docs (`prometheus/docs`, Apache 2.0), 4 pages:
  overview, metric types, instrumentation, alerting practices.
- `devops-otel-observability`: OpenTelemetry docs (`opentelemetry.io`, CC BY 4.0, attribution to
  The OpenTelemetry Authors, recorded in the manifest's licence column like the Kubernetes source),
  4 pages: observability primer and the logs, metrics and traces signals.
- Both licences checked on the upstream repos' LICENSE files. Rows say `added_by: owner`.
- Owner, 2026-11-21: the 28 older rows also say `added_by: owner` now (they said `claude`, which
  broke the no-AI-attribution rule). The field isn't in chunk metadata, so no re-ingest.
- Only the two new documents were embedded (`ingest --only`): the cache served the 1,592 existing
  chunks, 108 new chunks cost about 18.7K Voyage tokens.

## Changes
- Branch: `feat/t-023-monitoring-sources`
- PR: [#15](https://github.com/Oralino/gradpath-ai/pull/15)
- Files touched: `knowledge_base/source_manifest.csv` (2 rows), `knowledge_base/index_info.json`
  (29 documents, 1,700 chunks), `evaluation/results/retrieval-20261121-104638.json`, ARCHITECTURE
  (corpus v3), EVALUATION (retrieval re-check), TASKS, DONE.
- Commits (hash, message): `32b41c1` feat: add Prometheus and OpenTelemetry monitoring sources
  (T-023); `a5b1b66` merge of `origin/main`; `42fa671` docs: note the eval ran before the T-024
  merge (T-023).

## Verification
- Retrieval eval (one Voyage call, `retrieval-20261121-104638.json`): every summary number equals
  the baseline (Recall@5 0.961, Precision@5 0.605, MRR 0.987; at 0.45, 97% covered kept, 67%
  uncovered rejected; partial misses `q-001`, `q-027`, `q-034`). New chunks reach a top 10 only for
  two uncovered questions (`q-032`, `q-033`, scores 0.26 to 0.30, below the 0.45 threshold), so
  they displaced nothing that counts. The eval set has no monitoring question yet.
- Real answer from the owner's terminal, "What metrics should I monitor for a backend service and
  when should I alert?": a partial answer (queries, errors, latency; alert on user-visible
  symptoms) citing three Prometheus chunks (instrumentation, alerting; scores 0.55 to 0.60). Before
  this change the index had nothing on the topic.
- Both runs were made before `main`'s T-024 answer-prompt change was merged in; retrieval, which
  this ticket changes, is unaffected by it.
