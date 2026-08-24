from pathlib import Path

src = Path(r"d:\Docling\benchmarks\crops\tight")
dst = Path(r"d:\Docling\_tmp_review")
dst.mkdir(exist_ok=True)
for p in src.iterdir():
    if not p.name.startswith("15_"):
        continue
    for f in sorted(p.glob("*_p3_eq*.png")):
        out = dst / f"quat_{f.stem.split('_p3_')[-1]}.png"
        out.write_bytes(f.read_bytes())
        print(out, f.stat().st_size)
