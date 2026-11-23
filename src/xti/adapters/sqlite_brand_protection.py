"""Indexed current brand candidates, immutable evidence and atomic review/notification receipts."""
import base64
from contextlib import contextmanager
from datetime import datetime, timedelta
import hashlib
import json
import sqlite3
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.brand_protection import (PREFIX, IDENTITY_FIELDS, SCOPE_FIELDS, MAX_ARTIFACT,
    BrandProtectionError, identity, scope, parameters, canonical, digest, assess, validate_body, integer)
from xti.domain.mentions import mention_time

P = 'brand_protection_'


def one(connection, table, identifier):
    row = connection.execute(f'SELECT * FROM {P+table} WHERE id=?', (identifier,)).fetchone()
    if row is None: raise BrandProtectionError('not_found', 'Marka koruma kaydı bu çalışma alanında bulunamadı.')
    return dict(row)


def decoded(row, *fields):
    result = dict(row)
    for field in fields:
        raw, checksum = result.pop(field+'_json'), result.pop(field+'_sha256')
        if raw is None:
            if checksum is not None: raise StorageError('Marka kayıt hash alanları uyuşmuyor.')
            value = None
        else:
            try: value = json.loads(raw)
            except (ValueError, RecursionError): raise StorageError('Marka kayıt gövdesi geçersiz.') from None
            if canonical(value) != raw or digest(value) != checksum: raise StorageError('Marka kanıt kaydı bozuk.')
        result[field] = value
    if 'enabled' in result: result['enabled'] = bool(result['enabled'])
    return result


def identity_in(c, identifier):
    result = decoded(one(c,'identities',identifier),'definition')
    if result['definition'] != identity(result['definition']) or result['organization_id'] != result['definition']['organization_id']: raise StorageError('Marka kimliği kanonik değil.')
    return result


def watch_in(c, identifier):
    result = decoded(one(c,'watches',identifier),'scope')
    if scope(result['scope']) != result['scope'] or result['identity_id'] != result['scope']['identity_id']: raise StorageError('Marka izleme kapsamı bozuk.')
    brand = identity_in(c,result['identity_id'])
    result['binding_state'] = 'disabled' if not result['enabled'] else 'identity_disabled' if not brand['enabled'] else 'ready' if result['identity_revision'] == brand['revision'] else 'scope_changed'
    return result


def evidence_in(c, identifier):
    result = decoded(one(c,'evidence',identifier),'body')
    validate_body(result['body'])
    for art in result['body']['artifacts']:
        row = c.execute(f'SELECT bytes FROM {P}artifacts WHERE id=?',(art['sha256'],)).fetchone()
        if row is None or row[0] != art['bytes']: raise StorageError('Marka görsel kanıt bağı bulunamadı.')
    return result


def candidate_in(c, identifier):
    result = one(c,'candidates',identifier)
    result['evidence'] = evidence_in(c,result['evidence_id'])
    body = result['evidence']['body']; candidate = body['candidate']
    if candidate['kind'] != result['kind'] or candidate['url'] != result['url'] or digest([candidate['kind'],candidate['url'],candidate.get('subject_name')]) != result['candidate_key'] or body['assessment']['priority'] != result['priority']:
        raise StorageError('Marka adayı özgün kanıtla uyuşmuyor.')
    row=c.execute(f'SELECT * FROM {P}reviews WHERE candidate_id=? ORDER BY revision DESC LIMIT 1',(identifier,)).fetchone()
    result['review'] = dict(row) if row else None
    review=result['review']
    if (review['revision'] if review else 0) != result['review_revision']: raise StorageError('Marka inceleme sürümü bozuk.')
    result['needs_review'] = not review or review['evidence_id'] != result['evidence_id'] or review['observation_revision'] != result['observation_revision']
    watch=watch_in(c,result['watch_id'])
    if watch['identity_id']!=result['identity_id']:raise StorageError('Marka adayı başka kimliğe bağlanmış.')
    result['scope_current'] = watch['revision']==result['scope_revision'] and watch['identity_revision']==result['identity_revision'] and watch['binding_state']=='ready'
    return result


def change_in(c, identifier):
    result=one(c,'changes',identifier)
    result['before']=evidence_in(c,result['before_evidence_id']) if result['before_evidence_id'] else None
    result['after']=evidence_in(c,result['after_evidence_id'])
    return result


