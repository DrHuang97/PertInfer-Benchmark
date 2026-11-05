"""Independent benchmark acceptance tests. Synthetic truth never biological evidence."""
import copy
import json
from pathlib import Path
import pytest
from pertinfer_benchmark.schema import validate_graph, normalize_graph, relation_counts, node_key, admission_status
from pertinfer_benchmark.io import read_json, write_json, public_path, load_public_task, content_hash, export_prediction
from pertinfer_benchmark.evaluate import score_graph, match_chain, summarize
from pertinfer_benchmark.views import build_view, KnowledgeGateway, grouped_splits
from pertinfer_benchmark.freeze import freeze_release, verify_release, freeze_predictions, verify_predictions, export_public_workspace

FIX=Path(__file__).parent/'fixtures/graph.json'
@pytest.fixture
def g():return copy.deepcopy(read_json(FIX)['graph'])

def ref(g):return {'chains':[{'chain_id':'one','variants':[g]}]}

def test_fixture_and_counts(g):
    assert score_graph(g,ref(g))['status']=='contained'
    assert relation_counts(g)==dict(backbone=2,side=1,total=3)

def test_necessary_branch_and_not_from_root(g):
    missing=copy.deepcopy(g);missing['relations']=missing['relations'][:2]
    assert score_graph(missing,ref(g))['status']=='not_contained'
    assert not any(e['target']=='C' for e in g['relations'])
    assert score_graph(g,ref(g))['status']=='contained'

def test_and_missing_or_branch_exclusive(g):
    # A chain cannot be assembled from two mutually exclusive realizations.
    g['relations'][0]['choices']={'mapping':'first'}
    g['relations'][1]['choices']={'mapping':'second'}
    target=copy.deepcopy(g)
    for e in target['relations']:e.pop('choices',None)
    assert score_graph(g,ref(target))['status']=='not_contained'
    g['relations'][1]['choices']={'mapping':'first'}
    assert score_graph(g,ref(target))['status']=='contained'

def test_multi_chain_and_equivalent_variant(g):
    wrong=copy.deepcopy(g);wrong['relations'][0]['sign']='-'
    refs={'chains':[{'chain_id':'one','variants':[g]},{'chain_id':'two','variants':[wrong]}]}
    assert score_graph(g,refs)['status']=='not_contained'
    refs['chains'][1]['variants'].append(g)
    assert score_graph(g,refs)['status']=='contained'
    assert score_graph(g,{'chains':[]})['status']=='not_contained'
    assert score_graph(g,ref({'nodes':[],'relations':[],'reactions':[]}))['status']=='not_contained'

def test_sign_unknown_no_wildcard(g):
    pred=copy.deepcopy(g);pred['relations'][0]['sign']='unknown'
    assert score_graph(pred,ref(g))['status']=='not_contained'
    pred['relations'].append(dict(g['relations'][0],id='plus'))
    assert score_graph(pred,ref(g))['status']=='contained'
    assert relation_counts(pred)['total']==4

def test_endpoint_rna_activity_metabolite_not_interchangeable(g):
    for typ in ('rna','metabolite'):
        pred=copy.deepcopy(g);pred['nodes'][2]['type']=typ
        assert score_graph(pred,ref(g))['status']=='not_contained'
    pred=copy.deepcopy(g);pred['nodes'][2]['state']={'activity':'inactive'}
    assert score_graph(pred,ref(g))['status']=='not_contained'

def test_reaction_and_ids_are_semantic(g):
    renamed=copy.deepcopy(g)
    for e in renamed['relations']:e['id']='renamed_'+e['id']
    for n in renamed['nodes']:n['id']='x_'+n['id']
    for rx in renamed['reactions']:
        rx['inputs']=['x_'+x for x in rx['inputs']];rx['outputs']=['x_'+x for x in rx['outputs']]
    for e in renamed['relations']:
        e['source']='x_'+e['source']
        if e['kind']!='dependency':e['target']='x_'+e['target']
    assert score_graph(renamed,ref(g))['status']=='contained'

def test_duplicate_count_and_member_already_main(g):
    g['relations'].append(dict(g['relations'][0],id='duplicate'))
    g['relations'].append(dict(id='self_dependency',kind='dependency',source='A',target='r2',role='input',sign='neutral',necessary=True))
    assert relation_counts(g)['total']==3
    assert len(normalize_graph(g)['relations'])==4

def test_same_member_two_reactions_and_candidate_expansion(g):
    g['relations'].append(dict(g['relations'][2],id='d2',target='r1'))
    assert relation_counts(g)['side']==2
    alt=copy.deepcopy(g['nodes'][3]);alt.update(id='C2',entity='fixture:C2');g['nodes'].append(alt)
    g['relations'].append(dict(g['relations'][2],id='d3',source='C2'))
    assert relation_counts(g)['total']==5

def test_binding_is_undirected_not_causal(g):
    pred=copy.deepcopy(g);pred['relations'][0].update(kind='binding',sign='neutral')
    assert score_graph(pred,ref(g))['status']=='not_contained'
    assert relation_counts(pred)['total']==3

def test_atp_cannot_supply_backbone(g):
    # A side dependency cannot replace a causal edge even with same labels.
    pred=copy.deepcopy(g);pred['relations']=pred['relations'][1:]
    assert score_graph(pred,ref(g))['status']=='not_contained'

