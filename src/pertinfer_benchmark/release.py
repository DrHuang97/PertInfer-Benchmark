"""Package curator-supplied tasks and references without generating mechanisms."""
from pathlib import Path

from .freeze import freeze_release
from .io import load_public_task, read_json, validate_id, write_json
from .schema import node_key, relation_counts, validate_graph
from .tasks import causal_path, validate_fixed_boundaries, validate_task
from .views import build_view, grouped_splits

SCORING_POLICIES = {"provisional_abstract_chain", "not_scored_reference_incomplete"}


def validate_reference(task, reference, policy):
    if policy not in SCORING_POLICIES:
        raise ValueError("unknown reference policy")
    if not isinstance(reference, dict) or not isinstance(reference.get("chains"), list):
        raise ValueError("reference requires a chain list")
    if policy == "provisional_abstract_chain" and not reference["chains"]:
        raise ValueError("eligible task has no reference")
    chain_ids = set()
    for chain in reference["chains"]:
        if not chain.get("chain_id") or chain["chain_id"] in chain_ids or not chain.get("variants"):
            raise ValueError("missing or duplicate reference chain/variants")
        chain_ids.add(chain["chain_id"])
        for graph in chain["variants"]:
            validate_graph(graph)
            if policy == "provisional_abstract_chain":
                validate_fixed_boundaries(task, graph)
                keys = {node_key(n): n["id"] for n in graph["nodes"]}
                if relation_counts(graph)["total"] < 2 or not causal_path(
                    graph, keys[node_key(task["human_start"])], keys[node_key(task["human_endpoint"])]
                ):
                    raise ValueError("reference must connect boundaries with a mediator or necessary participant")


def validate_contents(root):
    root = Path(root)
    policies = read_json(root / "private/scoring_eligibility.json")["tasks"]
    cohorts = read_json(root / "cohorts.json")["tasks"]
    tasks = {}
    for p in sorted((root / "public").glob("*/task.json")):
        task = validate_task(read_json(p))
        tid = validate_id(task["task_id"])
        if tid != p.parent.name or tid in tasks:
            raise ValueError("task identity/path mismatch")
        # This first extraction preserves development semantics. Independent
        # qualification requires a separately reviewed dataset release.
        if task["qualification"] not in ("provisional", "proxy", "synthetic"):
            raise ValueError("this toolkit release does not admit independently qualified datasets")
        if task.get("human_response_direction") != "not_given":
            raise ValueError("target response direction must not be supplied")
        for n in (task["human_start"], task["human_endpoint"]):
            if {"response", "direction", "change", "fold_change", "observed_response"} & set(n.get("state", {})):
                raise ValueError("human boundary contains observed response")
        source = validate_graph(read_json(p.parent / "source_graph.json"))
        ids = {n["id"] for n in source["nodes"]}
        if task.get("source_start") not in ids or task.get("source_endpoint") not in ids or not causal_path(source, task["source_start"], task["source_endpoint"]):
            raise ValueError("source graph does not connect declared boundaries")
        context = read_json(p.parent / "allowed_context.json")
        if {"ortholog_candidates", "human_graph", "candidate_graph"} & set(context):
            raise ValueError("method-generated mappings and human candidates do not belong in benchmark inputs")
        validate_reference(task, read_json(root / "private" / tid / "reference_chains.json"), policies[tid]["policy"])
        cohort = cohorts[tid]
        if not isinstance(cohort.get("scope"), str) or not cohort["scope"]:
            raise ValueError("cohort scope missing")
        for key in ("previously_exposed", "mechanism_group_previously_exposed"):
            if key not in cohort or (cohort[key] is not None and type(cohort[key]) is not bool):
                raise ValueError("exposure must be true, false or null")
        for view in ("open", "masked"):
            bundle = load_public_task(root, tid, view)
            blocked = set(bundle["view_manifest"]["blocked_ids"])
            for row in bundle["knowledge"]:
                if {row["record_id"], *row.get("evidence_ids", []), *row.get("ancestors", []), *row.get("aliases", [])} & blocked:
                    raise ValueError("blocked evidence lineage survives")
        tasks[tid] = task
    if not tasks or set(tasks) != set(policies) or set(tasks) != set(cohorts):
        raise ValueError("empty or mismatched task/eligibility/cohort inventory")
    splits = read_json(root / "splits.json")
    if set(splits["assignments"]) != set(tasks):
        raise ValueError("split/task inventory mismatch")
    for group in grouped_splits(list(tasks.values()))["groups"]:
        if len({splits["assignments"][tid] for tid in group["task_ids"]}) != 1:
            raise ValueError("related tasks split across partitions")
    return tasks


def build_release(spec, destination):
    """Copy explicit curator definitions into a new, separately sealed release."""
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=False)
    tasks, cohorts, policies = [], {}, {}
    for entry in spec["tasks"]:
        task = validate_task(entry["task"])
        tid = validate_id(task["task_id"])
        if tid in cohorts:
            raise ValueError("duplicate task ID")
        for name in ("task", "source_graph", "source_provenance", "allowed_context"):
            write_json(root / "public" / tid / f"{name}.json", entry[name])
        for name in ("reference_chains", "reference_evidence", "adjudication"):
            write_json(root / "private" / tid / f"{name}.json", entry[name])
        cohorts[tid] = entry["cohort"]
        policies[tid] = entry["scoring_policy"]
        tasks.append(task)
    write_json(root / "private/scoring_eligibility.json", {"tasks": policies})
    write_json(root / "cohorts.json", {"tasks": cohorts})
    write_json(root / "splits.json", grouped_splits(tasks, exposed_groups=spec.get("exposed_groups", [])))
    for view in ("open", "masked"):
        build_view(spec.get("knowledge", []), spec.get("blocked_ids", []), view=view,
                   output=root / "views" / view, versions=spec.get("versions", {}))
    write_json(root / "dataset_metadata.json", spec.get("metadata", {}))
    validate_contents(root)
    return freeze_release(root)
