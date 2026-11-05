import copy
import json
import subprocess
import sys

import pytest

from pertinfer_benchmark.demo import fixture_spec, graph, run_demo
from pertinfer_benchmark.freeze import (
    code_hashes, export_public_workspace, freeze_predictions, planned_runs,
    verify_predictions, verify_public_workspace, verify_release,
)
from pertinfer_benchmark.io import content_hash, export_prediction, load_public_task, read_json, write_json
from pertinfer_benchmark.release import build_release, validate_contents
from pertinfer_benchmark.runner import run
from pertinfer_benchmark.tasks import validate_task


@pytest.fixture
def release(tmp_path):
    root = tmp_path / "release"
    build_release(fixture_spec(), root)
    return root


def prepare_predictions(root, release, *, missing=False, mutate=None):
    tid = "synthetic_chain"
    bundle = load_public_task(release, tid, "masked")
    rh = read_json(release / "release_manifest.json")["release_hash"]
    plan = {"release_hash": rh, "expected_runs": [dict(method="test", view="masked", seed=0, task_id=tid)]}
    write_json(root / "run_plan.json", plan)
    if not missing:
        p = export_prediction(root / "prediction.json", task_id=tid, method="test", view="masked", seed=0,
                              graph=graph(9606), release_hash=rh, knowledge_hash=bundle["view_manifest"]["knowledge_hash"],
                              draft_hash=content_hash({}), config_hash=content_hash({}), input_hash=bundle["input_hash"],
                              cohort_hash=content_hash(read_json(release / "cohorts.json")["tasks"][tid]))
        if mutate:
            mutate(p)
            write_json(root / "prediction.json", p)
    freeze_predictions(root, [tid], root / "run_plan.json")
    return root


def test_offline_demo_has_success_failure_missing_and_null(tmp_path):
    result = run_demo(tmp_path / "demo")
    rows = {(r["task_id"], r["method"]): r for r in result["rows"]}
    assert len(rows) == 6
    assert rows["synthetic_chain", "synthetic_exact"]["lower"] == 1
    assert rows["synthetic_chain", "abstain"]["lower"] == 0
    assert rows["synthetic_chain", "missing"]["status"] == "missing"
    assert rows["synthetic_chain", "missing"]["lower"] == 0
    for method in ("synthetic_exact", "abstain", "missing"):
        assert rows["synthetic_incomplete", method]["lower"] is None
    assert result["main_metrics"]["C"] is None
    with pytest.raises(FileExistsError):
        run_demo(tmp_path / "demo")


def test_public_export_preserves_bindings_and_excludes_references(release, tmp_path):
    public = export_public_workspace(release, tmp_path / "public", "masked")
    verify_public_workspace(public)
    assert not (public / "private").exists()
    assert not (public / "views/open").exists()
    for tid in ("synthetic_chain", "synthetic_incomplete"):
        assert load_public_task(public, tid, "masked") == load_public_task(release, tid, "masked")
    with pytest.raises(FileExistsError):
        export_public_workspace(release, public, "masked")
    write_json(public / "unexpected.json", {})
    with pytest.raises(ValueError, match="changed"):
        verify_public_workspace(public)


def test_all_failed_arm_stays_in_denominator(release, tmp_path):
    predictions = prepare_predictions(tmp_path / "predictions", release, missing=True)
    report = run(release, predictions, tmp_path / "scores.json")
    assert report["rows"][0]["status"] == "missing"
    assert report["summaries"][0]["C_denominator"] == 1
    assert report["summaries"][0]["C_lower"] == 0


@pytest.mark.parametrize("field", ["input_hash", "cohort_hash", "knowledge_hash", "release_hash"])
def test_changed_bindings_rejected(release, tmp_path, field):
    predictions = prepare_predictions(tmp_path / "predictions", release, mutate=lambda p: p.update({field: "0" * 64}))
    with pytest.raises(ValueError, match="binding"):
        run(release, predictions, tmp_path / "scores.json")


def test_malformed_graph_counts_as_invalid_not_success(release, tmp_path):
    predictions = prepare_predictions(tmp_path / "predictions", release,
                                      mutate=lambda p: p.update(graph={"nodes": [None], "reactions": [], "relations": []}))
    row = run(release, predictions, tmp_path / "scores.json")["rows"][0]
    assert row["status"] == "invalid" and row["lower"] == 0


def test_wrong_boundary_and_crash_are_failures(release, tmp_path):
    def wrong(p):
        p["graph"]["nodes"][2]["type"] = "protein"
    p = prepare_predictions(tmp_path / "wrong", release, mutate=wrong)
    assert run(release, p, tmp_path / "wrong.json")["rows"][0]["status"] == "invalid"
    p = prepare_predictions(tmp_path / "crash", release, mutate=lambda p: p.update(status="crash"))
    row = run(release, p, tmp_path / "crash.json")["rows"][0]
    assert row["status"] == "crash" and row["lower"] == 0


