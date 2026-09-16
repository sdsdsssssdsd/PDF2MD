# PDF2MD

![PDF2MD](docs/images/product-promo.png)

Windows desktop app that turns **academic PDFs and screenshots into Markdown** you can actually edit in Typora or VS Code.

It is not “one model for the whole paper.” Structured conversion **parses cheaply**, **measures** what broke, then **recovers only those pages or blocks**. Vision modes ask DeepSeek to write Markdown on the first pass. A fifth mode repairs Markdown you already have.

Five workflows, kept separate on purpose:

| # | Mode | Input | Who writes Markdown | API key |
|---|------|-------|---------------------|---------|
| 1 | **日常识图** | Screenshots | DeepSeek Vision API (one shot) | Yes |
| 2 | **API 高精度** | PDF pages | DeepSeek Vision API (one shot) | Yes |
| 3 | **快速自动** | PDF | Docling / MinerU + local formula recovery | No |
| 4 | **网页高保真** | PDF pages | DeepSeek **website** via Playwright | No (browser login) |
| 5 | **格式修正** | Existing `.md` / `.txt` | DeepSeek Chat API | Yes |

Modes **1 / 2 / 4** do **not** add a second API “cleanup” call. Mode **3** stays local. Missing a DeepSeek key must not break modes 3–4.

> **Status: Alpha (v0.1.0-alpha).** Treat output as a draft. Spot-check formulas, tables, and figure placement before you publish.

License: **Apache-2.0** — [`LICENSE`](LICENSE) · [`NOTICE`](NOTICE).  
中文：[README.zh-CN.md](README.zh-CN.md)

---

## Before / after

Structured workflow (PDF excerpt → Markdown).

**PDF**

![PDF before conversion](docs/images/demo-01-pdf-source.png)

**Markdown**

![Markdown after conversion](docs/images/demo-02-markdown-result.png)

---

## Which mode?

| | **日常识图** | **API 高精度** | **快速自动** | **网页高保真** | **格式修正** |
|---|---|---|---|---|---|
| **Best for** | Slides, notes, phone shots | Official API, no browser | Batch papers, local GPU | Hard layouts, no API quota | Broken `$` / `$$` / `---` |
| **Output** | Preview or `日常识图/` | `output/<stem>_API视觉/` | `output/<stem>/` | `output/<stem>_高保真/` | Sibling `*_修复版.md` |
| **Typical time** | Seconds–minutes | Minutes | Seconds–minutes | Minutes–hours | Seconds–minutes |

The main window keeps frequent options only (export images + Markdown; tables + references). Diagnostics sit behind **…**.

---

## Markdown contract

Every export path is supposed to obey these rules. If a change breaks them, it is a bug.

```text
Inline math:   $n$
Display math (never a single-line $$...$$ fence):

$$
F(\lambda)\sim\cdots\tag{1}
$$

Do not auto-insert ---
Keep printed equation mentions: 公式 (19)
```

- At least one **blank line** between a table row (`| ... |`) and an image (`![...](...)`). Otherwise CommonMark / Typora / GitHub will swallow the figure into the table.
- Display math must be a **multiline** `$$` fence so Typora (MathJax) can show `\tag{n}` on the right.

---

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install docling
python run_gui.py
```

Or double-click `run_gui.bat`.

### DeepSeek API (modes 1, 2, 5)

```bat
set DEEPSEEK_API_KEY=your-deepseek-api-key
```

Or paste the key in **Settings → DeepSeek API**. It is stored in Windows Credential Manager and is not written to logs.

### Web vision (mode 4)

```bash
pip install playwright
playwright install chromium
```

Log in once in the headed browser. The profile lives in `data/deepseek_profile/` (gitignored). Do not close that window mid-batch. If DeepSeek shows **服务器繁忙**, the app waits about 10 minutes and continues.

### Local formula recovery (mode 3, optional)

Point a separate Python/CUDA env at DeepSeek-OCR-2. Do not stuff that stack into the GUI interpreter.

```bat
set PDF2MD_HF_HOME=%CD%\.cache\hf
set PDF2MD_DEEPSEEK_MODEL_DIR=%CD%\models\DeepSeek-OCR-2
set PDF2MD_DSOCR2_PYTHON=%CD%\envs\dsocr2\Scripts\python.exe
python scripts/start_deepseek_ocr_daemon.py --warmup
```

China mirrors are opt-in:

```bat
set HF_ENDPOINT=https://hf-mirror.com
set MINERU_MODEL_SOURCE=modelscope
```

See [`.env.example`](.env.example).

---

## What structured conversion actually does

Mode 3 is a small runtime, not “Docling with extra buttons”:

```text
PDF
  → cheap parse (Docling default; MinerU when the profiler says the file is scan-heavy)
  → DocumentIR (blocks, order, provenance — not a quality score dump)
  → Unified QA (VERIFIED / WARNINGS / INCOMPLETE / FAILED)
  → recover only failing pages/blocks (formula / table / coverage)
  → measure again
  → Markdown + .pdf2md/{run.json, document.ir.json, qa.json}
