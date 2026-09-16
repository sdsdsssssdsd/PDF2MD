# Docs assets

Static assets referenced by the root [README.md](../README.md) and [README.zh-CN.md](../README.zh-CN.md).

## `images/`

| File | Usage |
|------|--------|
| `product-promo.png` | Hero / repository social preview (README top) |
| `product-promo2.png` | Alternate promo crop (optional marketing) |
| `demo-01-pdf-source.png` | README before/after — PDF excerpt |
| `demo-02-markdown-result.png` | README before/after — Markdown result |
| `1.png` / `2.png` | Extra promo / UI crops (optional) |

These files are **documentation only** (no runtime dependency). Do not commit user PDFs or conversion output here.

## Regenerating promos

Replace the PNGs under `docs/images/` and commit. They ship with the repository; nothing in the app loads them at runtime.
