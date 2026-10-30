# SecureVibeBench

<p align="left">
    <img src="https://img.shields.io/badge/Version-v0.2-blue.svg?style=for-the-badge" alt="Version: v0.2">
    <a href="https://2026.aclweb.org/"><img src="https://img.shields.io/badge/Venue-ACL%202026-2ea44f.svg?style=for-the-badge" alt="Venue: ACL 2026"></a>
    <a href="https://arxiv.org/abs/2509.22097"><img src="https://img.shields.io/badge/arXiv-2509.22097-b31b1b.svg?style=for-the-badge" alt="arXiv"></a>
    <a href="https://huggingface.co/datasets/iCSawyer/SecureVibeBench"><img src="https://img.shields.io/badge/HF-SecureVibeBench-FFD21F.svg?style=for-the-badge&logo=huggingface" alt="Hugging Face: SecureVibeBench"></a>
    <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="License MIT"></a>
    <!-- <a href="https://chen-junkai.github.io/securevibebench-leaderboard/"><img src="https://img.shields.io/badge/Leaderboard-Online-2ea44f.svg?style=for-the-badge" alt="Leaderboard"></a> -->
</p>

> [!IMPORTANT]
> **SecureVibeBench is now v0.2**, with Harbor-format tasks and a unified mini-swe-agent evaluation workflow. We refer to the original release and evaluation workflow as **v0.1**.
>
> **Results obtained with v0.2 may differ from v0.1.** The original task instructions, tests, and scoring logic remain unchanged. Please report the benchmark version and agent/model configuration when comparing results.

<p align="left">
    ✨&nbsp;<a href="#nav-news">News</a>
    | 🛠️&nbsp;<a href="#nav-quick-start">Quick Start</a>
    | 🔭&nbsp;<a href="#nav-overview">Overview</a>
    | 📚&nbsp;<a href="#nav-citation">Citation</a>
    | 🙏&nbsp;<a href="#nav-acknowledgments">Acknowledgments</a>
</p>

<a id="nav-news"></a>

## ✨ News

