"""Offline synthetic integration fixture. No historical experiments or biology."""
from copy import deepcopy
from pathlib import Path

from .freeze import export_public_workspace, freeze_predictions
from .io import content_hash, export_prediction, load_public_task, read_json, write_json
from .release import build_release
from .schema import SCHEMA_VERSION


def graph(taxon):
    nodes = [dict(id="input", entity="fixture:input", taxon=0, type="compound", state={}),
             dict(id="mediator", entity="fixture:mediator", taxon=taxon, type="protein", state={}),
             dict(id="output", entity="fixture:output", taxon=taxon, type="rna", state={})]
    return dict(nodes=nodes, reactions=[
        dict(id="r1", type="fixture_step", inputs=["input"], outputs=["mediator"]),
        dict(id="r2", type="fixture_step", inputs=["mediator"], outputs=["output"])], relations=[
        dict(id="e1", kind="causal", sign="+", source="input", target="mediator", reaction_id="r1"),
        dict(id="e2", kind="causal", sign="+", source="mediator", target="output", reaction_id="r2")])


def fixture_spec():
    target = graph(9606)
    task = dict(schema_version=SCHEMA_VERSION, task_id="synthetic_chain", mechanism_group_id="fixture",
                qualification="synthetic", source_taxon={"taxon_id": 10090, "scientific_name": "Mus musculus"},
                source_context={"host_taxon": 10090, "description": "Synthetic fixture, no experiment"},
                human_context={"host_taxon": 9606, "description": "Synthetic fixture, no experiment"},
                perturbation={"identity": "fixture:input"}, source_start="input", source_endpoint="output",
                human_start=target["nodes"][0], human_endpoint=target["nodes"][2],
                human_response_direction="not_given", endpoint_type="rna", evaluation_level="state_explicit")
    entry = dict(task=task, source_graph=graph(10090), source_provenance={"records": [], "synthetic": True},
                 allowed_context={}, reference_chains={"chains": [{"chain_id": "fixture", "variants": [target]}]},
                 reference_evidence={"synthetic": True}, adjudication={"independent_review": False, "reviewer": None},
                 scoring_policy={"policy": "provisional_abstract_chain", "reason": "Synthetic engineering fixture only"},
                 cohort={"scope": "synthetic", "previously_exposed": True, "mechanism_group_previously_exposed": True})
    incomplete = deepcopy(entry)
    incomplete["task"]["task_id"] = "synthetic_incomplete"
    incomplete["reference_chains"] = {"chains": []}
    incomplete["scoring_policy"] = {"policy": "not_scored_reference_incomplete", "reason": "Exercise null-reference handling"}
    return dict(tasks=[entry, incomplete], knowledge=[], blocked_ids=[],
                metadata={"synthetic": True, "purpose": "Serialization and scoring demonstration; not a biological benchmark dataset"})


def run_demo(destination):
    from .runner import run
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=False)
    spec = fixture_spec()
    write_json(root / "curation_spec.json", spec)
    manifest = build_release(spec, root / "release")
    public = export_public_workspace(root / "release", root / "public", "masked")
    task_ids = [t["task"]["task_id"] for t in spec["tasks"]]
    methods = ["synthetic_exact", "abstain", "missing"]
    plan = {"release_hash": manifest["release_hash"], "expected_runs": [
        dict(task_id=tid, method=method, view="masked", seed=0) for tid in task_ids for method in methods]}
    write_json(root / "predictions/run_plan.json", plan)
    for tid in task_ids:
        bundle = load_public_task(public, tid, "masked")
        cohort = read_json(public / "cohorts.json")["tasks"][tid]
        for method in methods[:2]:
            # Hard-coded synthetic identities; never reads evaluator references.
            prediction = graph(9606) if method == "synthetic_exact" else {"nodes": [], "reactions": [], "relations": []}
            export_prediction(root / "predictions" / f"{tid}_{method}.json", task_id=tid, method=method, view="masked", seed=0,
                              graph=prediction, release_hash=manifest["release_hash"],
                              knowledge_hash=bundle["view_manifest"]["knowledge_hash"], draft_hash=content_hash({}),
                              config_hash=content_hash({"synthetic": True}), input_hash=bundle["input_hash"],
                              cohort_hash=content_hash(cohort), status="ok" if method == "synthetic_exact" else "no_path")
    freeze_predictions(root / "predictions", task_ids, root / "predictions/run_plan.json")
    return run(root / "release", root / "predictions", root / "scores.json")
