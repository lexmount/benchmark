"""Independent-source reconstruction; no network, VM, or model."""
import ast
from copy import deepcopy
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import repair_scholar_reference as repair
HAVE_LXML = importlib.util.find_spec('lxml') is not None
UPSTREAM = Path(os.environ.get('OSWORLD_UPSTREAM_DIR', '/tmp/osworld-corpus-5123'))


def write(path, value):
    path.write_text(json.dumps(value, indent=2))


def fixture(root):
    profile = '''<div id="gsc_prf_in">Yann LeCun</div><table id="gsc_rsb_st"><tbody>
<tr><td>All</td><td>512066</td></tr><tr><td>h</td><td>178</td></tr><tr><td>i10</td><td>520</td></tr>
</tbody></table><table><tbody id="gsc_a_b"><tr><td class="gsc_a_t">
<a href="/citations?view_op=view_citation&amp;user=WLN3QrAAAAAJ&amp;citation_for_view=WLN3QrAAAAAJ:paper">Deep learning</a>
<div>Y LeCun, Y Bengio, G Hinton</div><div>nature 521 (7553), 436-444, 2015</div></td>
<td class="gsc_a_y"><span>2015</span></td></tr></tbody></table>'''
    facts = {'citation_title': 'Deep learning', 'citation_journal_title': 'Nature',
        'citation_volume': '521', 'citation_issue': '7553', 'citation_firstpage': '436',
        'citation_lastpage': '444', 'citation_doi': repair.DOI, 'citation_publication_date': '2015/05'}
    publisher = '<html><head>' + ''.join('<meta name="'+key+'" content="'+value+'">' for key, value in facts.items())
    publisher += ''.join('<meta name="citation_author" content="'+name+'">' for name in ['LeCun, Yann', 'Bengio, Yoshua', 'Hinton, Geoffrey']) + '</head></html>'
    api = {'response': {'numFound': 1, 'docs': [{'title_s': ['Deep learning'], 'authFullName_s': ['Yann Lecun', 'Yoshua Bengio', 'Geoffrey Hinton'],
        'doiId_s': repair.DOI, 'producedDateY_i': 2015, 'halId_s': 'hal-04206682',
        'uri_s': 'https://hal.science/hal-04206682v1', 'fileMain_s': 'https://hal.science/hal-04206682/document'}]}}
    (root/'profile.html').write_text(profile)
    (root/'publisher.html').write_text(publisher)
    write(root/'api.json', api)
    records = {'schema_version': 1, 'task_id': repair.TASK_ID, 'sources': {}}
    for key, name, url in [('profile','profile.html',repair.PROFILE_URL), ('publisher','publisher.html',repair.PUBLISHER_URL),
        ('hal_api','api.json','https://api.hal.science/search/?q=doiId_s%3A%2210.1038%2Fnature14539%22&wt=json')]:
        records['sources'][key] = {'url': url, 'path': name, 'sha256': repair.sha(root/name),
            'observed_at': '2026-11-17T14:00:00+00:00', 'http_status': 200, 'verified_tls': True}
    write(root/'sources.json', records)
    return root/'sources.json'


@unittest.skipUnless(HAVE_LXML, 'Requires the documented OSWorld lxml dependency')
class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = fixture(self.root)

    def change(self, key, func):
        records = repair.read(self.sources)
        item = records['sources'][key]
        path = self.root/item['path']
        func(path)
        item['sha256'] = repair.sha(path)
        write(self.sources, records)

    def test_six_fields_come_from_sources_not_historical_actor_counts(self):
        expected, identity, records = repair.expected_from_sources(self.sources)
        self.assertEqual(expected, ['Yann LeCun','512066','178','520','Deep learning','https://hal.science/hal-04206682/document'])
        self.assertFalse(identity['pdf_binary_verified'])
        self.assertEqual(identity['publisher_doi'], repair.DOI)
        self.assertEqual(set(records), {'profile','publisher','hal_api'})

    def test_profile_id_or_first_paper_identity_cannot_drift(self):
        for old, new in [('WLN3QrAAAAAJ','OtherUser'), ('Deep learning','Different paper'), ('G Hinton','G Someone')]:
            with self.subTest(change=new):
                fixture(self.root)
                self.change('profile',lambda p: p.write_text(p.read_text().replace(old,new)))
                with self.assertRaises(ValueError): repair.expected_from_sources(self.sources)

    def test_missing_profile_or_verification_page_is_not_a_reference(self):
        self.change('profile',lambda p:p.write_text('<html><title>Verifying...</title></html>'))
        with self.assertRaises(ValueError): repair.expected_from_sources(self.sources)

    def test_publisher_must_match_doi_and_all_authors(self):
        for old,new in [(repair.DOI,'10.0000/wrong'), ('LeCun, Yann','Other, Person')]:
            with self.subTest(change=new):
                fixture(self.root)
                self.change('publisher',lambda p:p.write_text(p.read_text().replace(old,new)))
                with self.assertRaises(ValueError): repair.expected_from_sources(self.sources)

    def test_hal_lookup_must_be_doi_based_not_an_actor_id(self):
        records=repair.read(self.sources)
        records['sources']['hal_api']['url']='https://api.hal.science/search/?q=halId_s:hal-04206682&wt=json'
        write(self.sources,records)
        with self.assertRaises(ValueError): repair.expected_from_sources(self.sources)

    def test_hal_must_be_unambiguous_and_same_paper(self):
        for kind in ('ambiguous','boolean_count','doi','year','author','title','external_pdf'):
            with self.subTest(kind=kind):
                fixture(self.root)
                def mutate(path):
                    api=repair.read(path);doc=api['response']['docs'][0]
                    if kind=='ambiguous':api['response']['numFound']=2
                    elif kind=='boolean_count':api['response']['numFound']=True
                    elif kind=='doi':doc['doiId_s']='10.0000/other'
                    elif kind=='year':doc['producedDateY_i']=2016
                    elif kind=='author':doc['authFullName_s'][0]='Another Author'
                    elif kind=='title':doc['title_s']=['Other paper']
                    else:doc['fileMain_s']='https://untrusted.example/paper.pdf'
                    write(path,api)
                self.change('hal_api',mutate)
                with self.assertRaises(ValueError):repair.expected_from_sources(self.sources)

    def test_source_hash_tls_http_and_timestamp_are_required(self):
        for key,value in [('sha256','0'*64),('verified_tls',False),('http_status',True),('observed_at','2026-11-17T14:00:00')]:
            with self.subTest(field=key):
                fixture(self.root);records=repair.read(self.sources);records['sources']['profile'][key]=value;write(self.sources,records)
                with self.assertRaises(ValueError):repair.expected_from_sources(self.sources)


