"""Contract v1: concrete, typed relations; no set nodes or implicit causal PPI."""
from __future__ import annotations
import copy
import json
import re

SCHEMA_VERSION = 'path_transfer_v5.contract_v1'
KINDS = {'causal', 'state_transition', 'binding', 'dependency'}
NODE_TYPES = {'protein', 'rna', 'metabolite', 'compound', 'complex', 'phenotype'}
TIERS = {'qualified', 'provisional', 'proxy', 'synthetic'}

def canonical(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(',', ':'))

def node_key(n):
    return (n['entity'], n['taxon'], n['type'], canonical(n.get('state', {})), n.get('compartment', 'unspecified'))

def validate_graph(graph):
    if not isinstance(graph, dict):
        raise ValueError('graph must be an object')
    for key in ('nodes', 'reactions', 'relations'):
        if not isinstance(graph.get(key), list):
            raise ValueError(f'missing list {key}')
    nodes, reactions = {}, {}
    for n in graph['nodes']:
        if not isinstance(n.get('id'), str) or not re.fullmatch(r'[A-Za-z0-9_.:-]+', n['id']):
            raise ValueError('illegal node identifier')
        if n['id'] in nodes or n.get('type') not in NODE_TYPES:
            raise ValueError('duplicate node or invalid type')
        if not isinstance(n.get('entity'), str) or ':' not in n['entity'] or '*' in n['entity']:
            raise ValueError('entity requires concrete namespace:identifier')
        if not isinstance(n.get('taxon'), int) or n['taxon'] < 0:
            raise ValueError('taxon must be integer (0 only for chemicals)')
        if not isinstance(n.get('state', {}), dict):
            raise ValueError('state must be explicit dictionary')
        if any(k in n for k in ('members', 'candidates', 'or')):
            raise ValueError('expand set nodes to concrete records')
        nodes[n['id']] = n
    for r in graph['reactions']:
        if r.get('id') in reactions or r.get('id') in nodes or not isinstance(r.get('id'), str):
            raise ValueError('duplicate/invalid reaction identifier')
        if not r.get('type') or not r.get('inputs') or not r.get('outputs'):
            raise ValueError('reaction requires type, inputs, outputs')
        if any(p not in nodes for p in r['inputs'] + r['outputs']):
            raise ValueError('unknown reaction participant')
        reactions[r['id']] = r
    seen = set()
    for e in graph['relations']:
        if not isinstance(e.get('id'), str) or e['id'] in seen:
            raise ValueError('duplicate/invalid relation id')
        seen.add(e['id'])
        if e.get('kind') not in KINDS or e.get('sign') not in ('+', '-', 'unknown', 'neutral'):
            raise ValueError('invalid kind or sign; unknown is literal, never wildcard')
        if e.get('source') not in nodes:
            raise ValueError('unknown source')
        if e['kind'] == 'dependency':
            if e.get('target') not in reactions or not e.get('role') or e.get('necessary') is not True:
                raise ValueError('dependency needs reaction target, role and necessary=true')
        elif e.get('target') not in nodes:
            raise ValueError('unknown target')
        if e['kind'] in ('causal', 'state_transition') and e.get('reaction_id') not in reactions:
            raise ValueError('causal/state relation needs concrete reaction')
        if e['kind'] in ('causal', 'state_transition'):
            rx = reactions[e['reaction_id']]
            if e['source'] not in rx['inputs'] or e['target'] not in rx['outputs']:
                raise ValueError('main relation must match reaction inputs/outputs')
        if e.get('reaction_id') and e['reaction_id'] not in reactions:
            raise ValueError('unknown reaction_id')
        if any(k in e for k in ('children', 'evaluation_relations', 'candidates')):
            raise ValueError('normalize explicit refinement to fixed evaluation layer before export')
        if not isinstance(e.get('choices', {}), dict) or any(not isinstance(v, str) for v in e.get('choices', {}).values()):
            raise ValueError('choices are group:string assignments')
    return graph

def reaction_key(r, nodes):
    return (r['type'], tuple(sorted(node_key(nodes[x]) for x in r['inputs'])),
            tuple(sorted(node_key(nodes[x]) for x in r['outputs'])),
            r.get('compartment', 'unspecified'), canonical(r.get('conditions', {})))

