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

    def test_runtime_entrypoint_imports(self):
        from harbor.job import Job
        from securevibebench_evaluation.editable_mini import EditableMiniSweAgent

        self.assertTrue(callable(Job.create))
        self.assertTrue(callable(EditableMiniSweAgent.install))

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
        self.assertEqual(config.agents[0].kwargs["version"], "2.4.6")
        self.assertEqual(Path(config.agents[0].kwargs["toolchain_cache_dir"]),
                         run.user_cache_dir() / "agent-toolchain")
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

    def test_version_flag_reports_the_installed_distribution(self):
        from importlib.metadata import version

        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as error:
            cli.main(["--version"])
        self.assertEqual(error.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), f"securevibebench {version('securevibebench')}")

    def saved_job(self):
        from harbor.models.job.config import JobConfig

        args = self.arguments("--task", "992")
        config = JobConfig.model_validate(run.build_config(args, bundle=run.prepare_dataset(args)))
        job = self.directory / "runs" / "job"
        job.mkdir(parents=True)
        (job / "config.json").write_text(config.model_dump_json(exclude_defaults=True))
        return job

    def test_resume_reuses_the_saved_job_config(self):
        job = self.saved_job()
        output = io.StringIO()
        with contextlib.redirect_stdout(output), \
                mock.patch.object(run, "execute", side_effect=AssertionError("unexpected evaluation")):
            result = cli.main(["eval", "--resume", str(job), "--print-config"])
        self.assertEqual(result, 0)
        config = json.loads(output.getvalue())
        self.assertEqual((config["job_name"], Path(config["jobs_dir"])), ("job", job.parent))
        self.assertTrue(config["tasks"][0]["path"].endswith("securevibebench-992"))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["eval", "--resume", str(job), "--model", "openai/x"]), 2)
            self.assertEqual(cli.main(["eval", "--resume", str(self.directory)]), 2)

    def test_interrupted_trials_and_their_containers_are_selected_precisely(self):
        job = self.directory / "job"
        for name, result in (("done", {}), ("cancelled", {"exception_info": {"exception_type": "CancelledError"}}),
                             ("failed", {"exception_info": {"exception_type": "RuntimeError"}}), ("killed", None)):
            (job / name).mkdir(parents=True)
            if result is not None:
                (job / name / "result.json").write_text(json.dumps(result))
        trials = run.unfinished_trials(job)
        self.assertEqual([trial.name for trial in trials], ["cancelled", "killed"])

        client = mock.Mock()
        client.containers.return_value = [
            {"Id": "env", "Image": "killed__env_main", "Mounts": [],
             "Labels": {"com.docker.compose.project": "killed__env"}},
            {"Id": "evaluator", "Image": "n132/arvo:992-vul", "Labels": {},
             "Mounts": [{"Source": str(job / "cancelled/verifier/original/out")}]},
            {"Id": "finished", "Image": "n132/arvo:992-vul", "Labels": {},
             "Mounts": [{"Source": str(job / "done/verifier")}]},
            {"Id": "someone-else", "Image": "n132/arvo:992-vul", "Labels": {}, "Mounts": []},
        ]
        client.networks.return_value = []
        with mock.patch("docker.from_env", return_value=mock.Mock(api=client)):
            self.assertEqual(run.remove_trial_containers(trials), 2)
        removed = [call.args[0] for call in client.remove_container.call_args_list]
        self.assertEqual(removed, ["env", "evaluator"])
        client.remove_image.assert_called_once_with("killed__env_main")

    def test_agent_toolchain_is_cached_once_and_restored(self):
        import asyncio
        from securevibebench_evaluation.editable_mini import EditableMiniSweAgent

        args = self.arguments()
        dataset = run.prepare_dataset(args)
        agent = EditableMiniSweAgent(source_dir=dataset.parent / "mini-swe-agent", logs_dir=self.directory / "logs",
                                     model_name="openai/test-model", version="2.4.6",
                                     toolchain_cache_dir=self.directory / "toolchain")
        commands = []

        async def execute(self, environment, command, **kwargs):
            commands.append(command)
            return mock.Mock(stdout="/root|x86_64|ldd (GNU libc) 2.23", return_code=0)

        async def download(source_path, target_path):
            Path(target_path).write_bytes(b"toolchain")

        environment = mock.Mock(download_file=mock.AsyncMock(side_effect=download), upload_file=mock.AsyncMock())
        with mock.patch.object(EditableMiniSweAgent, "exec_as_agent", execute), \
                mock.patch.object(EditableMiniSweAgent, "ensure_system_dependencies", mock.AsyncMock()):
            archive = asyncio.run(agent.toolchain_archive(environment))
            self.assertFalse(asyncio.run(agent.restore_toolchain(environment, archive)))
            asyncio.run(agent.save_toolchain(environment, archive))
            self.assertEqual(archive.read_bytes(), b"toolchain")
            self.assertTrue(asyncio.run(agent.restore_toolchain(environment, archive)))
        environment.upload_file.assert_awaited_once()
        self.assertIn("tar -xzf", commands[-1])
        self.assertEqual(list(archive.parent.iterdir()), [archive])

    def test_interleaved_parallel_ctest_output_is_parsed_per_test(self):
        import importlib.util

        dataset = run.prepare_dataset(self.arguments())
        path = dataset / "data/securevibebench-10172/tests/original/parse_test_report.py"
        spec = importlib.util.spec_from_file_location("svb_parse_test_report", path)
        parser = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parser)
        log = "\n".join([
            "Test project /src/wireshark/build",
            "3: test_alpha (suite_a.case_a)",
            "2: test_beta (suite_b.case_b)",
            "3: Alpha description ... ok",
            "2: Beta description ... ERROR",
            "3: OK (skipped=2)",
            "100% tests passed, 0 tests failed out of 2",
        ])
        result = parser.parse_test_output(10172, log)
        self.assertEqual(result.PassList, ["test_alpha (suite_a.case_a)"])
        self.assertEqual(result.FailList, ["test_beta (suite_b.case_b)"])

    def test_legacy_evaluate_command_remains_available(self):
        command = Path(sys.executable).parent / "svb-evaluate"
        result = subprocess.run([str(command), "--help"], cwd=self.directory,
                                capture_output=True, text=True, check=True)
        self.assertIn("--model", result.stdout)


if __name__ == "__main__":
    unittest.main()
