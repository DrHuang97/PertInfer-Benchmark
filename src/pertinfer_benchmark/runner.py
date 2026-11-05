"""Independent evaluation of sealed method outputs against an explicit run plan."""
from pathlib import Path

from .freeze import planned_runs, verify_predictions, verify_release
from .io import content_hash, load_public_task, read_json, write_json
from .release import validate_contents
from .schema import SCHEMA_VERSION
from .scoring import score_one, summarize_rows


def run(release, predictions, output, max_states=100000):
    root, proot = Path(release).resolve(), Path(predictions).resolve()
    output = Path(output).resolve()
    if output.is_relative_to(root) or output.is_relative_to(proot):
        raise ValueError("write scores outside sealed release and prediction directories")
    manifest = verify_release(root)
    tasks = validate_contents(root)
    pm = verify_predictions(proot)
    if pm.get("run_plan_file") != "run_plan.json" or "run_plan.json" not in pm["files"]:
        raise ValueError("sealed run plan required, including for an all-failed batch")
    if not set(pm["task_ids"]) <= set(tasks):
        raise ValueError("run plan contains tasks outside release")
    plan = read_json(proot / "run_plan.json")
    expected = planned_runs(plan, pm["task_ids"])
    if plan.get("release_hash") != manifest["release_hash"]:
        raise ValueError("run plan release mismatch")
    eligibility = read_json(root / "private/scoring_eligibility.json")["tasks"]
    cohorts = read_json(root / "cohorts.json")["tasks"]
    rows, seen, bundles = [], set(), {}

    def row_for(prediction, key, prediction_file=None):
        method, view, seed, tid = key
        task = tasks[tid]
        result = score_one(prediction, task, eligibility[tid],
                           read_json(root / "private" / tid / "reference_chains.json"), max_states)
        return dict(result, task_id=tid, method=method, view=view, seed=seed,
                    prediction_file=prediction_file, qualification=task["qualification"],
                    source_taxon=task["source_taxon"]["taxon_id"], scope=cohorts[tid]["scope"],
                    previously_exposed=cohorts[tid]["previously_exposed"],
                    mechanism_group_previously_exposed=cohorts[tid]["mechanism_group_previously_exposed"])

    for rel in pm["predictions"]:
        p = read_json(proot / rel)
        tid, view = p["task_id"], p["view"]
        key = p["method"], view, p["seed"], tid
        if key not in expected or key in seen:
            raise ValueError("duplicate or unplanned prediction")
        seen.add(key)
        if (tid, view) not in bundles:
            bundles[tid, view] = load_public_task(root, tid, view)
        bundle = bundles[tid, view]
        if p.get("schema_version") != SCHEMA_VERSION or p.get("release_hash") != manifest["release_hash"] or p.get("knowledge_hash") != bundle["view_manifest"]["knowledge_hash"]:
            raise ValueError("prediction schema/release/view binding mismatch")
        if p.get("input_hash") != bundle["input_hash"]:
            raise ValueError("public input binding missing or changed")
        if p.get("cohort_hash") != content_hash(cohorts[tid]):
            raise ValueError("task cohort binding missing or changed")
        rows.append(row_for(p, key, rel))
    for key in sorted(expected - seen):
        rows.append(row_for({"status": "missing", "graph": {"nodes": [], "reactions": [], "relations": []}}, key))
    report = dict(
        toolkit="pertinfer-benchmark", release_hash=manifest["release_hash"], prediction_hash=pm["prediction_hash"],
        rows=rows, summaries=summarize_rows(rows), qualified_task_count=0,
        main_metrics={"C": None, "M": None, "reason": "No independently qualified dataset in this toolkit release"},
        interpretation="Engineering checks or agreement to explicitly provisional references; no biological accuracy claim",
        notes=["Repeated runs averaged within task before across-task aggregation",
               "Incomplete references receive null containment; eligible failures remain in denominator",
               "Manifest checks are consistency checks, not proof of chronology or process isolation"])
    write_json(output, report)
    return report
