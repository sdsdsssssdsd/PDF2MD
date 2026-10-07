"""应用路径：项目根目录由 __file__ / 环境变量解析。"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

# 固定使用用户默认 Python，不依赖 PATH / venv
PYTHON_EXE = Path(os.environ.get("PDF2MD_PYTHON", "python"))
DOCLING_EXE = Path(os.environ.get("PDF2MD_DOCLING_EXE", "docling"))
MINERU_EXE = Path(os.environ.get("PDF2MD_MINERU_EXE", "mineru"))

APP_ROOT = Path(__file__).resolve().parents[2]
DOCLING_ARTIFACTS_DIR = Path(
    os.environ.get(
        "PDF2MD_DOCLING_ARTIFACTS",
        str(APP_ROOT / ".cache" / "docling-artifacts"),
    )
)
INPUT_DIR = APP_ROOT / "input"
TESTSET_DIR = Path(os.environ.get("PDF2MD_TESTSET_DIR", str(APP_ROOT / "input")))
OULAD_PDF_DIR = Path(
    os.environ.get("PDF2MD_OULAD_PDF_DIR", str(INPUT_DIR / "oulad"))
)
OUTPUT_DIR = APP_ROOT / "output"
# 视觉模式的中间产物（渲染页 / 批次回答 / 断点清单）：不进用户导出目录
VISION_WORK_ROOT = OUTPUT_DIR / "_vision_work"
LOGS_DIR = APP_ROOT / "logs"
# 实验结果诊断镜像（timings / formula_qa）；不进论文导出目录
EXPERIMENT_DIR = LOGS_DIR / "experiment"
ICONS_DIR = APP_ROOT / "icons"
SCRIPTS_DIR = APP_ROOT / "scripts"
BENCHMARK_DIR = APP_ROOT / "debug" / "formula_benchmark"
BENCHMARK_CORPUS = BENCHMARK_DIR / "corpus"
BENCHMARK_RUNS = BENCHMARK_DIR / "runs"
BENCHMARK_EXPECTED = BENCHMARK_DIR / "expected"
DEEPSEEK_BENCHMARK_RUNS = BENCHMARK_DIR / "deepseek_runs"
K5_BENCHMARK_DIR = APP_ROOT / "benchmarks"
K5_MANIFESTS_DIR = K5_BENCHMARK_DIR / "manifests"
K5_CROPS_DIR = K5_BENCHMARK_DIR / "crops"
K5_TIGHT_CROPS_DIR = K5_CROPS_DIR / "tight"
K5_GOLD_DIR = K5_BENCHMARK_DIR / "gold"
K5_RESULTS_DIR = K5_BENCHMARK_DIR / "results"
K5_HARD_CASES_DIR = K5_BENCHMARK_DIR / "hard_cases"

# 转换结果保存位置：
#   pdf_sibling  —— 默认。在原 PDF 所在文件夹建「PDF名_MD」独立文件夹
#   root_folder  —— 导出根目录下建「PDF名」独立文件夹
#   root_flat    —— 直接写入导出根目录（多篇混在一起）
SAVE_MODE_PDF_SIBLING = "pdf_sibling"
SAVE_MODE_ROOT_FOLDER = "root_folder"
SAVE_MODE_ROOT_FLAT = "root_flat"
SAVE_MODES = (SAVE_MODE_PDF_SIBLING, SAVE_MODE_ROOT_FOLDER, SAVE_MODE_ROOT_FLAT)
DEFAULT_SAVE_MODE = SAVE_MODE_PDF_SIBLING
MD_SIBLING_SUFFIX = "_MD"
VISION_SIBLING_SUFFIX = "_高保真"
VISION_API_SIBLING_SUFFIX = "_API视觉"

SAVE_MODE_LABELS = {
    SAVE_MODE_PDF_SIBLING: "PDF 所在文件夹（PDF名_MD）",
    SAVE_MODE_ROOT_FOLDER: "导出目录（每篇独立子文件夹）",
    SAVE_MODE_ROOT_FLAT: "导出目录（不建子文件夹）",
}


def normalize_save_mode(mode: object) -> str:
    text = str(mode or "").strip()
    return text if text in SAVE_MODES else DEFAULT_SAVE_MODE


def ensure_dirs() -> None:
    for d in (
        INPUT_DIR,
        OUTPUT_DIR,
        LOGS_DIR,
        EXPERIMENT_DIR,
        ICONS_DIR,
        SCRIPTS_DIR,
        BENCHMARK_DIR,
        BENCHMARK_CORPUS,
        BENCHMARK_RUNS,
        BENCHMARK_EXPECTED,
        DEEPSEEK_BENCHMARK_RUNS,
        K5_BENCHMARK_DIR,
        K5_MANIFESTS_DIR,
        K5_CROPS_DIR,
        K5_TIGHT_CROPS_DIR,
        K5_GOLD_DIR,
        K5_RESULTS_DIR,
        K5_HARD_CASES_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)


def experiment_doc_dir(stem: str) -> Path:
    """单篇文档的实验结果镜像目录。"""
    d = EXPERIMENT_DIR / stem
    d.mkdir(parents=True, exist_ok=True)
    return d


def sibling_archive_dir(pdf_path: Path, suffix: str = MD_SIBLING_SUFFIX) -> Path:
    """PDF 旁的同名独立文件夹：paper.pdf -> <原目录>/paper{suffix}。"""
    pdf = Path(pdf_path)
    return pdf.parent / f"{pdf.stem}{suffix}"


def sibling_archive_dir_writable(pdf_path: Path, suffix: str = MD_SIBLING_SUFFIX) -> bool:
    """能否在 PDF 所在文件夹建档（只读目录会失败 → 调用方回退导出根目录）。"""
    target = sibling_archive_dir(pdf_path, suffix)
    try:
        if target.exists():
            return target.is_dir() and os.access(target, os.W_OK)
        parent = target.parent
        if not parent.is_dir():
            return False
        return os.access(parent, os.W_OK)
    except OSError:
        return False


def task_output_dir(
    output_root: Path,
    pdf_path: Path,
    per_folder: bool = True,
    *,
    save_mode: object = DEFAULT_SAVE_MODE,
) -> Path:
    """结构化转换输出目录。

    默认 save_mode=pdf_sibling：PDF 旁「PDF名_MD」；不可写时回退导出根目录。
    per_folder 是旧参数：未显式给出 save_mode 时，per_folder=False 等价 root_flat。
    """
    mode = normalize_save_mode(save_mode)
    stem = Path(pdf_path).stem
    if mode == SAVE_MODE_PDF_SIBLING:
        if sibling_archive_dir_writable(pdf_path, MD_SIBLING_SUFFIX):
            return sibling_archive_dir(pdf_path, MD_SIBLING_SUFFIX)
        return Path(output_root) / stem
    if mode == SAVE_MODE_ROOT_FLAT or not per_folder:
        return Path(output_root)
    return Path(output_root) / stem


def vision_task_output_dir(
    output_root: Path,
    pdf_path: Path,
    *,
    save_mode: object = SAVE_MODE_ROOT_FOLDER,
) -> Path:
    """高保真模式：PDF 旁「Pdf名_高保真」，或导出目录下同名子文件夹。"""
    mode = normalize_save_mode(save_mode)
    if mode == SAVE_MODE_PDF_SIBLING and sibling_archive_dir_writable(
        pdf_path, VISION_SIBLING_SUFFIX
    ):
        return sibling_archive_dir(pdf_path, VISION_SIBLING_SUFFIX)
    return Path(output_root) / f"{Path(pdf_path).stem}{VISION_SIBLING_SUFFIX}"


def vision_api_task_output_dir(
    output_root: Path,
    pdf_path: Path,
    *,
    save_mode: object = SAVE_MODE_ROOT_FOLDER,
) -> Path:
    """API 高精度视觉：PDF 旁「Pdf名_API视觉」，或导出目录下同名子文件夹。"""
    mode = normalize_save_mode(save_mode)
    if mode == SAVE_MODE_PDF_SIBLING and sibling_archive_dir_writable(
        pdf_path, VISION_API_SIBLING_SUFFIX
    ):
        return sibling_archive_dir(pdf_path, VISION_API_SIBLING_SUFFIX)
    return Path(output_root) / f"{Path(pdf_path).stem}{VISION_API_SIBLING_SUFFIX}"


def resolve_vision_output_dir(
    output_root: Path,
    pdf_path: Path,
    workflow: str,
    *,
    save_mode: object = SAVE_MODE_ROOT_FOLDER,
) -> Path:
    """兼容入口：返回视觉模式的**工作目录**（渲染页 / 批次 / manifest 所在处）。"""
    return resolve_vision_paths(
        output_root, pdf_path, workflow, save_mode=save_mode
    ).work_dir


@dataclass(frozen=True)
class VisionPaths:
    """视觉模式落盘布局。

    work_dir    —— 渲染页 / 批次回答 / manifest（断点续跑与裁图重建都靠它）
    result_dir  —— 最终 <PDF名>.md
    images_name —— 图片目录名（位于 result_dir 下）
    """

    work_dir: Path
    result_dir: Path
    images_name: str = "images"
    flat: bool = False

    @property
    def images_dir(self) -> Path:
        return self.result_dir / self.images_name


def _vision_suffix(workflow: str) -> str:
    from app.task_model import is_vision_api_workflow, normalize_workflow

    if is_vision_api_workflow(normalize_workflow(workflow)):
        return VISION_API_SIBLING_SUFFIX
    return VISION_SIBLING_SUFFIX


def _has_vision_manifest(path: Path) -> bool:
    return (Path(path) / ".vision" / "manifest.json").is_file()


def _legacy_manifest_matches_pdf(path: Path, pdf_path: Path) -> bool:
    """旧工作目录是否属于这个 PDF（manifest 记录了完整路径时按路径核对）。"""
    import json

    try:
        data = json.loads(
            (Path(path) / ".vision" / "manifest.json").read_text(encoding="utf-8")
        )
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    recorded = str(data.get("pdf_path") or "").strip()
    if not recorded:
        return True  # 老 manifest 只记文件名：按目录同名沿用
    try:
        return Path(recorded).resolve() == Path(pdf_path).resolve()
    except OSError:
        return False


def resolve_vision_paths(
    output_root: Path,
    pdf_path: Path,
    workflow: str,
    *,
    save_mode: object = DEFAULT_SAVE_MODE,
) -> VisionPaths:
    """视觉模式落盘：结果与工作文件分开，还是同一处。

    root_flat（导出目录·不建子文件夹）：
      结果扁平写入导出目录 —— <导出目录>/<PDF名>.md + <导出目录>/<PDF名>.images/；
      渲染页 / 批次 / manifest 等工作文件放到应用侧
      output/_vision_work/<PDF名><后缀>_<路径哈希>/，多篇之间互不覆盖。
    其它模式：工作目录与结果目录同一个（PDF 旁，或导出目录下的 <PDF名><后缀>）。
    """
    mode = normalize_save_mode(save_mode)
    pdf = Path(pdf_path)
    stem = pdf.stem
    suffix = _vision_suffix(workflow)
    workspace = (
        sibling_archive_dir(pdf, suffix)
        if mode == SAVE_MODE_PDF_SIBLING and sibling_archive_dir_writable(pdf, suffix)
        else Path(output_root) / f"{stem}{suffix}"
    )
    if mode != SAVE_MODE_ROOT_FLAT:
        return VisionPaths(work_dir=workspace, result_dir=workspace)

    digest = hashlib.sha1(str(pdf.resolve()).encode("utf-8")).hexdigest()[:8]
    work_dir = VISION_WORK_ROOT / f"{stem}{suffix}_{digest}"
    legacy = Path(output_root) / f"{stem}{suffix}"
    if not _has_vision_manifest(work_dir) and _legacy_manifest_matches_pdf(legacy, pdf):
        # 扁平化之前留下的工作目录：沿用，避免重渲染 + 重调 API
        work_dir = legacy
    return VisionPaths(
        work_dir=work_dir,
        result_dir=Path(output_root),
        images_name=f"{stem}.images",
        flat=True,
    )


def resolve_output_dir(
    output_root: Path,
    pdf_path: Path,
    workflow: str,
    *,
    save_mode: object = DEFAULT_SAVE_MODE,
    per_folder: bool = True,
) -> Path:
    """按工作流统一解析输出目录（结构化 / 高保真 / API 视觉共用）。

    视觉模式返回**工作目录**；结果 md 的位置见 resolve_vision_paths().result_dir。
    """
    from app.task_model import is_vision_workflow

    if is_vision_workflow(workflow):
        return resolve_vision_output_dir(
            output_root, pdf_path, workflow, save_mode=save_mode
        )
    return task_output_dir(output_root, pdf_path, per_folder, save_mode=save_mode)


def daily_archive_root(output_root: Path) -> Path:
    return Path(output_root) / "日常识图"


def daily_archive_dir(output_root: Path, label: str = "截图") -> Path:
    from datetime import datetime
    import re

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    safe = re.sub(r'[<>:"/\\|?*]', "_", (label or "截图").strip())[:40] or "截图"
    return daily_archive_root(output_root) / f"{stamp}_{safe}"
