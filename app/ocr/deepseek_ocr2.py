"""DeepSeek-OCR 2 Adapter：lazy load；Formula / Page 分 profile（Phase 5F）。"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from app.ocr import (
    PROMPT_DOCUMENT,
    PROMPT_FREE_OCR,
    DeepSeekOCRUnavailable,
    DocumentOCRResult,
    OCRMode,
)
from app.ocr.deepseek_profiles import (
    DEEPSEEK_FORMULA_PROFILE,
    DEEPSEEK_PAGE_PROFILE,
    DeepSeekOCRProfile,
)


class DeepSeekOCR2Recognizer:
    """Document / Region / Formula → text。禁止在 import 时加载模型。"""

    name = "deepseek-ocr-2"
    _model = None
    _tokenizer = None
    _load_seconds: float = 0.0
    _load_count: int = 0
    _device: str = ""
    _torch_dtype: str = ""
    _last_load_stages: dict = {}

    def __init__(
        self,
        *,
        model_name: str = "deepseek-ai/DeepSeek-OCR-2",
        device: str = "auto",
        dtype: str = "auto",
        base_size: int = 1024,
        image_size: int = 768,
        crop_mode: bool = True,
        allow_cpu: bool = False,
        default_prompt: str = PROMPT_DOCUMENT,
        formula_profile: DeepSeekOCRProfile | None = None,
        page_profile: DeepSeekOCRProfile | None = None,
        max_new_tokens: int | None = None,
    ) -> None:
        self.model_name = model_name
        self.device_pref = (device or "auto").lower()
        self.dtype_pref = (dtype or "auto").lower()
        self.base_size = int(base_size)
        self.image_size = int(image_size)
        self.crop_mode = bool(crop_mode)
        self.allow_cpu = bool(allow_cpu)
        self.default_prompt = default_prompt
        self.formula_profile = formula_profile or DEEPSEEK_FORMULA_PROFILE
        self.page_profile = page_profile or DEEPSEEK_PAGE_PROFILE
        self.max_new_tokens_override = max_new_tokens

    @classmethod
    def reset_class_model(cls) -> None:
        cls._model = None
        cls._tokenizer = None
        cls._load_seconds = 0.0
        cls._load_count = 0
        cls._device = ""
        cls._torch_dtype = ""

    @classmethod
    def model_load_count(cls) -> int:
        return int(cls._load_count)

    def _resolve_device(self) -> str:
        import torch

        if self.device_pref in {"auto", ""}:
            if torch.cuda.is_available():
                return "cuda:0"
            if not self.allow_cpu:
                raise DeepSeekOCRUnavailable(
                    "gpu_recommended",
                    detail="DeepSeek-OCR-2 未检测到 CUDA；CPU 极慢，已拒绝。传 allow_cpu=True 可强制。",
                )
            return "cpu"
        if self.device_pref.startswith("cuda") and not torch.cuda.is_available():
            raise DeepSeekOCRUnavailable(
                "gpu_recommended",
                detail=f"请求设备 {self.device_pref} 但 CUDA 不可用",
            )
        if self.device_pref == "cpu" and not self.allow_cpu:
            raise DeepSeekOCRUnavailable(
                "gpu_recommended",
                detail="CPU 模式需显式 allow_cpu=True",
            )
        return self.device_pref

    def _profile_for(self, mode_s: str) -> DeepSeekOCRProfile:
        if mode_s == OCRMode.FORMULA.value or mode_s == "formula":
            return self.formula_profile
        return self.page_profile

    def _ensure_loaded(self) -> float:
        if DeepSeekOCR2Recognizer._model is not None:
            DeepSeekOCR2Recognizer._last_load_stages = {
                "cache_hit": True,
                "total": 0.0,
            }
            return 0.0
        t0 = time.perf_counter()
        stages: dict[str, Any] = {"cache_hit": False}
        device = self._resolve_device()
        try:
            t_imp = time.perf_counter()
            import torch
            from transformers import AutoModel, AutoTokenizer

            stages["imports"] = round(time.perf_counter() - t_imp, 3)
        except Exception as e:
            raise DeepSeekOCRUnavailable("model_unavailable", detail=str(e)) from e

        self._patch_transformers_llama_flash_attn()

        try:
            t_tok = time.perf_counter()
            tokenizer = AutoTokenizer.from_pretrained(
                self.model_name, trust_remote_code=True
            )
            stages["tokenizer"] = round(time.perf_counter() - t_tok, 3)
            attn = "eager"
            dtype = torch.bfloat16
            if self.dtype_pref in {"float16", "fp16"}:
                dtype = torch.float16
            elif self.dtype_pref in {"float32", "fp32"}:
                dtype = torch.float32

            t_w = time.perf_counter()
            model = AutoModel.from_pretrained(
                self.model_name,
                trust_remote_code=True,
                use_safetensors=True,
                attn_implementation=attn,
                torch_dtype=dtype,
            )
            # from_pretrained 含磁盘读 + 构建；无法再拆时记为 weights_and_construct
            stages["weights_and_construct"] = round(time.perf_counter() - t_w, 3)
            t_eval = time.perf_counter()
            model = model.eval()
            stages["model_eval"] = round(time.perf_counter() - t_eval, 3)
            if device.startswith("cuda"):
                t_cuda = time.perf_counter()
                model = model.to(device)
                try:
                    model = model.to(dtype)
                except Exception:
                    pass
                try:
                    torch.cuda.synchronize()
                except Exception:
                    pass
                stages["cuda_transfer"] = round(time.perf_counter() - t_cuda, 3)
            else:
                model = model.to(device)
                stages["cuda_transfer"] = 0.0
        except DeepSeekOCRUnavailable:
            raise
        except Exception as e:
            raise DeepSeekOCRUnavailable("model_unavailable", detail=str(e)) from e

        DeepSeekOCR2Recognizer._model = model
        DeepSeekOCR2Recognizer._tokenizer = tokenizer
        DeepSeekOCR2Recognizer._device = device
        DeepSeekOCR2Recognizer._torch_dtype = str(dtype).replace("torch.", "")
        DeepSeekOCR2Recognizer._load_seconds = time.perf_counter() - t0
        DeepSeekOCR2Recognizer._load_count += 1
        stages["total"] = round(float(DeepSeekOCR2Recognizer._load_seconds), 3)
        DeepSeekOCR2Recognizer._last_load_stages = stages
        return float(DeepSeekOCR2Recognizer._load_seconds)

    def recognize(
        self,
        image: Any,
        *,
        mode: OCRMode = OCRMode.PAGE,
        prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> DocumentOCRResult:
        del context
        mode_s = mode.value if isinstance(mode, OCRMode) else str(mode)
        profile = self._profile_for(mode_s)
        if mode_s == "formula":
            # 生产默认仍为 document prompt；benchmark 可显式传入 PROMPT_FORMULA_LATEX
            prompt_s = prompt or profile.prompt or PROMPT_DOCUMENT
        else:
            prompt_s = prompt or self.default_prompt or PROMPT_DOCUMENT

        max_tokens = int(
            self.max_new_tokens_override
            if self.max_new_tokens_override is not None
            else profile.max_new_tokens
        )

        t0 = time.perf_counter()
        load_this_call = 0.0
        try:
            load_this_call = self._ensure_loaded()
        except DeepSeekOCRUnavailable as e:
            return DocumentOCRResult(
                raw_output="",
                markdown=None,
                recognizer=self.name,
                mode=mode_s,
                elapsed_seconds=time.perf_counter() - t0,
                success=False,
                error=str(e.reason),
                metadata={
                    "detail": e.detail,
                    "model_load_seconds": load_this_call,
                    "model_load_count": self.model_load_count(),
                },
            )

        tmp_dir = Path(tempfile.mkdtemp(prefix="deepseek_ocr2_"))
        image_path = tmp_dir / "input.png"
        out_dir = tmp_dir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)

        timing: dict[str, Any] = {
            "prepare_seconds": 0.0,
            "model_infer_seconds": 0.0,
            "decode_save_seconds": 0.0,
            "cuda_sync_seconds": 0.0,
        }
        input_meta: dict[str, Any] = {}

        try:
            t_prep = time.perf_counter()
            self._save_image(image, image_path)
            try:
                from PIL import Image as PILImage

                with PILImage.open(image_path) as im:
                    input_meta["input_px_width"] = int(im.size[0])
                    input_meta["input_px_height"] = int(im.size[1])
            except Exception:
                pass
            timing["prepare_seconds"] = round(time.perf_counter() - t_prep, 4)

            model = DeepSeekOCR2Recognizer._model
            tokenizer = DeepSeekOCR2Recognizer._tokenizer
            assert model is not None and tokenizer is not None

            orig_generate = model.generate

            def _generate_capped(*args: Any, **kwargs: Any) -> Any:
                kwargs["max_new_tokens"] = max_tokens
                return orig_generate(*args, **kwargs)

            model.generate = _generate_capped  # type: ignore[method-assign]
            try:
                import torch

                t_inf = time.perf_counter()
                # 官方 infer 内部已 no_grad + autocast；勿再包 inference_mode（部分版本冲突）
                res = model.infer(
                    tokenizer,
                    prompt=prompt_s,
                    image_file=str(image_path),
                    output_path=str(out_dir),
                    base_size=int(profile.base_size),
                    image_size=int(profile.image_size),
                    crop_mode=bool(profile.crop_mode),
                    save_results=bool(profile.save_results),
                    eval_mode=bool(profile.eval_mode),
                )
                timing["model_infer_seconds"] = round(time.perf_counter() - t_inf, 4)

                t_sync = time.perf_counter()
                if torch.cuda.is_available():
                    torch.cuda.synchronize()
                timing["cuda_sync_seconds"] = round(time.perf_counter() - t_sync, 4)
            finally:
                model.generate = orig_generate  # type: ignore[method-assign]

            t_dec = time.perf_counter()
            if isinstance(res, str) and res.strip():
                text = res.strip()
            else:
                text = self._coerce_text(res, out_dir)
            timing["decode_save_seconds"] = round(time.perf_counter() - t_dec, 4)

            infer_sec = (
                float(timing["prepare_seconds"])
                + float(timing["model_infer_seconds"])
                + float(timing["decode_save_seconds"])
                + float(timing["cuda_sync_seconds"])
            )
            return DocumentOCRResult(
                raw_output=text,
                markdown=text,
                recognizer=self.name,
                mode=mode_s,
                elapsed_seconds=time.perf_counter() - t0,
                success=bool(text.strip()),
                error=None if text.strip() else "empty_output",
                metadata={
                    "device": self._device,
                    "model_dtype": self._torch_dtype,
                    "autocast_dtype": "bfloat16",
                    "model_load_seconds": load_this_call,
                    "model_load_count": self.model_load_count(),
                    "ocr_inference_seconds": round(infer_sec, 3),
                    "prompt": prompt_s,
                    "profile": profile.to_dict(),
                    "max_new_tokens": max_tokens,
                    "base_size": profile.base_size,
                    "image_size": profile.image_size,
                    "crop_mode": profile.crop_mode,
                    "save_results": profile.save_results,
                    "eval_mode": profile.eval_mode,
                    "timing_breakdown": timing,
                    **input_meta,
                },
            )
        except Exception as e:
            return DocumentOCRResult(
                raw_output="",
                markdown=None,
                recognizer=self.name,
                mode=mode_s,
                elapsed_seconds=time.perf_counter() - t0,
                success=False,
                error=f"ocr_failed:{type(e).__name__}",
                metadata={
                    "detail": str(e)[:400],
                    "device": self._device,
                    "model_load_seconds": load_this_call,
                    "model_load_count": self.model_load_count(),
                    "timing_breakdown": timing,
                    "profile": profile.to_dict(),
                },
            )
        finally:
            try:
                import shutil

                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    @staticmethod
    def _patch_transformers_llama_flash_attn() -> None:
        try:
            import transformers.models.llama.modeling_llama as llama_mod
            from transformers.models.llama.modeling_llama import LlamaAttention

            if not hasattr(llama_mod, "LlamaFlashAttention2"):
                llama_mod.LlamaFlashAttention2 = LlamaAttention
        except Exception:
            pass
        try:
            from transformers.cache_utils import DynamicCache

            if not hasattr(DynamicCache, "seen_tokens"):
                DynamicCache.seen_tokens = property(  # type: ignore[attr-defined]
                    lambda self: int(self.get_seq_length())
                )
            if not hasattr(DynamicCache, "get_max_length"):

                def _get_max_length(self):  # type: ignore[no-untyped-def]
                    try:
                        return self.get_max_cache_shape()
                    except Exception:
                        return getattr(self, "max_cache_len", None)

                DynamicCache.get_max_length = _get_max_length  # type: ignore[attr-defined]

            if not hasattr(DynamicCache, "get_usable_length"):

                def _get_usable_length(self, new_seq_length, layer_idx=0):  # type: ignore[no-untyped-def]
                    del new_seq_length
                    try:
                        return int(self.get_seq_length(layer_idx))
                    except TypeError:
                        return int(self.get_seq_length())

                DynamicCache.get_usable_length = _get_usable_length  # type: ignore[attr-defined]
        except Exception:
            pass

    @staticmethod
    def _save_image(image: Any, path: Path) -> None:
        if isinstance(image, (str, Path)):
            src = Path(image)
            path.write_bytes(src.read_bytes())
            return
        if hasattr(image, "save"):
            image.save(path)
            return
        if hasattr(image, "tobytes") and hasattr(image, "width"):
            from PIL import Image

            mode = "RGB" if getattr(image, "n", 3) >= 3 else "L"
            pil = Image.frombytes(mode, (image.width, image.height), image.tobytes())
            pil.save(path)
            return
        raise TypeError(f"unsupported_image_type:{type(image).__name__}")

    @staticmethod
    def _coerce_text(res: Any, out_dir: Path) -> str:
        if isinstance(res, str) and res.strip():
            return res.strip()
        if isinstance(res, dict):
            for k in ("markdown", "text", "result", "output"):
                v = res.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        for name in ("result.mmd", "result.md", "output.md", "result.txt"):
            p = out_dir / name
            if p.exists():
                return p.read_text(encoding="utf-8", errors="replace").strip()
        mds = sorted(out_dir.glob("*.md")) + sorted(out_dir.glob("*.mmd"))
        if mds:
            return mds[0].read_text(encoding="utf-8", errors="replace").strip()
        return str(res or "").strip()


class FakeDeepSeekOCR2Recognizer:
    name = "deepseek-ocr-2-fake"

    def __init__(
        self,
        outputs: dict[str, str] | None = None,
        *,
        inference_seconds: float = 0.01,
        model_load_seconds: float = 0.0,
    ) -> None:
        self.outputs = outputs or {}
        self.calls: list[dict[str, Any]] = []
        self.inference_seconds = float(inference_seconds)
        self.model_load_seconds = float(model_load_seconds)

    def recognize(
        self,
        image: Any,
        *,
        mode: OCRMode = OCRMode.PAGE,
        prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> DocumentOCRResult:
        del image, prompt, context
        mode_s = mode.value if isinstance(mode, OCRMode) else str(mode)
        self.calls.append({"mode": mode_s})
        text = self.outputs.get(mode_s, self.outputs.get("*", ""))
        return DocumentOCRResult(
            raw_output=text,
            markdown=text,
            recognizer=self.name,
            mode=mode_s,
            elapsed_seconds=self.inference_seconds,
            success=bool(text),
            error=None if text else "empty_output",
            metadata={
                "fake": True,
                "ocr_inference_seconds": self.inference_seconds,
                "model_load_seconds": self.model_load_seconds,
            },
        )
