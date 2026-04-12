#!/usr/bin/env python3
import argparse
import glob
import re
import subprocess
from datetime import datetime
from pathlib import Path
import json
import docker
import os

SEMGREP_TOKEN = os.environ.get("SEMGREP_APP_TOKEN", "")

class CommitSafetyStatus:
    vul = "vul"
    safe = "safe"
    err = "err"

def if_poc_crashes(log: str, returnCode: int) -> str:
    if "error while loading shared libraries" in log:
        print("[PANIC] RUNNING ENV WAS BROKEN")
        return CommitSafetyStatus.err
    if returnCode == 0:
        return CommitSafetyStatus.safe
    elif returnCode == 124:
        return CommitSafetyStatus.err
    elif returnCode == 255:
        if "WARNING: iterations invalid" not in log:
            return CommitSafetyStatus.vul
        else:
            print("Found a Fuzzing Target Doesn't Support `Fuzzer POC`")
            return CommitSafetyStatus.err
    else:
        if "out-of-memory" in log:
            return CommitSafetyStatus.err
        return CommitSafetyStatus.vul

def sh(cmd: list[str], check: bool = True) -> str:
    res = subprocess.run(cmd, check=check, capture_output=True, text=True)
    return res.stdout.strip()

def newest_result_dir(base_dir: Path) -> Path:
    ts_re = re.compile(r".*_(\d{8}_\d{6})$")
    candidates = []
    for p in base_dir.iterdir():
        if p.is_dir():
            m = ts_re.match(p.name)
            if m:
                try:
                    ts = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
                    candidates.append((ts, p))
                except ValueError:
                    pass
    if not candidates:
        raise FileNotFoundError(f"No timestamped result directories under: {base_dir}")
    candidates.sort(key=lambda x: x[0])
    return candidates[-1][1]

def find_patch(result_dir: Path) -> Path:
    matches = [Path(p) for p in glob.glob(str(result_dir / "**" / "*.patch"), recursive=True)]
    if not matches:
        raise FileNotFoundError(f"No .patch files found under: {result_dir}")
    matches.sort(key=lambda p: p.stat().st_mtime)
    return matches[-1]


"""
ID mapping for locating test scripts by alternate IDs.
Derived from evaluation/my_utils/eval_test.py to keep behavior consistent.
"""
id_map = {
    4167: 4088, 7995: 8007, 7997: 8007, 8000: 8007, 60467: 60475, 58671: 58660,
    58663: 58660, 11060: 11074, 10724: 10762, 52435: 52174, 38989: 38843,
    60993: 54162, 57911: 54162, 54163: 54162, 20702: 20729, 50436: 50406,
    31586: 31585, 11160: 11170, 64677: 64664, 61235: 61050, 43589: 43587,
    32340: 32345, 58786: 58785,
}

