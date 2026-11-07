"""Freeze native agent installation, replay a submission, and export artifacts."""
import hashlib
import gzip
import tarfile
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from securevibebench_evaluation.harbor_native import configure_dns, digest, write_config
for parent in Path(__file__).resolve().parents:
    if (parent / 'tools/image_build').is_dir():
        sys.path.insert(0, str(parent))
        break
from tools.image_build.task_assets import shared_hashes
from tools.image_build.metadata import REPOSITORY_URL, SOURCE_LABEL

TAG = 'securevibebench/cpython-61721:offline-20261107'


def native_install(builder, name, image, *, public):
    folder = builder.work/name
    if (folder/'jobs').exists():
        archived=builder.work/'archive'
        archived.mkdir(exist_ok=True)
        shutil.move(str(folder),str(archived/(name+'-'+str(time.time_ns()))))
    folder.mkdir(parents=True,exist_ok=True)
    task = folder/'tasks'/builder.task.name
    if not task.exists(): shutil.copytree(builder.task,task)
    builder.task_config(image,task,public=public)
    configure_dns(task/'environment',builder.args.cpus)
    # Install-only has no agent execution phase, so Harbor may create no egress sidecar.
    import yaml
    overlay=task/'environment/docker-compose.yaml'
    network=yaml.safe_load(overlay.read_text())
    network['services'].pop('harbor-docker-egress-control-sidecar',None)
    # Docker commit promotes bind targets to image volumes. DNS files must not become volumes.
    network['services']['main'].pop('volumes',None)
    if public:
        shared_network = 'junkai-arvo-image-preparation'
        available = subprocess.run(['docker','network','inspect',shared_network],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if available.returncode:
            builder.run('create-preparation-network',['docker','network','create','--label','securevibebench.purpose=online-preparation',shared_network])
        network.setdefault('networks',{})['default']={'external':True,'name':shared_network}
        network['services']['main']['dns']=[line.split()[1] for line in (task/'environment/resolv.conf').read_text().splitlines() if line.startswith('nameserver ')]
    overlay.write_text(yaml.safe_dump(network,sort_keys=False))
    config = folder/'job-input.json'
    config.write_text(json.dumps({'tasks':[{'path':str(task)}]},indent=2)+'\n')
    jobs = folder/'jobs'
    jobname = 'junkai-arvo-'+str(builder.config['metadata']['localid'])+'-'+name
    empty_env=builder.work/'empty.env'
    empty_env.write_text('')
    command = [str(Path(sys.executable).with_name('harbor')),'run','-c',str(config),'-a','mini-swe-agent',
               '--install-only','--skip-credential-checks','--env-file',str(empty_env),'--jobs-dir',str(jobs),'--job-name',jobname]
    if public: command += ['--no-delete','--ek','keep_containers=true','--agent-setup-timeout-multiplier','5']
    builder.run(name,command)
    records = list((jobs/jobname).glob('*/result.json'))
    if len(records)!=1: raise RuntimeError('Expected one native installation result')
    result=json.loads(records[0].read_text())
    if result.get('exception_info'): raise RuntimeError('Native installation failed: '+str(result['exception_info'].get('exception_type')))
    evidence=builder.bundle/'evidence'/name
    evidence.mkdir(parents=True,exist_ok=True)
    shutil.copy2(records[0],evidence/'result.json')
    for path in records[0].parent.rglob('*'):
        if path.is_file() and path.suffix in ('.log','.txt'):
            destination=evidence/path.relative_to(records[0].parent)
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,destination)
    return records[0].parent.name.lower()+'__env-main-1'


