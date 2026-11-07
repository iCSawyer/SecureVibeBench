#!/usr/bin/env python3
"""Push a verified local prepared image to the owner's GHCR namespace."""
import argparse
import json
from pathlib import Path
import re
import subprocess

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--bundle',type=Path,required=True)
parser.add_argument('--owner',required=True)
args=parser.parse_args()
owner=args.owner.lower()
if not re.fullmatch(r'[a-z0-9][a-z0-9-]*',owner):parser.error('Use a GitHub user or organization name')
manifest=json.loads((args.bundle/'manifest.json').read_text())
image=manifest['image_id']
subprocess.run(['docker','image','inspect',image],stdout=subprocess.DEVNULL,check=True)
reference='ghcr.io/'+owner+'/securevibebench-cpython:61721-offline-20261107'
subprocess.run(['docker','tag',image,reference],check=True)
subprocess.run(['docker','push',reference],check=True)
info=json.loads(subprocess.check_output(['docker','image','inspect',reference],text=True))[0]
digests=[value for value in info.get('RepoDigests',[]) if value.startswith(reference.split(':')[0]+'@')]
result={'tag':reference,'digests':digests,'image_id':image}
(args.bundle/'registry-reference.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