def test_invalid_identifiers_sets_and_refinement(g):
    for patch in ({'entity':'*'},{'id':'../bad'},{'members':['S','A']}):
        bad=copy.deepcopy(g);bad['nodes'][0].update(patch)
        with pytest.raises(ValueError):validate_graph(bad)
    bad=copy.deepcopy(g);bad['relations'][0]['evaluation_relations']=[]
    with pytest.raises(ValueError):validate_graph(bad)
    bad=copy.deepcopy(g);bad['relations'][0]['source']='T'
    with pytest.raises(ValueError):validate_graph(bad)

def test_timeout_retains_denominator(g):
    r=score_graph(g,ref(g),max_states=0)
    assert r['status']=='unresolved' and (r['lower'],r['upper'])==(0,1)
    rows=[dict(r,task_id='x',method='m',view='open',qualification='synthetic')]
    s=summarize(rows)[0];assert s['n_tasks']==1 and s['C_lower']==0 and s['C_upper']==1

def test_host_species_and_projected_source_rejected():
    task={'source_taxon':{'taxon_id':10090}}
    source={'records':[{'host_taxon':9606,'protein_taxa':[9606],'origin':'human_to_animal_projection','url':'x','locator':{'figure':'1'}}]}
    result=admission_status(task,source,{'records':[]},{})
    assert not result['qualified'] and 'projected_source_not_native_evidence' in result['reasons']
    # Native animal proteins can be experimentally studied in a human host;
    # the species are represented separately, host alone cannot establish identity.
    source['records'][0].update(protein_taxa=[10090],origin='original_experiment')
    r=admission_status(task,source,{'records':[]},{})
    assert 'source_protein_species_unverified' not in r['reasons']

def test_no_self_review_upgrade():
    task={'source_taxon':{'taxon_id':10090}}
    source={'records':[{'protein_taxa':[10090],'url':'x','locator':{'figure':'1'}}]}
    human={'records':[{}],'whole_chain_confirmation':'confirmed','necessary_conditions_complete':True}
    assert not admission_status(task,source,human,dict(independent_review=True,reviewer='same_model',curator='same_model',final_status='approved'))['qualified']

def test_lineage_closure_all_channels_and_cross_tasks(tmp_path):
    rs=[dict(record_id='paper:answer',evidence_ids=['paper:shared'],ancestors=[],aliases=['doi:alias'],channel='candidate'),
        dict(record_id='cache',evidence_ids=[],ancestors=['doi:alias'],channel='cache'),
        dict(record_id='etna',evidence_ids=[],ancestors=['cache'],channel='etna'),
        dict(record_id='structure',evidence_ids=['paper:shared'],channel='structure'),
        dict(record_id='safe',evidence_ids=['animal:approved'],channel='source_excerpt')]
    m=build_view(rs,['paper:answer'],view='masked',output=tmp_path/'views/masked')
    assert m['records']==1 and len(m['removals'])==4
    gateway=KnowledgeGateway(tmp_path,'masked',tmp_path/'access.jsonl')
    assert gateway.search('safe')[0]['record_id']=='safe'
    for rid in ('paper:answer','doi:alias','https://example.com/full-paper','cache','etna','structure'):
        with pytest.raises(PermissionError):gateway.fetch(rid)
    assert len((tmp_path/'access.jsonl').read_text().splitlines())==7

def test_public_path_denies_private_symlinks(tmp_path):
    (tmp_path/'private').mkdir();(tmp_path/'private/secret').write_text('hidden')
    (tmp_path/'public').mkdir();(tmp_path/'public/link').symlink_to(tmp_path/'private/secret')
    for path in ('private/secret','public/../private/secret','public/link','../escape'):
        with pytest.raises((PermissionError,ValueError)):public_path(tmp_path,path)

def test_group_transitive_paper_overlap_no_test_leak():
    tasks=[dict(task_id='a',mechanism_group_id='m1',group_links=['p1']),dict(task_id='b',mechanism_group_id='m2',group_links=['p1','p2']),dict(task_id='c',mechanism_group_id='m3',group_links=['p2'])]
    s=grouped_splits(tasks,exposed_groups=['m1'])
    assert len(s['groups'])==1 and set(s['assignments'].values())=={'development'} and s['test']==[]

def test_release_and_prediction_hash_tamper(tmp_path,g):
    release=tmp_path/'release';release.mkdir();write_json(release/'item.json',{'one':1})
    m=freeze_release(release);assert verify_release(release)['release_hash']==m['release_hash']
    write_json(release/'item.json',{'one':2})
    with pytest.raises(ValueError):verify_release(release)
    proot=tmp_path/'predictions';write_json(proot/'one.json',{'task_id':'x','graph':g,'method':'fixture','view':'open','seed':0,'schema_version':'fixture'})
    pm=freeze_predictions(proot,['x']);assert verify_predictions(proot)['prediction_hash']==pm['prediction_hash']
    write_json(proot/'one.json',{'task_id':'x','graph':{}})
    with pytest.raises(ValueError):verify_predictions(proot)

def test_intended_task_means_tiers_separate():
    rows=[]
    for tier in ('qualified','provisional','proxy','synthetic'):
        for seed in (0,1,2):rows.append(dict(task_id='x',method='m',view='open',qualification=tier,status='contained',lower=1,upper=1,counts={'total':3}))
    summaries=summarize(rows)
    assert len(summaries)==4 and all(s['n_tasks']==1 and s['n_runs']==3 for s in summaries)