def audit_image(builder,image):
    code='''import json,subprocess,os,hashlib
from pathlib import Path
root=Path(json.loads(Path('/opt/svb/task.json').read_text())['repo_cwd'])
for name in ['/root/.codex/auth.json','/root/.claude/.credentials.json','/root/.docker/config.json','/root/.netrc']:
 if Path(name).exists():raise RuntimeError('Unexpected agent credential file')
mini_env=Path('/root/.config/mini-swe-agent/.env')
if mini_env.exists():
 for line in mini_env.read_text().splitlines():
  name,sep,value=line.partition('=')
  if sep and 'API_KEY' in name.upper() and value.strip().strip(chr(34)+chr(39)):
   raise RuntimeError('Unexpected saved mini credential')
keys=[key for key,value in os.environ.items() if value and any(marker in key.upper() for marker in ['API_KEY','AUTH_TOKEN','ACCESS_TOKEN','AWS_ACCESS_KEY','AWS_SECRET','GITHUB_TOKEN','GH_TOKEN','HF_TOKEN'])]
if keys:raise RuntimeError('Unexpected credential variables: '+','.join(keys))
def git(*args):return subprocess.check_output(['git',*args],cwd=root,text=True).strip()
assert git('rev-list','--all','--count')=='1'
assert not git('status','--porcelain')
print(json.dumps({'commit_count':1,'tree':git('rev-parse','svb-start^{tree}'),'credentials_present':False,'baseline_sha256':hashlib.sha256(Path('/opt/svb/baseline.json').read_bytes()).hexdigest()}))
'''
    result=builder.run('image-audit',['docker','run','--rm','--network','none','--entrypoint','/opt/svb/python/bin/python3',image,'-I','-c',code],capture=True)
    audit=json.loads(result.stdout)
    if audit['baseline_sha256']!=builder.state['offline_gold_baseline_sha256']:raise RuntimeError('Baseline changed in frozen image')
    return audit


def replay(builder,image):
    builder.task_config(image,builder.task,prepared=True)
    if (builder.work/'submission-replay').exists():
        archive=builder.work/'archive'
        archive.mkdir(exist_ok=True)
        shutil.move(str(builder.work/'submission-replay'),str(archive/('submission-replay-'+str(time.time_ns()))))
    from tools.image_build.verify import score_local
    result=score_local(builder,builder.args.submission.resolve(),builder.work/'submission-replay',image,'submission-replay')
    if len(result.get('results',[]))!=1 or result['results'][0].get('exception'):
        raise RuntimeError('Submission replay did not finish normally')
    for path in (builder.work/'submission-replay').rglob('verifier/result.json'):
        target=builder.bundle/'evidence/submission-replay'
        target.mkdir(parents=True,exist_ok=True)
        for name in ['result.json','reward.json','network.json','functional.json','compile.log.exit','functional.log.exit','poc.log.exit']:
            source=path.parent/name
            if source.exists():shutil.copy2(source,target/name)
    return result['results'][0]['rewards']


def export_image(builder,image):
    archive=builder.bundle/'cpython-61721-offline.tar.gz'
    print('Exporting '+str(archive),flush=True)
    with archive.open('wb') as stream, (builder.logs/'docker-save.log').open('wb') as log:
        save=subprocess.Popen(['docker','save',image],stdout=subprocess.PIPE,stderr=log,env=builder.env)
        compress=subprocess.Popen(['gzip','-n','-c'],stdin=save.stdout,stdout=stream,stderr=log,env=builder.env)
        save.stdout.close()
        if compress.wait() or save.wait():raise RuntimeError('Image export failed')
    sha=hashlib.sha256()
    with archive.open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b''):sha.update(chunk)
    return {'filename':archive.name,'sha256':sha.hexdigest(),'bytes':archive.stat().st_size}


def host_wheels(builder, wheels):
    from importlib.metadata import distribution
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    pending=[('securevibebench',frozenset())]
    seen, versions=set(), {}
    while pending:
        name,extras=pending.pop()
        key=(canonicalize_name(name),extras)
        if key in seen:continue
        seen.add(key)
        package=distribution(name)
        if canonicalize_name(name)!='securevibebench':
            versions[package.metadata['Name']]=package.version
        for text in package.requires or []:
            requirement=Requirement(text)
            if requirement.marker and not any(requirement.marker.evaluate({'extra':extra}) for extra in extras or {''}):continue
            pending.append((requirement.name,frozenset(requirement.extras)))
    lock=builder.bundle/'requirements-host.lock'
    lock.write_text(''.join(name+'=='+version+'\n' for name,version in sorted(versions.items(),key=lambda item:item[0].lower())))
    builder.run('host-wheelhouse',[sys.executable,'-m','pip','download','--only-binary=:all:','--no-deps','--dest',str(wheels),'-r',str(lock)])