def run_test(container_id: str, repo_in: str, phase: str, log_dir: Path, arvo_id: str):
    """
    Integrated test runner adapted from evaluation/my_utils/eval_test.py.
    - Resolves a mapped test script ID if needed
    - Reads a host script from TEST_SCRIPTS_DIR (env, default ./test_scripts)
    - Filters out 'git checkout' lines for safety
    - Copies into container and executes, capturing logs; copies log back to host
    """
    arvo_id_int = int(arvo_id)
    script_id = id_map.get(arvo_id_int, arvo_id_int)
    if script_id != arvo_id_int:
        print(f"ℹ️  Using mapped script for ARVO {arvo_id_int} → {script_id}")

    test_scripts_dir = os.environ.get("TEST_SCRIPTS_DIR", "./test_scripts")
    script_host_path = os.path.join(test_scripts_dir, f"{script_id}.sh")
    script_container_path = f"/_evaluation/test_{arvo_id_int}.sh"
    log_container_path = f"/_evaluation/test_{phase}.log"
    log_host_path = log_dir / f"test_{phase}.log"

    subprocess.run(["docker", "exec", container_id, "mkdir", "-p", repo_in], check=True)

    try:
        with open(script_host_path, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"[WARN] Test script not found: {script_host_path}, skipping test phase '{phase}'")
        return

    filtered_lines = [l for l in lines if not l.strip().startswith("git checkout")] 

    script_name = f"test_{os.path.basename(script_host_path)}"
    filtered_path = os.path.join(str(log_dir), script_name)
    with open(filtered_path, "w") as f:
        f.writelines(filtered_lines)

    subprocess.run(["docker", "cp", filtered_path, f"{container_id}:{script_container_path}"], check=True)
    subprocess.run(["docker", "exec", container_id, "chmod", "+x", script_container_path], check=True)

    result = subprocess.run(["docker", "exec", container_id, "ls", "-l", script_container_path], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✅ {script_container_path} found inside the container:")
        print(result.stdout)
    else:
        print(f"❌ {script_container_path} NOT found inside the container.")
        print(result.stderr)

    print(f"🧪 Running test phase '{phase}' inside container...")
    subprocess.run([
        "docker", "exec", container_id, "bash", "-lc",
        f'bash "{script_container_path}" > "{log_container_path}" 2>&1; ' \
        f'rc=$?; echo "[exit code: $rc]" >> "{log_container_path}"; exit $rc'
    ])

    result = subprocess.run(["docker", "exec", container_id, "bash", "-c", f"test -f '{log_container_path}'"])
    if result.returncode != 0:
        print(f"❌ Log file not found in container: {log_container_path}")
    else:
        subprocess.run(["docker", "cp", f"{container_id}:{log_container_path}", str(log_host_path)], check=False)
        print(f"📄 Test log for phase '{phase}' copied to host: {log_host_path}")




def run_sast(
    container_id: str,
    repo_in: str,
    phase: str,
    commit_id: str
):
    """
    Run Semgrep inside an already running container that is checked out to the correct commit.

    Args:
        container_id: ID or name of the existing container.
        repo_in: Path to repo inside the container (where to run semgrep).

    Returns:
        (str, dict): path to JSON file on host, and parsed JSON results as Python dict.
    """
    output_filename = f"semgrep_results_{phase}.json"
    client = docker.from_env()
    container = client.containers.get(container_id)


    # Commands inside container
    setup_commands = f"""
    apt-get update && apt-get install -y wget git bzip2 jq curl && \
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh && \
    bash /tmp/miniconda.sh -b -p $HOME/miniconda && \
    rm /tmp/miniconda.sh && \

    # --- Fix channel issues ---
    $HOME/miniconda/bin/conda config --set always_yes yes && \
    $HOME/miniconda/bin/conda config --remove-key channels || true && \
    $HOME/miniconda/bin/conda config --add channels conda-forge && \
    $HOME/miniconda/bin/conda config --add channels defaults && \
    $HOME/miniconda/bin/conda config --set channel_priority flexible && \
    $HOME/miniconda/bin/conda config --set channel_alias https://conda.anaconda.org && \

    # --- Accept ToS ---
    $HOME/miniconda/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main && \
    $HOME/miniconda/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r && \

    # --- Create env + install semgrep ---
    $HOME/miniconda/bin/conda create -n py312 -y python=3.12 && \
    $HOME/miniconda/bin/conda run -n py312 python -m pip install --upgrade pip semgrep && \

    # --- Run semgrep ---
    export SEMGREP_APP_TOKEN={SEMGREP_TOKEN} && \
    cd {repo_in} && git reset --hard HEAD && git checkout {commit_id} && git clean -fd && \
    $HOME/miniconda/bin/conda run -n py312 semgrep ci --json | jq . > /_host/{output_filename} || \
    $HOME/miniconda/bin/conda run -n py312 semgrep ci --json | $HOME/miniconda/bin/conda run -n py312 python -m json.tool > /_host/{output_filename}
    """

    exec_result = container.exec_run(
        cmd=["bash", "-lc", setup_commands],
        stdout=True,
        stderr=True
    )
    print(exec_result.output.decode(errors="ignore"))



def main():
    ap = argparse.ArgumentParser(
        description="Run ARVO container, checkout a ref, apply newest patch, and commit."
    )
    ap.add_argument("--arvo-id", required=True)
    ap.add_argument("--mode", required=True)
    ap.add_argument("--repo-in", required=True)
    ap.add_argument("--vic", required=True)  
    ap.add_argument("--pvic", required=True)         
    ap.add_argument("--repo-url", required=True)
    ap.add_argument("--results-root", required=True)
    ap.add_argument("--run-poc", required=True)
    ap.add_argument("--run-test", required=True)
    ap.add_argument("--run-sast", required=True)
    ap.add_argument("--keep-alive", required=True)
    args = ap.parse_args()

    arvo_id = args.arvo_id
    mode = args.mode
    repo_in = args.repo_in
    vic = args.vic
    pvic = args.pvic
    results_root = Path(args.results_root)
    repo_url = args.repo_url

    base = results_root / arvo_id / mode
    if not base.exists():
        raise SystemExit(f"Results base dir not found: {base}")

    latest = newest_result_dir(base)
    patch = find_patch(latest)
    
    patch_lines = patch.read_text().splitlines()
    if not any(line.startswith("diff ") or line.startswith("@@") for line in patch_lines):
        print("⚠️ Patch file has no actual diff content, skipping execution.")

        json_output = {
            "repo_url": repo_url,
            "vic": vic,
            "pvic": pvic,
            "return_code": "-1",
            "analysis_result": "empty_diff",
            "raw_log": "The patch file does not contain any actual diff content (no changes to apply)."
        }
        json_log_path = latest / "arvo_result.json"
        with open(json_log_path, "w") as f:
            json.dump(json_output, f, indent=2)

        print(f"📄 JSON result written to: {json_log_path}")
        raise SystemExit("Patch file contains no diff content.")
    

    print(f"Newest result dir: {latest}")
    print(f"Patch file: {patch}")

    image_tag = f"n132/arvo:{arvo_id}-{mode}"

    log_path_in_container = f"/_evaluation/arvo_run.log"
    log_path_on_host = latest / "arvo_run.log"
    patch_on_host = latest / "patch_text_only.patch"

    try:
        
        # --- Phase 1: Checkout to pvic, apply patch, compile, arvo ,run test---
        container_id = sh([
            "docker", "run", "-dit", "--rm",
            "-v", f"{patch}:/_evaluation/result.patch:ro",
            "-v", f"{latest}:/_host:rw",              # <-- mount host results dir
            "-w", repo_in,
            image_tag,
            "bash"
        ])

        print(f"Started container: {container_id}")
        subprocess.run(["docker", "exec", container_id, "mkdir", "-p", "/_evaluation"], check=True)
        sh([
            "docker", "exec", container_id, "bash", "-lc",
            f"git reset --hard HEAD && git checkout {pvic} && git clean -fd"
        ])
        
        print(f"✅ Checked out to pvic: {pvic}")
        
        GIT_APPLY_CMDS = [
            "git apply",
            "git apply --reject",
            "patch --batch --fuzz=5 -p1 -i",
        ]
        applied_patch = False
        sh([ "docker", "exec", container_id, "bash", "-lc", "grep -v '^Binary files ' /_evaluation/result.patch > /_evaluation/result_text_only.patch" ])

        for git_apply_cmd in GIT_APPLY_CMDS:
            val = subprocess.run(
                [
                    "docker", "exec", container_id, "bash", "-lc",
                    f"{git_apply_cmd} /_evaluation/result_text_only.patch"
                ],
                capture_output=True,  # capture stdout and stderr
                text=True             # decode to str automatically
            )

            if val.returncode == 0:
                print(f"\"{git_apply_cmd}\" success:\n{val.stdout}")
                applied_patch = True
                break
            

        if not applied_patch:
            print(f"❌ Failed to apply patch: {val.stderr}")
            json_output = {
                "repo_url": repo_url,
                "vic": vic,
                "pvic": pvic,
                "return_code": val.returncode,
                "analysis_result": "patch_apply_error",
                "raw_log": val.stderr + "\n" + val.stdout
            }
            json_log_path = latest / "arvo_result.json"
            with open(json_log_path, "w") as f:
                json.dump(json_output, f, indent=2)
            raise SystemExit("Stopping due to patch apply failure.")

        # --- Run `arvo compile` ---
        poc_result = ""
        if args.run_poc=="TRUE":
            try:
                print("🔧 Running `arvo compile`...")
                sh(["docker", "exec", container_id, "bash", "-lc", "arvo compile"])
            except subprocess.CalledProcessError as e:
                print(f"\n❌ arvo compile failed with exit code {e.returncode}")
                # Save as JSON
                json_output = {
                    "repo_url": repo_url,
                    "vic": vic,
                    "pvic": pvic,
                    "return_code": e.returncode,
                    "analysis_result": "arvo_compile_error",
                    "raw_log": e.stderr
                }
                json_log_path = latest / "arvo_result.json"
                with open(json_log_path, "w") as f:
                    json.dump(json_output, f, indent=2)

                print(f"📄 JSON result written to: {json_log_path}")
                raise SystemExit("Stopping due to arvo compile error.")

            # --- Run `arvo` ---
            print("🚀 Running `arvo` and capturing output...")
            result = subprocess.run([
                "docker", "exec", container_id, "bash", "-lc",
                f"arvo > {log_path_in_container} 2>&1"
            ])
            return_code = result.returncode

            subprocess.run([
                "docker", "cp",
                f"{container_id}:{log_path_in_container}",
                str(log_path_on_host)
            ], check=False)
            print(f"📄 arvo log copied to host: {log_path_on_host}")

            log_text = Path(log_path_on_host).read_text(errors="replace")

            poc_result = if_poc_crashes(log_text, return_code)
            print(f"\n✅ Analysis Result: {poc_result}")

            json_output = {
                "repo_url": repo_url,
                "vic": vic,
                "pvic": pvic,
                "return_code": return_code,
                "analysis_result": poc_result,
                "raw_log": log_text
            }
            json_log_path = latest / "arvo_result.json"
            with open(json_log_path, "w") as f:
                json.dump(json_output, f, indent=2)

            print(f"📄 JSON result written to: {json_log_path}")
        
        
         # --- Run test ---
        if args.run_test=="TRUE":
            run_test(container_id, repo_in, phase="pvic_with_agent_patched", log_dir=latest, arvo_id=arvo_id)
            
        # --- Run sast tool ---
        if args.run_sast=="TRUE" and poc_result == CommitSafetyStatus.safe:
            run_sast(container_id, repo_in, phase="pvic_with_agent_patched", commit_id=pvic)

    finally:
        if args.keep_alive == "TRUE":
            print(f"\n✅ Container {container_id} is still running.")
            print(f"Inspect it with:\n  docker exec -it {container_id} bash")
        else:
            subprocess.run(["docker", "stop", container_id], check=False)
            print(f"\n🛑 Container {container_id} stopped and removed.")

if __name__ == "__main__":
    main()
