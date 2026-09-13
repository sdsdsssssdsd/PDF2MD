# PDF2MD

![PDF2MD product](docs/images/product-promo.png)

Windows desktop app for **academic PDF / screenshots → Markdown**. Five independent workflows:

| # | Mode | Input | Who writes Markdown |
|---|------|-------|---------------------|
| 1 | **日常识图** | Screenshots | DeepSeek Vision API (one shot) |
| 2 | **API 高精度** | PDF pages | DeepSeek Vision API (one shot, format included) |
| 3 | **快速自动** | PDF | Docling / MinerU + local formula recovery |
| 4 | **网页高保真** | PDF pages | DeepSeek **website** via Playwright |
| 5 | **格式修正** | Existing `.md` / `.txt` | DeepSeek Chat API (full-document format repair) |

Modes **1 / 2 / 4** ask DeepSeek to emit correct Markdown **on the first pass** (inline `$...$`, multiline `$$`, no `---`). They do **not** add a second API call afterwards.

Mode **5** is a standalone fixer: paste or import a messy Markdown file, send the whole document to DeepSeek, save `原名_修复版.md`.

Mode **3** stays local. It never requires a DeepSeek API key.

> **Status: Alpha (v0.1.0-alpha).**  
> Treat all outputs as drafts. Formula-heavy or vision runs still need spot-checks.

License: **Apache-2.0** — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

中文说明：[README.zh-CN.md](README.zh-CN.md)

---

## Screenshots

Synthetic document excerpt — **PDF before** vs **Markdown after** (structured workflow).

**Before · PDF**

![PDF before conversion](docs/images/demo-01-pdf-source.png)

**After · Markdown**

![Markdown after conversion](docs/images/demo-02-markdown-result.png)

---

## Choose a workflow

| | **日常识图** | **API 高精度** | **快速自动** | **网页高保真** | **格式修正** |
|---|---|---|---|---|---|
| **Input** | Screenshots / paste | PDF | PDF | PDF | Existing Markdown |
| **Engine** | DeepSeek Vision API | DeepSeek Vision API | Docling / MinerU | DeepSeek web + Playwright | DeepSeek Chat API |
| **Needs API Key** | Yes | Yes | No | No (browser login) | Yes |
| **Output** | Preview or `日常识图/` archive | `output/<stem>_API视觉/` | `output/<stem>/` | `output/<stem>_高保真/` | Sibling `*_修复版.md` |
| **Typical time** | Seconds–minutes | Minutes | Seconds–minutes | Minutes–hours | Seconds–minutes |
| **Best for** | Slides, notes, phone shots | Official API, no browser | Batch papers, local GPU | Hard layouts, no API quota | Broken `$` / `$$` / `---` |

---

## Shared Markdown rules

Enforced in prompts and post-process:

```text
Inline math:   $n$
Display math:
$$
F(\lambda)\sim\cdots
$$
Never auto-insert ---
Keep equation refs: 公式 (19)
Restore context vars: 若 (n) 为奇数 → 若 $n$ 为奇数
```

- Blank line between table rows and `![figure](...)` (otherwise CommonMark eats the image into the table)
- Display math must be **multiline** `$$` fences (Typora / MathJax `\tag{n}`)
- Main window: high-frequency options only; diagnostics behind **…**

---

## Mode details

### 1. 日常识图 (Daily vision)

Paste or drop screenshots. DeepSeek Vision API transcribes visible text into Markdown (formulas, tables, figure markers). Optional archive writes `document.md` + source copies under `日常识图/`.

No second correction pass. Format rules live in the transcription prompt.

### 2. API 高精度 (Vision API)

PDF pages are rendered and sent to DeepSeek Vision API. Same prompt family as web vision: page markers, multiline `$$`, printed `\tag{n}` only when visible, no `---`.

Output folder: `<PdfName>_API视觉/`.

Configure **Settings → DeepSeek API**: Base URL, Key (`DEEPSEEK_API_KEY` or Windows Credential Manager), transport (auto / Base64 / Files API), timeout.

Missing Key **must not** break modes 3–4. Modes 1 / 2 / 5 will ask you to configure a Key.

### 3. 快速自动 (Structured)

