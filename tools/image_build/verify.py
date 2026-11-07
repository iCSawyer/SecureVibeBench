"""Verify an unpublished local image through native Harbor without a registry."""

import json
from pathlib import Path
import shlex
import shutil
import sys

from securevibebench_evaluation.harbor_native import configure_dns, write_config
from securevibebench_evaluation.submissions import submission_tasks


def score_local(builder, submission, output, image, stage):
    """Use the trusted producer task while its image has no registry digest."""
    found = submission_tasks(submission)
    if len(found) != 1 or found[0][0] != builder.task.name:
        raise ValueError("Image verification requires exactly the producer's task")
    target = output / "inputs" / builder.task.name
    shutil.copytree(builder.task, target)
    config = builder.task_config(image, target, prepared=True)
    config["agent"]["network_mode"] = "no-network"
    config["agent"].pop("allowed_hosts", None)
    write_config(target / "task.toml", config)
    configure_dns(target / "environment", builder.args.cpus)
    solution = target / "solution"
    solution.mkdir(exist_ok=True)
    shutil.copy2(found[0][1], solution / "submission.patch")
    repo = shlex.quote(config["metadata"]["repo_cwd"])
    (solution / "solve.sh").write_text(
        "#!/bin/bash\nset -euo pipefail\ncd "
        + repo
        + "\nif test -s /solution/submission.patch; then git apply --check /solution/submission.patch; git apply /solution/submission.patch; fi\n"
    )
    empty = output / "empty.env"
    empty.write_text("")
    builder.run(
        stage,
        [
            str(Path(sys.executable).with_name("harbor")),
            "run",
            "-p",
            str(target),
            "-a",
            "oracle",
            "--jobs-dir",
            str(output / "jobs"),
            "--job-name",
            "image-verification",
            "--env-file",
            str(empty),
        ],
    )
    results = []
    for path in (output / "jobs/image-verification").glob("*/result.json"):
        record = json.loads(path.read_text())
        results.append(
            {
                "task": record.get("task_name"),
                "exception": record.get("exception_info"),
                "rewards": (record.get("verifier_result") or {}).get("rewards"),
            }
        )
    if len(results) != 1 or results[0]["exception"] or not results[0]["rewards"]:
        raise RuntimeError("Local image verifier did not complete")
    result = {"results": results, "network": "no-network"}
    (output / "eval.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
