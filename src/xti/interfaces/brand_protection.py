"""Brand protection commands and company JSON composition boundary."""
import base64
from contextlib import nullcontext
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from xti.domain.assets import ValidationError
from xti.domain.brand_protection import PREFIX, IDENTITY_FIELDS, SCOPE_FIELDS, WRITES, PROVIDERS, DECISIONS, integer
from xti.interfaces.text import safe_text

CLI={v.replace('.','-'):PREFIX+v for v in ('capabilities','identities','identity.add','identity.update','identity.show','watches','watch.add','watch.update','watch.show','plan','run','runs','run.show','candidates','candidate.show','evidence.show','artifact.get','review','reviews','changes','report','recover')}


def make_brand_protection_service(database,*,request_usage=None):
    from xti.adapters.betterleaks import BetterleaksScanner
    from xti.adapters.content_http import ContentHTTP
    from xti.adapters.brand_protection_sources import BrandProtectionSources
    from xti.adapters.sqlite_brand_protection import SQLiteBrandProtectionRepository
    from xti.application.brand_protection import BrandProtectionService
    return BrandProtectionService(SQLiteBrandProtectionRepository(database),BrandProtectionSources(database,BetterleaksScanner(),http=ContentHTTP(request_usage=request_usage)))


def register_brand_protection_parser(actions):
    commands=actions.add_parser('protection',help='Marka/domain/sayfa/logo/sosyal/uygulama adaylarını kanıtla karşılaştır.').add_subparsers(dest='protection_action',required=True)
    for name,operation in CLI.items():
        parser=commands.add_parser(name);parser.set_defaults(protection_operation=operation)
        if name.endswith(('-show','-update')) or name in ('plan','run','artifact-get','review','reviews','recover'):parser.add_argument('identifier')
        if name in ('identity-add','identity-update'):
            parser.add_argument('--name',required=name=='identity-add');parser.add_argument('--domain',dest='domains',action='append',required=name=='identity-add')
            parser.add_argument('--organization',dest='organization_id');parser.add_argument('--logo',dest='logos',action='append')
            parser.add_argument('--profile',dest='profiles',action='append')
            parser.add_argument('--app-json',dest='apps',action='append');parser.add_argument('--person-json',dest='people',action='append')
        if name in ('watch-add','watch-update'):
            parser.add_argument('--name');parser.add_argument('--identity',dest='identity_id',required=name=='watch-add')
            parser.add_argument('--source',dest='sources',action='append',choices=PROVIDERS);parser.add_argument('--country',dest='countries',action='append')
            parser.add_argument('--platform',dest='platforms',action='append');parser.add_argument('--url',dest='urls',action='append')
            for option in ('max-requests','max-seconds','max-items','max-pages','interval-seconds'):parser.add_argument('--'+option,type=int)
        if name in ('identity-update','watch-update'):
            enabled=parser.add_mutually_exclusive_group();enabled.add_argument('--enable',dest='enabled',action='store_const',const=True,default=None);enabled.add_argument('--disable',dest='enabled',action='store_const',const=False)
        if name in ('identity-update','watch-update','run','review'):parser.add_argument('--expected-revision',type=int)
        if name=='run':parser.add_argument('--force',action='store_true')
        if name=='review':
            parser.add_argument('--evidence-id',required=True);parser.add_argument('--observation-revision',dest='expected_observation_revision',type=int)
            parser.add_argument('--decision',required=True,choices=DECISIONS);parser.add_argument('--reason',required=True)
        if name in ('identities','watches','runs','candidates','reviews','changes'):
            parser.add_argument('--after',type=int,default=0);parser.add_argument('--limit',type=int,default=20)
        if name in ('watches','runs','candidates','changes','report'):
            parser.add_argument('--identity-id');parser.add_argument('--domain')
            if name!='report':parser.add_argument('--watch-id')
        if name=='candidates':parser.add_argument('--kind',choices=('page','domain','social','mobile','person_profile'));parser.add_argument('--decision',choices=DECISIONS)
        if name=='artifact-get':parser.add_argument('--output',type=Path)
        if operation in WRITES:parser.add_argument('--idempotency-key')
    monitor=commands.add_parser('monitor');monitor.add_argument('identifier');monitor.add_argument('--cycles',type=int,default=1)


