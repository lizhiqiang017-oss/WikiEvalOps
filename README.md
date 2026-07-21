# WikiEvalOps

WikiEvalOps is a trace-first evaluation harness for enterprise knowledge systems. It evaluates normalized execution traces instead of depending on a specific RAG, agent, vector database, or memory implementation.

This repository currently contains the first implementation slice:

- strict, versionable contracts for benchmark cases and full-chain traces;
- JSONL benchmark and offline-trace validation;
- task-aware metric profiles;
- deterministic routing, retrieval, claim-grounding, and commerce-risk metrics;
- dataset-level route Macro-F1 and high-risk recall aggregation;
- immutable run metadata and atomic JSON artifact writes;
- a CLI and a twelve-case smoke benchmark;
- unit and end-to-end tests that require no model API or external service.

The demo data is synthetic and contains no company code, internal configuration, or production data.

## Architecture

```text
EvalCase JSONL                     Offline or live system
      |                                      |
      v                                      v
Dataset validator                       Trace adapter
      |                                      |
      +------------------+-------------------+
                         v
                Evaluation harness
                         |
             task -> metric profile
                         |
          deterministic metric registry
                         |
         per-case results + run summary
                         |
                  JSON run artifact
```

The six execution stages remain available in `EvaluationTrace` for later error attribution: route, retrieval, context, memory, generation, and operational timing/cost. The initial public metric surface is intentionally small.

## Quick start

Create a virtual environment, then install the project in editable mode:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Validate the included benchmark and traces:

```powershell
wikieval validate benchmarks/smoke/cases.jsonl
wikieval validate examples/traces/reference-v1.jsonl --kind traces
```

For repository-only development without an editable install, use `PYTHONPATH=src` or run the test suite, which is already configured for the `src` layout.

Run the benchmark:

```powershell
wikieval run `
  --dataset benchmarks/smoke/cases.jsonl `
  --traces examples/traces/reference-v1.jsonl `
  --config configs/evaluation.json `
  --output artifacts/runs/reference-v1.json
```

The demo intentionally contains regressions, so `wikieval run` exits with code `2`. Exit codes are stable for CI integration:

- `0`: evaluation completed and all configured thresholds passed;
- `1`: invalid input or configuration;
- `2`: evaluation completed but quality thresholds failed.

Run tests:

```powershell
python -m pytest
```

## Data contracts

An `EvalCase` stores task type, risk level, expected route, gold evidence, required claims, and optional risk label. An `EvaluationTrace` stores the observed route, retrieved documents, assembled context, memory reads/writes, atomic claims, citations, timing, cost, and runtime errors.

Claims must explicitly identify supporting evidence. The deterministic `supported_claim_rate` counts a claim as supported only when it cites non-empty evidence and every cited evidence item exists in the assembled context. A later judge layer may assess semantic entailment, but it will not replace this structural check.

## Metric model

Each case runs only the metrics selected by its `metric_profile`. The first slice includes:

- `route_correctness`: per-case multi-label route F1;
- `evidence_recall_at_5`: fraction of gold evidence found in the first five retrieved documents;
- `supported_claim_rate`: fraction of atomic claims structurally grounded in available context;
- `risk_label_correctness`: per-case commerce risk classification correctness.

The run summary additionally calculates dataset-level `route_macro_f1` and `high_risk_recall`. Diagnostic detail remains attached to each case instead of expanding the top-level dashboard with many secondary metrics.

## Artifact reproducibility

Every run records:

- UTC run identifier;
- system version;
- absolute dataset path;
- SHA-256 digest of the benchmark;
- SHA-256 digest of the effective evaluation configuration;
- per-case scores and evidence;
- aggregate metrics, task slices, failed cases, and missing traces.

Artifacts are written through a temporary file and atomically replaced to avoid partially written CI output.

## Next implementation slices

1. Add baseline/candidate regression comparison and quality gates over confidence intervals.
2. Add rule-first failure attribution for route, retrieval, context, memory, generation, and business decision failures.
3. Build a lightweight reference pipeline with intentionally different v1/v2 behavior.
4. Add public-source Wiki grounding cases and synthetic commerce recommendation/diagnosis cases.
5. Add perturbation testing and benchmark challenge-set evolution after the deterministic core is stable.
