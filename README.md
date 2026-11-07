# SecureVibeBench

> **`habour` branch:** Use **native Harbor + your model** to generate submissions; `securevibebench eval` scores them. See [docs/README.md](docs/README.md) for fixed images, API-only agent execution, and offline submission scoring.

<p align="left">
    <!-- <img src="https://img.shields.io/badge/Version-v0.2-blue.svg?style=for-the-badge" alt="Version: v0.2"> -->
    <a href="https://2026.aclweb.org/"><img src="https://img.shields.io/badge/Venue-ACL%202026-2ea44f.svg?style=for-the-badge" alt="Venue: ACL 2026"></a>
    <a href="https://arxiv.org/abs/2509.22097"><img src="https://img.shields.io/badge/arXiv-2509.22097-b31b1b.svg?style=for-the-badge" alt="arXiv"></a>
    <a href="https://huggingface.co/datasets/iCSawyer/SecureVibeBench"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fhuggingface.co%2Fapi%2Fdatasets%2FiCSawyer%2FSecureVibeBench%3Fexpand%255B%255D%3DdownloadsAllTime&query=%24.downloadsAllTime&label=Downloads&color=FFD21F&style=for-the-badge&logo=huggingface" alt="Hugging Face Downloads"></a>
    <!-- <a href="https://huggingface.co/datasets/iCSawyer/SecureVibeBench"><img src="https://img.shields.io/badge/HF-SecureVibeBench-FFD21F.svg?style=for-the-badge&logo=huggingface" alt="Hugging Face: SecureVibeBench"></a> -->
    <!-- <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="License MIT"></a> -->
    <!-- <a href="https://chen-junkai.github.io/securevibebench-leaderboard/"><img src="https://img.shields.io/badge/Leaderboard-Online-2ea44f.svg?style=for-the-badge" alt="Leaderboard"></a> -->
</p>




> [!NOTE]
> The `habour` branch is experimental. Its prepared image catalog currently covers 21 tasks. Other benchmark tasks need prepared images before they can use this workflow. Use this checkout; this work has not been formally released.

<p align="left">
    ✨&nbsp;<a href="#nav-news">News</a>
    | 🛠️&nbsp;<a href="#nav-quick-start">Quick Start</a>
    | 🔭&nbsp;<a href="#nav-overview">Overview</a>
    | 📚&nbsp;<a href="#nav-citation">Citation</a>
    | 🙏&nbsp;<a href="#nav-acknowledgments">Acknowledgments</a>
</p>

<a id="nav-news"></a>

## ✨ News

