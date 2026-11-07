# Prepared CPython environment: task 61721

This bundle contains a Linux amd64 environment for SecureVibeBench task 61721.
The host evaluator uses Python 3.12; the task source is a historical CPython 3.13 development snapshot. Use Python 3.12 and Docker with Compose on the host. Allocate 8 CPUs and 16 GiB of memory. Source starts at the parent of reference commit
`b8f96b5eda5b376b05a9dbf046208388249e30a6`. The original Git history is replaced
with one initial commit tagged `svb-start`.

The reference baseline and candidate tests both run with no network. They use
CPython's native resource defaults with external networking disabled, a fixed
test-order seed, and eight test workers. The make wrapper also bounds the nested
freeze-test build. No source assertions are removed.

Native Harbor installs mini-swe-agent during image preparation. A second native
installation check runs without network. API credentials and model responses are
not included. Model credentials must be supplied by the downstream user.
Other agents and untested model backends may need separate preparation.

## Upload to GitHub

Store the task bundle and recipe in the GitHub repository or a Release. The
container image can be uploaded to GitHub Container Registry (GHCR):

```bash
# Run from the generated bundle directory. Authenticate with your own account.
docker login ghcr.io -u YOUR_GITHUB_NAME
python recipe/publish_ghcr.py --bundle . --owner YOUR_GITHUB_NAME
```

The script prints the registry digest and saves `registry-reference.json`.
Give downstream users that digest and this task bundle. Configure package
visibility in GitHub for the intended users. The builder does not publish or
change package visibility automatically. See the
[official GHCR documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

The image archive is an alternative for offline transfer. Its checksum is in
`manifest.json` and `SHA256SUMS`.

## Downstream installation

```bash
python3.12 -m venv .venv
source .venv/bin/activate
export LITELLM_LOCAL_MODEL_COST_MAP=True
pip install --no-index --find-links wheels -r requirements-host.lock wheels/securevibebench-*.whl
# Either pull the registry digest supplied by the publisher:
docker pull ghcr.io/OWNER/securevibebench-cpython@sha256:REGISTRY_DIGEST
# Or leave cpython-61721-offline.tar.gz beside manifest.json for local loading.
python recipe/import_image.py --bundle .
```

The task bundle also includes Harbor's firewall-sidecar image. Import loads and verifies that image, so evaluation does not need to build or download it. Import verifies the task files, platform, frozen image ID, and shared runtime.
It refreshes DNS and CPU placement for the local machine. The bundled wheel is
from the experimental `habour` branch; it is not a new PyPI release.

For the prepared full-test policy inside a container, use `bash /opt/svb/functional.sh`.
This applies the offline resource selection and worker budget; plain upstream
`make test` retains its upstream defaults.

## Score a submission with no model credentials

```bash
securevibebench eval /path/to/submission --tasks tasks --offline
```

The submission must contain `securevibebench-61721/submission.patch`, or be a
supported native Harbor job. Scoring applies the patch in a fresh container,
recompiles the source, runs the vulnerability check, and compares functional
results against the offline reference baseline. Verification has no network.

## Generate with the frozen native mini installation

```bash
export OPENROUTER_API_KEY='<your own key>'
securevibebench generate --agent mini-swe-agent \
  --model openrouter/deepseek/deepseek-v4.1-flash-1017 \
  --tasks tasks --task 61721 --offline --allow-model-host openrouter.ai \
  --agent-env OPENROUTER_API_KEY \
  --ak 'config={"model":{"model_class":"openrouter","model_kwargs":{"model":"deepseek/deepseek-v4.1-flash-1017"}}}' \
  --ak 'session_id_headers=[]' --eval
```

Harbor manages the agent. Setup uses the prepared dependencies without network;
agent execution can access the declared model/authentication hosts. This recipe
uses mini's native OpenRouter backend. The image preparation itself makes no
model API requests.

## Rebuild and evidence

The recipe uses a digest-pinned ARVO base and a checksum-verified uv bootstrap.
From a SecureVibeBench checkout with the matching package installed:

```bash
python tools/cpython_image/prepare.py \
  --task /path/to/tasks/securevibebench-61721 \
  --output /path/to/new-build \
  --base-image n132/arvo@sha256:BASE_DIGEST \
  --submission /path/to/existing-submission
```

Omit `--submission` to run an empty-patch environment check without any model output.

The build downloads interpreter and agent dependencies during preparation.
Exact environment reuse uses the exported image, since rebuilding can resolve
newer native agent dependencies. `manifest.json` records the source, image,
test policy, resource budget, artifact hashes, and submission replay result.
Full private build logs remain beside `bundle/`; selected validation evidence
is inside `evidence/`. The candidate patch is not distributed in the image or
bundle.
