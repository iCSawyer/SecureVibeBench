"""Native Harbor configuration and result helpers."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

import tomli_w
from harbor.models.task.config import TaskConfig

HOSTS = ["api.openai.com", "api.anthropic.com", "chatgpt.com", "auth.openai.com"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_config(path, config):
    TaskConfig.model_validate(config)
    path.write_text(tomli_w.dumps(config))


def select_cpus(environment: Path, count=2):
    """Spread configured task budgets across the CPUs available on this host."""
    allowed = sorted(os.sched_getaffinity(0))
    offset = int.from_bytes(
        hashlib.sha256(str(environment.resolve()).encode()).digest()[:4], "big"
    ) % len(allowed)
    return [
        allowed[(offset + i) % len(allowed)]
        for i in range(min(max(1, math.ceil(count)), len(allowed)))
    ]


def configure_dns(environment: Path, count=2):
    """Configure host-specific DNS and CPU placement for native Docker trials."""
    environment.mkdir(parents=True, exist_ok=True)
    cpus = select_cpus(environment, count)
    import ipaddress

    nameservers = []
    for candidate in [
        Path("/etc/resolv.conf"),
        Path("/run/systemd/resolve/resolv.conf"),
    ]:
        if not candidate.exists():
            continue
        for line in candidate.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "nameserver":
                address = ipaddress.ip_address(parts[1])
                if not address.is_loopback and str(address) not in nameservers:
                    nameservers.append(str(address))
        if nameservers:
            break
    if not nameservers:
        raise ValueError(
            "No container-reachable DNS resolver found; configure host DNS first"
        )
    (environment / "resolv.conf").write_text(
        "".join("nameserver " + host + "\n" for host in nameservers)
    )
    (environment / "docker-compose.yaml").write_text(
        "services:\n"
        "  main:\n"
        '    cpuset: "' + ",".join(map(str, cpus)) + '"\n'
        "    volumes:\n"
        "      - ${CONTEXT_DIR}/resolv.conf:/etc/resolv.conf:ro\n"
        "  harbor-docker-egress-control-sidecar:\n"
        "    volumes:\n"
        "      - ${CONTEXT_DIR}/resolv.conf:/etc/resolv.conf:ro\n"
    )
    return cpus


def agent_backend_error(trial):
    log = trial / "agent/codex.txt"
    if log.is_file():
        for line in log.read_text(errors="replace").splitlines():
            if (
                " ERROR codex_core::tools::router:" in line
                and "failed to spawn code-mode host" in line
            ):
                return "AgentToolBackendError"
    return None


def summarize_job(job):
    records = []
    for path in sorted(job.glob("*/result.json")):
        data = json.loads(path.read_text())
        exception = data.get("exception_info") or {}
        records.append(
            {
                "task": data.get("task_name"),
                "rewards": (data.get("verifier_result") or {}).get("rewards"),
                "exception_type": exception.get("exception_type")
                or agent_backend_error(path.parent),
                "result": str(path),
            }
        )
    return records
