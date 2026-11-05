"""Runnable public-only integration template; no biological inference."""
import argparse
from pathlib import Path

from pertinfer_benchmark import export_prediction, load_public_task
from pertinfer_benchmark.freeze import freeze_predictions, verify_public_workspace
from pertinfer_benchmark.io import content_hash, read_json, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    public, output = Path(args.public).resolve(), Path(args.output).resolve()
    if output.is_relative_to(public):
        raise ValueError("prediction output must be outside the public input workspace")
    binding = verify_public_workspace(public)
    cohorts = read_json(public / "cohorts.json")["tasks"]
    tasks = sorted(cohorts)
    output.mkdir(parents=True, exist_ok=False)
    plan = dict(release_hash=binding["release_hash"], expected_runs=[
        dict(task_id=tid, method="abstention_template", view=binding["view"], seed=0) for tid in tasks])
    write_json(output / "run_plan.json", plan)
    for tid in tasks:
        bundle = load_public_task(public, tid, binding["view"])
        export_prediction(output / f"{tid}.json", task_id=tid, method="abstention_template",
                          view=binding["view"], seed=0, status="no_path",
                          graph={"nodes": [], "reactions": [], "relations": []},
                          release_hash=binding["release_hash"], knowledge_hash=bundle["view_manifest"]["knowledge_hash"],
                          input_hash=bundle["input_hash"], cohort_hash=content_hash(cohorts[tid]),
                          draft_hash=content_hash({}), config_hash=content_hash({"method": "abstain"}))
    freeze_predictions(output, tasks, output / "run_plan.json")
    print(output)


if __name__ == "__main__":
    main()
