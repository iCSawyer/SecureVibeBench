# Prepared ARVO image workflow

Evaluation uses immutable prepared images. It does not build environments or download dependencies. See [the evaluation guide](../../docs/README.md) for user commands.

## Produce an image

Use an original source task, with its Dockerfile and preparation scripts. The minimal runtime tasks in `example/` and the HF release are not build inputs. Install maintainer dependencies with `pip install .`.

```bash
python tools/arvo_images/prepare.py --tasks ORIGINAL_TASKS --task ID \
  --output runs/images-ID --workers 1 --cpus 4 --memory-mb 8192 \
  --owner icsawyer --publish
```

Online preparation acquires dependencies. Offline acceptance builds the reference and starting source, records the baseline, and tests native Harbor mini-swe-agent setup and separate verification. Publication checks private visibility and pulls the digest back to confirm the image ID. Credentials and original Git history must not remain in the image. Keep raw logs and acceptance evidence.

The producer uses native Harbor directly to verify an unpublished local image. It does not call the user evaluator or require a registry digest until publication. Failed reference baselines must be investigated; do not change assertions to obtain a successful image.

## Add images to the runtime catalog

The runtime format contains `instruction.md`, `task.toml`, and `tests/test.sh`. The Dockerfile, installer scripts, and evidence remain in maintainer build inputs and run archives.

For a verified ten-image distribution:

```bash
python tools/arvo_images/catalog.py --bundle RUN/distribution --output data
securevibebench pull --tasks data --task full
securevibebench generate --tasks data --task ID --model 'openai/<model>' --local-images --eval
```

The exporter records each registry digest, expected image ID, platform, baseline hash, and verified native agent. Publish those definitions and the image catalog to HF `full-habour`; do not put the complete dataset in GitHub. Update `evaluation/dataset-lock.json` after verifying the HF commit. The current HF release contains 21 image tasks. The wrapper only accepts declared image tasks and never falls back to a Dockerfile.

Published offline bundles from earlier batches retain their own framework wheel and importer. Use those frozen bundles as complete archives. The current evaluator consumes the minimal image task format; export a new task root when using an earlier distribution with the current package.

## Sync the HF staging branch

`full-habour` contains only tasks with published image digests. `availability.json` lists every benchmark ID and marks tasks without images as unsupported. HF README files are not changed by the publisher.

```bash
python tools/publish_dataset.py --source TASK_FILES --catalog IMAGE_CATALOG_JSON \
  --framework PREPARED_FRAMEWORK --all-tasks ORIGINAL_TASKS --output runs/hf-stage
python tools/publish_dataset.py --source TASK_FILES --catalog IMAGE_CATALOG_JSON \
  --framework PREPARED_FRAMEWORK --all-tasks ORIGINAL_TASKS --output runs/hf-stage \
  --publish --expected-head REVIEWED_FULL_HABOUR_COMMIT
```

The first command validates and stages task files, the image catalog, availability, and a deterministic archive. Review those artifacts before publishing. The second command updates exactly the reviewed branch head, removes obsolete task files, and writes `tools/image_build/publication-lock.json` plus the runtime HF release lock. The immutable source-data lock stays separate so image production can still obtain the original build inputs.

## Repository association

New prepared images carry `org.opencontainers.image.source=https://github.com/iCSawyer/SecureVibeBench`. GHCR uses this source label to associate the image package with the repository.

For an existing package, a label-only auxiliary version can establish the association without replacing the task's evaluation tag or digest. `link_repository.py` accepts an audited image inventory, uses `GITHUB_DOCKER` from the project `.env`, and verifies the package repository, original evaluation digest, and original tag after publication. The temporary Docker authentication file is removed when the command finishes.

The auxiliary tag is `repository-link-20261107`. Its filesystem layers and runtime configuration must match the evaluation image. Package visibility remains a separate setting; repository association does not imply anonymous pull access.

## Downstream use

```bash
pip install .
docker login ghcr.io
securevibebench pull --task full
securevibebench generate --task 992 --model 'openai/<model>' --local-images --eval
securevibebench eval ./submission --local-images
```

Private packages require read access. `pull` downloads fixed image digests before trials. `--local-images` prevents registry access. Native agent setup, compilation, patch collection, and separate verification run without network. Only agent execution can access the configured model API allowlist. Current images declare mini-swe-agent; other agents require a new image and offline setup verification.

## FreeType repair for task 58663

The original reference installer requested `libtool-dev`, which does not exist
in its Ubuntu package sources. This aborted a transaction that included FreeType.
Most shaping tests then failed because `hb-shape` had no `ft` backend. The recipe
removes that invalid package token and requires `--with-freetype=yes` in ordinary
tests. Existing reference failures must be diagnosed before acceptance.

For an already frozen image, `repair_freetype.py` installs the missing OS dependency
online, reuses the starting source and the native Mini installation, generates a
new reference baseline in a disposable offline container with the original Git
objects, then runs native offline setup and the complete offline submission
verifier before privately republishing. Original Git objects are never copied
into the corrected starting image. The previous image digest and batch artifacts
remain archived. This avoids repeating checks already subsumed by the actual
verifier while still testing the corrected environment.

## Additional batch policies

The next batch also prepares zstd, pcre2, newer file tasks, another lwan task,
and additional oniguruma and HarfBuzz task IDs. These policies preserve test
commands and assertions:

- Autotools ordinary builds clean prior sanitizer objects before configuration.
- Legacy file fuzz links include zlib, bzip2 and lzma when those symbols are used.
  The newer corpus preparation uses `mkdir -p` so repeated compilation succeeds.
- The lwan compatibility hook accepts both literal `-lFuzzingEngine` and the
  `$LIB_FUZZING_ENGINE` variable before adding its required Lua library.
- The old zstd CLI runner executes from `tests/` and uses `ZSTD`. The adapter
  supplies that variable and the newer aliases in a subshell. It retains the full
  CLI, benchmark and 10,000-round stream tests.
- Failed reference suites retain their inner `test-suite.log` files. Known missing
  backend, module and shared-library errors prevent reference acceptance.

Online native installation can reuse the labeled Docker network
`junkai-arvo-image-preparation`. This avoids allocating one subnet for each
retained installer. After an immutable image and credential audit exist, each
new task releases only its own stopped installer; shared networks remain.
Offline setup, source probes and verifier network isolation do not use this
online preparation override. Do not run cross-batch pruning watchers on the
shared Docker host.
