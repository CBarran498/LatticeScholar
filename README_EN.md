# LatticeScholar

LatticeScholar is an open-source, evidence-grounded research intelligence workspace for project-centered literature discovery, reproducible search history, paper dissection, journal fit, reviewed policy signals, falsifiable idea formation, and project-grounded research discussion. Version 0.9 adds a document-first Idea Lab for PDF, DOCX, PPTX, XLSX, ODT, text, Markdown, RTF, HTML, CSV, JSON, BibTeX, RIS, NBIB, LaTeX, and Jupyter Notebook files, alongside balanced Chinese typography and a redesigned research-path overview. Usage logs store token and latency metadata, not prompts, paper content, questions, or answers.

The project is designed around four rules: claims should be traceable, search paths should be reproducible, missing information should stay missing, and generated ideas should be testable. It runs without an LLM. Optional providers include DeepSeek, Qwen, GLM, Kimi, MiniMax, Hunyuan, Doubao, Qianfan, OpenAI, Anthropic, Gemini, Mistral, Cohere, xAI, OpenRouter, and local/institutional OpenAI-compatible gateways. The balanced route uses fast models for query strategy and quality models for paper analysis, Idea Lab, and project discussion. Policy discovery uses a review queue and never auto-publishes discovered candidates.

See the [Chinese README](README.md) for the full quick start, feature matrix, architecture, privacy model, and roadmap.

## Desktop Download (No Python Required)

Download the standalone build for your platform from [GitHub Releases](https://github.com/CBarran498/LatticeScholar/releases), extract, and double-click to run. No Python installation, no command line required.

| Platform | File | Launch |
|---|---|---|
| macOS (Apple Silicon M1/M2/M3/M4) | `LatticeScholar-macos-arm64.tar.gz` | Extract, double-click `LatticeScholar` |
| Windows 10/11 (64-bit) | `LatticeScholar-windows-x64.zip` | Extract, double-click `LatticeScholar.exe` |
| Linux x64 (Ubuntu 22.04+/Debian 12+) | `LatticeScholar-linux-x64.tar.gz` | Extract, run `./LatticeScholar` |

Your browser opens [http://127.0.0.1:8765](http://127.0.0.1:8765) automatically. You will see an email login page on first launch — enter your email and the verification code is displayed directly on the page. All features are free for logged-in users. Data is stored in `~/.latticescholar/`.

> **Intel Mac users**: download the ARM64 build — macOS runs it automatically via Rosetta 2.
>
> **macOS Gatekeeper**: if blocked, right-click → Open → Confirm, or run `xattr -cr LatticeScholar/` in Terminal.
>
> **Windows SmartScreen**: if you see "Windows protected your PC", click "More info" → "Run anyway". Extract to a simple path without spaces or non-ASCII characters.
>
> **Unsupported environments** (Windows 7/8, 32-bit, Linux ARM64, older glibc, etc.): install from source with Python 3.9+.

## From Source (Developers)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
latticescholar
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). The default auth mode is `accounts` (email login). When SMTP is not configured, verification codes are shown directly on the login page. Set `LATTICE_ADMIN_EMAILS=your@email.edu` to get admin (Pro) access. To disable login entirely, set `LATTICE_AUTH_MODE=open`.

The default `core` PDF engine uses PDFPlumber with a pypdf fallback and keeps the Apache-compatible installation free of implicit AGPL components. It is intended for PDFs with a searchable text layer. An opt-in `advanced-pdf` extra provides PyMuPDF/PyMuPDF4LLM and local OCR routing:

```bash
pip install -e ".[advanced-pdf]"
export LATTICE_PDF_ENGINE=pymupdf
```

Those optional packages are licensed under AGPL v3 or an Artifex commercial license and are not relicensed by this project. Review [third-party notices](THIRD_PARTY_NOTICES.md) before hosted, closed-source, or commercial use.

Open **Model Console** to configure a provider through the encrypted BYOK flow. Server-side DeepSeek environment configuration remains available for unattended deployments:

```bash
export LATTICE_LLM_PROVIDER=deepseek
export DEEPSEEK_API_KEY=sk-your-key
export LATTICE_ALLOW_REMOTE_LLM=true
export LATTICE_DEEPSEEK_ROUTING=balanced
latticescholar
```

See the [multi-provider and BYOK guide](docs/MODEL_PROVIDERS.md) for the support matrix, routing, privacy boundaries, retries, cost controls, and troubleshooting. Never commit a real API key or submit identifiable, confidential, embargoed, or restricted research data to a remote model.

The community edition is licensed under Apache-2.0. The official hosted service may offer Free and Pro plans to cover managed infrastructure, model usage, licensed integrations, sync, and support. Self-hosted local workflows remain available without hosted quotas. Scholarly metadata and publication content remain subject to their respective source terms and copyrights. See the [open-source release guide](docs/OPEN_SOURCE_RELEASE.md) and [release audit](docs/RELEASE_AUDIT.md) before publishing a fork.
