# Contributing to PDF2MD

Thanks for your interest in contributing.

## Development setup

1. Fork and clone the repository
2. Create a virtualenv and install `requirements.txt`
3. Install Docling / MinerU according to upstream docs
4. Run lightweight checks (no model download):
   ```bash
   python -m compileall -q app tests
   pip install pytest
   pytest
   ```
5. Run `python run_gui.py`

## Guidelines

- Keep the UI responsive: never run Docling/MinerU on the Qt main thread
- Prefer small, focused PRs
- Do not commit model weights, caches, personal PDFs, or local absolute paths
- Match existing code style; avoid unrelated refactors

## Pull requests

Please include:

- What changed and why
- How you tested (OS / Python / GPU if relevant)
- Screenshots for UI changes when useful

## License

By contributing, you agree that your contributions are licensed under the
Apache License 2.0 (see `LICENSE`).
