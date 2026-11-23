from copy import deepcopy
from io import BytesIO
import base64
import hashlib
import json
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.brand_protection_sources import BrandProtectionSources,Budget
from xti.adapters.brand_protection_page import capture_page,PageParser
from xti.domain.brand_protection import identity,scope,validate_visual,compare_visual
from xti.domain.assets import ValidationError
from tests.test_content_monitoring import Scanner


class HTTP:
    def __init__(self,values):self.values=values;self.calls=[]
    def get(self,url,**kwargs):
        self.calls.append(url)
        value=self.values.get(url,{'status':'not_found','body':b''})
        return {**value,'attempts':[{'http_status':200 if value['status']=='complete' else 404}]}


def html(text):return {'status':'complete','body':('<html><title>Example Corp</title><body>'+text+'</body></html>').encode(),'content_type':'text/html'}


def renderer(*args,**kwargs):return {'status':'not_installed'}


class ProtectionSourceTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.path=Path(temporary.name)/'xti.db';SQLiteAssetRepository(self.path).initialize()
        self.brand=identity({'name':'Example Corp','domains':['example.com']})
        self.scope=scope({'identity_id':'00000000-0000-0000-0000-000000000001','sources':['web'],'urls':['https://candidate.example/']})
    def source(self,values,**kwargs):
        self.http=HTTP(values)
        return BrandProtectionSources(self.path,Scanner(),http=self.http,renderer=renderer,**kwargs)
    def test_source_parses_domains_with_existing_crt_parser(self):
        source=self.source({})
        data=[{'id':123,'name_value':'login.example.com\n*.help.example.com','entry_timestamp':'2026-11-21T00:00:00','common_name':'example.com'}]
        from xti.adapters.crtsh import CrtShSource
        self.http.values[CrtShSource().search_url('%example%')]={'status':'complete','body':json.dumps(data).encode()}
        rows,report=source._domains('crt.sh',self.brand,Budget(self.http,self.scope),20)
        self.assertEqual({r['url'] for r in rows},{'https://login.example.com/','https://help.example.com/'})
        self.assertTrue(report['window_only'])
    def test_text_and_form_signals_are_public_evidence_without_submission(self):
        source=self.source({'https://example.com/':html('Example Corp'), 'https://candidate.example/':html('<form action="https://other.example/submit"><input type="password"></form>Example Corp\nsynthetic-secret')})
        result=source.collect({'brand':self.brand,'scope':self.scope},[],cancelled=lambda:False)
        row=result['candidates'][0]
        self.assertEqual(row['password_fields'],1);self.assertTrue(row['cross_domain_form'])
        self.assertNotIn('synthetic-secret',repr(row));self.assertIn('MASKELENDİ',row['text'])
        self.assertFalse(any('/submit' in u for u in self.http.calls));self.assertEqual(result['status'],'partial')
    def test_unsafe_url_is_dropped_not_replaced_with_a_different_identity(self):
        url='https://candidate.example/synthetic-secret'
        source=self.source({'https://example.com/':html('Example Corp'),url:html('Example Corp')})
        selected={**self.scope,'urls':[url]}
        result=source.collect({'brand':self.brand,'scope':selected},[],cancelled=lambda:False)
        self.assertEqual(result['candidates'],[]);self.assertTrue(result['privacy_incomplete'])
    def test_unavailable_scanner_does_not_persist_unscanned_text_or_url(self):
        source=self.source({'https://example.com/':html('Sensitive'), 'https://candidate.example/':html('Sensitive')})
        source.scanner.status=lambda:{'state':'not_installed'}
        result=source.collect({'brand':self.brand,'scope':self.scope},[],cancelled=lambda:False)
        self.assertEqual(result['candidates'],[]);self.assertEqual(result['reference']['status'],'privacy_rejected')
    def test_budget_caps_requests_and_cooldown_survives_next_budget(self):
        source=self.source({});self.http.values['https://provider.example/']={'status':'rate_limited','body':b'','retry_after_seconds':3600}
        first=Budget(self.http,{**self.scope,'max_requests':2},cooldowns=source.cooldowns)
        self.assertEqual(first.get('https://provider.example/')['status'],'rate_limited')
        second=Budget(self.http,self.scope,cooldowns=source.cooldowns)
        self.assertEqual(second.get('https://provider.example/')['status'],'cooldown');self.assertEqual(len(self.http.calls),1)
        budget=Budget(self.http,{**self.scope,'max_requests':1})
        budget.get('https://a.example/');self.assertEqual(budget.get('https://b.example/')['status'],'budget_exhausted')
    def test_retained_failure_preserves_old_and_unchecked_cursor_does_not_advance(self):
        old={'kind':'page','url':'https://old.example/','title':'Old','text':'Kept','sources':['old']}
        source=self.source({'https://example.com/':html('Example Corp')})
        result=source.collect({'brand':self.brand,'scope':{**self.scope,'max_pages':1}},[old],cancelled=lambda:False)
        self.assertFalse(result['retained_complete']);self.assertFalse(any(r['url']==old['url'] for r in result['candidates']))
    def test_apple_ids_regions_and_empty_success(self):
        source=self.source({})
        from urllib.parse import urlencode
        url='https://itunes.apple.com/search?'+urlencode({'term':'Example Corp','entity':'software','country':'tr','limit':10})
        self.http.values[url]={'status':'complete','body':json.dumps({'resultCount':1,'results':[{'wrapperType':'software','trackId':123,'trackName':'Example Corp','sellerName':'Example Publisher','artistId':99}]}).encode()}
        rows,report=source._apps('apple','Example Corp','TR',Budget(self.http,self.scope),10,lambda:False)
        self.assertEqual(rows[0]['app_id'],'123');self.assertEqual(rows[0]['developer_id'],'99');self.assertEqual(report['country'],'TR')
        self.http.values[url]['body']=b'{"resultCount":0,"results":[]}'
        rows,report=source._apps('apple','Example Corp','TR',Budget(self.http,self.scope),10,lambda:False)
        self.assertEqual(rows,[]);self.assertEqual(report['status'],'complete')
    def test_google_parser_missing_data_not_treated_as_empty_success_and_tls_is_unchanged(self):
        from xti.adapters.brand_protection_process import run_worker
        original=ssl._create_default_https_context
        result=run_worker({'mode':'google','html':'<html>no app dataset</html>','query':'Example','country':'TR','limit':10,'app_id':'com.example.app'},10)
        self.assertNotEqual(result['status'],'complete');self.assertIs(ssl._create_default_https_context,original)
    def test_page_resource_budget_excludes_scripts_forms_and_private_urls(self):
        body=html('<img src="https://127.0.0.1/a"><img src="https://images.example/logo.png" alt="logo"><script src="https://script.example/a.js"></script><form action="https://form.example/"></form>')
        http=HTTP({'https://example.com/':body})
        result,_=capture_page('https://example.com/',Budget(http,self.scope),cancelled=lambda:False,renderer=renderer)
        self.assertNotIn('https://127.0.0.1/a',http.calls)
        self.assertNotIn('https://script.example/a.js',http.calls);self.assertNotIn('https://form.example/',http.calls)
        self.assertIsNotNone(result['template_sha256'])

    def test_reference_brand_logos_exclude_partner_images_and_explicit_selection_wins(self):
        page = html('<link rel="icon" href="/favicon.png">'
                    '<img src="/logo.png">'
                    '<img src="/example-corp.png" alt="Example Corp">'
                    '<img class="partner-logo" src="/aws.png" alt="AWS logo">'
                    '<img class="partner-logo" src="/github.png" alt="GitHub logo">')
        urls = ['https://example.com/' + name for name in ('favicon.png', 'logo.png', 'example-corp.png', 'aws.png', 'github.png')]
        values = {'https://example.com/': page, **{url: {'status': 'complete', 'body': b'image', 'content_type': 'image/png'} for url in urls}}
        visual = {'phash': '1'*16, 'dhash': '2'*16, 'colorhash': '3'*11, 'entropy': 5.0}
        image = (visual, {'role': 'candidate_logo', 'sha256': 'a'*64, 'bytes': 5}, b'image')
        with patch('xti.adapters.brand_protection_page.artifact', return_value=image):
            http = HTTP(values)
            result, _ = capture_page('https://example.com/', Budget(http, self.scope), cancelled=lambda: False,
                                     reference_name='Example Corp', renderer=renderer)
            self.assertEqual({row['url'] for row in result['logos']}, set(urls[:3]))
            # Partner images may render in the page but never become brand logo evidence.
            self.assertTrue(set(urls[3:]) <= set(http.calls))
            selected, _ = capture_page('https://example.com/', Budget(HTTP(values), self.scope), cancelled=lambda: False,
                                      reference_name='Example Corp', logo_urls=[urls[2]], renderer=renderer)
            self.assertEqual([row['url'] for row in selected['logos']], [urls[2]])


