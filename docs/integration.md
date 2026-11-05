# Integration contract

## Modules and responsibilities

`schema` defines graph identity, normalization and relation counts. `tasks`
validates multi-species public tasks and fixed human boundaries. `io` loads tasks
and exports predictions. `freeze` handles manifests and public exports. These
modules do not import reference matching or scoring code.

`release` packages curator inputs and validates references. `evaluate` contains
the scientific matcher, `scoring` the eligibility/aggregation rules and `runner`
the independent scoring command. `materials` constructs original-source libraries.

## Curator input

See `examples/synthetic_spec.json`. Each task entry supplies:

- Public `task`, `source_graph`, `source_provenance` and `allowed_context`.
- Evaluator-only `reference_chains`, `reference_evidence` and `adjudication`.
- `scoring_policy` and `cohort` describing reference eligibility, endpoint scope,
  task-level exposure and mechanism-level exposure.

Qualification is explicit: `synthetic`, `proxy` or `provisional`. Source taxon and
scientific name must agree. Unresolved rat identity uses genus taxon 10114 with
`resolution: genus`. Human response direction is `not_given`. Predictions preserve
the human boundary identity, state and compartment.

Optional `knowledge` and `blocked_ids` define frozen record evidence views.
`views.build_view` applies lineage closure. `KnowledgeGateway` is a simple optional
record reader, not the agent's graph-directed search implementation or a recreation
of the whole-paper/material-library experiment. Material-library datasets need
their own corpus snapshot and access-policy bindings.

The builder does not generate human candidates or ortholog mappings. Related
mechanism/study groups remain together. The inherited split helper creates
development/feasibility partitions, not an independently qualified test set.

## Prediction workflow

1. Build the release and export its `open` or `masked` public workspace.
2. Define the run plan before inference; record its hash externally if independent
   proof of chronology matters.
3. Load public inputs and export each method output with its input bindings.
4. Seal the plan and outputs, including any all-failed method arm.
5. Run evaluation separately with the full release and sealed predictions.

```python
from pertinfer_benchmark import load_public_task, export_prediction
from pertinfer_benchmark.freeze import verify_public_workspace
from pertinfer_benchmark.io import content_hash, read_json

public = "artifacts/public"
manifest = verify_public_workspace(public)
bundle = load_public_task(public, "synthetic_chain", "masked")
cohort = read_json(f"{public}/cohorts.json")["tasks"]["synthetic_chain"]

# Replace this abstention with your method's output.
export_prediction(
    "artifacts/my-run/prediction.json",
    task_id="synthetic_chain", method="my_method", view="masked", seed=0,
    graph={"nodes": [], "reactions": [], "relations": []}, status="no_path",
    release_hash=manifest["release_hash"],
    knowledge_hash=bundle["view_manifest"]["knowledge_hash"],
    input_hash=bundle["input_hash"], cohort_hash=content_hash(cohort),
    draft_hash=content_hash({}), config_hash=content_hash({"method_version": "example"}),
)
```

`draft_hash` identifies the initial graph or an explicitly documented empty object
when none is supplied. `config_hash` identifies the method configuration. The
scorer requires the public input, cohort, release, evidence-view and graph-contract
bindings. See `examples/abstain.py` for a complete runnable template.

The run plan (replace the placeholder hash) is:

```json
{
  "release_hash": "<release SHA256>",
  "expected_runs": [
    {"task_id": "synthetic_chain", "method": "my_method", "view": "masked", "seed": 0}
  ]
}
```

```bash
pertinfer-benchmark freeze-predictions --predictions artifacts/my-run \
  --run-plan artifacts/my-run/run_plan.json --task-ids synthetic_chain
pertinfer-benchmark score --release artifacts/release \
  --predictions artifacts/my-run --output artifacts/my-scores.json
```

Freeze once. Write scores outside sealed input directories. Unknown runs,
duplicates and input mismatches are rejected; missing planned outputs remain
counted. Runtime statuses are `ok`, `no_path`, `crash`, `resource_limit`, `invalid`.

## Scoring

Containment requires every reference chain, allowing any accepted variant for
each chain. Scientific entity/reaction identity matters, not arbitrary IDs.
Signs, states, participants and necessary side dependencies are explicit; unknown
signs are not wildcards. Mutually exclusive choices cannot be combined within a
chain match. Compatibility is not enforced across separate reference chains.

The original matcher uses a five-second timeout per variant and a configurable
search-state limit. Exhaustion yields unresolved bounds `[0, 1]`, not a false
negative. Graph size counts unique main relations and unique necessary extra
participant/reaction pairs; a participant already present on a main relation for
that reaction is not charged again. This is representation-specific size, not
biological accuracy or verification effort.

`provisional_abstract_chain` means an explicit reference is available for matching;
task qualification remains separate, including for synthetic fixtures.
`not_scored_reference_incomplete` gives null containment even for a failed run.
An empty eligible reference is a dataset error. Failed, invalid and missing
predictions receive zero on eligible tasks. Sizes on failures must not be
interpreted as efficient successful answers.

Repeats are averaged within task before equal weighting across tasks. Species,
endpoint scope, qualification, task exposure and mechanism exposure stay in
separate summaries. Unknown exposure remains null. This toolkit release reports
no confirmatory biological primary metrics.
