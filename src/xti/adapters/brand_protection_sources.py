"""Free public discovery behind bounded HTTPS, offline parsers and existing social tools."""
import base64
from datetime import datetime,timezone
import importlib.metadata
import json
from pathlib import Path
import time
from urllib.parse import urlencode, urlsplit

from xti.adapters.content_http import ContentHTTP
from xti.adapters.brand_protection_page import capture_page
from xti.adapters.brand_protection_process import run_worker
from xti.adapters.brand_protection_visual import artifact
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.content_monitoring import public_url, digest
from xti.domain.brand_protection import BrandProtectionError, folded
from xti.ports.discovery import SourceError
from xti.domain.code_exposure import CodeExposureError


class Budget:
    def __init__(self,http,scope,*,clock=time.monotonic,cancelled=lambda:False,cooldowns=None):
        self.http,self.scope,self.clock,self.cancelled=http,scope,clock,cancelled
        self.cooldowns=cooldowns
        self.started=clock();self.attempts=[];self.calls=0;self.bytes=0;self.exhausted=False
    @property
    def remaining(self):return max(0,self.scope['max_seconds']-(self.clock()-self.started))
    def get(self,url):
        if self.cancelled():return {'status':'cancelled','body':b''}
        left=self.scope['max_requests']-len(self.attempts)
        if self.calls>=self.scope['max_requests'] or left<=0 or self.remaining<.1 or self.bytes>=16*1024*1024:
            self.exhausted=True;return {'status':'budget_exhausted','body':b''}
        self.calls+=1
        host=urlsplit(public_url(url)).hostname
        if self.cooldowns:
            deadline=self.cooldowns.get(host)
            if deadline>time.time():return {'status':'cooldown','body':b'','retry_after_seconds':round(deadline-time.time())}
        response=self.http.get(public_url(url),seconds=min(20,self.remaining),max_operations=min(4,left))
        if self.cooldowns and response['status'] in ('rate_limited','unavailable','timeout'):
            self.cooldowns.extend(host,time.time()+min(86400,max(30,response.get('retry_after_seconds',90))),datetime.now(timezone.utc).isoformat())
        self.attempts.extend(response.get('attempts',[]));self.bytes+=len(response.get('body',b''))
        if self.bytes>16*1024*1024:self.exhausted=True;return {'status':'budget_exhausted','body':b''}
        return response


def _safe_text(value,limit=6000):
    if not isinstance(value,str):return ''
    return ' '.join(value.split())[:limit]


def _page_candidate(url,source,kind='page',**extra):
    return {'kind':kind,'url':public_url(url),'title':'','text':'','sources':[source],**extra}


