# PDF2MD

![PDF2MD product](docs/images/product-promo.png)

Windows desktop tool for converting **academic PDFs → Markdown** using
**Docling** / **MinerU**, plus a conservative **RepairPipeline** after parsing.

> **Status: Alpha (v0.1.0-alpha).**  
> Formula reconstruction and complex academic layouts may still require
> manual review. Treat outputs as drafts, not publication-ready text.

License: **Apache-2.0** (see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE)).

---

## Screenshots

Same academic excerpt — **PDF before conversion** vs **Markdown after conversion**.

**Before · PDF**

![PDF before conversion](docs/images/demo-01-pdf-source.png)

**After · Markdown (.md)**

![Markdown after conversion](docs/images/demo-02-markdown-result.png)

---

## Current features

- Drag & drop one or many PDFs (Chinese paths / spaces supported)
- Engines: **Docling** (default) / **MinerU** / Auto
- Background workers (UI stays responsive)
- Configurable **export directory** (per-paper subfolders optional)
- Image quality: Fast / Standard / High; relative or absolute image links
- Formula recognition hooks (Docling enrichment / MinerU `-f`)
- Parser writes `*.raw.md` only; **RepairPipeline** produces final `*.md`
  (+ optional `*.repair.json`)
- Safe Unicode / decimal cleanup; conservative PDF geometry repairs
  (e.g. detached subscripts); table rows protected from `$` breaking `|`
- Settings persisted via `QSettings`
- Optional batch helper: `scripts/convert.ps1 -OutputDir ...`

## Roadmap (not implemented yet)

- Stronger formula-quality detection / confidence reports
- Local olmOCR (vision) fallback via Ollama
- DeepSeek-assisted multi-evidence reconciliation
- Broader table structure repair from PDF geometry

Do **not** assume olmOCR / DeepSeek are available in this Alpha.

---

## Requirements

- Windows 10/11 recommended (primary target)
- Python **3.10+** (3.12 tested)
- NVIDIA GPU optional but recommended
- Engines installed separately:
  - `docling`
  - `mineru` (optional but recommended)
  - CUDA-enabled `torch` if you want GPU acceleration

---

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
pip install docling
# MinerU: follow upstream docs, e.g. pip install "mineru[pipeline]"
python run_gui.py
```

Or double-click `run_gui.bat` (it also refreshes `PDF2MD.lnk` with the
desktop cover icon — pin or copy that shortcut for a branded launcher).

China network tip (optional — **not** set by default):

```bat
set HF_ENDPOINT=https://hf-mirror.com
set MINERU_MODEL_SOURCE=modelscope
```

---

## Usage

1. Start the app  
2. Set **导出目录** (export directory) if you do not want the default `output/`  
3. Drag PDFs in  
4. Choose engine / OCR / image options  
5. Click **开始转换**  
6. Open Markdown or the export folder  

Default layout: `output/<paper_name>/` (when “per paper folder” is on).

---

## Architecture

```text
PDF
 → Docling / MinerU (parser)
 → *.raw.md
 → RepairPipeline (analyze → safe repair → optional geometry)
 → *.md + *.repair.json
```

Parsers do **not** own final Markdown cleanup. Repair is intentionally
conservative: prefer missing a fix over corrupting prose.

---

## Project layout

```text
PDF2MD/
├── app/
│   ├── engines/          # Docling / MinerU → raw Markdown
│   ├── repair/           # RepairPipeline, analyzer, validator, router
│   │   └── pdf/          # geometry helpers (PyMuPDF)
│   ├── utils/            # paths, logging, md_postprocess
│   ├── workers/          # QThread conversion workers
│   ├── dialogs/
│   └── main_window.py
├── tests/                # pure-Python repair / postprocess tests
├── scripts/convert.ps1
├── .github/workflows/ci.yml
├── input/ output/ logs/  # gitignored runtime dirs (+ .gitkeep)
├── run_gui.py
├── requirements.txt
├── pyproject.toml
├── LICENSE / NOTICE
└── README.md
```

---

## Configuration

| Item | Notes |
|------|--------|
| Export dir | Main window / Settings |
| Image quality | Fast(1x) / Standard(2x) / High(3x) |
| Image path mode | Relative (default) or Absolute |
| OCR | Auto / Force / Off |
| Formulas | UI toggle; Docling enrichment + repair post-process |
| Parallel jobs | Prefer `1` on 8GB VRAM GPUs |

Environment overrides:

| Variable | Purpose |
|----------|---------|
| `PDF2MD_PYTHON` | Force Python executable for subprocess tooling |
| `PDF2MD_DOCLING_ARTIFACTS` | Local Docling model/artifacts directory |
| `HF_ENDPOINT` | Hugging Face endpoint / mirror (**opt-in**) |
| `MINERU_MODEL_SOURCE` | `huggingface` / `modelscope` / `local` (**opt-in**) |

---

## Development

```bash
pip install -r requirements.txt
pip install -e ".[dev]"
python -m compileall app
pytest
```

CI runs `compileall` + `pytest` on Python 3.10–3.12 and does **not**
download Docling/MinerU models.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).  
Security reports: [`SECURITY.md`](SECURITY.md).

---

## Disclaimer

- This tool converts documents you provide locally.
- You are responsible for copyright / privacy of your PDFs.
- OCR / layout / formula accuracy varies; review output before publishing.
- Third-party engines and models have their own licenses and terms
  (see [`NOTICE`](NOTICE)).