| Area | Behavior |
|------|----------|
| Parse | **Docling** lean path (formula enrich OFF, tables FAST, pictures ×3) |
| Engines | Docling (default) / MinerU / Auto |
| Figures | **AssetPipeline**: `image_{N}_{stem}.png` |
| Formulas | Broken / `formula-not-decoded` → local DeepSeek-OCR-2 Worker |
| Identity | Bind printed Eq.(n) **before** OCR |
| Writeback | High-confidence only; multiline `$$` + optional `\tag{n}` |
| Worker | GUI-independent daemon on `127.0.0.1:18765` |

Illustrative warm times: no broken formulas **~4–11 s**; ~7 recoveries **~60–70 s**; cold model load can add **~3–4 min** once.

### 4. 网页高保真 (Web vision)

| Area | Behavior |
|------|----------|
| Render | PDF pages → labeled PNGs at **3×** (`bookfigures/`) |
| Transcribe | Batches of **10 pages** via Playwright (headed Chromium) |
| Prompt | Same first-pass format rules as API mode (`vision-transcribe-v2.2`) |
| Resilience | Level-0–4 recovery; **「服务器繁忙」** cooldown ~10 min |
| State | `.vision/manifest.json`; resumable |
| Figures | Docling auto-crop into `FIGURE` slots after merge |

**Playwright auto** (recommended): profile in `data/deepseek_profile/`.  
**Clipboard semi-auto**: manual paste if automation is unavailable.  
Calibrate UI: toolbar **DeepSeek UI…** or `scripts/calibrate_deepseek_ui.py`.

Does **not** call the Vision API a second time after the browser transcript.

### 5. 格式修正 (Format repair)

Standalone tool for Markdown that already exists but is broken:

```text
bad.md  →  DeepSeek Chat API  →  bad_修复版.md
```

Local code only: read file / clipboard, split long docs on safe boundaries (not inside `$$` or fences), call API, join, save. **No regex “is this inline or display?” layer.**

Requires an API Key. Does not rewrite math conclusions, numbers, or equation references.

---

## Architecture

```text
Parser
  ├── Daily screenshots  → DeepSeek Vision API
  ├── PDF Vision API     → DeepSeek Vision API
  ├── PDF Structured     → Docling / MinerU → AssetPipeline → FormulaPipeline
  └── PDF Web vision     → Playwright DeepSeek site
        ↓
Normalization (structured / web only)
  ├── AssetPipeline / figure writeback
  └── SafeRepair (Unicode, table↔figure spacing, $$ fences)
        ↓
Format repair mode (optional, existing Markdown only)
  └── DeepSeek full-document format repair
        ↓
Exporter
```

### Structured (Lean Balanced)

```text
PDF
  → Docling (lean)
  → *.raw.md + images
  → AssetPipeline
  → RepairPipeline
       → FormulaPipeline (local DeepSeek-OCR-2, optional)
  → *.md + *.formula_qa.json
```

### Vision (API or web)

```text
PDF
  → render pages
  → DeepSeek (API **or** website) — content + Markdown format in one response
  → merge / clean / figure writeback
  → final *.md
```

---

## Requirements

- Windows 10/11 (primary target)
- Python **3.10+** (3.12 tested)
- **Structured + formulas**: NVIDIA GPU recommended for DeepSeek-OCR-2
- **API / daily / format repair**: DeepSeek API Key
- **Web vision**: `playwright` + Chromium; logged-in DeepSeek account
- Install engines separately: `docling`, optional `mineru`, CUDA `torch` matching your driver

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

Or paste the Key in **Settings → DeepSeek API** (stored in Credential Manager; never logged).

### Web vision (Playwright)

```bash
pip install playwright
playwright install chromium
```

First run: log in to DeepSeek in the opened window. Profile is reused from `data/deepseek_profile/`.

### Local formula recovery (mode 3, optional)

```bat
set PDF2MD_HF_HOME=D:\path\to\hf-cache
set PDF2MD_DEEPSEEK_MODEL_DIR=D:\path\to\DeepSeek-OCR-2
set PDF2MD_DSOCR2_PYTHON=D:\path\to\dsocr2\Scripts\python.exe
```

```bash
python scripts/start_deepseek_ocr_daemon.py --warmup
```

China mirror tip (**opt-in**):

```bat
set HF_ENDPOINT=https://hf-mirror.com
set MINERU_MODEL_SOURCE=modelscope
```

See [`.env.example`](.env.example).

---

## Usage

