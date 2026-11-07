#!/usr/bin/env python3
"""Verify a prepared bundle and load its image without downloads."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def checksum(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):value.update(block)
    return value.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    args=parser.parse_args();root=args.bundle.resolve()
    manifest=json.loads((root/'manifest.json').read_text())
    for name,expected in manifest['files_sha256'].items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or checksum(path)!=expected:
            raise ValueError('Bundle checksum mismatch: '+name)
    for item in manifest.get('framework_images',[]):
        available=subprocess.run(['docker','image','inspect',item['image_id']],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if available.returncode:
            subprocess.run(['docker','load','-i',str(root/item['archive']['filename'])],check=True)
        subprocess.run(['docker','tag',item['image_id'],item['local_tag']],check=True)
    os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP','True')
    from complete_bundle import framework_tag
    expected=framework_tag()
    if expected not in {item['local_tag'] for item in manifest.get('framework_images',[])}:
        raise ValueError('Harbor firewall image differs from this host package; install the bundled wheels')
    image=manifest['image_id']
    found=subprocess.run(['docker','image','inspect',image],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if found.returncode:
        archive=root/manifest['archive']['filename']
        if not archive.is_file():
            raise FileNotFoundError('Pull the prepared GHCR image or place '+archive.name+' in the bundle')
        if checksum(archive)!=manifest['archive']['sha256']:raise ValueError('Image archive checksum mismatch')
        subprocess.run(['docker','load','-i',str(archive)],check=True)
    info=json.loads(subprocess.check_output(['docker','image','inspect',image],text=True))[0]
    if info['Id']!=image or info['Os']!='linux' or info['Architecture']!='amd64':
        raise ValueError('Prepared image identity or platform mismatch')
    subprocess.run(['docker','tag',image,manifest['local_tag']],check=True)
    from securevibebench_evaluation.images import read_task
    from securevibebench_evaluation.harbor_native import configure_dns
    task=root/'tasks/securevibebench-61721'
    read_task(task)
    configure_dns(task/'environment',manifest['resources']['cpus'])
    print('Verified task 61721:',image)
    print('Use --tasks '+str(root/'tasks')+' --local-images with generate or eval.')


if __name__=='__main__':main()