```

New backends register as **providers** (capability + license + isolation). They do **not** become a sixth UI mode. Experimental pieces (PP-Structure, Docling VLM, Marker, incubator parsers) stay **disabled** until they pass quality, stability, resource, license, and distributability gates. A benchmark win alone is not enough; Marker’s OpenRAIL-M license cannot become the default parser.

Web vision is an **experimental browser provider** with a site contract. If DeepSeek’s logged-in chat UI is gone, the run fails as `INCOMPATIBLE_SITE` instead of trying every selector until something sticks.

---

## CLI (no Qt)

```bash
python -m app doctor          # Python / GPU / providers / disk / licenses
python -m app providers       # installed / available / enabled / healthy
python -m app inspect paper.pdf --json
python -m app convert paper.pdf --json          # plan only
python -m app convert paper.pdf --execute       # runs ConversionService
python -m app benchmark --help
python -m app smoke
```

`convert` without `--execute` only profiles and plans. That is intentional: full conversion needs Docling (and optionally CUDA workers) on the machine.

---

## Requirements

- Windows 10/11 (primary)
- Python **3.10+** (3.12 tested)
- Structured + formulas: NVIDIA GPU recommended for the OCR worker
- Modes 1 / 2 / 5: DeepSeek API key
- Mode 4: Playwright Chromium + a logged-in DeepSeek account
- Install engines yourself: `docling`, optional `mineru`, CUDA `torch` that matches the driver

Optional extras (see `pyproject.toml`): `pdf2md[gui]`, `pdf2md[docling]`, `pdf2md[web]`, `pdf2md[paddle]`, `pdf2md[deepseek-ocr]`. Large CUDA runtimes stay out of the GUI environment.

---

## Project layout

```text
PDF2MD/
├── app/
│   ├── core/                 # JobRunner, DocumentIR, QA, providers, CLI
│   ├── engines/              # Docling / MinerU
│   ├── assets/               # figure naming
│   ├── formula/              # local formula recovery
│   ├── ocr/                  # DeepSeek-OCR-2 worker client
│   ├── vision_api/           # official DeepSeek HTTP
│   ├── deepseek_api/         # Chat + vision clients
│   ├── daily_vision/         # mode 1
│   ├── format_repair/        # mode 5
│   ├── vision_transcribe/    # modes 2 and 4
│   ├── ui/                   # controllers (Qt is a thread bridge)
│   └── main_window.py        # view
├── data/deepseek_templates/
├── scripts/
├── tests/
├── docs/images/
├── run_gui.py
└── requirements.txt
```

---

## Configuration

| Item | Notes |
|------|--------|
| Export directory | Main window |
| DeepSeek API | Settings: Base URL, key, vision model, transport |
| Image quality | Prefer **High (×3)** for papers with figures |
| Vision batch | Default 10 pages |
| Upload cooldown | Default 600 s when the site rate-limits |

| Variable | Purpose |
|----------|---------|
| `DEEPSEEK_API_KEY` | Official API (modes 1, 2, 5) |
| `PDF2MD_PYTHON` | Interpreter for subprocess tooling |
| `PDF2MD_DOCLING_ARTIFACTS` | Docling artifacts directory |
| `PDF2MD_HF_HOME` | Hugging Face cache root |
| `PDF2MD_DEEPSEEK_MODEL_DIR` | Local DeepSeek-OCR-2 snapshot |
| `PDF2MD_DSOCR2_PYTHON` | Interpreter that can load DeepSeek-OCR-2 |
| `PDF2MD_PADDLE_PYTHON` | Isolated Paddle env (never the GUI Python) |
| `DEEPSEEK_WORKER_IDLE_UNLOAD_SECONDS` | Unload OCR weights after idle (default 3600) |
| `HF_ENDPOINT` / `MINERU_MODEL_SOURCE` | Mirrors (opt-in) |

---

## Development

```bash
pip install -r requirements.txt
pip install -e ".[dev]"
python -m compileall app
python scripts/check_github_submit_privacy.py
pytest
```

CI (`.github/workflows/ci.yml`): `compileall` + `pytest` + privacy scan on Windows × Python 3.10–3.12. It does **not** download Docling / DeepSeek weights, run OmniDocBench, or call live DeepSeek.

| Script | Purpose |
|--------|---------|
| `scripts/start_deepseek_ocr_daemon.py` | Formula worker daemon |
| `scripts/calibrate_deepseek_ui.py` | Recalibrate web-vision UI templates |
| `scripts/record_deepseek_dom.py` | Record DOM replay steps |
| `scripts/run-portable.ps1` | Portable GUI launch (not an installer) |

Public schemas (`DocumentIR`, QA, `run.json`, Provider) are **1.x: additive only**. Breaking changes wait for 2.0.

---

## Contributing / security

[`CONTRIBUTING.md`](CONTRIBUTING.md) · [`SECURITY.md`](SECURITY.md)

Do not commit personal PDFs, model weights, `.cache`, browser profiles, or API keys.

---

## Disclaimer

- Converts files you provide locally.
- You are responsible for copyright and privacy of those files.
- Web vision uses the DeepSeek **website** under your account; follow their terms.
- Official API usage is billed by DeepSeek; keys stay on your machine.
- OCR / layout / formula accuracy varies. Review before you ship.
- Third-party engines and models have their own licenses (see [`NOTICE`](NOTICE)).