def _company_in(c, organization_id, *, offset=0, limit=20):
    predicate=f'identity_id IN (SELECT id FROM {P}identities WHERE organization_id=?)'
    total=c.execute(f'SELECT COUNT(*) FROM {P}candidates WHERE '+predicate,(organization_id,)).fetchone()[0]
    items=c.execute(f'SELECT id FROM {P}candidates WHERE '+predicate+' ORDER BY sequence DESC LIMIT ? OFFSET ?',(organization_id,limit,offset)).fetchall()
    watches=c.execute(f'SELECT id FROM {P}watches WHERE '+predicate+' ORDER BY sequence DESC LIMIT ? OFFSET ?',(organization_id,limit,offset)).fetchall()
    watch_total=c.execute(f'SELECT COUNT(*) FROM {P}watches WHERE '+predicate,(organization_id,)).fetchone()[0]
    coverage=[]
    for row in watches:
        watch=watch_in(c,row[0]);run=decoded(one(c,'runs',watch['last_run_id']),'snapshot','report') if watch['last_run_id'] else None
        coverage.append({'id':watch['id'],'name':watch['scope']['name'],'binding_state':watch['binding_state'],
            'last_run_id':run['id'] if run else None,'last_status':run['status'] if run else 'not_checked',
            'last_checked_at':(run['finished_at'] or run['started_at']) if run else None,
            'sources':((run or {}).get('report') or {}).get('sources',[]),'old_evidence_preserved':True})
    return {'items':[candidate_in(c,row[0]) for row in items], 'total_count':total,
        'state':'recorded' if total else 'no_recorded_candidates' if watch_total else 'not_configured',
        'offset':offset,'limit':limit,'has_more':total>offset+limit,
        'watches':{'items':coverage,'total_count':watch_total,'has_more':watch_total>offset+limit,'offset':offset,'limit':limit}}


def company_in(c, organization_id, *, offset=0, limit=20):
    previous=c.row_factory;c.row_factory=sqlite3.Row
    try:return _company_in(c,organization_id,offset=offset,limit=limit)
    finally:c.row_factory=previous


def case_snapshot(connection, identifier):
    from xti.domain.cases import CaseEvidenceSnapshot, canonical_snapshot
    previous=connection.row_factory;connection.row_factory=sqlite3.Row
    try:
        record=candidate_in(connection,identifier)
        payload,checksum=canonical_snapshot({'version':1,'type':'brand_protection','candidate':record})
        body=record['evidence']['body']
        return CaseEvidenceSnapshot('brand_protection',identifier,body['brand']['name']+' — '+body['candidate'].get('title',record['url'])[:200],
            'brand protection candidate-show '+identifier,payload,checksum)
    finally:connection.row_factory=previous


def validate_case_snapshot(value):
    from xti.domain.mentions import mention_uuid
    try:
        if set(value)!={'version','type','candidate'} or value['version']!=1 or value['type']!='brand_protection':raise ValueError()
        record=value['candidate'];evidence=record['evidence'];body=validate_body(evidence['body'])
        for identifier in (record['id'],record['watch_id'],record['identity_id'],evidence['id']):mention_uuid(identifier)
        if record['evidence_id']!=evidence['id'] or record['candidate_key']!=digest([body['candidate']['kind'],body['candidate']['url'],body['candidate'].get('subject_name')]):raise ValueError()
        if record['url']!=body['candidate']['url'] or record['priority']!=body['assessment']['priority']:raise ValueError()
        return value
    except (KeyError,TypeError,ValueError):raise StorageError('Marka vaka kopyası geçersiz.') from None


