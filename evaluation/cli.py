"""Generate with native Harbor or score source submissions using fixed images."""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib.metadata import version
import json
import subprocess
from pathlib import Path
from uuid import uuid4

from .images import acquire, select_tasks, task_statuses
from .dataset import resolve_tasks


def build_parser():
    parser = argparse.ArgumentParser(prog="securevibebench", description=__doc__)
    parser.add_argument(
        "--version", action="version", version="%(prog)s " + version("securevibebench")
    )
    sub = parser.add_subparsers(dest="action", required=True)
    listing = sub.add_parser(
        "list", help="Show supported and temporarily unsupported tasks"
    )
    listing.add_argument("--tasks", type=Path)
    listing.add_argument(
        "--local-images", action="store_true", help="Use cached HF data without network"
    )
    listing.add_argument("--json", action="store_true")
    pull = sub.add_parser(
        "pull", help="Download and verify pinned images before evaluation"
    )
    generate = sub.add_parser(
        "generate", help="Run a native Harbor agent and package its submission"
    )
    score = sub.add_parser(
        "eval", help="Score a generated or external submission without network"
    )
    package = sub.add_parser(
        "package", help="Export a native Harbor job as submission patches"
    )
    for command in (pull, generate, score):
        command.add_argument(
            "--tasks",
            type=Path,
            help="Native image task root; default: pinned HF release cache",
        )
        command.add_argument(
            "--output", type=Path, help="New directory for logs and results"
        )
        command.add_argument(
            "--local-images",
            action="store_true",
            help="Require local images; never contact a registry",
        )
    for command in (pull, generate):
        command.add_argument(
            "--task",
            action="extend",
            nargs="+",
            help="IDs separated by spaces or commas, or full (default)",
        )
    for command in (generate, score):
        command.add_argument(
            "--jobs", type=int, default=1, help="Native Harbor trial concurrency"
        )
    from harbor.models.agent.name import AgentName

    generate.add_argument(
        "--agent", choices=sorted(AgentName.values()), default="mini-swe-agent"
    )
    generate.add_argument("--model", required=True)
    generate.add_argument(
        "--eval",
        action="store_true",
        help="Score this submission after generation succeeds",
    )
    generate.add_argument("--agent-env", action="append", default=[], metavar="NAME")
    generate.add_argument(
        "--agent-kwarg", "--ak", action="append", default=[], metavar="KEY=VALUE"
    )
    generate.add_argument(
        "--allow-model-host", action="append", default=[], metavar="HOST"
    )
    generate.add_argument("--auth", choices=["chatgpt", "api"])
    generate.add_argument("--auth-file", type=Path)
    generate.add_argument("--base-url")
    generate.add_argument("--api-key-name")
    generate.add_argument(
        "--api-format",
        choices=[
            "openai_chat_completions",
            "openai_responses",
            "anthropic_messages",
            "google_generate_content",
            "bedrock_converse",
        ],
    )
    score.add_argument("submission", type=Path, nargs="?", default=Path("submissions"))
    package.add_argument("--job", type=Path, required=True)
    package.add_argument("--output", type=Path, required=True)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "jobs", 1) < 1:
        parser.error("--jobs must be positive")
    if args.action != "list" and args.output is None:
        parent = "submissions" if args.action == "generate" else "runs"
        args.output = Path(parent) / (
            args.action
            + "-"
            + datetime.now().strftime("%Y%m%d-%H%M%S")
            + "-"
            + uuid4().hex[:8]
        )
    if args.action != "list":
        args.output = args.output.resolve()
        print("Output:", args.output, flush=True)
    try:
        if args.action != "package":
            args.tasks = resolve_tasks(args.tasks, local_only=args.local_images)
        if args.action == "list":
            records = task_statuses(args.tasks)
            if args.json:
                print(json.dumps(records, indent=2))
            else:
                print("ID\tPROJECT\tSTATUS\tREASON")
                for item in records:
                    print(
                        "\t".join(
                            str(item.get(key, ""))
                            for key in ("localid", "project", "status", "reason")
                        )
                    )
            return 0
        if args.action == "pull":
            tasks = select_tasks(args.task, args.tasks)
            acquire(tasks, args.output, local_only=args.local_images)
            print("Images ready:", len(tasks), flush=True)
            return 0
        if args.action == "generate":
            from .generation import generate

            tasks = select_tasks(args.task, args.tasks)
            code = generate(
                tasks,
                args.agent,
                args.model,
                args.output,
                auth=args.auth,
                auth_file=args.auth_file,
                jobs=args.jobs,
                base_url=args.base_url,
                api_key_name=args.api_key_name,
                api_format=args.api_format,
                local_only=args.local_images,
                agent_kwargs=args.agent_kwarg,
                agent_env=args.agent_env,
                allow_hosts=args.allow_model_host,
            )
            if code == 0 and args.eval:
                from .submissions import score

                code = score(
                    args.output / "submission",
                    args.tasks,
                    args.output / "evaluation",
                    args.jobs,
                    local_only=True,
                )
                summary_path = args.output / "summary.json"
                summary = json.loads(summary_path.read_text())
                summary.update(
                    evaluation_exit_code=code,
                    evaluation_result=str(args.output / "evaluation/eval.json"),
                )
                summary_path.write_text(json.dumps(summary, indent=2) + "\n")
            return code
        if args.action == "package":
            from .submissions import package_job

            print(json.dumps(package_job(args.job, args.output), indent=2))
            return 0
        from .submissions import score

        return score(
            args.submission.resolve(),
            args.tasks.resolve(),
            args.output,
            args.jobs,
            local_only=args.local_images,
        )
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print("Error:", exc, file=__import__("sys").stderr)
        return 1
