#!/usr/bin/env python3
"""Explicit public-source acceptance; isolated data, no paid source or active scan submission."""
import argparse
import json
from pathlib import Path
import resource
import sys
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--domain',required=True);parser.add_argument('--name',required=True)
    parser.add_argument('--data-dir',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--app-control',action='store_true')
    args=parser.parse_args()
    if args.output.exists() or args.data_dir.exists():parser.error('Use new data/output paths; existing evidence is never overwritten')
    from protection_acceptance_identity import identity
    from xti.adapters.sqlite import SQLiteAssetRepository
    from xti.interfaces.brand_protection import make_brand_protection_service
    from xti.domain.brand_protection import PREFIX
    from xti.adapters.brand_protection_sources import Budget
    args.data_dir.mkdir(parents=True,mode=0o700)
    database=args.data_dir/'xti.db';SQLiteAssetRepository(database).initialize()
    service=make_brand_protection_service(database)
    code=identity()
    brand=service.execute(PREFIX+'identity.add',name=args.name,domains=[args.domain],idempotency_key='live-identity')
    watch=service.execute(PREFIX+'watch.add',identity_id=brand['id'],sources=['web','apple','google','urlscan','crt.sh','stored','social'],
        max_requests=100,max_seconds=480,max_items=40,max_pages=10,idempotency_key='live-watch')
    print('Public-source acceptance started: '+args.domain,flush=True)
    run=service.execute(PREFIX+'run',identifier=watch['id'],expected_revision=1,idempotency_key='live-run')
    candidates=service.execute(PREFIX+'candidates',watch_id=watch['id'],limit=100)
    observed=0
    for row in candidates['items']:
        for artifact in row['evidence']['body']['artifacts']:
            service.execute(PREFIX+'artifact.get',identifier=artifact['sha256']);observed+=1
    controls=[]
    if args.app_control:
        budget=Budget(service.sources.http,{**watch['scope'],'max_requests':10,'max_seconds':120})
        for provider,identifier in [('apple','1055677337'),('google','org.mozilla.focus')]:
            items,report=service.sources._apps(provider,'Firefox Focus','US',budget,10,lambda:False,identifier=identifier)
            controls.append({'provider':provider,'report':report,'identity_matched':len(items)==1 and items[0]['app_id']==identifier,
                'items':[{k:r.get(k) for k in ('store','app_id','title','developer','developer_id','url')} for r in items]})
    peak=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*(1 if sys.platform=='darwin' else 1024)
    result={'code':code,'ended_at':datetime.now(timezone.utc).isoformat(),'kind':'public_live_acceptance','scope':{'name':args.name,'domain':args.domain,'people':[]},
        'run':run,'candidates':candidates,'artifact_references_verified':observed,
        'independent_controls':{'reference':'https://www.firefox.com/en-US/mobile/','not_customer_evidence':True,'items':controls},
        'process_measurement':{'max_reported_child_rss_bytes':peak,'basis':'getrusage(RUSAGE_CHILDREN), not aggregate concurrent Chromium process memory'},
        'paid_api_calls':0,'all_internet_covered':False,'real_vip_accepted':False}
    with args.output.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({'output':str(args.output),'status':run['status'],'candidates':candidates['total_count'],
        'sources':run['report']['sources'],'controls':controls},ensure_ascii=False))
    return 0 if run['status'] in ('complete','partial') else 1

if __name__=='__main__':raise SystemExit(main())
