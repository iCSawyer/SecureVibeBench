#!/usr/bin/env python3
"""Build and validate task 61721 before exporting a credential-free image."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tomllib

from securevibebench_evaluation.harbor_native import digest, select_cpus, write_config
for parent in Path(__file__).resolve().parents:
    if (parent / 'tools/image_build').is_dir():
        sys.path.insert(0, str(parent))
        break
from tools.image_build.task_assets import ASSETS, SHARED, shared_hashes
from tools.image_build.toolchain import copy_uv

HERE = Path(__file__).resolve().parent


def now():
    return datetime.now(timezone.utc).isoformat()


class Builder:
    def __init__(self, args):
        self.args = args
        self.output = args.output.resolve()
        self.bundle = self.output / 'bundle'
        self.work = self.output / 'work'
        self.logs = self.output / 'logs'
        for path in (self.bundle, self.work, self.logs):
            path.mkdir(parents=True, exist_ok=True)
        self.state = {'state': 'running', 'started_at': now(), 'stages': {}, 'task': '61721'}
        self.env = {key:value for key,value in os.environ.items() if not any(marker in key.upper()
                    for marker in ('API_KEY', 'AUTH_TOKEN', 'ACCESS_TOKEN', 'HF_TOKEN', 'BASE_URL', 'API_BASE', 'CODEX_AUTH'))}
        self.cpus = select_cpus(self.output, args.cpus)
        self.suffix = hashlib.sha256(str(self.output).encode()).hexdigest()[:8]
        self.source = args.task.resolve()
        self.config = tomllib.loads((self.source/'task.toml').read_text())
        if str(self.config['metadata']['localid']) != '61721':
            raise ValueError('This recipe supports CPython task 61721 only')
        self.task = self.bundle/'tasks/securevibebench-61721'
        if self.task.exists():
            if not args.resume:
                raise FileExistsError('Use a new output directory')
            self.state = json.loads((self.output/'status.json').read_text())
            if not self.state.get('candidate_image'):
                raise ValueError('Resume is available after core validation only')
            self.candidate = self.state['candidate_image']
            self.base_image = self.state['base_image']
            self.toolchain = self.state['toolchain']
            self.state.setdefault('attempt_history',[]).append({'state':self.state['state'],'error':self.state.pop('error',None),'at':now()})
            self.state['state'] = 'running'
            self.save()
            return
        shutil.copytree(self.source, self.task, ignore=shutil.ignore_patterns('toolchain','__pycache__','resolv.conf','docker-compose.yaml'))
        self.save()

    def save(self):
        self.state['updated_at'] = now()
        temporary = self.output/'status.tmp'
        temporary.write_text(json.dumps(self.state, indent=2)+'\n')
        temporary.replace(self.output/'status.json')

    def run(self, name, command, *, check=True, capture=False):
        if (self.logs/(name+'.log')).exists():
            archive = self.logs/'archive'
            archive.mkdir(exist_ok=True)
            shutil.copy2(self.logs/(name+'.log'), archive/(name+'-'+str(time.time_ns())+'.log'))
        record = {'state':'running','started_at':now(),'command':list(map(str,command)), 'log':str(self.logs/(name+'.log'))}
        self.state['stages'][name] = record
        self.save()
        print(now(), name, flush=True)
        start = time.monotonic()
        if capture:
            result = subprocess.run(command, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            Path(record['log']).write_text(result.stdout+result.stderr)
        else:
            with Path(record['log']).open('w') as stream:
                result = subprocess.run(command, env=self.env, stdout=stream, stderr=subprocess.STDOUT)
        record.update(state='completed' if result.returncode==0 else 'failed', exit_code=result.returncode,
                      elapsed_seconds=time.monotonic()-start, finished_at=now())
        self.save()
        if check: result.check_returncode()
        return result

    def docker_run(self, name, image, command, *, create=False):
        return ['docker','create' if create else 'run','--name',name,'--network','none','--cpus',str(self.args.cpus),
                '--cpuset-cpus',','.join(map(str,self.cpus)),'--memory',str(self.args.memory_mb)+'m',
                '--entrypoint','/opt/svb/python/bin/python3',image,*command]

    def collect(self, container, name):
        path = self.bundle/'evidence'/name
        path.parent.mkdir(exist_ok=True)
        if path.exists():
            archive = path.parent / 'archive'
            archive.mkdir(exist_ok=True)
            path.rename(archive / (name + '-' + str(time.time_ns())))
        self.run(name+'-logs',['docker','cp',container+':/opt/svb/preparation/.',str(path)],check=False)

    def core(self):
        context = self.work/'foundation'
        (context/'toolchain/bin').mkdir(parents=True)
        svb = context/'svb'
        (svb/'build-bin').mkdir(parents=True)
        self.toolchain = copy_uv(context/'toolchain/bin/uv', self.work/'toolchain-cache')
        shutil.copy2(HERE/'Dockerfile',context/'Dockerfile')
        for name in SHARED: shutil.copy2(ASSETS/name,svb/name)
        shutil.copy2(HERE/'container_prepare.py',svb/'image_prepare.py')
        shutil.copy2(HERE/'functional.sh',svb/'functional.sh')
        shutil.copy2(HERE/'make',svb/'build-bin/make')
        (svb/'build-bin/make').chmod(0o755)
        fields = ('localid','repo_cwd','base_commit','functional_script_id')
        (svb/'task.json').write_text(json.dumps({key:self.config['metadata'][key] for key in fields},indent=2)+'\n')
        source = self.args.base_image or self.config['metadata'].get('prepared_base_image') or (self.source/'environment/Dockerfile').read_text().splitlines()[0].removeprefix('FROM ').strip()
        info = self.run('inspect-base',['docker','image','inspect',source],capture=True,check=False)
        if info.returncode:
            self.run('pull-base',['docker','pull',source])
            info = self.run('inspect-base-after-pull',['docker','image','inspect',source],capture=True)
        base = json.loads(info.stdout)[0]
        if base['Os']!='linux' or base['Architecture']!='amd64':
            raise ValueError('This recipe requires a Linux amd64 ARVO base')
        self.base_image = next((value for value in base.get('RepoDigests',[]) if value.startswith('n132/arvo@')),base['Id'])
        foundation = 'junkai-cpython-foundation:'+self.suffix
        self.run('foundation',['docker','build','--pull=false','--cpuset-cpus',','.join(map(str,self.cpus)),
                 '--build-arg','BASE_IMAGE='+self.base_image,'-t',foundation,str(context)])
        gold = 'junkai-cpython-61721-gold-'+self.suffix
        result = self.run('gold', self.docker_run(gold,foundation,['/opt/svb/image_prepare.py','gold','--commit',self.config['metadata']['vic']]), check=False)
        self.collect(gold,'gold')
        if result.returncode: raise RuntimeError('Offline gold validation failed; see logs/gold.log')
        baseline = self.work/'baseline.json'
        self.run('gold-baseline',['docker','cp',gold+':/opt/svb/baseline.json',str(baseline)])
        start = 'junkai-cpython-61721-start-'+self.suffix
        self.run('create-start',self.docker_run(start,foundation,['/opt/svb/image_prepare.py','start','--commit',self.config['metadata']['base_commit']],create=True))
        self.run('copy-baseline',['docker','cp',str(baseline),start+':/opt/svb/baseline.json'])
        result = self.run('start',['docker','start','-a',start],check=False)
        self.collect(start,'start')
        actual_exit = int(self.run('start-exit',['docker','inspect',start,'--format','{{.State.ExitCode}}'],capture=True).stdout.strip())
        if result.returncode or actual_exit: raise RuntimeError('Starting source preparation failed')
        self.run('commit-start',['docker','commit','--change','ENTRYPOINT ["/usr/bin/env"]','--change','CMD ["bash","-c","sleep infinity"]','--change','WORKDIR /src/cpython3',start,'junkai-cpython-prepared:'+self.suffix])
        candidate = self.run('inspect-start',['docker','image','inspect','junkai-cpython-prepared:'+self.suffix,'--format','{{.Id}}'],capture=True).stdout.strip()
        probe = 'junkai-cpython-61721-probe-'+self.suffix
        result = self.run('probe',self.docker_run(probe,candidate,['/opt/svb/runtime.py','probe']),check=False)
        self.collect(probe,'probe')
        if result.returncode: raise RuntimeError('Offline recompilation/test probe failed')
        shutil.copy2(HERE/'functional.sh',self.task/'environment/svb/functional.sh')
        self.candidate = candidate
        self.state.update(candidate_image=candidate, base_image=self.base_image, cpuset_cpus=self.cpus,
                          cpu_budget=self.args.cpus,memory_mb=self.args.memory_mb, toolchain=self.toolchain,
                          shared_assets_sha256=shared_hashes(),offline_gold_baseline_sha256=digest(baseline))
        self.save()

    def task_config(self, image, directory, *, public=False, prepared=False):
        config = json.loads(json.dumps(self.config))
        config['environment'].update(docker_image=image,cpus=self.args.cpus,memory_mb=self.args.memory_mb,network_mode='public' if public else 'no-network')
        config['environment'].pop('allowed_hosts',None)
        config['verifier']['environment'].update(cpus=self.args.cpus,memory_mb=self.args.memory_mb,network_mode='no-network')
        metadata = config['metadata']
        for key in list(metadata):
            if key.startswith('preparation_') or key=='prepared_agents': metadata.pop(key)
        metadata.update(offline_preparation_probe_passed=prepared,preparation_image=image,
                        preparation_agent_installation='harbor-native',preparation_shared_assets=self.state.get('shared_assets_sha256', shared_hashes()),
                        preparation_toolchain_sha256=digest(Path(__import__('tools.image_build.toolchain',fromlist=['x']).__file__)),
                        preparation_source_config={key:metadata[key] for key in ('localid','repo_cwd','base_commit','functional_script_id')},
                        dependency_lock_status='frozen_image',prepared_agents=['mini-swe-agent'] if prepared else [])
        metadata['preparation_inputs']={str(p.relative_to(directory)):digest(p) for folder in ['environment/svb','tests'] for p in (directory/folder).rglob('*') if p.is_file()}
        metadata['preparation_dockerfile_sha256']=digest(directory/'environment/Dockerfile')
        write_config(directory/'task.toml',config)
        return config


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--base-image')
    parser.add_argument('--cpus',type=int,default=8)
    parser.add_argument('--memory-mb',type=int,default=16384)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--submission',type=Path,help='Existing candidate to replay; omitted uses an empty-patch environment check')
    args=parser.parse_args()
    if args.cpus!=8: parser.error('This verified recipe currently uses eight build/test workers')
    if args.submission is None:
        args.submission=args.output.resolve()/'work/empty-submission'
        empty=args.submission/'securevibebench-61721/submission.patch'
        empty.parent.mkdir(parents=True,exist_ok=True)
        empty.write_text('')
        args.validation_kind='empty_patch_environment_check'
    else:
        args.submission=args.submission.resolve()
        args.validation_kind='existing_submission'
    builder=Builder(args)
    try:
        if not args.resume:
            builder.core()
        from freeze import finish
        finish(builder)
        from complete_bundle import complete
        builder.state['transfer']=complete(builder.output)
        builder.state.update(state='completed',finished_at=now());builder.save()
    except Exception as error:
        builder.state.update(state='failed',error=type(error).__name__+': '+str(error));builder.save();raise

if __name__=='__main__': main()