def protection_lines(data):
    if 'items' in data:
        lines=[]
        for row in data['items']:lines.extend(protection_lines(row))
        if not lines:lines.append('Bu kapsamda kayıtlı aday yok; kaynak çalışma durumunu da inceleyin.')
        if data.get('next_after'):lines.append('Sonraki sayfa: --after '+str(data['next_after']))
        return lines
    if 'evidence' in data:
        body=data['evidence']['body'];candidate=body['candidate'];assessment=body['assessment']
        return [f"{data['id']} | {data['kind']} | {safe_text(candidate.get('title') or candidate['url'])}",
            '  Adres: '+safe_text(candidate['url']),'  Kaynak: '+', '.join(safe_text(v) for v in candidate.get('sources',[])),
            '  Gerekçe: '+', '.join(assessment['signals']),f"  Öncelik: {assessment['priority']} | Otomatik sonuç: aday",
            '  Marka bağı: '+{'declared':'kullanıcı tarafından tanımlı','candidate':'karşılaştırma ipucu var','unestablished':'kurulamadı; yalnız kaynak arama sonucu'}[assessment['brand_link_state']],
            f"  Karar: {data['review']['decision'] if data['review'] else 'inceleme bekliyor'} | Yeniden inceleme: {data['needs_review']}",
            f"  Kanıt: {data['evidence_id']} | Gözlem: {data['observation_revision']} | Güncel kapsam: {data['scope_current']}",
            '  Görseller: '+', '.join(a['role']+':'+a['sha256'] for a in body['artifacts'])]
    if 'snapshot' in data:
        report=data.get('report') or {};return [f"Çalışma: {data['id']} | {data['status']}",*['  '+safe_text(v['provider'])+': '+safe_text(v['status']) for v in report.get('sources',[])],
            f"Yeni aday: {report.get('new_candidates',0)} | Değişen: {report.get('changes',0)}",'Adayları görmek için: brand protection candidates --watch-id '+data['watch_id']]
    if 'definition' in data:return [f"{data['id']} | {safe_text(data['definition']['name'])} | sürüm {data['revision']} | etkin {data['enabled']}", '  Domain: '+', '.join(data['definition']['domains'])]
    if 'scope' in data:return [f"{data['id']} | {safe_text(data['scope']['name'])} | sürüm {data['revision']} | {data['binding_state']}"]
    if 'watch' in data:return protection_lines(data['watch'])+['Ağ isteği: hayır. Kapsam: seçili kaynaklar; bütün internet değil.']
    if 'tools' in data:return [v['tool']+': '+v['state'] for v in data['tools']]+['Tarayıcı: '+data['browser_state']]
    if 'body' in data:return [f"Kanıt: {data['id']}",safe_text(json.dumps(data['body'],ensure_ascii=False))]
    if 'sha256' in data:return ['Görsel: '+data['sha256'],f"PNG: {data['bytes']} byte",'Dosya kaydı için --output kullan.']
    if 'decision' in data:return [f"İnceleme: {data['id']} | {data['decision']}",safe_text(data['reason'])]
    return [safe_text(json.dumps(data,ensure_ascii=False))]


def execute_brand_protection(database,args):
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.domain.brand_protection import BrandProtectionError
    service=make_brand_protection_service(database)
    if args.protection_action=='monitor':
        integer(args.cycles,1,100);runs=[]
        for index in range(args.cycles):
            with LocalExecutionLock(database).acquire():
                watch=service.execute(PREFIX+'watch.show',identifier=args.identifier)
                result=service.execute(PREFIX+'run',identifier=watch['id'],expected_revision=watch['revision'],idempotency_key='monitor:'+str(uuid4()))
            runs.append({'id':result['id'],'status':result['status']})
            if not args.json:print('\n'.join(protection_lines(result)),flush=True)
            if index+1<args.cycles:time.sleep(watch['scope']['interval_seconds'])
        return {'runs':runs},['Marka izleme döngüsü tamamlandı.']
    operation=args.protection_operation
    keys=IDENTITY_FIELDS|SCOPE_FIELDS|{'identifier','after','limit','watch_id','domain','kind','decision','reason','evidence_id','expected_revision','expected_observation_revision','enabled','force','idempotency_key'}
    values={k:getattr(args,k) for k in keys if getattr(args,k,None) is not None}
    for field in ('apps','people'):
        if field in values:
            try:values[field]=[json.loads(v) for v in values[field]]
            except (ValueError,RecursionError):raise ValidationError('Uygulama/kişi tanımı geçerli JSON olmalı.') from None
    if operation in WRITES:values.setdefault('idempotency_key','cli:'+str(uuid4()))
    with LocalExecutionLock(database).acquire() if operation in WRITES else nullcontext():
        if operation in (PREFIX+'identity.update',PREFIX+'watch.update',PREFIX+'run',PREFIX+'review') and 'expected_revision' not in values:
            action='identity.show' if operation==PREFIX+'identity.update' else 'candidate.show' if operation==PREFIX+'review' else 'watch.show'
            record=service.execute(PREFIX+action,identifier=values['identifier'])
            values['expected_revision']=record['review_revision'] if operation==PREFIX+'review' else record['revision']
        if operation==PREFIX+'review' and 'expected_observation_revision' not in values:values['expected_observation_revision']=service.execute(PREFIX+'candidate.show',identifier=values['identifier'])['observation_revision']
        result=service.execute(operation,**values)
    if args.protection_action=='artifact-get' and args.output:
        target=args.output
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(base64.b64decode(result.pop('base64'),validate=True))
        result['output']=str(target)
    return result,protection_lines(result)


def execute_platform_brand_protection(context,request):
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.domain.engine import EngineContractError
    values=dict(request.parameters)
    if values.pop('expected_workspace_id')!=context.workspace_id:raise EngineContractError('scope_mismatch','Marka isteği güncel firma alanına ait değil.')
    with LocalExecutionLock(context.database).acquire():return make_brand_protection_service(context.database).execute(request.operation,**values)
