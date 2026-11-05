"""Public task loading and method-neutral prediction export; no scoring imports."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile

from .schema import SCHEMA_VERSION, canonical, normalize_graph, validate_graph
from .tasks import validate_task


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as f:
            temporary = Path(f.name)
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def content_hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_path(root, relative):
    """Resolve a canonical relative file path without crossing the package root."""
    if not isinstance(relative, str) or "\\" in relative:
        raise ValueError("invalid package path")
    rel = PurePosixPath(relative)
    if rel.is_absolute() or not rel.parts or ".." in rel.parts or str(rel) != relative:
        raise ValueError("invalid package path")
    root = Path(root).resolve()
    path = (root / relative).resolve()
    path.relative_to(root)
    return path


def public_path(root, relative):
    path = checked_path(root, relative)
    parts = path.relative_to(Path(root).resolve()).parts
    if not parts or parts[0] not in ("public", "views") or "private" in parts:
        raise PermissionError("public whitelist denies path")
    return path


def validate_id(task_id):
    if not isinstance(task_id, str) or task_id in (".", "..") or not re.fullmatch(r"[A-Za-z0-9_.:-]+", task_id):
        raise ValueError("invalid task ID")
    return task_id


def load_public_task(root, task_id, view="open"):
    validate_id(task_id)
    if view not in ("open", "masked"):
        raise ValueError("invalid view")
    base = f"public/{task_id}"
    obj = {key: read_json(public_path(root, f"{base}/{key}.json")) for key in
           ("task", "source_graph", "source_provenance", "allowed_context")}
    validate_task(obj["task"])
    if obj["task"]["task_id"] != task_id:
        raise ValueError("task path and identity differ")
    validate_graph(obj["source_graph"])
    obj["view_manifest"] = read_json(public_path(root, f"views/{view}/manifest.json"))
    obj["knowledge"] = [json.loads(line) for line in public_path(root, f"views/{view}/knowledge.jsonl")
                        .read_text(encoding="utf-8").splitlines() if line]
    if obj["view_manifest"].get("view") != view:
        raise ValueError("view identity mismatch")
    if content_hash(obj["knowledge"]) != obj["view_manifest"]["knowledge_hash"]:
        raise ValueError("knowledge content differs from frozen view manifest")
    obj["input_hash"] = content_hash(obj)
    return obj


def export_prediction(path, *, task_id, method, view, seed, graph, release_hash,
                      knowledge_hash, draft_hash, config_hash, status="ok", trajectory=None, **metadata):
    validate_id(task_id)
    if view not in ("open", "masked") or status not in ("ok", "no_path", "crash", "resource_limit", "invalid"):
        raise ValueError("invalid view/status")
    if not isinstance(method, str) or not method or type(seed) is not int:
        raise ValueError("method must be nonempty and seed must be an integer")
    if not all(isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h)
               for h in (release_hash, knowledge_hash, draft_hash, config_hash)):
        raise ValueError("prediction requires four SHA256 hashes")
    obj = dict(metadata, schema_version=SCHEMA_VERSION, task_id=task_id, method=method,
               view=view, seed=seed, release_hash=release_hash, knowledge_hash=knowledge_hash,
               draft_hash=draft_hash, config_hash=config_hash, graph=normalize_graph(graph),
               status=status, trajectory=trajectory)
    write_json(path, obj)
    return obj
