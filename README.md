# PDF2MD

![PDF2MD product](docs/images/product-promo.png)

Windows desktop tool for **academic PDF → Markdown**, built around a
**Lean Docling** parse path plus a **DeepSeek-OCR-2** formula recovery
pipeline (persistent local Worker, controlled writeback).

> **Status: Alpha (v0.1.0-alpha).**  
> Most papers finish in seconds. Formula-heavy PDFs take longer and still
> need spot-checks. Treat outputs as drafts, not camera-ready copy.

License: **Apache-2.0** (see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE)).

中文说明：[README.zh-CN.md](README.zh-CN.md)

---

## Screenshots

Same academic excerpt — **PDF before** vs **Markdown after**.

**Before · PDF**

![PDF before conversion](docs/images/demo-01-pdf-source.png)

**After · Markdown (.md)**

![Markdown after conversion](docs/images/demo-02-markdown-result.png)

---

## What it does today

| Area | Behavior |
|------|----------|
| Parse | **Docling** lean path (formula enrich OFF, tables FAST, pictures ×3) |
| Engines | Docling (default) / MinerU / Auto |
| Figures | **AssetPipeline**: `image_{N}_{stem}.png`, optional `manifest.json` |
| Formulas | Detect broken / `formula-not-decoded` → DeepSeek formula-crop OCR |
| Identity | Bind printed Eq.(n) **before** OCR (PDF label / defining prose) |
| Writeback | High-confidence only; multiline `$$` + optional `\tag{n}` |
| Worker | **GUI-independent daemon** on `127.0.0.1:18765` (survives GUI restart) |
| Yield | CPU salvage after OCR (no extra GPU call) when extract/gate would discard a good raw |
| Repair | Conservative post-process: Unicode, table/`$` safety, table↔figure blank lines |

Typical wall times on a warm machine (illustrative, OULAD-style papers):

- No broken formulas → **~4–11 s**
- ~7 formulas recovered → **~60–70 s**
- Cold DeepSeek load (first time / model unloaded) → can add **~3–4 min** once per session

---

## Architecture (Lean Balanced)

```text
PDF
  → Docling (lean: no formula enrich)
  → *.raw.md + images
  → AssetPipeline
  → RepairPipeline
       → FormulaPipeline
            → bbox + Equation Identity
            → DeepSeek Worker OCR ×1 / formula (coverage-first)
            → FormulaCropExtractor (+ CPU salvage)
            → Gate (strong context conflict = hard veto)
            → Controlled writeback ($$\n...\n$$  \tag{n}?)
  → *.md + *.formula_qa.json + timings_*.json
```

**Design rules we keep:**

- DeepSeek decides **content**, not equation **numbers**
- No invented formulas from prose
- Prefer missing a writeback over a false accept
- GUI exit does **not** kill the OCR Worker (session-persistent daemon)

---

## Requirements

- Windows 10/11 (primary target)
- Python **3.10+** (3.12 tested)
- NVIDIA GPU strongly recommended for DeepSeek formula recovery
- Install engines separately:
  - `docling`
  - `mineru` (optional)
  - CUDA `torch` matching your driver
- Optional local DeepSeek-OCR-2 weights + dedicated venv (see env table)

---

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install docling
python run_gui.py
```

Or double-click `run_gui.bat` (also refreshes `PDF2MD.lnk`).

### DeepSeek formula recovery (optional but recommended)

Point env vars at your local install (never commit real paths/secrets):

```bat
set PDF2MD_HF_HOME=D:\path\to\hf-cache
set PDF2MD_DEEPSEEK_MODEL_DIR=D:\path\to\DeepSeek-OCR-2
set PDF2MD_DSOCR2_PYTHON=D:\path\to\dsocr2\Scripts\python.exe
```

Optional: keep the Worker warm across GUI restarts:

```bash
python scripts/start_deepseek_ocr_daemon.py --warmup
```

China mirror tip (**opt-in**):

```bat
set HF_ENDPOINT=https://hf-mirror.com
set MINERU_MODEL_SOURCE=modelscope
```

---

## Usage

1. Start the app  
2. Set export directory if needed  
3. Enable **DeepSeek limited production** / formulas when recovering academic equations  
4. Drag PDFs → **开始转换**  
5. Open `*.md`; for formula runs also check `*.formula_qa.json` (`recovery_yield`, `failure_class`, writeback counts)

Default layout: `output/<paper_name>/` (when per-paper folders are on).

---

## Project layout

```text
PDF2MD/
├── app/
│   ├── engines/           # Docling / MinerU
│   ├── formula/           # pipeline, identity, writeback, gain/tokens
│   ├── ocr/               # DeepSeek worker client, extractor, shadow, salvage
│   ├── assets/            # figure naming / manifest
│   ├── repair/            # RepairPipeline + PDF geometry
│   ├── workers/           # QThread conversion
│   └── main_window.py
├── scripts/               # daemon, convert helpers, phase runners
├── tests/
├── .cursor/rules/         # export hard rules (table↔figure, multiline $$)
├── docs/images/
├── run_gui.py
└── README.md
```

---

## Configuration

| Item | Notes |
|------|--------|
| Export dir | Main window / Settings |
| Image quality | Prefer **High (×3)** for papers with figures |
| Formulas + DeepSeek limited production | Lean Balanced formula path |
| Parallel jobs | Prefer `1` on 8GB VRAM |

| Variable | Purpose |
|----------|---------|
| `PDF2MD_PYTHON` | Python for subprocess tooling |
| `PDF2MD_DOCLING_ARTIFACTS` | Docling artifacts directory |
| `PDF2MD_HF_HOME` | HF / transformer cache root |
| `PDF2MD_DEEPSEEK_MODEL_DIR` | Local DeepSeek-OCR-2 snapshot |
| `PDF2MD_DSOCR2_PYTHON` | Interpreter that can load DeepSeek-OCR-2 |
| `PDF2MD_BENCH_PDF` / `PDF2MD_BENCH_ROOT` | Local benchmark PDFs for scripts |
| `DEEPSEEK_WORKER_IDLE_UNLOAD_SECONDS` | Idle unload model (default 3600); process stays |
| `HF_ENDPOINT` / `MINERU_MODEL_SOURCE` | Mirrors (**opt-in**) |

See [`.env.example`](.env.example).

---

## Development

```bash
pip install -r requirements.txt
pip install -e ".[dev]"
python -m compileall app
pytest
```

CI runs `compileall` + `pytest` on Python 3.10–3.12 and does **not**
download Docling / DeepSeek weights.

---

## Roadmap

- Stronger hard-document canary (O-003 / O-024 / O-028 style yield)
- Optional Windows login Task Scheduler warmup for the daemon
- Broader table structure repair from PDF geometry
- UI ETA when many formulas are queued

Frozen for now (intentionally): DeepSeek prompt / token budget, Lean Docling
picture×3, Worker watchdog timeouts, coverage-first mandatory OCR round.

---

## Contributing / security

[`CONTRIBUTING.md`](CONTRIBUTING.md) · [`SECURITY.md`](SECURITY.md)

---

## Disclaimer

- Converts documents you provide locally.
- You are responsible for copyright / privacy of your PDFs.
- OCR / layout / formula accuracy varies; review before publishing.
- Third-party engines and models have their own licenses (see [`NOTICE`](NOTICE)).
