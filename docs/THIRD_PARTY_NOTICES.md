# Third-party components

SecureVibeBench's task dataset is published under the MIT license at
[iCSawyer/SecureVibeBench](https://huggingface.co/datasets/iCSawyer/SecureVibeBench).
`evaluation/dataset-lock.json` pins the native Harbor dataset revision and manifest hash.
The dataset retains the task instructions. The installed evaluation package contains
the original parser and scoring functions shared by the tasks.

Harbor is an installed Python dependency. The default agent is Harbor's built-in
[mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent), licensed under MIT.
Harbor installs its package and dependencies during native agent setup, with their
package license metadata. This distribution does not bundle mini-swe-agent source or
the former host-side evaluator.

Optional Codex and Claude Code binaries are supplied by the user and remain subject
to their respective licenses and service terms. Credentials are not distributed.