def test_duplicate_and_undeclared_runs_rejected(release, tmp_path):
    plan = {"expected_runs": [dict(method="test", view="open", seed=0, task_id="a")]}
    plan["expected_runs"].append(copy.deepcopy(plan["expected_runs"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        planned_runs(plan, ["a"])
    with pytest.raises(ValueError, match="every declared task"):
        planned_runs({"expected_runs": plan["expected_runs"][:1]}, ["a", "b"])


def test_seals_detect_code_and_prediction_changes(release, tmp_path, monkeypatch):
    from pertinfer_benchmark import freeze
    original = code_hashes()
    monkeypatch.setattr(freeze, "code_hashes", lambda: dict(original, **{"evaluate.py": "0" * 64}))
    with pytest.raises(ValueError, match="code changed"):
        verify_release(release)
    monkeypatch.undo()
    predictions = prepare_predictions(tmp_path / "predictions", release)
    p = read_json(predictions / "prediction.json")
    p["graph"]["relations"][0]["sign"] = "-"
    write_json(predictions / "prediction.json", p)
    with pytest.raises(ValueError, match="changed after freeze"):
        verify_predictions(predictions)


def test_historical_seals_not_silently_reissued(release):
    manifest = read_json(release / "release_manifest.json")
    manifest.pop("format")
    write_json(release / "release_manifest.json", manifest)
    with pytest.raises(ValueError, match="archived evaluator"):
        verify_release(release)


def test_no_writes_inside_sealed_inputs(release, tmp_path):
    predictions = prepare_predictions(tmp_path / "predictions", release)
    for output in [release / "score.json", predictions / "score.json"]:
        with pytest.raises(ValueError, match="outside sealed"):
            run(release, predictions, output)
        assert not output.exists()


def test_empty_eligible_reference_is_dataset_error(tmp_path):
    spec = fixture_spec()
    spec["tasks"][0]["reference_chains"] = {"chains": []}
    with pytest.raises(ValueError, match="eligible task"):
        build_release(spec, tmp_path / "invalid")
    assert not (tmp_path / "invalid/release_manifest.json").exists()


def test_method_candidates_and_response_leak_not_admitted(tmp_path):
    spec = fixture_spec()
    spec["tasks"][0]["allowed_context"]["ortholog_candidates"] = {}
    with pytest.raises(ValueError, match="method-generated"):
        build_release(spec, tmp_path / "candidates")
    spec = fixture_spec()
    spec["tasks"][0]["task"]["human_response_direction"] = "increase"
    with pytest.raises(ValueError, match="response direction"):
        build_release(spec, tmp_path / "response")


def test_new_taxa_and_genus_resolution():
    task = fixture_spec()["tasks"][0]["task"]
    task["source_taxon"] = {"taxon_id": 9615, "scientific_name": "Canis lupus familiaris"}
    validate_task(task)
    task["source_taxon"] = {"taxon_id": 10114, "scientific_name": "Rattus"}
    with pytest.raises(ValueError, match="genus"):
        validate_task(task)
    task["source_taxon"]["resolution"] = "genus"
    validate_task(task)


def test_public_import_does_not_import_private_scorer():
    code = "import sys; import pertinfer_benchmark; from pertinfer_benchmark import freeze; assert not any(x in sys.modules for x in ['pertinfer_benchmark.runner', 'pertinfer_benchmark.evaluate', 'pertinfer_benchmark.scoring'])"
    # pytest's pythonpath does not carry to a subprocess unless passed explicitly.
    import os
    from pathlib import Path
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).parents[1] / "src"))
    subprocess.run([sys.executable, "-c", code], env=env, check=True)


def test_missing_reference_eligibility_preserves_null_on_crash():
    from pertinfer_benchmark.scoring import score_one
    entry = fixture_spec()["tasks"][1]
    row = score_one({"status": "crash", "graph": graph(9606)}, entry["task"], entry["scoring_policy"], entry["reference_chains"])
    assert row["lower"] is None and row["status"] == "crash"


def test_task_means_precede_across_task_aggregation():
    from pertinfer_benchmark.scoring import summarize_rows
    common = dict(method="test", view="open", source_taxon=10090, scope="synthetic", qualification="synthetic",
                  previously_exposed=True, mechanism_group_previously_exposed=True,
                  scoring_eligible=True, status="contained", counts={"total": 2})
    rows = [dict(common, task_id="a", lower=1, upper=1) for _ in range(3)]
    rows.append(dict(common, task_id="b", lower=0, upper=0))
    result = summarize_rows(rows)[0]
    assert result["C_lower"] == 0.5 and result["C_run_denominator"] == 4
