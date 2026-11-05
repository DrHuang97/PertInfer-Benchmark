"""Reference eligibility and aggregation rules from the v5.7 scorer."""

from collections import defaultdict

from .schema import relation_counts

from .tasks import validate_fixed_boundaries

from .evaluate import score_graph

def score_one(prediction,task,policy,references,max_states=100000):
    """Null C is deliberate for missing biological reference, including failed runs."""
    eligible=policy['policy']=='provisional_abstract_chain'
    if eligible and not references.get('chains'):
        raise ValueError('Dataset error: eligible task has no reference; this is not a method failure')
    if eligible and any(not c.get('chain_id') or not c.get('variants') for c in references['chains']):
        raise ValueError('Dataset error: malformed reference metadata')
    result=dict(status=prediction.get('status','missing'),lower=0 if eligible else None,
                upper=0 if eligible else None,counts={'backbone':0,'side':0,'total':0},
                scoring_eligible=eligible,reference_policy=policy['policy'])
    try:
        graph=prediction['graph']
        result['counts']=relation_counts(graph)
        # no_path/abstention graphs can be empty; their failures stay in denominator.
        if prediction.get('status')=='ok':
            validate_fixed_boundaries(task,graph)
            if eligible:
                result.update(score_graph(graph,references,max_states=max_states))
            else:result['status']='not_scored_reference_incomplete'
    except (ValueError,KeyError,TypeError,AttributeError,IndexError,RecursionError) as exc:
        result.update(status='invalid',error=str(exc))
    if not eligible:
        result.update(lower=None,upper=None,scoring_status='not_scored_reference_incomplete')
    return result

def summarize_rows(rows):
    groups=defaultdict(list)
    fields=['method','view','source_taxon','scope','qualification','previously_exposed','mechanism_group_previously_exposed']
    for r in rows:groups[tuple(r[k] for k in fields)].append(r)
    output=[]
    for key,rs in sorted(groups.items(),key=lambda x:str(x[0])):
        valid=[r for r in rs if r['scoring_eligible']]
        tasks=defaultdict(list)
        for r in rs:tasks[r['task_id']].append(r)
        means=[dict(task_id=tid,eligible=tr[0]['scoring_eligible'],
            lower=sum(r['lower'] for r in tr)/len(tr) if tr[0]['scoring_eligible'] else None,
            upper=sum(r['upper'] for r in tr)/len(tr) if tr[0]['scoring_eligible'] else None,
            M=sum(r['counts']['total'] for r in tr)/len(tr)) for tid,tr in tasks.items()]
        eligible_means=[t for t in means if t['eligible']]
        output.append(dict(zip(fields,key),runs=len(rs),n_tasks=len(tasks),C_denominator=len(eligible_means),C_run_denominator=len(valid),
            reference_incomplete_runs=len(rs)-len(valid),
            C_lower=sum(t['lower'] for t in eligible_means)/len(eligible_means) if eligible_means else None,
            C_upper=sum(t['upper'] for t in eligible_means)/len(eligible_means) if eligible_means else None,
            M_all=sum(t['M'] for t in means)/len(means),
            M_C_eligible=sum(t['M'] for t in eligible_means)/len(eligible_means) if eligible_means else None,
            aggregation='Mean within task over preregistered repeats, then equal-weight mean across tasks',
            failed_or_missing=sum(r['status'] not in ('contained','not_contained','unresolved','ok','not_scored_reference_incomplete') for r in rs)))
    return output
