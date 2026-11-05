"""Public task validation adapted from the v5.7 multi-species policy."""

import re

from .schema import SCHEMA_VERSION, TIERS, validate_graph, node_key

POLICY='path_transfer_v5.multispecies_v57'

TAXA={10090:'Mus musculus',10116:'Rattus norvegicus',10114:'Rattus',9615:'Canis lupus familiaris',
      9541:'Macaca fascicularis',9544:'Macaca mulatta',9483:'Callithrix jacchus',9555:'Papio anubis',
      9823:'Sus scrofa',9986:'Oryctolagus cuniculus',10141:'Cavia porcellus',
      10036:'Mesocricetus auratus',7955:'Danio rerio',9669:'Mustela putorius furo'}

def validate_task(task):
 required=('task_id','mechanism_group_id','qualification','source_taxon','source_context','human_context',
           'perturbation','human_start','human_endpoint','endpoint_type','evaluation_level')
 if task.get('schema_version')!=SCHEMA_VERSION or any(k not in task for k in required):raise ValueError('incomplete graph-contract task')
 if not re.fullmatch(r'[A-Za-z0-9_.:-]+',task['task_id']):raise ValueError('invalid task ID')
 if task['qualification'] not in TIERS:raise ValueError('invalid qualification')
 tax=task['source_taxon'].get('taxon_id')
 if tax not in TAXA:raise ValueError('source taxon outside versioned allowlist')
 if not task['source_taxon'].get('scientific_name'):raise ValueError('missing source name')
 if task['source_taxon']['scientific_name']!=TAXA[tax]:raise ValueError('source scientific name does not match declared taxon')
 if tax==10114 and task['source_taxon'].get('resolution')!='genus':raise ValueError('unresolved rat must remain genus level')
 if task['human_endpoint']['type']!=task['endpoint_type']:raise ValueError('endpoint type mismatch')
 if task['human_context'].get('host_taxon',9606)!=9606:raise ValueError('target is not human host')
 if task.get('taxon_policy')==POLICY:
  if task.get('human_response_direction')!='not_given':raise ValueError('public human response direction leak')
  for n in [task['human_start'],task['human_endpoint']]:
   if any(k in n.get('state',{}) for k in ['response','direction','change','fold_change','observed_response']):raise ValueError('response must not be public endpoint identity')
 return task

def causal_path(graph,start,end):
 pending=[start];seen={start}
 while pending:
  n=pending.pop()
  if n==end:return True
  for e in graph['relations']:
   if e['kind'] in ['causal','state_transition'] and e['source']==n and e['target'] not in seen:
    seen.add(e['target']);pending.append(e['target'])
 return False

def validate_fixed_boundaries(task,graph):
 """Human predictions retain the declared chemical, state, compartment and assay identity."""
 validate_graph(graph)
 keys={node_key(n):n['id'] for n in graph['nodes']}
 if node_key(task['human_start']) not in keys or node_key(task['human_endpoint']) not in keys:
  raise ValueError('fixed human boundary identity/state/compartment mismatch')
 return graph