def frozen_agent_image(builder):
    native=native_install(builder,'native-install',builder.candidate,public=True)
    info=json.loads(builder.run('inspect-native',['docker','inspect',native],capture=True).stdout)[0]
    changes=[f'LABEL {SOURCE_LABEL}={REPOSITORY_URL}','ENV UV_OFFLINE=1','WORKDIR /src/cpython3','ENTRYPOINT ["/usr/bin/env"]','CMD ["bash","-c","sleep infinity"]',
             'LABEL org.opencontainers.image.title="SecureVibeBench CPython 61721 offline environment"']
    for item in info['Config'].get('Env',[]):
        key,value=item.split('=',1)
        if value and any(marker in key.upper() for marker in ['API_KEY','AUTH_TOKEN','ACCESS_TOKEN','AWS_ACCESS_KEY','AWS_SECRET','GITHUB_TOKEN','GH_TOKEN','HF_TOKEN']):
            raise RuntimeError('Unexpected credential in native setup image')
        if 'proxy' in key.lower() or key.startswith('HARBOR_'):changes.append('ENV '+key+'=')
    for key in (info['Config'].get('Labels') or {}):
        if key.startswith('com.docker.compose.'):changes.append('LABEL '+key+'=""')
    command=['docker','commit']
    for change in changes:command+=['--change',change]
    builder.run('commit-native',command+[native,TAG])
    image=builder.run('inspect-frozen',['docker','image','inspect',TAG,'--format','{{.Id}}'],capture=True).stdout.strip()
    builder.state['frozen_image']=image;builder.save()
    platform=builder.run('image-platform',['docker','image','inspect',image,'--format','{{.Os}}/{{.Architecture}}'],capture=True).stdout.strip()
    if platform!='linux/amd64':raise RuntimeError('Unexpected image platform: '+platform)
    audit=audit_image(builder,image)
    builder.state['image_audit']=audit
    builder.save()
    return image,audit


def finish(builder):
    here=Path(__file__).resolve().parent
    builder.args.submission=builder.args.submission.resolve()
    builder.env={key:value for key,value in builder.env.items() if not any(marker in key.upper() for marker in ('TOKEN','SECRET','API_KEY','ACCESS_KEY','CODEX_AUTH'))}
    os.chdir(builder.work)
    (builder.task/'environment/Dockerfile').write_text('FROM '+TAG+'\nWORKDIR /src/cpython3\n')
    metadata=builder.config['metadata']
    (builder.task/'environment/svb/reference.sh').write_text('#!/bin/bash\nset -euo pipefail\ngit checkout '+metadata['vic']+'\nexec bash -e /opt/svb/functional.sh\n')
    if builder.state.get('frozen_image') and builder.state.get('image_audit') and builder.state['stages'].get('image-audit',{}).get('state')=='completed':
        image,audit=builder.state['frozen_image'],builder.state['image_audit']
    else:
        image,audit=frozen_agent_image(builder)
    native_install(builder,'offline-native-install',image,public=False)
    builder.run('native-package-inventory',['docker','run','--rm','--network','none','--entrypoint','bash',image,'-lc',
                'uv tool list && uv pip freeze --python /root/.local/share/uv/tools/mini-swe-agent/bin/python'],capture=True)
    rewards=replay(builder,image)
    archive=export_image(builder,image)
    package_bundle(builder,image,audit,rewards,archive)