@unittest.skipUnless(HAVE_LXML and (UPSTREAM/'desktop_env/evaluators/metrics/general.py').is_file(), 'Requires documented lxml and OSWORLD_UPSTREAM_DIR')
class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.run=self.root/'run';self.run.mkdir();write(self.run/'run.json',{'frozen':True})
        self.sources=fixture(self.root)
        self.original=self.run/'receipt.json';write(self.original,{'task_sha256':'task-sha','score':None})
        self.actual=self.run/'researchers.xlsx';self.actual.write_bytes(b'retained-original-cache')
        self.task={'evaluator':{'options':deepcopy(repair.OPTIONS)}}
        self.metadata={'osworld_root':str(UPSTREAM)}
        self.binding={'kind':'retained_original_result_getter_cache_reparsed_with_original_pandas_semantics','actual_sha256':repair.sha(self.actual)}
        metric_path=UPSTREAM/'desktop_env/evaluators/metrics/general.py'
        node=next(n for n in ast.parse(metric_path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='literal_match')
        node.returns=None
        for arg in node.args.args:arg.annotation=None
        namespace={};exec(compile(ast.Module(body=[node],type_ignores=[]),str(metric_path),'exec'),namespace)
        self.metric=namespace['literal_match'];self.metric_path=metric_path
        self.expected=repair.expected_from_sources(self.sources)[0]
        for target,value in [('inputs',(self.metadata,self.task,self.original,self.actual,self.binding)),('_metric',(self.metric,self.metric_path)),('actual_last_row',self.expected)]:
            patcher=patch.object(repair,target,return_value=value);patcher.start();self.addCleanup(patcher.stop)

    def test_roundtrip_uses_original_literal_options_and_preserves_null(self):
        original=self.original.read_bytes();result=repair.repair(self.run,self.sources,self.root/'correction')
        self.assertEqual(result['score'],1.)
        self.assertIsNone(result['original_score'])
        self.assertFalse(result['original_ui_reference_getter_succeeded'])
        self.assertFalse(result['pdf_binary_verified'])
        self.assertEqual(self.original.read_bytes(),original)
        self.assertEqual(repair.verify_correction(self.run,self.root/'correction/correction.json'),result)

    def test_valid_source_does_not_force_a_success_when_actual_differs(self):
        with patch.object(repair,'actual_last_row',return_value=['Wrong']*6):
            result=repair.repair(self.run,self.sources,self.root/'correction')
        self.assertEqual(result['score'],0.)

    def test_boolean_score_and_edited_archived_source_are_rejected(self):
        result=repair.repair(self.run,self.sources,self.root/'correction');path=self.root/'correction/correction.json'
        wrong=deepcopy(result);wrong['score']=True;write(path,wrong)
        with self.assertRaises(ValueError):repair.verify_correction(self.run,path)
        write(path,result);(path.parent/'repair_scholar_reference.py').write_text('changed')
        with self.assertRaises(ValueError):repair.verify_correction(self.run,path)

    def test_changed_source_even_with_new_hash_cannot_change_paper(self):
        repair.repair(self.run,self.sources,self.root/'correction');path=self.root/'correction/correction.json'
        sources=repair.read(path.parent/'primary-sources.json');api=path.parent/sources['sources']['hal_api']['path'];data=repair.read(api);data['response']['docs'][0]['doiId_s']='10.0000/other';write(api,data)
        sources['sources']['hal_api']['sha256']=repair.sha(api);write(path.parent/'primary-sources.json',sources)
        record=repair.read(path);record['primary_sources_sha256']=repair.sha(path.parent/'primary-sources.json');write(path,record)
        with self.assertRaises(ValueError):repair.verify_correction(self.run,path)

    def test_fresh_output_is_required(self):
        repair.repair(self.run,self.sources,self.root/'correction')
        with self.assertRaises(FileExistsError):repair.repair(self.run,self.sources,self.root/'correction')


if __name__=='__main__':unittest.main()