def relation_key(e, graph):
    nodes = {n['id']: n for n in graph['nodes']}
    reactions = {r['id']: r for r in graph['reactions']}
    src = node_key(nodes[e['source']])
    if e['kind'] == 'dependency':
        return ('dependency', src, reaction_key(reactions[e['target']], nodes), e['role'], True)
    dst = node_key(nodes[e['target']])
    if e['kind'] == 'binding':
        src, dst = sorted((src, dst))
    rx = reaction_key(reactions[e['reaction_id']], nodes) if e.get('reaction_id') else None
    return (e['kind'], src, dst, e['sign'], rx)

def normalize_graph(graph):
    validate_graph(graph)
    out = copy.deepcopy(graph)
    # Distinct alternatives retained for global matching; count ignores duplicate science.
    found, relations = set(), []
    for e in out['relations']:
        key = (relation_key(e, out), canonical(e.get('choices', {})))
        if key not in found:
            relations.append(e)
            found.add(key)
    out['relations'] = relations
    return out

def relation_counts(graph):
    validate_graph(graph)
    main, side = set(), set()
    nodes = {n['id']: n for n in graph['nodes']}
    reactions = {r['id']: r for r in graph['reactions']}
    # Explicit dependency duplicates of a main participant of that reaction are free.
    participants = set()
    for e in graph['relations']:
        if e['kind'] != 'dependency':
            main.add(relation_key(e, graph))
            if e.get('reaction_id'):
                participants.add((node_key(nodes[e['source']]), reaction_key(reactions[e['reaction_id']], nodes)))
                participants.add((node_key(nodes[e['target']]), reaction_key(reactions[e['reaction_id']], nodes)))
    for e in graph['relations']:
        if e['kind'] == 'dependency':
            k = relation_key(e, graph)
            if (k[1], k[2]) not in participants:
                side.add(k[:3])
    return {'backbone': len(main), 'side': len(side), 'total': len(main) + len(side)}

def validate_task(task):
    required = ('task_id', 'mechanism_group_id', 'qualification', 'source_taxon', 'source_context',
                'human_context', 'perturbation', 'human_start', 'human_endpoint', 'endpoint_type', 'evaluation_level')
    if task.get('schema_version') != SCHEMA_VERSION or any(k not in task for k in required):
        raise ValueError('incomplete task or unsupported schema')
    if task['qualification'] not in TIERS or task['source_taxon'].get('taxon_id') not in (10090, 9544, 9541):
        raise ValueError('unaccepted tier/source species; explicitly revise taxon allowlist for new monkey species')
    if not task['source_taxon'].get('scientific_name'):
        raise ValueError('source scientific name required')
    if task['human_endpoint']['type'] != task['endpoint_type']:
        raise ValueError('fixed endpoint type mismatch')
    return task


def admission_status(task, source_provenance, reference_evidence, adjudication):
    """Fail closed for main eligibility; automation is not independent peer review."""
    reasons=[]
    source_records=source_provenance.get('records',[])
    if not source_records: reasons.append('missing_source_experiments')
    for r in source_records:
        if r.get('origin') in ('orthology_projection','database_inferred','human_to_animal_projection'):
            reasons.append('projected_source_not_native_evidence')
        if task['source_taxon']['taxon_id'] not in r.get('protein_taxa',[]):
            reasons.append('source_protein_species_unverified')
        if not r.get('locator') or not r.get('url'):
            reasons.append('source_original_location_missing')
    if reference_evidence.get('whole_chain_confirmation')!='confirmed' or not reference_evidence.get('necessary_conditions_complete'):
        reasons.append('human_chain_or_members_pending')
    if not reference_evidence.get('records'):reasons.append('human_evidence_missing')
    reviewer=adjudication.get('reviewer')
    if (not adjudication.get('independent_review') or not reviewer or reviewer==adjudication.get('curator') or
            adjudication.get('final_status')!='approved'):
        reasons.append('independent_review_missing')
    return dict(qualified=not reasons,reasons=sorted(set(reasons)),
                status='qualified' if not reasons else 'provisional')
