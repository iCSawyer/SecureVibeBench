# Prepared ARVO image workflow

Evaluation uses immutable prepared images. It does not build environments or download dependencies. See [the evaluation guide](../../docs/README.md) for user commands.

## Produce an image

Use an original source task, with its Dockerfile and preparation scripts. The minimal runtime tasks in `example/` and the HF release are not build inputs. Install maintainer dependencies with `pip install .`.

```bash
python tools/arvo_images/prepare.py --tasks ORIGINAL_TASKS --task ID \
  --output runs/images-ID --workers 1 --cpus 4 --memory-mb 8192 \
  --owner icsawyer --package securevibebench --publish
```

The image sets CMake, CTest, and Make parallelism from `--cpus`. Docker CPU affinity alone does not limit the number of compiler processes. CMake build commands also pass the job limit to Make or Ninja, so CMake versions before 3.12 are covered. Timed-out build and test commands stop their process group, including child compilers.

Online preparation acquires dependencies. Offline acceptance builds the reference and starting source, records the baseline, and tests native Harbor mini-swe-agent setup and separate verification. Publication requires an existing Public package before any push. It verifies the published manifest anonymously and pulls the digest with an empty Docker authentication config to confirm the image ID. Credentials and original Git history must not remain in the image. Keep raw logs and acceptance evidence.

Use `GITHUB_DOCKER` in the project `.env` for maintainer publication only. The temporary Docker authentication config is removed after each image. The shared package stays Public, and tags use `arvo-ID-offline-YYYYMMDD-IMAGEID`. The publisher refuses missing or private packages and refuses to replace a tag that points to a different image. It does not modify existing task tags.

ARVO compilation retains the base image's declared working directory. Task functional tests still run in the task repository. This keeps relative dependency paths valid for nDPI and curl. Build scripts and before/after diagnostics are retained; failed online preparation emits internal logs before Docker removes its container.

A compulsory post-freeze verifier compiles the submitted starting source, runs the PoC and full functional suite, and checks network isolation. The producer does not repeat the same compile/test probe before freezing.

Count-only suites retain their reported counts. The reference must contain positive passes. Submission results must not reduce the pass count or total count, or increase failures or unknowns. These tasks declare `count-results-no-regression-v1`; counts do not identify individual cases. Existing list and Boolean comparisons keep their original rules.

The producer uses native Harbor directly to verify an unpublished local image. It does not call the user evaluator or require a registry digest until publication. Failed reference baselines must be investigated; do not change assertions to obtain a successful image.

## Add images to the runtime catalog

The runtime format contains `instruction.md`, `task.toml`, and `tests/test.sh`. The Dockerfile, installer scripts, and evidence remain in maintainer build inputs and run archives.

For a completed Public image run:

```bash
python tools/arvo_images/catalog.py --run RUN --output data
securevibebench pull --tasks data --task full
securevibebench generate --tasks data --task ID --model 'openai/<model>' --local-images --eval
```

The exporter records each registry digest, expected image ID, platform, baseline hash, and verified native agent. Publish those definitions and the image catalog to HF `full-habour`; do not put the complete dataset in GitHub. Update `evaluation/dataset-lock.json` after verifying the HF commit. The current HF release contains 100 image tasks. The wrapper only accepts declared image tasks and never falls back to a Dockerfile.

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

## Consolidate accepted images

Use one Public package, `ghcr.io/icsawyer/securevibebench`. Versions use `arvo-ID-offline-YYYYMMDD-IMAGEID`. Dataset task files pin the full manifest digest.

```bash
python tools/arvo_images/consolidate.py --inventory INVENTORY_JSON \
  --output runs/registry-consolidation --crane /path/to/crane
```

Each inventory entry contains `task`, `reference` (the accepted source digest), and `image_id`. The target package must already be Public and linked to the benchmark repository. The copier preserves manifest digests, checks anonymous pulls, and writes `mapping.json`. Existing versions remain available. Apply verified mappings to task contracts before publishing the HF release. The publisher's default package is `securevibebench`.

## Repository association

New prepared images carry `org.opencontainers.image.source=https://github.com/iCSawyer/SecureVibeBench`. GHCR uses this source label to associate the image package with the repository.

For an existing package, a label-only auxiliary version can establish the association without replacing the task's evaluation tag or digest. `link_repository.py` accepts an audited image inventory, uses `GITHUB_DOCKER` from the project `.env`, and verifies the package repository, original evaluation digest, and original tag after publication. The temporary Docker authentication file is removed when the command finishes.

The auxiliary tag is `repository-link-20261107`. Its filesystem layers and runtime configuration must match the evaluation image. Package visibility remains a separate setting; repository association does not imply anonymous pull access.

## Downstream use

```bash
pip install .
securevibebench pull --task full
securevibebench generate --task 992 --model 'openai/<model>' --local-images --eval
securevibebench eval ./submission --local-images
```

Published evaluation images are Public; users do not need a package token or Docker login. `pull` downloads fixed image digests before trials. `--local-images` prevents registry access. Native agent setup, compilation, patch collection, and separate verification run without network. Only agent execution can access the configured model API allowlist. Current images declare mini-swe-agent; other agents require a new image and offline setup verification.

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
verifier before republishing. Original Git objects are never copied
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


The remaining-task producer also clears MRuby target artifacts with `rake clean`,
which retains downloaded gems. Ordinary tests use GCC; the original ARVO fuzz
flags remain unchanged. libsrtp removes stale archive members before its fuzz
configuration. HarfBuzz `-m32` fuzz builds do not discover 64-bit optional libraries
installed for ordinary tests; the original fuzz image had none of those backends.
Ordinary HarfBuzz shape tests still use FreeType and their full test suite.

Miniz example invocations supply the output filenames required by the original
utilities. Compression and decompression still compare the resulting files with
`diff`. Successful program cases emit explicit IDs after their assertions; the
parser preserves those case IDs instead of assuming a fixed number of success
messages. An earlier command failure prevents its pass marker.


## Repeated offline recipes

Project adapters keep build scripts usable across reference, starting-source, and
submission checks. Miniz uses a fresh generated build directory when compiler
flags change. MRuby retains its downloaded LPM dependency and bounds Ninja jobs.
MuPDF copies seed resources instead of moving them. Scripts run from the declared
repository directory; host-side Docker launch commands are removed from container
tests. Python package installation remains in online reference preparation.

The original MuPDF PDF and Open vSwitch dictionary are retained in `fixtures/`.
Their manifest records the original URL, source image, and SHA256. The producer
checks each hash before copying an input into the image. Compilation and tests
read these local files and do not download replacements.

## Repeated-build repairs

The producer cleans generated caches when ordinary tests and fuzz targets use different compilers or architectures. Optional fuzz dependencies absent from the original image remain disabled after ordinary-test packages are installed. Target sanitizer flags are retained.

Task 38843 builds its host `mrbc` compiler from the current candidate source with GCC, then uses it to generate code for the original MSan target. The producer checks the target library for MSan symbols. It never reuses a reference-source host compiler.

Task 20702 runs `make check` and each fixture through the original `tests/test` driver. The report retains aggregate and individual failures. Acceptance compares the reference pass set with the submitted pass set.

Pinned libavc and igraph archives are fetched only by the online producer and copied into the image after SHA-256 verification. Offline commands use those files. CUPS libraries finish building before installation starts. Hermes compilation has a 7200-second limit; its compiler and lit job counts follow the image CPU budget.
