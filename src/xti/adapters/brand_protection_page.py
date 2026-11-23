"""Static public-page evidence without scripts, logins, forms or browser network access."""
import base64
import hashlib
from html import escape
from html.parser import HTMLParser
import re
from urllib.parse import unquote,urljoin,urlsplit

from xti.domain.brand_protection import digest,folded
from xti.domain.content_monitoring import public_url
from xti.domain.assets import ValidationError
from xti.adapters.brand_protection_process import run_worker
from xti.adapters.brand_protection_visual import artifact


class PageParser(HTMLParser):
    def __init__(self,url):
        super().__init__(convert_charrefs=True);self.url=url;self.links=[];self.images=[];self.styles=[];self.scripts=[];self.forms=[];self.words=[];self.title=[];self.passwords=0;self.hidden=0;self.in_title=False;self.tags=[]
        self.image_labels = {}
    def address(self,value):
        try:return public_url(urljoin(self.url,value))
        except (ValidationError,ValueError):return None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if len(self.tags)<5000:self.tags.append(tag)
        if tag in ('script','style','noscript'):self.hidden+=1
        if tag=='title':self.in_title=True
        url=self.address(attrs.get('href','')) if attrs.get('href') else None
        if tag=='a' and url and len(self.links)<100:self.links.append(url)
        if tag=='link' and url:
            rel=attrs.get('rel','').casefold()
            if 'stylesheet' in rel and len(self.styles)<4:self.styles.append(url)
            if 'icon' in rel and len(self.images)<12:self.images.append((0,url))
        if tag=='img' and len(self.images)<12:
            src=attrs.get('src') or attrs.get('data-src')
            if src and (image:=self.address(src)):
                label=' '.join((attrs.get('alt',''),attrs.get('class',''),src)).casefold()
                self.images.append((1 if 'logo' in label else 2,image))
                self.image_labels[image] = attrs.get('alt', '')
        if tag=='script' and attrs.get('src') and (src:=self.address(attrs['src'])) and len(self.scripts)<50:self.scripts.append(digest(src))
        if tag=='form':
            action=self.address(attrs.get('action',''))
            if len(self.forms)<50:self.forms.append({'host':urlsplit(action).hostname if action else None,'method':attrs.get('method','get').lower()})
        if tag=='input' and attrs.get('type','').casefold()=='password':self.passwords+=1
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript'):self.hidden=max(0,self.hidden-1)
        if tag=='title':self.in_title=False
    def handle_data(self,data):
        if self.in_title:self.title.append(data)
        if not self.hidden and sum(map(len,self.words))<12000:self.words.append(data)

    def reference_logos(self, name, explicit):
        """Keep partner/product images out of the brand's reference logo set.

        Declared URLs take precedence. Otherwise use site icons, a generic
        logo filename, or an image labelled with the brand name. This remains
        a source clue, not verified logo ownership.
        """
        if explicit:
            return set(explicit)
        compact_name = ''.join(c for c in folded(name) if c.isalnum())
        selected = set()
        for rank, url in self.images:
            filename = unquote(urlsplit(url).path.rsplit('/', 1)[-1])
            stem = filename.rsplit('.', 1)[0].casefold()
            label = folded(self.image_labels.get(url, '') + ' ' + filename)
            compact_label = ''.join(c for c in label if c.isalnum())
            generic_logo = re.fullmatch(r'(?:brand[-_])?logo(?:[-_](?:dark|light|white|black|horizontal|vertical|small|large|[0-9]+))*', stem)
            if rank == 0 or generic_logo or (len(compact_name) >= 3 and compact_name in compact_label):
                selected.add(url)
        return selected