def package_bundle(builder,image,audit,rewards,archive):
    here=Path(__file__).resolve().parent
    metadata=builder.config['metadata']
    recipe=builder.bundle/'recipe'
    shutil.copytree(here,recipe,ignore=shutil.ignore_patterns('__pycache__'),dirs_exist_ok=True)
    shutil.copytree(here.parent/'image_build',builder.bundle/'tools/image_build',ignore=shutil.ignore_patterns('__pycache__'),dirs_exist_ok=True)
    shutil.copy2(here/'README.md',builder.bundle/'README.md')
    shutil.copy2(builder.work/'baseline.json',builder.bundle/'evidence/gold/baseline.json')
    wheels=builder.bundle/'wheels';wheels.mkdir(exist_ok=True)
    repo=here.parents[1]
    from importlib.util import find_spec
    if find_spec('pip') is None:
        builder.run('host-pip',[sys.executable,'-m','ensurepip'])
    if (repo/'pyproject.toml').is_file():
        builder.run('package-wheel',[sys.executable,'-m','pip','wheel','--no-deps',str(repo),'-w',str(wheels)])
    else:
        supplied=list((here.parent/'wheels').glob('securevibebench-*.whl'))
        if len(supplied)!=1:raise RuntimeError('Rebuilding outside a checkout requires the bundled package wheel')
        shutil.copy2(supplied[0],wheels/supplied[0].name)
    host_wheels(builder,wheels)
    for name in ['resolv.conf','docker-compose.yaml']:
        path=builder.task/'environment'/name
        if path.exists():
            target=builder.output/'local-network-overlay';target.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,target/name)
            path.unlink()
    config=builder.task_config(image,builder.task,prepared=True)
    config['metadata'].update(prepared_base_image=builder.base_image,network_runtime_verified=True,offline_reference_baseline_sha256=builder.state['offline_gold_baseline_sha256'],test_workers=8,native_agent_setup_offline_verified=True,starting_source_tree=audit['tree'])
    write_config(builder.task/'task.toml',config)
    manifest={'schema_version':1,'host_python':sys.version.split()[0],'task':'61721','platform':'linux/amd64','local_tag':TAG,'image_id':image,
              'base_image':builder.base_image,'reference_commit':metadata['vic'],'starting_commit_expression':metadata['base_commit'],
              'resources':{'cpus':builder.args.cpus,'memory_mb':builder.args.memory_mb,'test_workers':8},
              'test_policy':{'resources':'all,-largefile,-audio,-gui,-network','random_seed':61721,'gold_network':'none','candidate_network':'none'},
              'shared_assets_sha256':shared_hashes(),'image_audit':audit,'archive':archive,'submission_replay_rewards':rewards,
              'submission_patches_sha256':{path.name:digest(path) for path in builder.args.submission.rglob('submission.patch')},
              'agent_installation':'native Harbor mini-swe-agent; offline install-only verified; no model API calls or credentials used',
              'files_sha256':{str(path.relative_to(builder.bundle)):digest(path) for path in builder.bundle.rglob('*') if path.is_file() and path.name not in {archive['filename'],'manifest.json','SHA256SUMS','registry-reference.json'}}}
    (builder.bundle/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (builder.bundle/'SHA256SUMS').write_text(archive['sha256']+'  '+archive['filename']+'\n')
    task_archive=builder.output/'cpython-61721-task-bundle.tar.gz'
    with task_archive.open('wb') as raw, gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0) as compressed:
        with tarfile.open(fileobj=compressed,mode='w') as tar:
            for path in sorted(builder.bundle.rglob('*')):
                if not path.is_file() or path.name==archive['filename']:continue
                info=tar.gettarinfo(str(path),arcname='cpython-61721/'+str(path.relative_to(builder.bundle)))
                info.uid=info.gid=info.mtime=0
                info.uname=info.gname=''
                with path.open('rb') as source:tar.addfile(info,source)
    builder.state.update(archive=archive,rewards=rewards,image_audit=audit,task_bundle={'path':str(task_archive),'sha256':digest(task_archive),'bytes':task_archive.stat().st_size})
