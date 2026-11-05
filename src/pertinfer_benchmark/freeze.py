"""Standalone manifests. Historical development seals are never rewritten."""
from pathlib import Path
import shutil

from .io import checked_path, content_hash, file_hash, read_json, validate_id, write_json
from .schema import SCHEMA_VERSION

RELEASE_FORMAT = "pertinfer_benchmark.release_v1"


def code_hashes():
    root = Path(__file__).parent
    return {p.name: file_hash(p) for p in sorted(root.glob("*.py"))}


def inventory(root, *, json_only=False, exclude=()):
    root = Path(root)
    files = {}
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            raise ValueError("sealed packages must not contain symlinks")
        if p.is_file() and str(p.relative_to(root)) not in exclude:
            if not json_only or p.suffix == ".json":
                files[p.relative_to(root).as_posix()] = file_hash(p)
    return files


def freeze_release(root):
    root = Path(root)
    if not root.is_dir():
        raise ValueError("release directory missing")
    if (root / "release_manifest.json").exists():
        raise FileExistsError("release already frozen; create a new release version")
    body = dict(format=RELEASE_FORMAT, schema_version=SCHEMA_VERSION,
                files=inventory(root), scorer_code=code_hashes())
    manifest = dict(body, release_hash=content_hash(body))
    write_json(root / "release_manifest.json", manifest)
    return manifest


def verify_release(root):
    root = Path(root)
    manifest = read_json(root / "release_manifest.json")
    if manifest.get("format") != RELEASE_FORMAT:
        raise ValueError("not a standalone release; use the archived evaluator for historical seals")
    body = {k: v for k, v in manifest.items() if k != "release_hash"}
    if content_hash(body) != manifest["release_hash"]:
        raise ValueError("manifest digest mismatch")
    for rel in manifest["files"]:
        checked_path(root, rel)
    if inventory(root, exclude=("release_manifest.json",)) != manifest["files"]:
        raise ValueError("release file inventory or content changed")
    if code_hashes() != manifest["scorer_code"]:
        raise ValueError("scoring code changed since release")
    return manifest


def planned_runs(plan, task_ids):
    if not isinstance(plan.get("expected_runs"), list) or not plan["expected_runs"]:
        raise ValueError("nonempty run plan required")
    runs = set()
    for row in plan["expected_runs"]:
        key = row["method"], row["view"], row["seed"], row["task_id"]
        validate_id(key[3])
        if not isinstance(key[0], str) or not key[0] or key[1] not in ("open", "masked") or type(key[2]) is not int or key[3] not in task_ids:
            raise ValueError("invalid planned method/view/seed/task")
        if key in runs:
            raise ValueError("duplicate planned run")
        runs.add(key)
    if {r[3] for r in runs} != set(task_ids):
        raise ValueError("every declared task needs at least one planned run")
    return runs


def freeze_predictions(root, task_ids, run_plan=None):
    """Without a plan, legacy sealing is allowed; standalone scoring requires a plan."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if (root / "prediction_manifest.json").exists():
        raise FileExistsError("predictions already frozen")
    task_ids = sorted(set(validate_id(x) for x in task_ids))
    expected = None
    if run_plan is not None:
        plan = read_json(run_plan)
        expected = planned_runs(plan, task_ids)
        if Path(run_plan).resolve() != (root / "run_plan.json").resolve():
            if (root / "run_plan.json").exists():
                raise FileExistsError("run plan already exists")
            write_json(root / "run_plan.json", plan)
    files = inventory(root, json_only=True)
    predictions, seen = [], set()
    for rel in files:
        p = read_json(root / rel)
        if not isinstance(p, dict) or not all(k in p for k in ("task_id", "graph", "method", "view", "seed", "schema_version")):
            continue
        key = p["method"], p["view"], p["seed"], p["task_id"]
        if p["task_id"] not in task_ids or key in seen or (expected is not None and key not in expected):
            raise ValueError("duplicate, unplanned or out-of-cohort prediction")
        seen.add(key)
        predictions.append(rel)
    if not predictions and expected is None:
        raise ValueError("no predictions; a run plan is required for an all-failed batch")
    body = dict(files=files, predictions=predictions, task_ids=task_ids)
    if expected is not None:
        body["run_plan_file"] = "run_plan.json"
    manifest = dict(body, prediction_hash=content_hash(body))
    write_json(root / "prediction_manifest.json", manifest)
    return manifest


def verify_predictions(root):
    root = Path(root)
    manifest = read_json(root / "prediction_manifest.json")
    if content_hash({k: v for k, v in manifest.items() if k != "prediction_hash"}) != manifest["prediction_hash"]:
        raise ValueError("prediction manifest tampered")
    for rel in manifest["files"]:
        checked_path(root, rel)
    if inventory(root, json_only=True, exclude=("prediction_manifest.json",)) != manifest["files"]:
        raise ValueError("prediction inventory or content changed after freeze")
    if len(set(manifest["predictions"])) != len(manifest["predictions"]) or not set(manifest["predictions"]) <= set(manifest["files"]):
        raise ValueError("invalid prediction file list")
    return manifest


def export_public_workspace(release, destination, view):
    if view not in ("open", "masked"):
        raise ValueError("invalid view")
    release, destination = Path(release), Path(destination)
    manifest = verify_release(release)
    destination.mkdir(parents=True, exist_ok=False)
    for rel in manifest["files"]:
        if rel.startswith("public/") or rel.startswith(f"views/{view}/") or rel in ("splits.json", "cohorts.json"):
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(checked_path(release, rel), target)
    write_json(destination / "release_manifest.json", dict(
        release_hash=manifest["release_hash"], schema_version=SCHEMA_VERSION, public_only=True, view=view))
    write_json(destination / "public_run_manifest.json", dict(
        release_hash=manifest["release_hash"], view=view, files=inventory(destination),
        private_copied=False, os_isolation=False))
    return destination


def verify_public_workspace(root):
    root = Path(root)
    m = read_json(root / "public_run_manifest.json")
    binding = read_json(root / "release_manifest.json")
    if not binding.get("public_only") or binding["release_hash"] != m["release_hash"] or binding["view"] != m["view"]:
        raise ValueError("public workspace binding mismatch")
    for rel in m["files"]:
        checked_path(root, rel)
        if not (rel.startswith("public/") or rel.startswith(f"views/{m['view']}/") or rel in ("splits.json", "cohorts.json", "release_manifest.json")):
            raise ValueError("unexpected file in public workspace")
    if inventory(root, exclude=("public_run_manifest.json",)) != m["files"]:
        raise ValueError("public workspace changed")
    return m