def capture_page(url,fetch,*,cancelled,logo_urls=(),reference_name=None,renderer=run_worker):
    response=fetch.get(url)
    if response['status']!='complete':return {'url':url,'status':response['status']},{}
    raw=response['body'];content_type=response.get('content_type','').lower()
    if 'html' not in content_type and not raw.lstrip().lower().startswith((b'<!doctype html',b'<html')):
        return {'url':url,'status':'not_html'},{}
    final=response.get('final_url',url)
    parser=PageParser(final)
    try:parser.feed(raw.decode('utf-8',errors='replace'))
    except (ValueError,RecursionError):return {'url':url,'status':'invalid_html'},{}
    result={'url':url,'final_url':final,'status':'complete','title':' '.join(' '.join(parser.title).split())[:400],
        'text':' '.join(' '.join(parser.words).split())[:6000],'html_sha256':hashlib.sha256(raw).hexdigest(),'password_fields':parser.passwords,
        'cross_domain_form':any(v['host'] and v['host']!=urlsplit(final).hostname for v in parser.forms),
        'form_hosts':sorted({v['host'] for v in parser.forms if v['host']}),
        'template_sha256':digest({'tags':parser.tags,'scripts':parser.scripts,'forms':parser.forms}) if parser.forms or parser.scripts else None,
        'links':parser.links,'logos':[],'_artifacts':[],'visual':None,'render_state':'not_checked','render_mode':'static_no_javascript'}
    resources={url:{'body':base64.b64encode(raw).decode(),'content_type':'text/html; charset=utf-8'}}
    if final!=url:resources[final]=resources[url]
    blobs={};images=list(dict.fromkeys([*logo_urls,*[item[1] for item in sorted(parser.images)]]))[:5]
    logo_evidence = parser.reference_logos(reference_name, logo_urls) if reference_name else set(images)
    if reference_name:
        result['logo_selection'] = 'declared_only' if logo_urls else 'brand_name_site_icon_or_generic_logo'
    for location in [*parser.styles,*images]:
        if cancelled() or fetch.remaining<2:break
        item=fetch.get(location)
        if item['status']!='complete':continue
        resources[location]={'body':base64.b64encode(item['body']).decode(),'content_type':item.get('content_type','application/octet-stream')}
        if location in images and location in logo_evidence:
            try:
                image_data=item['body']
                if 'svg' in item.get('content_type','').lower() or image_data.lstrip().startswith(b'<svg'):
                    wrapper='https://xti-image.invalid/'
                    html=('<html><body style="margin:0"><img style="width:512px;height:512px;object-fit:contain" src="'+escape(location,quote=True)+'"></body></html>').encode()
                    rendered=renderer({'mode':'render','url':wrapper,'image_url':location,'resources':{
                        wrapper:{'body':base64.b64encode(html).decode(),'content_type':'text/html'},location:resources[location]}},min(20,fetch.remaining),cancelled=cancelled)
                    if rendered.get('status')!='complete':continue
                    image_data=base64.b64decode(rendered['png'],validate=True)
                visual,meta,png=artifact(image_data,'candidate_logo')
            except ValidationError:continue
            except Exception as exc:
                # Known invalid images are incomplete visual evidence, not a lost page.
                from xti.domain.brand_protection import BrandProtectionError
                if not isinstance(exc,BrandProtectionError):raise
                continue
            result['logos'].append({'url':location,'visual':visual,'sha256':meta['sha256']});result['_artifacts'].append(meta);blobs[meta['sha256']]=png
    if not cancelled() and fetch.remaining>1:
        rendered=renderer({'mode':'render','url':final,'resources':resources},min(25,fetch.remaining),cancelled=cancelled)
        result['render_state']=rendered['status']
        if rendered['status']=='complete':
            try:
                visual,meta,png=artifact(base64.b64decode(rendered['png'],validate=True),'candidate_page')
                result['visual']=visual;result['_artifacts'].append(meta);blobs[meta['sha256']]=png
                result['blocked_resources']=rendered['blocked_resources']
            except (ValueError,ValidationError):result['render_state']='invalid_image'
    if result['render_state']!='complete':result['status']='partial'
    return result,blobs
