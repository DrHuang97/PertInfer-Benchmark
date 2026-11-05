"""Evidence-lineage views and an offline retrieval gateway, public only at run time."""
from __future__ import annotations
import json
from pathlib import Path
from .io import content_hash, write_json, public_path


def build_view(records, blocked_ids, *, view, output, versions=None):
    if view not in ('open', 'masked'):
        raise ValueError('unknown view')
    blocked = set(blocked_ids) if view == 'masked' else set()
    # Undirected equivalence/derivation closure: aliases, caches, annotations and ETNA
    # records must be blocked even when only one version initially names a paper.
    closure = set(blocked)
    changed = True
    while changed:
        changed = False
        for r in records:
            family = {r['record_id'], *r.get('evidence_ids', []), *r.get('ancestors', []), *r.get('aliases', [])}
            if family & closure and not family <= closure:
                closure.update(family)
                changed = True
    kept, removed = [], []
    for r in records:
        family = {r['record_id'], *r.get('evidence_ids', []), *r.get('ancestors', []), *r.get('aliases', [])}
        if family & closure:
            removed.append({'record_id':r['record_id'], 'reason':'test-reference-lineage', 'channel':r.get('channel')})
        else:
            kept.append(r)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    text = ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in kept)
    (output/'knowledge.jsonl').write_text(text)
    manifest = dict(view=view, knowledge_hash=content_hash(kept), records=len(kept),
                    blocked_ids=sorted(closure), removals=removed, versions=versions or {},
                    rules='lineage closure before candidate/cache/ETNA/structure use; offline retrieval only',
                    residual_pretraining_exposure=True, os_isolation=False)
    write_json(output/'manifest.json', manifest)
    return manifest


class KnowledgeGateway:
    def __init__(self, root, view, log_path):
        self.root, self.view, self.log_path = Path(root), view, Path(log_path)
        if view not in ('open','masked'):
            raise ValueError('unknown view')
        self.manifest = json.loads(public_path(root, f'views/{view}/manifest.json').read_text())
        self.records = [json.loads(x) for x in public_path(root, f'views/{view}/knowledge.jsonl').read_text().splitlines() if x]
        if content_hash(self.records) != self.manifest['knowledge_hash']:
            raise ValueError('knowledge hash mismatch')
    def search(self, query, limit=10):
        if not isinstance(query,str) or not 0 < limit <= 100:
            raise ValueError('invalid query/limit')
        words = query.lower().split()
        result = [r for r in self.records if any(w in json.dumps(r).lower() for w in words)][:limit]
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open('a') as f:
            f.write(json.dumps(dict(view=self.view,query=query,returned=[r['record_id'] for r in result],
                                    knowledge_hash=self.manifest['knowledge_hash']))+'\n')
        return result
    def fetch(self, record_id):
        found = [r for r in self.records if r['record_id']==record_id]
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open('a') as f:
            f.write(json.dumps(dict(view=self.view,fetch=record_id,allowed=bool(found)))+'\n')
        if not found:
            raise PermissionError('record outside frozen view; raw papers and arbitrary URLs unavailable')
        return found[0]


def grouped_splits(tasks, *, exposed_groups=()):
    """Connected closure of mechanism/papers/experiments/overlap tokens; all pilot here."""
    components = []
    for task in tasks:
        tokens = {task['mechanism_group_id'], *task.get('group_links', [])}
        members = {task['task_id']}
        matches = [c for c in components if c[0] & tokens]
        for c in matches:
            tokens |= c[0]; members |= c[1]; components.remove(c)
        components.append((tokens,members))
    assignments, groups = {}, []
    for i, (tokens, ids) in enumerate(components):
        split = 'development' if tokens & set(exposed_groups) else 'feasibility_pilot'
        for task_id in ids:
            assignments[task_id] = split
        groups.append(dict(group=f'closure_{i}', task_ids=sorted(ids), tokens=sorted(tokens), split=split))
    return dict(assignments=assignments, groups=groups, test=[], policy='qualification before split; no unseen test claims',
                legacy_v4='all eight legacy tasks permanently development/exposed; not imported')