1. Start the app
2. Pick a mode in the 2×2 (+ format repair) picker
3. Set export directory if needed
4. **日常识图**: paste/drop images
5. **API / 快速自动 / 网页**: drag PDFs → **开始转换**
6. **格式修正**: paste or import `.md` → **修正格式** (needs Key)
7. Review `*.md`; structured formula runs also write `*.formula_qa.json`

**Web vision tips**

- Do not close the DeepSeek browser during a batch
- On **服务器繁忙**, the app pauses ~10 minutes per account and resumes
- Right-click: **仅重合并与裁图** / **强制重跑浏览器转录**

---

## Project layout

```text
PDF2MD/
├── app/
│   ├── engines/              # Docling / MinerU
│   ├── assets/               # Figure naming / manifest
│   ├── repair/               # RepairPipeline + PDF geometry
│   ├── formula/              # Detection, identity, gate, writeback
│   ├── ocr/                  # DeepSeek-OCR-2 Worker client
│   ├── vision_api/           # Official DeepSeek HTTP client (Key, Files API)
│   ├── deepseek_api/         # Thin Chat wrapper (format repair)
│   ├── daily_vision/         # Screenshot → Markdown
│   ├── format_repair/        # Mode 5: chunk + full-document DeepSeek
│   ├── vision_transcribe/    # API + Playwright vision pipeline
│   ├── workers/              # QThread workers
│   ├── ui/widgets/           # WorkflowPicker, workspaces
│   └── main_window.py
├── data/
│   ├── deepseek_ui.json
│   └── deepseek_templates/   # L2 screenshot templates (incl. 服务器繁忙)
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
| Export dir | Main window |
| DeepSeek API | Settings page: Base URL, Key, vision model, transport |
| Image quality | Prefer **High (×3)** for papers with figures |
| Formulas + local OCR | Structured workflow only |
| Vision batch size | Default 10 pages |
| Server-busy cooldown | Default 600 s |

| Variable | Purpose |
|----------|---------|
| `DEEPSEEK_API_KEY` | Official API (daily / API vision / format repair) |
| `PDF2MD_PYTHON` | Python for subprocess tooling |
| `PDF2MD_DOCLING_ARTIFACTS` | Docling artifacts directory |
| `PDF2MD_HF_HOME` | HF / transformer cache root |
| `PDF2MD_DEEPSEEK_MODEL_DIR` | Local DeepSeek-OCR-2 snapshot |
| `PDF2MD_DSOCR2_PYTHON` | Interpreter that can load DeepSeek-OCR-2 |
| `DEEPSEEK_WORKER_IDLE_UNLOAD_SECONDS` | Idle unload model (default 3600) |
| `HF_ENDPOINT` / `MINERU_MODEL_SOURCE` | Mirrors (**opt-in**) |

---

## Development

```bash
pip install -r requirements.txt
pip install -e ".[dev]"
python -m compileall app
python scripts/check_github_submit_privacy.py
pytest
```

CI (`.github/workflows/ci.yml`): `compileall` + `pytest` + privacy scan on Windows × Python 3.10–3.12.  
Does **not** download Docling / DeepSeek weights or hit live DeepSeek.

| Script | Purpose |
|--------|---------|
| `scripts/start_deepseek_ocr_daemon.py` | Formula Worker daemon |
| `scripts/calibrate_deepseek_ui.py` | Recalibrate web-vision UI templates |
| `scripts/record_deepseek_dom.py` | Record DOM replay steps |
| `scripts/smoke_deepseek_load.py` | GPU load smoke test |

---

## Roadmap

- Stronger formula canary yield on hard documents
- Web vision: smarter batch sizing and ETA
- Optional Task Scheduler warmup for the OCR daemon
- Broader table structure repair from PDF geometry

Frozen for now: DeepSeek OCR prompt/token budget, Lean Docling picture×3, coverage-first mandatory OCR round.

---

## Contributing / security

[`CONTRIBUTING.md`](CONTRIBUTING.md) · [`SECURITY.md`](SECURITY.md)

Do not commit personal PDFs, model weights, `.cache`, or API keys.

---

## Disclaimer

- Converts documents you provide locally.
- You are responsible for copyright / privacy of your files.
- Web vision uses the DeepSeek **website** under your account; respect their terms.
- Official API usage is billed / limited by DeepSeek; keys stay on your machine.
- OCR / layout / formula accuracy varies; review before publishing.
- Third-party engines and models have their own licenses (see [`NOTICE`](NOTICE)).