- **[2026-10-29]** We updated to **v0.2**, introducing a PyPI package, Harbor-format tasks, and unified model evaluation. The original version is now referred to as **v0.1**.
<!-- - **[2026-06-06]** 🏆 We released the online [Leaderboard](https://chen-junkai.github.io/securevibebench-leaderboard/) for SecureVibeBench.
- **[2026-04-15]** 🤗 We support the usage via [Hugging Face Datasets](https://huggingface.co/datasets/iCSawyer/SecureVibeBench). 
- **[2026-04-11]** 🚀 We released code and data for SecureVibeBench. -->
- **[2026-04-07]** 🎉 Our paper has been accepted to **ACL 2026**.


<a id="nav-quick-start"></a>

## 🛠️ Quick Start

Requirements: Linux x86-64, Python 3.12+, and Docker with Compose. Use this experimental `habour` checkout.

### 1. Environment installation

```bash
pip install .
docker login ghcr.io
securevibebench list
securevibebench pull --task 992
```

Task files are hosted on HF `full-habour`. The image packages are private. Your GitHub account needs package access and a token with `read:packages`. The HF release contains 21 prepared image tasks. The package downloads the pinned task release into a local cache before trials. GitHub keeps only one example. `pull --task full` caches the HF task release and downloads all supported images. uv is optional: use `uv sync --locked` instead of `pip install .`.

### 2. Generate a submission with mini-swe-agent

```bash
export OPENAI_API_KEY='<your-api-key>'
securevibebench generate --agent mini-swe-agent --model 'openai/<model>' \
  --task 992 --local-images --output submissions/mini-992 --eval
```

Harbor runs its native mini-swe-agent adapter. The fixed image supplies the source, build dependencies, verifier, and cached native agent installation. Setup and compilation have no network; only agent execution can reach the model API allowlist. `--eval` scores the resulting submission in fresh offline containers. Patches, Harbor trajectories, and scores remain in the output directory.

### 3. Evaluate a submission

```bash
securevibebench eval submissions/mini-992 --local-images
securevibebench eval /path/to/external-submission --local-images
```

Scoring needs no model API key. Without `--local-images`, missing fixed images are pulled before trials start. No evaluation command builds an image or downloads task dependencies. See [the usage guide](docs/README.md) for task selection, other agents, and submission requirements.


<a id="nav-overview"></a>

## 🔭 Overview

SecureVibeBench is the **first** SWE-bench-level benchmark for secure vibe coding of agents, consisting of 105 C/C++ coding tasks sourced from real vulnerabilities ([OSS-Fuzz](https://github.com/google/oss-fuzz)/[ARVO](https://arxiv.org/abs/2408.02153)) covering various projects.

![Overview](https://raw.githubusercontent.com/iCSawyer/SecureVibeBench/main/assets/overview.png)

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

If you find our project useful, please consider citing our paper: 

```bibtex
@inproceedings{chen2026securevibebench,
  title     = "{S}ecure{V}ibe{B}ench: Benchmarking Secure Vibe Coding of {AI} Agents via Reconstructing Vulnerability-Introducing Scenarios",
  author    = "Chen, Junkai and Huang, Huihui and Lyu, Yunbo and An, Junwen and
               Shi, Jieke and Yang, Chengran and Zhang, Ting and Tian, Haoye and
               Li, Yikun and Li, Zhenhao and Zhou, Xin and Hu, Xing and Lo, David",
  editor    = "Liakata, Maria and Moreira, Viviane P. and Zhang, Jiajun and Jurgens, David",
  booktitle = "Proceedings of the 64th Annual Meeting of the {A}ssociation for {C}omputational {L}inguistics (Volume 1: Long Papers)",
  year      = "2026", month = jul, pages = "24144--24168",
  address   = "San Diego, California, United States",
  publisher = "Association for Computational Linguistics",
  url       = "https://aclanthology.org/2026.acl-long.1107/",
  ISBN      = "979-8-89176-390-6"
}
```

<a id="nav-acknowledgments"></a>

## 🙏 Acknowledgments

Our work builds on the following excellent works, and please consider citing them: [OSS-Fuzz](https://github.com/google/oss-fuzz), [ARVO](https://arxiv.org/abs/2408.02153), [habour](https://github.com/harbor-framework/harbor), and [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent).

```bibtex
@misc{mei2024arvoatlasreproduciblevulnerabilities,
  title         = {ARVO: Atlas of Reproducible Vulnerabilities for Open Source Software},
  author        = {Xiang Mei and Pulkit Singh Singaria and Jordi Del Castillo and Haoran Xi and
                   Abdelouahab and Benchikh and Tiffany Bao and Ruoyu Wang and Yan Shoshitaishvili and
                   Adam Doupé and Hammond Pearce and Brendan Dolan-Gavitt},
  year          = {2024}, eprint = {2408.02153},
  archivePrefix = {arXiv}, primaryClass = {cs.CR},
  url           = {https://arxiv.org/abs/2408.02153}
}
```

```bibtex
@article{serebryany2017oss,
  title  = {$\{$OSS-Fuzz$\}$-Google's continuous fuzzing service for open source software},
  author = {Serebryany, Kostya},
  year   = {2017}
}
```

```bibtex
@software{Harbor_Framework,
author = {{Harbor Framework Team}},
title = {{Harbor: A framework for evaluating and optimizing agents and models in container environments}},
year = {2026},
doi = {10.5281/zenodo.20953922},
url = {https://doi.org/10.5281/zenodo.20953922}
}
```

```bibtex
@inproceedings{yang2024sweagent,
  title={{SWE}-agent: Agent-Computer Interfaces Enable Automated Software Engineering},
  author={John Yang and Carlos E Jimenez and Alexander Wettig and Kilian Lieret and Shunyu Yao and Karthik R Narasimhan and Ofir Press},
  booktitle={The Thirty-eighth Annual Conference on Neural Information Processing Systems},
  year={2024},
  url={https://arxiv.org/abs/2405.15793}
}
```