class BrandProtectionSources:
    def __init__(self,database,scanner,*,http=None,renderer=run_worker,clock=time.monotonic,social=None):
        self.database,self.scanner=database,scanner
        self.http,self.renderer,self.clock,self.social=http or ContentHTTP(),renderer,clock,social
        from xti.adapters.sqlite_brand_protection import BrandCooldowns
        self.cooldowns=BrandCooldowns(database)

    def status(self):
        tools=[]
        for name,expected in (('Pillow','13.0.0'),('ImageHash','4.3.2'),('playwright','1.65.2'),('google-play-scraper','1.2.7')):
            try:version=importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:version=None
            tools.append({'tool':name,'version':version,'expected_version':expected,'state':'ready' if version==expected else 'not_ready'})
        from xti.adapters.brand_protection_tools import browser_status
        browser=browser_status()
        return {'policy':'brand-protection-v1','tools':tools,'browser_state':browser['state'],
                'privacy_scanner':self.scanner.status(),'providers':['web','social','apple','google','urlscan','crt.sh','stored'],
                'render_mode':'static_no_javascript','network_access':False,'automatic_impersonation_verdict':False,
                'paid_api_calls':False,'coverage':'selected_sources_regions_and_reviewed_identity'}

    def collect(self,snapshot,retained,*,cancelled):
        brand,scope=snapshot['brand'],snapshot['scope']; budget=Budget(self.http,scope,clock=self.clock,cancelled=cancelled,cooldowns=self.cooldowns)
        candidates={};reports=[];blobs={};partial=False;privacy_failed=False;truncated=False
        def add(row):
            nonlocal truncated
            try:row['url']=public_url(row['url'])
            except ValidationError:return
            key=digest([row['kind'],row['url'],row.get('subject_name')])
            if key in candidates:
                existing=candidates[key];row['sources']=sorted(set(existing.get('sources',[])+row.get('sources',[])))
                candidates[key]={**existing,**row};return
            if len(candidates)>=scope['max_items']:truncated=True;return
            candidates[key]=row
        reference,images=capture_page('https://'+brand['domains'][0]+'/',budget,cancelled=cancelled,logo_urls=brand['logos'],reference_name=brand['name'],renderer=self.renderer)
        for item in reference.get('_artifacts',[]):item['role']=item['role'].replace('candidate','reference')
        blobs.update(images)
        reports.append({'provider':'reference','status':reference['status'],'url':reference['url'],'render_mode':'static_no_javascript'})
        if reference['status']!='complete':partial=True
        # Keep the reference compact; links are discovery inputs, not ownership confirmations.
        links=reference.pop('links',[])
        for url in scope['urls']:add(_page_candidate(url,'declared_candidate'))
        for old in retained:
            add({**old, '_retained': True})
        for url in brand['profiles']:
            add(_page_candidate(url,'declared_official_profile','social'))
        for app in brand['apps']:
            for country in scope['countries']:
                url='https://apps.apple.com/'+country.lower()+'/app/id'+app['id'] if app['store']=='apple' else 'https://play.google.com/store/apps/details?'+urlencode({'id':app['id'],'gl':country.lower()})
                add(_page_candidate(url,'declared_official_app','mobile',store=app['store'],app_id=app['id'],country=country))
        for person in brand['people']:
            for url in person['profiles']:add(_page_candidate(url,'declared_person_profile','person_profile',subject_name=person['name'],role=person['role']))
        for provider in scope['sources']:
            if cancelled() or budget.remaining<=1:
                reports.append({'provider':provider,'status':'cancelled' if cancelled() else 'budget_exhausted'});partial=True;continue
            try:
                if provider=='web':
                    from xti.domain.social_discovery import profile_url
                    found=0
                    for link in links:
                        try:profile=profile_url(link)
                        except ValidationError:continue
                        add(_page_candidate(profile['url'],'official_site_link','social',platform=profile['platform']));found+=1
                    reports.append({'provider':'web','status':reference['status'],'linked_profiles':found,'ownership_confirmed':False})
                elif provider in ('apple','google'):
                    for country in scope['countries']:
                        rows,report=self._apps(provider,brand['name'],country,budget,scope['max_items'],cancelled)
                        reports.append(report)
                        for row in rows:add(row)
                        partial |= report['status']!='complete'
                elif provider in ('urlscan','crt.sh'):
                    rows,report=self._domains(provider,brand,budget,scope['max_items']);reports.append(report)
                    for row in rows:add(row)
                    partial |= report['status']!='complete'
                elif provider=='social':
                    rows,report=self._social(brand,scope,budget,retained);reports.append(report)
                    for row in rows:add(row)
                    partial |= report['status']!='complete'
                elif provider=='stored':
                    rows,report=self._stored(brand,scope['max_items']);reports.append(report)
                    for row in rows:add(row)
                    partial |= report['status']!='complete'
            except (SourceError,ValidationError,OSError,ValueError,KeyError,TypeError,RecursionError):
                reports.append({'provider':provider,'status':'source_error'});partial=True
        checked=[];pages=0;retained_done=0
        for key,row in list(candidates.items()):
            if cancelled() or budget.remaining<.2:partial=True;break
            old=row.pop('_retained', False)
            if old and (row['kind']=='mobile' or 'web' in scope['sources'] and pages<scope['max_pages'] and budget.remaining>2):retained_done+=1
            if row['kind']=='mobile' and (old or not row.get('title')):
                try:rows,report=self._apps(row['store'],brand['name'],row.get('country',scope['countries'][0]),budget,1,cancelled,identifier=row['app_id'])
                except (ValidationError,ValueError,KeyError,TypeError):rows,report=[],{'provider':row['store'],'status':'source_error'}
                reports.append(report)
                if rows:
                    previous_sources=row.get('sources',[]);row.update(rows[0]);row['sources']=sorted(set(previous_sources+row.get('sources',[])))
                else:
                    partial=True
                    if old:continue
            if row['kind']!='mobile' and 'web' in scope['sources'] and pages<scope['max_pages'] and budget.remaining>2:
                page,images=capture_page(row['url'],budget,cancelled=cancelled,renderer=self.renderer)
                pages+=1
                reports.append({'provider':'page','status':page['status'],'url':row['url']})
                if page['status'] in ('complete','partial'):
                    page.pop('links',None);row.update(page);blobs.update(images)
                    partial |= page['status']!='complete'
                else:
                    partial=True
                    if old:continue
                    row['page_status']=page['status']
            elif row['kind']!='mobile':
                row['page_status']='not_checked';partial=True
                if old:continue
            if row['kind']=='mobile' and row.get('icon_url') and budget.remaining>1:
                image=budget.get(row['icon_url'])
                if image['status']=='complete':
                    try:
                        visual,meta,png=artifact(image['body'],'candidate_logo');row['logos']=[{'url':row['icon_url'],'visual':visual,'sha256':meta['sha256']}]
                        row['_artifacts']=[meta];blobs[meta['sha256']]=png
                    except ValidationError:partial=True
            if not self._privacy(row,budget.remaining):partial=True;privacy_failed=True
            if row.pop('_discard',False):continue
            checked.append(row)
        if not self._privacy(reference,budget.remaining):partial=True;privacy_failed=True
        if reference.pop('_discard',False):reference={'url':'https://'+brand['domains'][0]+'/','status':'privacy_rejected'}
        elapsed=round(self.clock()-budget.started,3)
        status='interrupted' if cancelled() else 'failed' if not checked and reference['status'] not in ('complete','partial') else 'partial' if partial or truncated or budget.exhausted else 'complete'
        return {'status':status,'reference':reference,'candidates':checked,'artifacts':blobs,'sources':reports,
                'http_attempts':budget.attempts,'http_requests':len(budget.attempts),'http_bytes':budget.bytes,
                'external_social_tool_http_requests':None if 'social' in scope['sources'] else 0,
                'elapsed_seconds':elapsed,'truncated':truncated,'privacy_incomplete':privacy_failed,
                'pages_checked':pages,'retained_complete':retained_done==len(retained),'retained_outside_window_preserved':True,'paid_calls':0}

    def _privacy(self,value,remaining):
        fields=('title','text','developer')
        started=self.clock()
        def time_left():return max(.01,min(3,remaining-(self.clock()-started)))
        if self.scanner.status().get('state')!='ready':
            for key in fields:
                if key in value:value[key]=''
            value['privacy']='scanner_unavailable';value['_discard']=True;return False
        try:
            for key in fields:
                if value.get(key):
                    lines=value[key].splitlines()
                    hits=self.scanner.scan(value[key],seconds=time_left())
                    for hit in hits:
                        index=hit.get('line',0)-1
                        if 0<=index<len(lines):lines[index]='[MASKELENDİ]'
                    value[key]='\n'.join(lines)
            urls=[value[k] for k in ('url','final_url','icon_url') if value.get(k)]
            urls.extend(v['url'] for v in value.get('logos',[]) if v.get('url'))
            if self.scanner.scan('\n'.join(urls),seconds=time_left()):
                # Never change a candidate URL to another identity to hide a secret.
                value['privacy']='unsafe_url_rejected';value['_discard']=True;return False
            value['privacy']='text_scanned_visual_not_redacted';return True
        except (ValidationError,SourceError,CodeExposureError,OSError):
            for key in fields:
                if key in value:value[key]=''
            value['privacy']='scanner_failed';value['_discard']=True;return False

    def _domains(self,provider,brand,budget,limit):
        label=brand['domains'][0].split('.')[0]
        if provider=='urlscan':
            from xti.adapters.urlscan import UrlscanSource,parse_response
            url=UrlscanSource().search_url(label+'*')
        else:
            from xti.adapters.crtsh import CrtShSource,parse_response
            url=CrtShSource().search_url('%'+label+'%')
        response=budget.get(url)
        if response['status']!='complete':return [],{'provider':provider,'status':response['status']}
        batch=parse_response(response['body']);seen=set();rows=[]
        for doc in batch.documents:
            for domain in doc.records:
                if domain.domain not in seen:
                    seen.add(domain.domain);rows.append(_page_candidate('https://'+domain.domain+'/',provider,'domain'))
        return rows[:limit],{'provider':provider,'status':'partial' if batch.warnings or len(rows)>limit else 'complete','records':batch.record_count,'candidates':len(rows[:limit]),'coverage':list(batch.coverage_notes),'window_only':True}

    def _apps(self,provider,query,country,budget,limit,cancelled,identifier=None):
        if provider=='apple':
            args={'id':identifier,'country':country.lower()} if identifier else {'term':query,'entity':'software','country':country.lower(),'limit':min(limit,100)}
            url='https://itunes.apple.com/'+('lookup' if identifier else 'search')+'?'+urlencode(args)
        else:
            url='https://play.google.com/store/'+('apps/details?'+urlencode({'id':identifier,'hl':'en','gl':country.lower()}) if identifier else 'search?'+urlencode({'q':query,'c':'apps','hl':'en','gl':country.lower()}))
        response=budget.get(url);report={'provider':provider,'country':country,'status':response['status'],'window_only':True,'exact_lookup':bool(identifier)}
        if response['status']!='complete':return [],report
        if provider=='apple':
            payload=json.loads(response['body'])
            if not isinstance(payload,dict) or not isinstance(payload.get('results'),list) or len(payload['results'])>200:raise ValueError()
            records=payload['results'];rows=[]
            for item in records[:limit]:
                if item.get('wrapperType')!='software':continue
                app_id=str(item['trackId'])
                if identifier and app_id!=identifier:raise ValueError()
                rows.append(_page_candidate('https://apps.apple.com/'+country.lower()+'/app/id'+app_id,'apple','mobile',store='apple',app_id=app_id,
                    title=_safe_text(item.get('trackName'),400),text=_safe_text(item.get('description')),developer=_safe_text(item.get('sellerName'),200),
                    developer_id=str(item.get('artistId','')),country=country,icon_url=public_url(item['artworkUrl100']) if item.get('artworkUrl100') else None))
        else:
            parsed=self.renderer({'mode':'google','html':response['body'].decode('utf-8'),'query':query,'country':country,'limit':min(limit,100),'app_id':identifier},min(15,budget.remaining),cancelled=cancelled)
            report['status']=parsed['status'];rows=[]
            for item in parsed.get('items',[]):
                app_id=str(item['appId'])
                if identifier and app_id!=identifier:raise ValueError()
                rows.append(_page_candidate('https://play.google.com/store/apps/details?'+urlencode({'id':app_id,'gl':country.lower()}),'google','mobile',store='google',app_id=app_id,
                    title=_safe_text(item.get('title'),400),text=_safe_text(item.get('summary') or item.get('description')),developer=_safe_text(item.get('developer'),200),developer_id=_safe_text(item.get('developerId'),200),country=country,
                    icon_url=public_url(item['icon']) if item.get('icon') else None))
        report.update(items=len(rows),may_have_more=len(rows)>=min(limit,100));return rows,report

    def _social(self,brand,scope,budget,retained):
        from xti.domain.social_discovery import parameters
        from xti.interfaces.social_discovery import make_social_discovery_service
        if budget.remaining<15:return [],{'provider':'social','status':'budget_exhausted'}
        service=self.social or make_social_discovery_service(self.database,network=True)
        options=parameters('brand.discovery.plan',{'domain':brand['domains'][0],'name':brand['name'],'platforms':scope['platforms'],
            'web_search':False,'timeout':5,'budget_seconds':min(60,max(15,int(budget.remaining/2))),'max_pages':min(scope['max_items'],30)})
        options['tracking']={'urls':[r['url'] for r in retained if r['kind'] in ('social','person_profile')]}
        report=service._collect(options);rows=[]
        for profile in report.get('profiles',[]):
            if profile['state'] not in ('found','candidate'):continue
            evidence=profile.get('evidence') or {}
            rows.append(_page_candidate(profile['url'],'social_discovery','social',platform=profile['platform'],title=_safe_text(evidence.get('title'),400),
                text=_safe_text(evidence.get('description')),profile_state=profile['state'],identity_evidence_sha256=evidence.get('body_sha256')))
        # Person affiliation is not inferred from the company's domain or a matching handle.
        for person in brand['people']:
            if budget.remaining<15:break
            opts={**options,'name':person['name'],'budget_seconds':min(30,max(15,int(budget.remaining/2)))}
            person_report=service._collect(opts)
            for profile in person_report.get('profiles',[]):
                evidence=profile.get('evidence') or {}
                if profile['state'] in ('found','candidate') and folded(person['name']).replace(' ','') in folded(profile.get('username','')).replace('_','').replace('.',''):
                    rows.append(_page_candidate(profile['url'],'person_social_discovery','person_profile',platform=profile['platform'],subject_name=person['name'],role=person['role'],title=_safe_text(evidence.get('title'),400),text=_safe_text(evidence.get('description'))))
        return rows,{'provider':'social','status':report.get('status','partial'),'candidates':len(rows),'paid_calls':0,'coverage':report.get('coverage',[]),'tool_http_requests':None}

    def _stored(self,brand,limit):
        from xti.adapters.sqlite import SQLiteAssetRepository
        with SQLiteAssetRepository(self.database)._connection(readonly=True) as c:
            q=','.join('?' for _ in brand['domains'])
            rows=c.execute(f'SELECT f.domain,f.id FROM findings f JOIN assets a ON f.asset_id=a.id WHERE a.value IN ({q}) ORDER BY f.created_at,f.id LIMIT ?',(*brand['domains'],limit+1)).fetchall()
        return [_page_candidate('https://'+r[0]+'/','stored_finding','domain',record_id=r[1]) for r in rows[:limit]],{'provider':'stored','status':'partial' if len(rows)>limit else 'complete','candidates':min(limit,len(rows)),'network_requests':0}
