"""Run against an installed distribution: python -m unittest discover -s tests -v."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from securevibebench_evaluation import cli, resources, run


class InstalledPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="svb-package-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def arguments(self, *extra):
        return cli.build_parser().parse_args([
            "eval", "--model", "openai/test-model", "--cache-dir", str(self.directory / "cache"), *extra,
        ])

    def test_help_runs_outside_the_repository_without_creating_a_cache(self):
        cache = self.directory / "xdg-cache"
        result = subprocess.run(
            [sys.executable, "-m", "securevibebench_evaluation", "--help"],
            cwd=self.directory, env={**os.environ, "XDG_CACHE_HOME": str(cache)},
            capture_output=True, text=True, check=True,
        )
        self.assertIn("eval", result.stdout)
        self.assertNotIn("--model", result.stdout)
        evaluation = subprocess.run(
            [sys.executable, "-m", "securevibebench_evaluation", "eval", "--help"],
            cwd=self.directory, env={**os.environ, "XDG_CACHE_HOME": str(cache)},
            capture_output=True, text=True, check=True,
        )
        self.assertIn("securevibebench eval", evaluation.stdout)
        self.assertIn("--model", evaluation.stdout)
        self.assertIn("--task", evaluation.stdout)
        self.assertNotIn("--hf-revision", evaluation.stdout)
        self.assertFalse(cache.exists())

    def test_defaults_use_user_cache_and_current_working_directory(self):
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.directory)}):
            args = cli.build_parser().parse_args(["eval", "--model", "openai/test-model"])
        self.assertEqual(args.cache_dir, self.directory / "securevibebench/resources")
        self.assertEqual(args.jobs_dir, Path.cwd() / "runs")

    def test_all_tasks_and_agent_source_materialize_without_network_or_git(self):
        args = self.arguments()
        with mock.patch("socket.getaddrinfo", side_effect=AssertionError("unexpected network")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("unexpected subprocess")):
            dataset = run.prepare_dataset(args)
            again = run.prepare_dataset(args)
        self.assertEqual(dataset, again)
        self.assertEqual(len(list((dataset / "data").glob("*/task.toml"))), 105)
        self.assertTrue((dataset / "evaluator/harbor_verifier.py").is_file())
        self.assertTrue((dataset.parent / "mini-swe-agent/src/minisweagent/__init__.py").is_file())
        self.assertFalse((dataset / "dev").exists())
        self.assertEqual(args.resolved_hf_commit, resources.manifest()["hf_commit"])

    def test_corrupt_cached_task_is_rejected(self):
        args = self.arguments()
        dataset = run.prepare_dataset(args)
        instruction = dataset / "data/securevibebench-992/instruction.md"
        instruction.write_text(instruction.read_text() + "\nchanged\n")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            run.prepare_dataset(args)

    def test_single_task_custom_endpoint_and_original_verifier(self):
        from harbor.agents.factory import AgentFactory
        from harbor.agents.installed.mini_swe_agent import MiniSweAgent
        from harbor.models.job.config import JobConfig
        from securevibebench_evaluation.hf_verifier import load_verifier

        args = self.arguments("--task", "992", "--task", "securevibebench-992",
                              "--base-url", "http://model-server:8000/v1",
                              "--api-key-name", "MODEL_API_KEY", "--api-format", "openai_chat_completions")
        dataset = run.prepare_dataset(args)
        with mock.patch("socket.getaddrinfo", side_effect=AssertionError("unexpected network")):
            config = JobConfig.model_validate(run.build_config(args, bundle=dataset))
            agent_class = AgentFactory.get_agent_class_from_config(config.agents[0])
            verifier = load_verifier(dataset, config.verifier.kwargs["verifier_sha256"])
        self.assertEqual(len(config.tasks), 1)
        self.assertEqual(config.tasks[0].path, dataset / "data/securevibebench-992")
        self.assertEqual(config.datasets, [])
        self.assertEqual(config.agents[0].base_url, args.base_url)
        self.assertEqual(config.agents[0].model_api_key_name, "MODEL_API_KEY")
        self.assertTrue(issubclass(agent_class, MiniSweAgent))
        self.assertIs(agent_class.run, MiniSweAgent.run)
        self.assertEqual(verifier.ROOT, dataset)
        self.assertEqual(Path(config.verifier.kwargs["baseline_dir"]), dataset.parent / "baselines")
        self.assertEqual(config.verifier.kwargs["run_sast"], "FALSE")

    def test_sast_is_disabled_by_default_and_can_be_enabled_explicitly(self):
        args = self.arguments("--task", "992")
        dataset = run.prepare_dataset(args)
        default = run.build_config(args, bundle=dataset)
        self.assertEqual(default["verifier"]["kwargs"]["run_sast"], "FALSE")
        enabled = self.arguments("--task", "992", "--run-sast", "TRUE")
        run.prepare_dataset(enabled)
        config = run.build_config(enabled, bundle=dataset)
        self.assertEqual(config["verifier"]["kwargs"]["run_sast"], "TRUE")

    def test_all_tasks_default_and_invalid_task(self):
        args = self.arguments()
        dataset = run.prepare_dataset(args)
        config = run.build_config(args, bundle=dataset)
        self.assertEqual(config["datasets"][0]["path"], str(dataset / "data"))
        for task in ("999999", "../992"):
            args.task = [task]
            with self.subTest(task=task), self.assertRaises(ValueError):
                run.build_config(args, bundle=dataset)

    def test_config_preview_does_not_start_docker_or_call_a_model(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), \
                mock.patch.object(run, "execute", side_effect=AssertionError("unexpected evaluation")):
            result = cli.main(["eval", "--model", "openai/test-model", "--task", "992",
                               "--cache-dir", str(self.directory / "cache"), "--print-config"])
        self.assertEqual(result, 0)
        self.assertEqual(len(json.loads(output.getvalue())["tasks"]), 1)

    def test_installed_console_entry_point_evaluates_the_selected_task(self):
        command = Path(sys.executable).parent / "securevibebench"
        result = subprocess.run(
            [str(command), "eval", "--model", "openai/test-model", "--task", "992",
             "--cache-dir", str(self.directory / "cache"), "--print-config"],
            cwd=self.directory, env=os.environ.copy(),
            capture_output=True, text=True, check=True,
        )
        config = json.loads(result.stdout)
        self.assertEqual(config["agents"][0]["model_name"], "openai/test-model")
        self.assertTrue(config["tasks"][0]["path"].endswith("securevibebench-992"))

    def test_cli_requires_a_model_and_rejects_unknown_commands(self):
        for arguments in (["eval"], ["unknown"], ["--model", "openai/test-model"]):
            with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    cli.main(arguments)
                self.assertEqual(error.exception.code, 2)

    def test_legacy_evaluate_command_remains_available(self):
        command = Path(sys.executable).parent / "svb-evaluate"
        result = subprocess.run([str(command), "--help"], cwd=self.directory,
                                capture_output=True, text=True, check=True)
        self.assertIn("--model", result.stdout)


if __name__ == "__main__":
    unittest.main()