class VisualTests(unittest.TestCase):
    def setUp(self):
        try:
            from PIL import Image
            import imagehash
        except ImportError:self.skipTest('P03 visual dependencies absent in core-only environment')
    def fixture(self,offset=0):
        from PIL import Image,ImageDraw
        image=Image.new('RGB',(160,100),'white');draw=ImageDraw.Draw(image)
        for i in range(16):draw.rectangle((i*10,0,i*10+9,99),fill=((i*17+offset)%256,i*11,255-i*13))
        draw.text((12,42),'EXAMPLE',fill='black');out=BytesIO();image.save(out,format='PNG');return out.getvalue()
    def test_actual_library_hashes_pass_domain_validation_and_small_changes(self):
        from xti.adapters.brand_protection_visual import fingerprint
        first,_=fingerprint(self.fixture());validate_visual(first)
        second,_=fingerprint(self.fixture(1));validate_visual(second)
        self.assertEqual(len(first['colorhash']),11);self.assertTrue(compare_visual(first,second)['similar'])
    def test_image_limits_and_corrupt_formats_rejected(self):
        from xti.adapters.brand_protection_visual import fingerprint
        for data in (b'',b'not a picture',b'a'*(4*1024*1024+1)):
            with self.subTest(size=len(data)),self.assertRaises(ValidationError):fingerprint(data)
        from PIL import Image
        image=Image.new('RGB',(4001,4000));out=BytesIO();image.save(out,format='PNG')
        with self.assertRaises(ValidationError):fingerprint(out.getvalue())
    def test_png_metadata_not_copied_and_hash_matches_normalized_artifact(self):
        from PIL import Image,PngImagePlugin
        from xti.adapters.brand_protection_visual import artifact
        image=Image.open(BytesIO(self.fixture()));meta=PngImagePlugin.PngInfo();meta.add_text('private','fixture metadata')
        out=BytesIO();image.save(out,format='PNG',pnginfo=meta)
        visual,receipt,data=artifact(out.getvalue(),'candidate_logo')
        self.assertNotIn(b'fixture metadata',data);self.assertEqual(receipt['sha256'],hashlib.sha256(data).hexdigest())
