# Bundled resources

SecureVibeBench installs the original dataset and evaluator from
[iCSawyer/SecureVibeBench](https://huggingface.co/datasets/iCSawyer/SecureVibeBench)
and bundles the source of [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent),
both licensed under the MIT license. Source distributions include the agent's
license in `mini-source.tar.gz`. Installed resources include both license texts
as `dataset/LICENSE` and `mini-swe-agent/LICENSE.md`.

The installed `resources.json` records the exact upstream commits and file
checksums. Dataset instructions, tests, and scoring code are preserved verbatim;
the host verifier is stored in `dataset/evaluator/` for packaging.
