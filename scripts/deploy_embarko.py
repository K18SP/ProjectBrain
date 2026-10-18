"""Build a source-only Embarko archive and optionally deploy with the saved token."""
import argparse
import json
import os
from pathlib import Path
import secrets
import tarfile
import time
import zipfile

import httpx
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]


def package():
    output = ROOT / 'data' / 'deployment'
    output.mkdir(parents=True, exist_ok=True)
    files = [ROOT/'main.py',ROOT/'requirements.txt']
    for folder in ('app','web'):
        files += [p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
    with tarfile.open(output/'projectbrain.tar.gz','w:gz') as archive, zipfile.ZipFile(output/'projectbrain.zip','w',zipfile.ZIP_DEFLATED) as zipped:
        for path in files:
            name=path.relative_to(ROOT).as_posix()
            archive.add(path,arcname=name)
            zipped.write(path,name)
    return output/'projectbrain.tar.gz'


def deploy(name):
    settings = dotenv_values(ROOT/'.env')
    host = settings.get('FALKORDB_HOST','')
    if host in ('','localhost','127.0.0.1','falkordb') or not settings.get('FALKORDB_PASSWORD'):
        raise SystemExit('A hosted FalkorDB endpoint and password are required. Nothing was deployed.')
    # Verify the remote graph before publishing any app.
    for key in ('FALKORDB_HOST','FALKORDB_PORT','FALKORDB_USERNAME','FALKORDB_PASSWORD','FALKORDB_SSL'):
        if settings.get(key): os.environ[key] = settings[key]
    import sys
    sys.path.insert(0,str(ROOT))
    from app.graph import GraphStore
    GraphStore().ping()
    credential_file = Path.home()/'.embarko'/'credentials'
    token = os.getenv('DEPLOY_TOKEN') or credential_file.read_text().splitlines()[0].removeprefix('DEPLOY_TOKEN=').strip()
    if not token: raise SystemExit('An authenticated Embarko token is required; anonymous deployment is disabled.')
    os.environ['DEPLOY_TOKEN'] = token
    access_file = ROOT/'data'/'hosting.env'
    access_file.parent.mkdir(exist_ok=True)
    access = dotenv_values(access_file)
    password = access.get('APP_PASSWORD') or secrets.token_urlsafe(24)
    set_key(access_file,'APP_USERNAME','reviewer'); set_key(access_file,'APP_PASSWORD',password)
    values = {key:value for key,value in settings.items() if value and key in {
        'FALKORDB_HOST','FALKORDB_PORT','FALKORDB_USERNAME','FALKORDB_PASSWORD','FALKORDB_SSL','OPENROUTER_API_KEY'}}
    # The user approved plaintext database access for public-source demo data only.
    values.pop('GITHUB_TOKEN', None)
    values.update(DEMO_PUBLIC_SOURCES_ONLY='true', FALKORDB_GRAPH='projectbrain_public_demo', APP_USERNAME='reviewer',APP_PASSWORD=password,PUBLIC_DEPLOYMENT='true',PUBLIC_BASE_URL=f'https://{name}.embarko.app',ALLOWED_HOSTS=f'{name}.embarko.app,localhost,127.0.0.1')
    archive = package()
    headers={'Authorization':f'Bearer {token}','X-Agent-Name':'codex'}
    with httpx.Client(base_url='https://ship.embarko.ai',headers=headers,timeout=90) as client:
        with archive.open('rb') as payload:
            response=client.post('/apps',headers={'X-App-Name':name},files={'source':('projectbrain.tar.gz',payload,'application/gzip')})
        response.raise_for_status()
        initial=response.json()
        if not initial.get('app',{}).get('claimed'):
            raise SystemExit('Host did not confirm authenticated ownership; check deployment status before proceeding.')
        configured=client.put(f'/api/apps/{name}/env-vars',json={'vars':[{'key':k,'value':v} for k,v in values.items()]})
        configured.raise_for_status()
        print('Authenticated deployment accepted. Secrets stored; waiting for build.',flush=True)
        # Wait for the first build before redeploying with the stored settings.
        for _ in range(30):
            time.sleep(10)
            first_status=client.get(f'/apps/{name}/status'); first_status.raise_for_status()
            if first_status.json().get('status') in ('live','failed','crashed','not_deployed'): break
        else: raise SystemExit('Initial build is still pending; resume from host status.')
        with archive.open('rb') as payload:
            response=client.post('/apps',headers={'X-App-Name':name},files={'source':('projectbrain.tar.gz',payload,'application/gzip')})
        response.raise_for_status()
        for _ in range(30):
            time.sleep(10)
            status=client.get(f'/apps/{name}/status'); status.raise_for_status(); result=status.json()
            state=result.get('status')
            print('Deployment status:',state,flush=True)
            if state in ('live','failed','crashed','not_deployed'):
                (ROOT/'data'/'deployment-status.json').write_text(json.dumps(result,indent=2))
                if state!='live': raise SystemExit('Deployment needs attention; inspect authenticated host logs.')
                break
        else: raise SystemExit('Build still pending; status recorded by the host.')
    with httpx.Client(base_url=values['PUBLIC_BASE_URL'],auth=('reviewer',password),timeout=30) as client:
        health=client.get('/api/health'); health.raise_for_status()
        if health.json().get('graph')!='connected': raise SystemExit('Hosted graph is not connected.')
        response=client.get('/api/projects'); response.raise_for_status()
    print('Verified hosted API and graph connection:',values['PUBLIC_BASE_URL'])
    print('Workspace sign-in details are in data/hosting.env (not included in the upload).')


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--deploy',action='store_true'); parser.add_argument('--name',default='projectbrain-k18sp')
    args=parser.parse_args()
    if args.deploy: deploy(args.name)
    else: print('Source-only package:',package())