- **[2026-10-29]** We updated to **v0.2**, introducing Harbor-format tasks and unified model generation and evaluation. The original version is now referred to as **v0.1**; results may differ between versions.
<!-- - **[2026-06-06]** 🏆 We released the online [Leaderboard](https://chen-junkai.github.io/securevibebench-leaderboard/) for SecureVibeBench.
- **[2026-04-15]** 🤗 We support the usage via [Hugging Face Datasets](https://huggingface.co/datasets/iCSawyer/SecureVibeBench). 
- **[2026-04-11]** 🚀 We released code and data for SecureVibeBench. -->
- **[2026-04-07]** 🎉 Our paper has been accepted to **ACL 2026**.


<a id="nav-quick-start"></a>

## 🛠️ Quick Start

<!-- The entry downloads tasks and their original evaluator from the HF [`habour-preview` branch](https://huggingface.co/datasets/iCSawyer/SecureVibeBench/tree/habour-preview), runs mini-swe-agent through Harbor, and reports functional and security metrics. Benchmark instructions, tests, and scoring remain unchanged. The existing HF default dataset is unaffected. -->

### 1. Prepare the environment

Install Python 3.8+ (available as `python3`), Git, Docker and Docker Compose, and ensure the Docker daemon is running. From the repository root, run:

```bash
bash evaluation/prepare.sh
```

The script **first downloads and verifies the HF tasks and evaluator** using only the system Python standard library. It then installs uv if needed (using curl or wget), **automatically clones official mini-swe-agent `v2.4.6`** into `evaluation/mini-swe-agent/`, and uses uv to prepare Python 3.12 and locked dependencies, including editable mini-swe-agent. The system Python is only used to bootstrap the dataset download; uv manages the project environment and dependencies. Existing source and local edits are preserved. No model API key is needed for this step.

### 2. Configure the model

For a model provider, export its API key and choose a `provider/model` identifier:

```bash
export OPENAI_API_KEY='<your-api-key>'
export MODEL='openai/<model-name>'
```

Use the corresponding key and model prefix for other providers, such as `ANTHROPIC_API_KEY` and `anthropic/<model-name>`.

For your own model served through an OpenAI-compatible API, configure its model name, endpoint and key instead:

```bash
export MODEL='openai/<your-served-model-name>'
export MODEL_BASE_URL='http://<model-server>:8000/v1'
export MODEL_API_KEY='<your-endpoint-api-key>'
```

The endpoint must be reachable from the task containers. If your server does not require authentication, use a placeholder key such as `unused`.

### 3. Run evaluation

Run one task:

```bash
bash evaluation/run.sh "$MODEL" --task 992
```

Run all 105 tasks by omitting `--task`:

```bash
bash evaluation/run.sh "$MODEL"
```

For your own OpenAI-compatible endpoint, pass the endpoint options with either command:

```bash
bash evaluation/run.sh "$MODEL" --task 992 \
  --base-url "$MODEL_BASE_URL" \
  --api-key-name MODEL_API_KEY \
  --api-format openai_chat_completions
```

Omit `--task 992` in this command to evaluate your own model on all tasks. Evaluation reuses the HF cache and synchronizes locked dependencies on each run.

Final metrics: `dev/runs/<job>/summary.json`. The same directory contains Harbor's original results, trajectories, patches, and benchmark reports. See [evaluation/README.md](./evaluation/README.md) for API endpoints and options.

```text
data/          One Harbor task example
evaluation/    generation → evaluation
pyproject.toml / uv.lock    Dependency declarations and locked versions
```

### Harbor task example

[`data/securevibebench-992/`](./data/securevibebench-992/) illustrates the Harbor task format:

```text
data/securevibebench-992/
├── instruction.md
├── task.toml
├── environment/
│   └── Dockerfile
└── tests/
    ├── task.json
    ├── test.sh
    └── original/
        ├── patch_diff.py
        ├── parse_test_report.py
        └── test_scripts/
            └── 992.sh
```

The original task instructions, tests, and evaluation code are preserved. This example requires the accompanying host-side verifier. Use [evaluation/](./evaluation/README.md) to run the benchmark; it downloads the complete tasks and evaluator from the HF `habour-preview` branch.


<a id="nav-overview"></a>

## 🔭 Overview

SecureVibeBench is the **first** SWE-bench-level benchmark for secure vibe coding of agents, consisting of 105 C/C++ coding tasks sourced from real vulnerabilities ([OSS-Fuzz](https://github.com/google/oss-fuzz)/[ARVO](https://arxiv.org/abs/2408.02153)) covering various projects.

![Overview](./assets/overview.png)

For each task in SecureVibeBench, we **reconstruct the real scenario where a human developer introduced a vulnerability** into the codebase, and then ask the agent to **implement the same requirements** and to see if the agent will also introduce the same vulnerability or not (and maybe new security issues as well).

To comprehensively evaluate the generated code of code agents, we conduct (i) **functional** correctness evaluation, (ii) PoV (proof-of-vulnerability) based **dynamic security** evaluation, and (iii) SAST-tool based **static security** evaluation.

> [!IMPORTANT]
> **Why SecureVibeBench?**
>
> - First SWE-bench-level, peer-reviewed benchmark for secure vibe coding.
> - Reconstruct coding scenarios where humans introduced vulnerabilities.
> - No other secure coding benchmark considering (i) functional correctness, (ii) PoV-based evaluation, and (iii) SAST tool-based new security issue detection.


<a id="nav-citation"></a>

## 📚 Citation

If you feel our work is helpful, please consider citing:

```bibtex
@inproceedings{chen2026securevibebench,
    title = "{S}ecure{V}ibe{B}ench: Benchmarking Secure Vibe Coding of {AI} Agents via Reconstructing Vulnerability-Introducing Scenarios",
    author = "Chen, Junkai  and
      Huang, Huihui  and
      Lyu, Yunbo  and
      An, Junwen  and
      Shi, Jieke  and
      Yang, Chengran  and
      Zhang, Ting  and
      Tian, Haoye  and
      Li, Yikun  and
      Li, Zhenhao  and
      Zhou, Xin  and
      Hu, Xing  and
      Lo, David",
    editor = "Liakata, Maria  and
      Moreira, Viviane P.  and
      Zhang, Jiajun  and
      Jurgens, David",
    booktitle = "Proceedings of the 64th Annual Meeting of the {A}ssociation for {C}omputational {L}inguistics (Volume 1: Long Papers)",
    month = jul,
    year = "2026",
    address = "San Diego, California, United States",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/2026.acl-long.1107/",
    pages = "24144--24168",
    ISBN = "979-8-89176-390-6"
}
```

<a id="nav-acknowledgments"></a>

## 🙏 Acknowledgments

Our work cannot be separated from the following excellent works, [OSS-Fuzz](https://github.com/google/oss-fuzz) and [ARVO](https://arxiv.org/abs/2408.02153):
```
@misc{mei2024arvoatlasreproduciblevulnerabilities,
      title={ARVO: Atlas of Reproducible Vulnerabilities for Open Source Software}, 
      author={Xiang Mei and Pulkit Singh Singaria and Jordi Del Castillo and Haoran Xi and Abdelouahab and Benchikh and Tiffany Bao and Ruoyu Wang and Yan Shoshitaishvili and Adam Doupé and Hammond Pearce and Brendan Dolan-Gavitt},
      year={2024},
      eprint={2408.02153},
      archivePrefix={arXiv},
      primaryClass={cs.CR},
      url={https://arxiv.org/abs/2408.02153}, 
}
```

```
@article{serebryany2017oss,
  title={$\{$OSS-Fuzz$\}$-Google's continuous fuzzing service for open source software},
  author={Serebryany, Kostya},
  year={2017}
}

```
