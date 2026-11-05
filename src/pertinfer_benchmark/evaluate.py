"""Private evaluator. Run only after predictions are frozen; never imported by methods."""
from __future__ import annotations
import time
from collections import defaultdict
from .schema import validate_graph, relation_key, relation_counts


def match_chain(prediction, reference, *, max_states=100000, timeout_s=5.0):
    validate_graph(prediction)
    validate_graph(reference)
    if not reference['relations']:
        return 'not_contained'
    index = defaultdict(list)
    for edge in prediction['relations']:
        index[relation_key(edge, prediction)].append(edge)
    options = [index.get(relation_key(e, reference), []) for e in reference['relations']]
    if any(not x for x in options):
        return 'not_contained'
    options.sort(key=len)
    deadline = time.monotonic() + timeout_s
    states = 0
    def visit(i, assignments):
        nonlocal states
        states += 1
        if states > max_states or time.monotonic() > deadline:
            raise TimeoutError
        if i == len(options):
            return True
        for e in options[i]:
            choices = e.get('choices', {})
            if all(k not in assignments or assignments[k] == v for k, v in choices.items()):
                if visit(i + 1, dict(assignments, **choices)):
                    return True
        return False
    try:
        return 'contained' if visit(0, {}) else 'not_contained'
    except (TimeoutError, RecursionError):
        return 'unresolved'


def score_graph(graph, references, *, max_states=100000, timeout_s=5.0):
    validate_graph(graph)
    outcomes = []
    for chain in references.get('chains', []):
        variants = [match_chain(graph, v, max_states=max_states, timeout_s=timeout_s) for v in chain['variants']]
        outcome = ('contained' if 'contained' in variants else
                   'unresolved' if 'unresolved' in variants else 'not_contained')
        outcomes.append({'chain_id': chain['chain_id'], 'status': outcome})
    statuses = [x['status'] for x in outcomes]
    status = ('not_contained' if not statuses or 'not_contained' in statuses else
              'unresolved' if 'unresolved' in statuses else 'contained')
    return dict(status=status, chains=outcomes, counts=relation_counts(graph),
                lower=int(status == 'contained'), upper=int(status != 'not_contained'))


def summarize(rows):
    """Do not mix tiers; task runs aggregate within each method/view/qualification."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row['method'], row['view'], row['qualification'])].append(row)
    results = []
    for (method, view, tier), runs in sorted(grouped.items()):
        tasks = defaultdict(list)
        for r in runs:
            tasks[r['task_id']].append(r)
        means = []
        for task_id, rs in sorted(tasks.items()):
            means.append(dict(task_id=task_id, lower=sum(r['lower'] for r in rs)/len(rs),
                              upper=sum(r['upper'] for r in rs)/len(rs),
                              M=sum(r['counts']['total'] for r in rs)/len(rs)))
        n = len(means)
        results.append(dict(method=method, view=view, qualification=tier, n_tasks=n,
                            n_runs=len(runs), unresolved=sum(r['status']=='unresolved' for r in runs),
                            C_lower=sum(r['lower'] for r in means)/n,
                            C_upper=sum(r['upper'] for r in means)/n,
                            M=sum(r['M'] for r in means)/n, task_means=means,
                            inference='feasibility only; no independent biological test sample'))
    return results