def notification_in(connection, identifier):
    previous=connection.row_factory;connection.row_factory=sqlite3.Row
    try:
        notice=one(connection,'notifications',identifier)
        change=change_in(connection,notice['change_id'])
        run=decoded(one(connection,'runs',change['run_id']),'snapshot','report')
        candidate=one(connection,'candidates',change['candidate_id'])
        if change['watch_id']!=run['watch_id'] or candidate['watch_id']!=run['watch_id'] or run['status']=='running':raise StorageError('Marka bildiriminin çalışma kapsamı uyuşmuyor.')
        for evidence in (change['before'],change['after']):
            if evidence is not None:
                body=evidence['body'];item=body['candidate']
                if digest([item['kind'],item['url'],item.get('subject_name')])!=candidate['candidate_key']:raise StorageError('Marka bildirimi başka aday kanıtına bağlı.')
        if change['after']['body']['brand']!=run['snapshot']['brand']:raise StorageError('Marka bildirimi tarihî kimliğe bağlı değil.')
        return {'id':identifier,'change':change,'before':change['before'],'after':change['after']}
    finally:connection.row_factory=previous


class SQLiteBrandProtectionRepository:
    def __init__(self,path): self.storage=SQLiteAssetRepository(path)

    @contextmanager
    def connection(self, *, write=False):
        with self.storage._connection(readonly=not write) as c:
            c.row_factory=sqlite3.Row
            c.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            try:
                yield c
                if write: c.commit()
            finally:
                if c.in_transaction: c.rollback()

    def read(self,operation,values):
        values=parameters(operation,values); name=operation.removeprefix(PREFIX)
        with self.connection() as c:
            loaders={'identity.show':identity_in,'watch.show':watch_in,'plan':watch_in,'candidate.show':candidate_in,'evidence.show':evidence_in,'run.show':lambda c,i:decoded(one(c,'runs',i),'snapshot','report')}
            if name in loaders:
                result=loaders[name](c,values['identifier'])
                if name=='plan': return {'watch':result,'identity':identity_in(c,result['identity_id']),'network_access':False,'all_internet_covered':False}
                return result
            if name=='artifact.get':
                row=one(c,'artifacts',values['identifier']); self._artifact(row['id'],row['body'])
                if len(row['body'])!=row['bytes']: raise StorageError('Marka görsel boyutu bozuk.')
                return {'sha256':row['id'],'mime_type':'image/png','bytes':row['bytes'],'base64':base64.b64encode(row['body']).decode(),'content_warning':'Public captured content; not automatically text-redacted.'}
            if name=='report':
                clauses,params=self._filters(values,'candidates')
                rows=c.execute(f'SELECT priority,COUNT(*) FROM {P}candidates WHERE '+clauses+' GROUP BY priority',params).fetchall()
                return {'total_candidates':sum(r[1] for r in rows),'priorities':{r[0]:r[1] for r in rows},'automatic_confirmed_impersonation':False,'notes':['Kaynak ve kanıt adaydır; insan kararını ayrı inceleyin.']}
            table={'identities':'identities','watches':'watches','runs':'runs','candidates':'candidates','reviews':'reviews','changes':'changes'}[name]
            clause,args=self._filters(values,table)
            if name=='reviews': clause+=' AND candidate_id=?';args.append(values['identifier'])
            if name=='candidates' and 'decision' in values:
                clause+=f' AND EXISTS (SELECT 1 FROM {P}reviews r WHERE r.candidate_id={P}candidates.id AND r.revision={P}candidates.review_revision AND r.decision=?)';args.append(values['decision'])
            total=c.execute(f'SELECT COUNT(*) FROM {P+table} WHERE '+clause,args).fetchone()[0]
            rows=c.execute(f'SELECT * FROM {P+table} WHERE '+clause+' AND sequence>? ORDER BY sequence LIMIT ?',(*args,values['after'],values['limit']+1)).fetchall()
            more=len(rows)>values['limit'];rows=rows[:values['limit']]
            loader={'identities':identity_in,'watches':watch_in,'candidates':candidate_in,'changes':change_in}.get(name)
            items=[];size=0
            for row in rows:
                item=loader(c,row['id']) if loader else decoded(row,'snapshot','report') if name=='runs' else dict(row)
                encoded=len(canonical(item).encode())
                if items and size+encoded>2*1024*1024:more=True;break
                items.append(item);size+=encoded
            return {'items':items,'total_count':total,'next_after':items[-1]['sequence'] if more else None,'page_byte_budget':2*1024*1024}

    @staticmethod
    def _filters(v,table):
        clause='1=1';args=[]
        if 'watch_id' in v:
            clause+= ' AND '+('id' if table=='watches' else 'watch_id')+'=?';args.append(v['watch_id'])
        if 'identity_id' in v or 'domain' in v:
            target='identity_id' if table in ('watches','candidates') else f'(SELECT identity_id FROM {P}watches WHERE id={P+table}.watch_id)'
            if 'identity_id' in v: clause+=' AND '+target+'=?';args.append(v['identity_id'])
            if 'domain' in v: clause+=f' AND {target} IN (SELECT identity_id FROM {P}domains WHERE domain=?)';args.append(v['domain'])
        if 'kind' in v: clause+=' AND kind=?';args.append(v['kind'])
        return clause,args

    @staticmethod
    def _request(operation,values): return digest({'operation':operation,'parameters':values})

    def _replay(self,c,operation,values):
        row=c.execute(f'SELECT * FROM {P}mutations WHERE request_key=?',(values['idempotency_key'],)).fetchone()
        if row:
            if row['request_sha256']!=self._request(operation,values): raise BrandProtectionError('idempotency_conflict','Tekrar anahtarı farklı marka isteğinde kullanılmış.')
            return decoded(row,'result')['result']

    @staticmethod
    def _idle(c,watch_id):
        if c.execute(f"SELECT 1 FROM {P}runs WHERE watch_id=? AND status='running' LIMIT 1",(watch_id,)).fetchone():
            raise BrandProtectionError('run_in_progress','Marka çalışması sürüyor; durmuş çalışmayı önce açıkça kurtarın.')

    def mutate(self,operation,values,at):
        values=parameters(operation,values);mention_time(at); name=operation.removeprefix(PREFIX)
        with self.connection(write=True) as c:
            replay=self._replay(c,operation,values)
            if replay is not None:return {**replay,'replayed':True}
            identifier=values.get('identifier',str(uuid4()))
            if name.startswith('identity.'):
                current=identity_in(c,identifier) if name.endswith('.update') else None
                if current and current['revision']!=values['expected_revision']: raise BrandProtectionError('revision_conflict','Marka kimliği sürümü değişti.')
                definition=identity({**(current['definition'] if current else {}),**{k:v for k,v in values.items() if k in IDENTITY_FIELDS}})
                if definition['organization_id']:
                    if c.execute('SELECT 1 FROM organizations WHERE id=? AND active=1',(definition['organization_id'],)).fetchone() is None: raise BrandProtectionError('not_found','Kuruluş bu çalışma alanında etkin değil.')
                if current:
                    c.execute(f'UPDATE {P}identities SET organization_id=?,definition_json=?,definition_sha256=?,revision=revision+1,enabled=?,updated_at=? WHERE id=?',(definition['organization_id'],canonical(definition),digest(definition),int(values.get('enabled',current['enabled'])),at,identifier))
                else:c.execute(f'INSERT INTO {P}identities (id,organization_id,revision,enabled,definition_json,definition_sha256,created_at,updated_at) VALUES (?,?,1,1,?,?,?,?)',(identifier,definition['organization_id'],canonical(definition),digest(definition),at,at))
                c.execute(f'DELETE FROM {P}domains WHERE identity_id=?',(identifier,));c.executemany(f'INSERT INTO {P}domains (identity_id,domain) VALUES (?,?)',[(identifier,d) for d in definition['domains']])
                result=identity_in(c,identifier)
            elif name.startswith('watch.'):
                current=watch_in(c,identifier) if name.endswith('.update') else None
                if current:
                    if current['revision']!=values['expected_revision']:raise BrandProtectionError('revision_conflict','Marka izleme sürümü değişti.')
                    self._idle(c,identifier)
                selected=scope({**(current['scope'] if current else {}),**{k:v for k,v in values.items() if k in SCOPE_FIELDS}})
                brand=identity_in(c,selected['identity_id'])
                stopping=current and values.get('enabled') is False and not SCOPE_FIELDS.intersection(values)
                if not stopping and not brand['enabled']:raise BrandProtectionError('identity_disabled','Marka kimliği devre dışı.')
                if current and selected['identity_id']!=current['identity_id']:raise BrandProtectionError('scope_changed','Farklı marka için yeni izleme oluşturun.')
                revision=current['identity_revision'] if stopping else brand['revision']
                if current:c.execute(f'UPDATE {P}watches SET scope_json=?,scope_sha256=?,revision=revision+1,identity_revision=?,enabled=?,updated_at=? WHERE id=?',(canonical(selected),digest(selected),revision,int(values.get('enabled',current['enabled'])),at,identifier))
                else:c.execute(f'INSERT INTO {P}watches (id,identity_id,revision,enabled,scope_json,scope_sha256,identity_revision,retained_after,created_at,updated_at) VALUES (?,?,1,1,?,?,?,0,?,?)',(identifier,selected['identity_id'],canonical(selected),digest(selected),revision,at,at))
                result=watch_in(c,identifier)
            elif name=='review':
                record=candidate_in(c,identifier)
                if record['review_revision']!=values['expected_revision'] or record['observation_revision']!=values['expected_observation_revision'] or record['evidence_id']!=values['evidence_id']:
                    raise BrandProtectionError('revision_conflict','Marka adayının kanıtı veya incelemesi değişti.')
                review_id=str(uuid4());revision=record['review_revision']+1
                c.execute(f'INSERT INTO {P}reviews (id,candidate_id,evidence_id,revision,observation_revision,decision,reason,created_at) VALUES (?,?,?,?,?,?,?,?)',(review_id,identifier,record['evidence_id'],revision,record['observation_revision'],values['decision'],values['reason'],at))
                c.execute(f'UPDATE {P}candidates SET review_revision=? WHERE id=?',(revision,identifier));result=dict(c.execute(f'SELECT * FROM {P}reviews WHERE id=?',(review_id,)).fetchone())
            elif name=='recover':
                result=decoded(one(c,'runs',identifier),'snapshot','report')
                if result['status']=='running':
                    report={'status':'interrupted','reason':'explicit_operator_recovery','no_source_request':True}
                    c.execute(f"UPDATE {P}runs SET status='interrupted',report_json=?,report_sha256=?,finished_at=? WHERE id=?",(canonical(report),digest(report),at,identifier));result=decoded(one(c,'runs',identifier),'snapshot','report')
            else:raise BrandProtectionError('invalid_parameters','Bilinmeyen marka yazma işlemi.')
            c.execute(f'INSERT INTO {P}mutations (id,request_key,request_sha256,result_json,result_sha256,created_at) VALUES (?,?,?,?,?,?)',(str(uuid4()),values['idempotency_key'],self._request(operation,values),canonical(result),digest(result),at))
            return result

    def reserve(self,values,at):
        values=parameters(PREFIX+'run',values);mention_time(at)
        with self.connection(write=True) as c:
            row=c.execute(f'SELECT * FROM {P}runs WHERE request_key=?',(values['idempotency_key'],)).fetchone()
            if row:
                if row['request_sha256']!=self._request(PREFIX+'run',values):raise BrandProtectionError('idempotency_conflict','Tekrar anahtarı farklı marka çalışmasına ait.')
                return decoded(row,'snapshot','report'),True
            watch=watch_in(c,values['identifier'])
            if watch['revision']!=values['expected_revision']:raise BrandProtectionError('revision_conflict','Marka izleme sürümü değişti.')
            if watch['binding_state']!='ready':raise BrandProtectionError('scope_changed','Marka kimliği/izleme kapsamı hazır değil; güncel kapsamı açıkça bağlayın.')
            self._idle(c,watch['id'])
            if watch['last_started_at'] and not values.get('force') and datetime.fromisoformat(at)<datetime.fromisoformat(watch['last_started_at'])+timedelta(seconds=watch['scope']['interval_seconds']):raise BrandProtectionError('not_due','Marka kontrol aralığı henüz dolmadı.')
            brand=identity_in(c,watch['identity_id'])
            snapshot={'scope':watch['scope'],'watch_revision':watch['revision'],'brand':brand['definition'],'identity_revision':brand['revision'],'retained_after':watch['retained_after']}
            identifier=str(uuid4());c.execute(f'INSERT INTO {P}runs (id,watch_id,request_key,request_sha256,snapshot_json,snapshot_sha256,status,started_at) VALUES (?,?,?,?,?,?,?,?)',(identifier,watch['id'],values['idempotency_key'],self._request(PREFIX+'run',values),canonical(snapshot),digest(snapshot),'running',at))
            c.execute(f'UPDATE {P}watches SET last_started_at=?,last_run_id=? WHERE id=?',(at,identifier,watch['id']))
            return decoded(one(c,'runs',identifier),'snapshot','report'),False

    def retained(self,watch_id,limit,after):
        with self.connection() as c:
            rows=c.execute(f'SELECT * FROM {P}candidates WHERE watch_id=? AND sequence>? ORDER BY sequence LIMIT ?',(watch_id,after,limit+1)).fetchall()
            more=len(rows)>limit; rows=rows[:limit]
            return {'items':[candidate_in(c,r['id'])['evidence']['body']['candidate'] for r in rows],'next_after':rows[-1]['sequence'] if more else None}

    @staticmethod
    def _artifact(identifier,body):
        if not isinstance(body,bytes) or not 1<=len(body)<=MAX_ARTIFACT or not body.startswith(b'\x89PNG\r\n\x1a\n') or hashlib.sha256(body).hexdigest()!=identifier:raise StorageError('Görsel boyut/biçim/hash kanıtı geçersiz.')

    def finish(self,run_id,result,at):
        mention_time(at)
        with self.connection(write=True) as c:
            run=decoded(one(c,'runs',run_id),'snapshot','report')
            if run['status']!='running':raise BrandProtectionError('run_finished','Marka çalışması zaten kapatılmış.')
            snapshot=run['snapshot'];watch=watch_in(c,run['watch_id'])
            if watch['revision']!=snapshot['watch_revision'] or watch['identity_revision']!=snapshot['identity_revision'] or watch['binding_state']!='ready':raise BrandProtectionError('scope_changed','Marka kapsamı toplama sırasında değişti; sonuç yayınlanmadı.')
            if result.get('status') not in ('complete','partial','failed','interrupted') or not isinstance(result.get('candidates'),list) or len(result['candidates'])>snapshot['scope']['max_items']:raise StorageError('Marka toplama sonucu kapsamı geçersiz.')
            reference=dict(result['reference']);reference_artifacts=reference.pop('_artifacts',[])
            artifacts=result.get('artifacts',{});counts={'new_candidates':0,'new_evidence':0,'new_artifacts':0,'changes':0}
            baseline=c.execute(f"SELECT 1 FROM {P}runs WHERE watch_id=? AND status IN ('complete','partial') LIMIT 1",(run['watch_id'],)).fetchone() is None
            seen=set()
            for raw in result['candidates']:
                candidate=dict(raw); candidate_artifacts=candidate.pop('_artifacts',[])
                candidate_key=digest([candidate['kind'],candidate['url'],candidate.get('subject_name')])
                if reference.get('status') not in (None,'complete','partial') and c.execute(f'SELECT 1 FROM {P}candidates WHERE watch_id=? AND candidate_key=?',(run['watch_id'],candidate_key)).fetchone():
                    # A reference outage must not replace a retained comparison with missing evidence.
                    continue
                body={'policy':'brand-protection-v1','brand':snapshot['brand'],'reference':reference,'candidate':candidate,'assessment':assess(snapshot['brand'],reference,candidate),'artifacts':reference_artifacts+candidate_artifacts}
                validate_body(body)
                key=digest([candidate['kind'],candidate['url'],candidate.get('subject_name')])
                if key in seen:raise StorageError('Toplama sonucunda yinelenen marka adayı var.')
                seen.add(key)
                for artifact in body['artifacts']:
                    found=c.execute(f'SELECT bytes FROM {P}artifacts WHERE id=?',(artifact['sha256'],)).fetchone()
                    if found:
                        if found[0]!=artifact['bytes']:raise StorageError('Görsel boyutu saklı kanıtla uyuşmuyor.')
                    else:
                        blob=artifacts.get(artifact['sha256']);self._artifact(artifact['sha256'],blob)
                        if len(blob)!=artifact['bytes']:raise StorageError('Görsel bildirim boyutu uyuşmuyor.')
                        c.execute(f'INSERT INTO {P}artifacts (id,body,bytes,created_at) VALUES (?,?,?,?)',(artifact['sha256'],blob,len(blob),at));counts['new_artifacts']+=1
                fingerprint=digest(body);row=c.execute(f'SELECT id FROM {P}evidence WHERE body_sha256=?',(fingerprint,)).fetchone()
                evidence_id=row[0] if row else str(uuid4())
                if not row:c.execute(f'INSERT INTO {P}evidence (id,body_json,body_sha256,created_at) VALUES (?,?,?,?)',(evidence_id,canonical(body),fingerprint,at));counts['new_evidence']+=1
                old=c.execute(f'SELECT * FROM {P}candidates WHERE watch_id=? AND candidate_key=?',(run['watch_id'],key)).fetchone()
                identifier=old['id'] if old else str(uuid4());changed=bool(old and old['evidence_id']!=evidence_id)
                if old:
                    candidate_in(c,identifier)
                    c.execute(f'UPDATE {P}candidates SET evidence_id=?,observation_revision=observation_revision+?,scope_revision=?,identity_revision=?,priority=?,last_seen=? WHERE id=?',(evidence_id,int(changed),snapshot['watch_revision'],snapshot['identity_revision'],body['assessment']['priority'],at,identifier))
                else:
                    c.execute(f'INSERT INTO {P}candidates (id,watch_id,identity_id,candidate_key,kind,url,evidence_id,scope_revision,identity_revision,observation_revision,review_revision,priority,first_seen,last_seen) VALUES (?,?,?,?,?,?,?,?,?,1,0,?,?,?)',(identifier,run['watch_id'],watch['identity_id'],key,candidate['kind'],candidate['url'],evidence_id,snapshot['watch_revision'],snapshot['identity_revision'],body['assessment']['priority'],at,at));counts['new_candidates']+=1
                if changed or (not old and not baseline):
                    from xti.adapters.sqlite_notification_sequence import next_notification_sequence
                    change=str(uuid4());c.execute(f'INSERT INTO {P}changes (id,watch_id,run_id,candidate_id,kind,before_evidence_id,after_evidence_id,created_at) VALUES (?,?,?,?,?,?,?,?)',(change,run['watch_id'],run_id,identifier,'changed' if changed else 'new',old['evidence_id'] if old else None,evidence_id,at))
                    c.execute(f'INSERT INTO {P}notifications (sequence,id,change_id,created_at) VALUES (?,?,?,?)',(next_notification_sequence(c),str(uuid4()),change,at));counts['changes']+=1
            report={k:v for k,v in result.items() if k not in ('reference','candidates','artifacts')}
            report.update(counts,policy='brand-protection-v1',silent_baseline=baseline,all_internet_covered=False,retained_data_preserved=True)
            c.execute(f'UPDATE {P}runs SET status=?,report_json=?,report_sha256=?,finished_at=? WHERE id=?',(result['status'],canonical(report),digest(report),at,run_id))
            c.execute(f'UPDATE {P}watches SET retained_after=? WHERE id=?',(integer(result.get('retained_after',0),0,2**63-1),run['watch_id']))
            return decoded(one(c,'runs',run_id),'snapshot','report')


