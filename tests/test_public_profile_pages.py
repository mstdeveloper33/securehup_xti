"""Public evidence transport must not follow private targets or mistake HTTP 200 for a profile."""
from io import BytesIO
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from xti.adapters.public_profile_pages import (
    MAX_BODY, PageFailure, PublicProfilePageSource, _request, parse_page, resolve_public,
)
from xti.adapters.social_discovery_sources import SocialDiscoverySourceAdapter
from xti.adapters.tavily_search import TavilySearchSource
from xti.domain.assets import ValidationError
from xti.domain.brand_username import BrandProfileMatch, BrandUsernamePreview
from xti.domain.social_discovery import assess, profile_url
from xti.ports.discovery import SourceError
from tests.test_social_discovery import AT,IG,SCOPE,profile
from tests.test_tavily_search import KEY,REQUEST,Response


class TransportTests(unittest.TestCase):
    def fetch(self,resolve=None,request=None,**changes):
        return PublicProfilePageSource(resolve=resolve or Mock(return_value='8.8.8.8'),request=request or Mock(return_value=(200,{},b'hello'))).fetch(
            IG,allowed_hosts=('instagram.com','www.instagram.com'),timeout=10,**changes)

    def test_private_dns_and_redirects_do_not_make_a_second_network_request(self):
        request=Mock()
        result=self.fetch(resolve=Mock(return_value='127.0.0.1'),request=request)
        self.assertEqual(result.error,'non_public_address');request.assert_not_called()
        for target in ('https://127.0.0.1/','https://instagram.com.evil.example/acme','http://instagram.com/acme',
                       'https://instagram.com:443@evil.example/acme','https://instagram.com:444/acme'):
            request=Mock(return_value=(302,{'location':target},b''))
            with self.subTest(target=target):
                self.assertEqual(self.fetch(request=request).error,'redirect_scope_rejected')
                self.assertEqual(request.call_count,1)

    def test_rebinding_and_numeric_socket_address_are_checked_for_each_approved_redirect(self):
        resolve=Mock(side_effect=['8.8.8.8','127.0.0.1'])
        request=Mock(return_value=(301,{'location':'https://www.instagram.com/acme/'},b''))
        result=self.fetch(resolve=resolve,request=request)
        self.assertEqual(result.error,'non_public_address');self.assertEqual(request.call_count,1)
        self.assertEqual(request.call_args.args[:3],('instagram.com','8.8.8.8','/acme'))

    def test_redirect_loops_and_fourth_hop_are_bounded(self):
        request=Mock(side_effect=[(301,{'location':'/one'},b''),(301,{'location':'/two'},b''),(301,{'location':'/three'},b'')])
        result=self.fetch(request=request)
        self.assertEqual((result.error,request.call_count),('redirect_limit',3))
        request=Mock(return_value=(302,{'location':IG},b''))
        self.assertEqual(self.fetch(request=request).error,'redirect_limit');self.assertEqual(request.call_count,1)

    def test_mixed_dns_answers_rejected_instead_of_choosing_a_public_one(self):
        for addresses in (['8.8.8.8','10.0.0.1'],[],['::1'],['169.254.169.254']):
            with self.subTest(addresses=addresses),patch('subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(addresses).encode())),self.assertRaises(PageFailure):
                resolve_public('instagram.com',1)

    def test_challenged_or_malformed_page_does_not_crash_or_become_absence(self):
        for status,headers,body,error in (
            (200,{},b'<meta property><meta name content><link rel href="/">',None),
            (200,{},b'<meta property="og:type" content="profile"><meta property="og:type" content="website">','conflicting_metadata'),
            (200,{'content-type':'application/json'},b'{}','unsupported_content_type'),
        ):
            with self.subTest(body=body):self.assertEqual(self.fetch(request=Mock(return_value=(status,headers,body))).error,error)
        self.assertEqual(self.fetch(request=Mock(side_effect=TimeoutError)).error,'timeout')

    def test_parser_bounds_body_depth_and_does_not_read_script_as_profile_evidence(self):
        for body in (b'x'*(MAX_BODY+1),b'<div>'*131):
            with self.assertRaises(PageFailure):parse_page(IG,IG,200,body,checked_at=AT)
        value=parse_page(IG,IG,200,b'<script>user: acme created: today karma: 1</script><p>Welcome</p>',checked_at=AT)
        self.assertEqual(value.visible_text,'Welcome')

    def test_linkedin_requires_the_top_level_profile_entity_not_an_unrelated_post_author(self):
        url='https://linkedin.com/showcase/acme'
        entity={'@type':'Organization','name':'Acme','url':url}
        for graph,expected in (([entity],'found'),([{'@type':'SocialMediaPosting','author':entity}],'inconclusive'),
                               ([{**entity,'url':'https://linkedin.com/showcase/other'}],'inconclusive')):
            html=f'<title>Acme | LinkedIn</title><link rel="canonical" href="{url}">'
            html+='<script type="application/ld+json">'+json.dumps({'@context':'https://schema.org','@graph':graph})+'</script>'
            value=parse_page(url,url,200,html.encode(),checked_at=AT)
            self.assertEqual(assess(profile_url(url),value,SCOPE)['state'],expected)
        hidden=f'<title>Acme | LinkedIn</title><link rel="canonical" href="{url}"><template><script type="application/ld+json">'
        hidden+=json.dumps({'@context':'https://schema.org',**entity})+'</script></template>'
        self.assertEqual(assess(profile_url(url),parse_page(url,url,200,hidden.encode(),checked_at=AT),SCOPE)['state'],'inconclusive')

    def test_gitlab_user_route_supports_a_different_display_name_but_project_page_does_not(self):
        url='https://gitlab.com/acme'
        for route,expected in (('users:show','found'),('projects:show','inconclusive')):
            html=f'<title>Security Review Bot · GitLab</title><meta property="og:url" content="{url}"><body data-page="{route}"></body>'
            value=parse_page(url,url,200,html.encode(),checked_at=AT)
            self.assertEqual(assess(profile_url(url),value,SCOPE)['state'],expected)
        hidden=f'<title>Acme | GitLab</title><meta property="og:url" content="{url}"><template><body data-page="users:show"></body></template>'
        self.assertEqual(assess(profile_url(url),parse_page(url,url,200,hidden.encode(),checked_at=AT),SCOPE)['state'],'inconclusive')

    def wire_request(self,wire):
        tls=Mock();tls.makefile.side_effect=lambda mode:BytesIO(wire)
        raw=Mock();context=Mock();context.wrap_socket.return_value=tls
        with patch('socket.create_connection',return_value=raw) as connect,patch('ssl.create_default_context',return_value=context):
            result=_request('instagram.com','8.8.8.8','/acme',10)
        connect.assert_called_once_with(('8.8.8.8',443),timeout=10)
        context.wrap_socket.assert_called_once_with(raw,server_hostname='instagram.com')
        sent=tls.sendall.call_args.args[0]
        self.assertIn(b'Host: instagram.com\r\n',sent);self.assertNotIn(b'Cookie:',sent);self.assertNotIn(b'Authorization:',sent)
        tls.close.assert_called_once()
        return result

    def test_real_http_response_parser_handles_length_chunking_redirect_and_close(self):
        for wire,body in ((b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhello',b'hello'),
                          (b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n0\r\n\r\n',b'hello'),
                          (b'HTTP/1.1 302 Found\r\nLocation: /next\r\nContent-Length: 100\r\n\r\n',b'')):
            with self.subTest(wire=wire):self.assertEqual(self.wire_request(wire)[2],body)
        for wire in (b'HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\n\r\n',
                     b'HTTP/1.1 200 OK\r\nContent-Length: 99999999\r\n\r\n',
                     b'HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nshort',
                     b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\nContent-Length: 5\r\n\r\nhello',
                     b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nContent-Length: 5\r\n\r\n'):
            with self.assertRaises(PageFailure):self.wire_request(wire)

    def test_slow_drip_body_and_headers_cannot_restart_the_total_deadline(self):
        from xti.adapters.public_profile_pages import _DeadlineFile
        for method in ('read','readline'):
            ticks=[0]
            def drip(size):ticks[0]+=0.6;return b'a'
            stream=Mock(read1=Mock(side_effect=drip))
            wrapped=_DeadlineFile(stream,Mock(),deadline=1)
            with patch('xti.adapters.public_profile_pages.time.monotonic',side_effect=lambda:ticks[0]),self.assertRaises(TimeoutError):
                getattr(wrapped,method)(1000)
            self.assertEqual(stream.read1.call_count,2)


class SourceTests(unittest.TestCase):
    def test_existing_tool_result_is_translated_and_unreported_never_becomes_absent(self):
        preview=BrandUsernamePreview('acme','maigret','0.test','pinned',AT,('Instagram','GitHub'),
                                     (BrandProfileMatch('GitHub','https://github.com/acme','claimed'),),('Instagram',),())
        with patch('xti.adapters.social_discovery_sources.MaigretUsernameSource') as factory:
            factory.return_value.preview.return_value=preview
            result=SocialDiscoverySourceAdapter().collect('maigret','acme',('Instagram','GitHub'),timeout=10,remaining=2)
        self.assertEqual(result['matches'],[{'url':'https://github.com/acme','platform':'GitHub'}])
        self.assertEqual(result['unreported_platforms'],['Instagram'])

    def test_missing_or_broken_tool_is_isolated_and_exception_details_do_not_leak(self):
        with patch('xti.adapters.social_discovery_sources.MaigretUsernameSource') as factory:
            factory.return_value.preview.side_effect=SourceError('secret diagnostic body')
            result=SocialDiscoverySourceAdapter().collect('maigret','acme',('Instagram',),timeout=10,remaining=2)
        self.assertEqual(result['status'],'failed');self.assertNotIn('secret',json.dumps(result))

    def test_tool_subprocess_is_clamped_to_shared_budget_including_version_check(self):
        clock=Mock(side_effect=[10,11,13]);runner=Mock(return_value=SimpleNamespace(returncode=0))
        adapter=SocialDiscoverySourceAdapter(runner=runner,monotonic=clock)
        def invoke(*args,**kwargs):
            wrapped=kwargs['runner']
            wrapped(['tool','--version'],timeout=15)
            import subprocess
            with self.assertRaises(subprocess.TimeoutExpired):wrapped(['tool','scan'],timeout=300)
            return Mock(preview=Mock(side_effect=SourceError('timeout')))
        with patch('xti.adapters.social_discovery_sources.MaigretUsernameSource',side_effect=invoke):
            adapter.collect('maigret','acme',('Instagram',),timeout=10,remaining=2)
        self.assertEqual(runner.call_args.kwargs['timeout'],1)

    def test_missing_search_key_makes_no_paid_call_and_no_secret_output(self):
        factory=Mock();loader=Mock(side_effect=ValidationError('key missing'))
        result=SocialDiscoverySourceAdapter(key_loader=loader,tavily_factory=factory).search(SCOPE,remaining=10)
        self.assertEqual(result[0]['error'],'missing_or_invalid_api_key');factory.assert_not_called()

    def test_advanced_search_payload_has_explicit_filters_usage_and_no_auto_expansion(self):
        opener=Mock(return_value=Response())
        source=TavilySearchSource(KEY,opener=opener,search_depth='advanced',include_domains=('instagram.com',),budget_seconds=3)
        source.fetch(REQUEST)
        outgoing=opener.call_args.args[0];payload=json.loads(outgoing.data)
        self.assertEqual(payload['search_depth'],'advanced');self.assertEqual(payload['include_domains'],['instagram.com'])
        self.assertFalse(payload['auto_parameters']);self.assertTrue(payload['include_usage'])
        self.assertNotIn(KEY,outgoing.data.decode());self.assertEqual(opener.call_args.kwargs['timeout'],3)

    def test_three_bounded_queries_partial_failure_and_credits_remain_visible(self):
        response=SimpleNamespace(query='Acme',request_id='public-id',credits=2,hits=())
        factory=Mock(side_effect=[Mock(fetch=Mock(return_value=response)),Mock(fetch=Mock(side_effect=SourceError('secret'))),
                                  Mock(fetch=Mock(return_value=response))])
        adapter=SocialDiscoverySourceAdapter(key_loader=lambda:KEY,tavily_factory=factory)
        result=adapter.search({**SCOPE,'platforms':['Instagram','Twitter']},remaining=10)
        self.assertEqual([r['status'] for r in result],['complete','failed','complete'])
        self.assertEqual([r['credits'] for r in result],[2,None,2])
        self.assertEqual(factory.call_count,3);self.assertNotIn(KEY,json.dumps(result));self.assertNotIn('secret',json.dumps(result))
        self.assertEqual([c.kwargs['include_domains'] for c in factory.call_args_list],[(),('instagram.com',),('x.com','twitter.com')])
