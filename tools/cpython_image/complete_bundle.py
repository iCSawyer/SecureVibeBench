#!/usr/bin/env python3
"""Include Harbor's firewall image so downstream evaluation needs no image build."""
import argparse
import gzip
import hashlib
from importlib.metadata import distribution
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile


def checksum(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):value.update(block)
    return value.hexdigest()


def framework_tag():
    os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP','True')
    from harbor.environments.docker.docker import DockerEnvironment
    from harbor.environments.docker.utils import docker_build_context_hash, _compute_image_name
    context=DockerEnvironment._EGRESS_CONTROL_SIDECAR_CONTEXT_PATH
    key=docker_build_context_hash(context=context,dockerfile_path=context/'Dockerfile',build_args={},platform='linux/amd64')
    return _compute_image_name('harbor-prebuilt:harbor-docker-egress-control-sidecar',key)


def complete(output):
    output=Path(output).resolve();root=output/'bundle'
    manifest=json.loads((root/'manifest.json').read_text())
    recipe_source=Path(__file__).resolve().parent
    if recipe_source!=(root/'recipe').resolve():
        shutil.copytree(recipe_source,root/'recipe',ignore=shutil.ignore_patterns('__pycache__'),dirs_exist_ok=True)
        shutil.copy2(recipe_source/'README.md',root/'README.md')
    state=json.loads((output/'status.json').read_text())
    manifest['toolchain']=state['toolchain']
    tag=framework_tag()
    info=json.loads(subprocess.check_output(['docker','image','inspect',tag],text=True))[0]
    directory=root/'framework';directory.mkdir(exist_ok=True)
    archive=directory/'harbor-egress-control.tar.gz'
    with archive.open('wb') as stream, (output/'logs/framework-export.log').open('wb') as log:
        save=subprocess.Popen(['docker','save',tag],stdout=subprocess.PIPE,stderr=log)
        compress=subprocess.Popen(['gzip','-n','-c'],stdin=save.stdout,stdout=stream,stderr=log)
        save.stdout.close()
        compressed=compress.wait();saved=save.wait()
        if compressed or saved:raise RuntimeError('Harbor firewall image export failed')
    manifest['framework_images']=[{'local_tag':tag,'image_id':info['Id'],'platform':info['Os']+'/'+info['Architecture'],
                                  'archive':{'filename':str(archive.relative_to(root)),'sha256':checksum(archive),'bytes':archive.stat().st_size}}]
    baseline=json.loads((root/'evidence/gold/baseline.json').read_text())
    manifest['reference_tests']={'passed':len(baseline.get('PassList',[])),'failed':len(baseline.get('FailList',[])),'skipped':len(baseline.get('UnknownList',[]))}
    manifest['submission_replay_kind']='empty_patch_environment_check' if set(manifest.get('submission_patches_sha256',{}).values())=={hashlib.sha256(b'').hexdigest()} else 'existing_submission'
    manifest['starting_commit']=json.loads((root/'evidence/start/source.json').read_text())['commit']
    native=json.loads((root/'evidence/native-install/result.json').read_text())
    manifest['native_mini_version']=native['agent_info']['version']
    expected_tree=subprocess.check_output(['docker','run','--rm','--pull=never','--network','none','--entrypoint','git',manifest['base_image'],'-C','/src/cpython3','rev-parse',manifest['starting_commit']+'^{tree}'],text=True).strip()
    if expected_tree!=manifest['image_audit']['tree']:raise RuntimeError('Prepared starting source differs from the declared commit')
    manifest['starting_source_tree_verified']=True
    inventory=output/'logs/native-package-inventory.log'
    if inventory.exists():shutil.copy2(inventory,root/'evidence/native-package-inventory.txt')
    notice=root/'licenses';notice.mkdir(exist_ok=True)
    package=distribution('securevibebench')
    for item in package.files or []:
        if '/licenses/' in str(item):
            path=package.locate_file(item)
            if path.is_file():shutil.copy2(path,notice/path.name)
    checkout=Path(__file__).resolve().parents[2]
    for source in [checkout/'LICENSE',checkout/'docs/THIRD_PARTY_NOTICES.md']:
        if source.is_file():shutil.copy2(source,notice/source.name)
    manifest['files_sha256']={str(path.relative_to(root)):checksum(path) for path in sorted(root.rglob('*'))
                              if path.is_file() and path.name not in {manifest['archive']['filename'],'manifest.json','SHA256SUMS','registry-reference.json'}}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    sums=[(manifest['archive']['sha256'],manifest['archive']['filename'])]
    sums.extend((item['archive']['sha256'],item['archive']['filename']) for item in manifest['framework_images'])
    (root/'SHA256SUMS').write_text(''.join(sha+'  '+name+'\n' for sha,name in sums))
    bundle=output/'cpython-61721-task-bundle.tar.gz'
    with bundle.open('wb') as raw, gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0) as compressed:
        with tarfile.open(fileobj=compressed,mode='w') as tar:
            for path in sorted(root.rglob('*')):
                if not path.is_file() or path.name==manifest['archive']['filename']:continue
                member=tar.gettarinfo(str(path),arcname='cpython-61721/'+str(path.relative_to(root)))
                member.uid=member.gid=member.mtime=0;member.uname=member.gname=''
                with path.open('rb') as stream:tar.addfile(member,stream)
    result={'state':'completed','image_id':manifest['image_id'],'task_bundle':{'filename':bundle.name,'sha256':checksum(bundle),'bytes':bundle.stat().st_size},
            'image_archive':manifest['archive'],'framework_images':manifest['framework_images'],'manifest_sha256':checksum(root/'manifest.json')}
    (output/'transfer-ready.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'artifact-checksums.txt').write_text(manifest['archive']['sha256']+'  bundle/'+manifest['archive']['filename']+'\n'+result['task_bundle']['sha256']+'  '+bundle.name+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    print(json.dumps(complete(args.output),indent=2))
