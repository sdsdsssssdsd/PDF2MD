# Docs assets

Static assets referenced by the root [README.md](../README.md) and [README.zh-CN.md](../README.zh-CN.md).

## `images/`

| File | Usage |
|------|--------|
| `product-promo.png` | Hero / repository social preview (README top) |
| `product-promo.prompt.md` | Brief that produced the hero (AI-generated — keep in sync with the five workflows) |
| `product-promo2.png` | Alternate promo crop (optional marketing) |
| `demo-01-pdf-source.png` | README before/after — PDF excerpt |
| `demo-02-markdown-result.png` | README before/after — Markdown result |
| `1.png` / `2.png` | Extra promo / UI crops (optional) |

These files are **documentation only** (no runtime dependency). Do not commit user PDFs or conversion output here.

## Regenerating promos

Replace the PNGs under `docs/images/` and commit. They ship with the repository; nothing in the app loads them at runtime.

The hero (`product-promo.png`) is a generated infographic, not a screenshot. Its text brief lives in
[`images/product-promo.prompt.md`](images/product-promo.prompt.md) — update that file whenever the
framework shown in the picture changes (workflows, layers, progress model, on-disk layout), so the
picture never drifts from the README tables.
