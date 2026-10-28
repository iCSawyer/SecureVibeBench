"""Install the official mini-swe-agent source editable inside Harbor sandboxes.

Only installation changes. The agent loop, model requests, command execution,
version detection, and ATIF conversion are inherited from Harbor's integration.
"""

from __future__ import annotations

import json
from pathlib import Path
import shlex
import shutil
import tempfile
from typing import Any

from harbor.agents.installed.mini_swe_agent import MiniSweAgent, MiniSweAgentOptions
from harbor.environments.base import BaseEnvironment
from pydantic import Field


REMOTE_SOURCE = "/installed-agent/mini-swe-agent-source"


def copy_source(source: Path, target: Path) -> None:
    """Copy the editable package, including local edits, without local state."""
    target.mkdir(parents=True)
    for name in ("pyproject.toml", "README.md", "LICENSE.md"):
        shutil.copyfile(source / name, target / name)
    shutil.copytree(
        source / "src", target / "src", symlinks=False,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info", ".git", ".venv", ".env", ".env.*"),
    )


def editable_proof_command(expected_version: str | None) -> str:
    code = f'''import importlib.metadata as metadata
import importlib.util
import json
from pathlib import Path

dist = metadata.distribution("mini-swe-agent")
direct = json.loads(dist.read_text("direct_url.json") or "{{}}")
module = importlib.util.find_spec("minisweagent")
source = Path({REMOTE_SOURCE!r})
assert direct.get("dir_info", {{}}).get("editable") is True, direct
assert direct.get("url") == source.as_uri(), direct
assert module is not None and Path(module.origin).is_relative_to(source), module
expected = {expected_version!r}
assert expected is None or dist.version == expected, (dist.version, expected)
print(json.dumps({{"version": dist.version, "editable": True, "url": direct["url"], "module_file": module.origin}}))
'''
    return (
        'if [ -f "$HOME/.local/bin/env" ]; then . "$HOME/.local/bin/env"; fi; '
        'export PATH="$HOME/.local/bin:$PATH"; '
        '"$(uv tool dir)/mini-swe-agent/bin/python" - <<\'SVB_EDITABLE_PROOF\'\n'
        + code + "SVB_EDITABLE_PROOF"
    )


class EditableMiniSweAgentOptions(MiniSweAgentOptions):
    source_dir: str = Field(description="Local official mini-swe-agent source checkout to install editable")


class EditableMiniSweAgent(MiniSweAgent):
    options_model = EditableMiniSweAgentOptions
    options: EditableMiniSweAgentOptions

    def __init__(self, *, source_dir: str | Path, **kwargs: Any) -> None:
        self.source_dir = Path(source_dir).resolve()
        for relative in ("pyproject.toml", "README.md", "LICENSE.md", "src/minisweagent/__init__.py"):
            if not (self.source_dir / relative).is_file():
                raise ValueError(f"Incomplete mini-swe-agent checkout: {self.source_dir / relative}")
        super().__init__(source_dir=str(self.source_dir), **kwargs)

    async def install(self, environment: BaseEnvironment) -> None:
        # Reuse upstream bootstrap rather than maintaining a second installer.
        await super().install(environment)
        setup_dir = self.logs_dir / "setup"
        setup_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="mini-source-", dir=setup_dir) as temporary:
            payload = Path(temporary) / "source"
            copy_source(self.source_dir, payload)
            await self.exec_as_root(environment, command=f"mkdir -p {shlex.quote(REMOTE_SOURCE)}")
            await environment.upload_dir(source_dir=payload, target_dir=REMOTE_SOURCE)
        if environment.default_user is not None:
            await self.exec_as_root(
                environment,
                command=f"chown -R {shlex.quote(str(environment.default_user))} {shlex.quote(REMOTE_SOURCE)}",
            )
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                'if [ -f "$HOME/.local/bin/env" ]; then . "$HOME/.local/bin/env"; fi; '
                'export PATH="$HOME/.local/bin:$PATH"; '
                'tool_python="$(uv tool dir)/mini-swe-agent/bin/python"; '
                # Only the pure-Python editable target needs a source build.
                # Keep upstream's already-resolved binary dependencies intact.
                f'UV_NO_BUILD=false uv pip install --python "$tool_python" --editable {shlex.quote(REMOTE_SOURCE)} '
                '--no-deps --reinstall-package mini-swe-agent && '
                'uv pip check --python "$tool_python" && mini-swe-agent --help >/dev/null'
            ),
        )
        proof = await self.exec_as_agent(environment, command=editable_proof_command(self._version))
        runtime = json.loads((proof.stdout or "").strip().splitlines()[-1])
        (self.logs_dir / "mini-swe-agent-editable.json").write_text(json.dumps({
            "host_source": str(self.source_dir), "container_source": REMOTE_SOURCE,
            "runtime": runtime,
        }, indent=2, sort_keys=True) + "\n")