class BrandCooldowns:
    """Provider host waits survive runs and are isolated inside the company workspace."""
    def __init__(self,path):self.repository=SQLiteBrandProtectionRepository(path)
    def get(self,host):
        import math
        from xti.domain.assets import normalize_domain
        host=normalize_domain(host)
        with self.repository.connection() as c:
            row=c.execute(f'SELECT not_before FROM {P}cooldowns WHERE id=?',(host,)).fetchone()
            if row and (not isinstance(row[0],(int,float)) or not math.isfinite(row[0]) or row[0]<0):raise StorageError('Marka kaynak bekleme kaydı bozuk.')
            return row[0] if row else 0
    def extend(self,host,deadline,at):
        import math
        from xti.domain.assets import normalize_domain
        host=normalize_domain(host);mention_time(at)
        if not isinstance(deadline,(int,float)) or not math.isfinite(deadline) or deadline<0:raise StorageError('Kaynak bekleme zamanı geçersiz.')
        with self.repository.connection(write=True) as c:
            c.execute(f"INSERT INTO {P}cooldowns (id,not_before,reason,updated_at) VALUES (?,?,'provider_wait',?) ON CONFLICT(id) DO UPDATE SET not_before=MAX(not_before,excluded.not_before),updated_at=excluded.updated_at",(host,deadline,at))
