"""RecoveryCostModel — EMA 运行时成本（Phase 4A/4B）。

- cold start（model_load）与 inference 分开
- observation outlier clipping，防止 736s 拉爆 EMA
- profile 按 device / recognizer / model / dtype 隔离
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.utils.paths import BENCHMARK_DIR, ensure_dirs

_DEFAULT_FORMULA_EMA = 2.65
_DEFAULT_PAGE_EMA = 40.0
_DEFAULT_MODEL_LOAD_EMA = 166.0


def _norm_key_part(s: str) -> str:
    t = re.sub(r"[^A-Za-z0-9]+", "_", (s or "").strip())
    return t.strip("_") or "unknown"


def make_profile_key(
    *,
    device: str = "",
    recognizer: str = "deepseek-ocr-2",
    model: str = "DeepSeek-OCR-2",
    dtype: str = "bf16",
) -> str:
    return "|".join(
        [
            _norm_key_part(device) or "unknown_device",
            _norm_key_part(recognizer),
            _norm_key_part(model),
            _norm_key_part(dtype),
        ]
    )


@dataclass
class RuntimeState:
    model_loaded: bool = False
    device: str = ""
    recognizer: str = "deepseek-ocr-2"
    model: str = "DeepSeek-OCR-2"
    dtype: str = "bf16"

    @property
    def profile_key(self) -> str:
        return make_profile_key(
            device=self.device,
            recognizer=self.recognizer,
            model=self.model,
            dtype=self.dtype,
        )


@dataclass
class CostModelSnapshot:
    device_key: str = ""
    device: str = ""
    recognizer: str = "deepseek-ocr-2"
    model: str = "DeepSeek-OCR-2"
    dtype: str = "bf16"
    formula_seconds_ema: float = _DEFAULT_FORMULA_EMA
    page_seconds_ema: float = _DEFAULT_PAGE_EMA
    model_load_seconds_ema: float = _DEFAULT_MODEL_LOAD_EMA
    formula_samples: int = 0
    page_samples: int = 0
    model_load_samples: int = 0
    page_usable_deficit_ema: float = 0.0
    page_quality_samples: int = 0
    last_raw_formula_seconds: float = 0.0
    last_raw_page_seconds: float = 0.0
    last_clipped_formula_seconds: float = 0.0
    last_clipped_page_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CostModelSnapshot:
        if not data:
            return cls()
        return cls(
            device_key=str(data.get("device_key") or ""),
            device=str(data.get("device") or ""),
            recognizer=str(data.get("recognizer") or "deepseek-ocr-2"),
            model=str(data.get("model") or "DeepSeek-OCR-2"),
            dtype=str(data.get("dtype") or "bf16"),
            formula_seconds_ema=float(
                data.get("formula_seconds_ema", _DEFAULT_FORMULA_EMA)
            ),
            page_seconds_ema=float(data.get("page_seconds_ema", _DEFAULT_PAGE_EMA)),
            model_load_seconds_ema=float(
                data.get("model_load_seconds_ema", _DEFAULT_MODEL_LOAD_EMA)
            ),
            formula_samples=int(data.get("formula_samples") or 0),
            page_samples=int(data.get("page_samples") or 0),
            model_load_samples=int(data.get("model_load_samples") or 0),
            page_usable_deficit_ema=float(data.get("page_usable_deficit_ema") or 0.0),
            page_quality_samples=int(data.get("page_quality_samples") or 0),
            last_raw_formula_seconds=float(data.get("last_raw_formula_seconds") or 0.0),
            last_raw_page_seconds=float(data.get("last_raw_page_seconds") or 0.0),
            last_clipped_formula_seconds=float(
                data.get("last_clipped_formula_seconds") or 0.0
            ),
            last_clipped_page_seconds=float(data.get("last_clipped_page_seconds") or 0.0),
        )


def default_profile_path() -> Path:
    ensure_dirs()
    return BENCHMARK_DIR / "formula_runtime_profile.json"


class RecoveryCostModel:
    """EMA 成本模型；按 device/model/dtype profile 持久化。"""

    def __init__(
        self,
        *,
        alpha: float = 0.3,
        max_outlier_multiplier: float = 3.0,
        profile_path: Path | None = None,
        snapshot: CostModelSnapshot | None = None,
        auto_load: bool = True,
        auto_save: bool = True,
    ) -> None:
        self.alpha = float(alpha)
        self.max_outlier_multiplier = float(max_outlier_multiplier)
        self.profile_path = Path(profile_path) if profile_path else default_profile_path()
        self.auto_save = bool(auto_save)
        self._lock = threading.Lock()
        self.runtime = RuntimeState()
        self._profiles: dict[str, dict[str, Any]] = {}
        if snapshot is not None:
            self.snap = snapshot
            if snapshot.device_key:
                self._profiles[snapshot.device_key] = snapshot.to_dict()
        elif auto_load and self.profile_path.exists():
            self.snap = self._load_active()
        else:
            self.snap = CostModelSnapshot()

    def _load_active(self) -> CostModelSnapshot:
        try:
            raw = json.loads(self.profile_path.read_text(encoding="utf-8"))
        except Exception:
            return CostModelSnapshot()
        if isinstance(raw.get("profiles"), dict):
            self._profiles = {str(k): v for k, v in raw["profiles"].items() if isinstance(v, dict)}
            key = str(raw.get("active_key") or "")
            if key and key in self._profiles:
                return CostModelSnapshot.from_dict(self._profiles[key])
            if self._profiles:
                first = next(iter(self._profiles.values()))
                return CostModelSnapshot.from_dict(first)
            return CostModelSnapshot()
        # legacy flat file
        snap = CostModelSnapshot.from_dict(raw)
        key = snap.device_key or make_profile_key(
            device=snap.device, recognizer=snap.recognizer, model=snap.model, dtype=snap.dtype
        )
        snap.device_key = key
        self._profiles[key] = snap.to_dict()
        return snap

    @staticmethod
    def load(path: Path) -> CostModelSnapshot:
        """兼容：加载文件当前 active snapshot。"""
        m = RecoveryCostModel(profile_path=path, auto_load=True, auto_save=False)
        return m.snap

    def save(self, path: Path | None = None) -> Path:
        dest = Path(path) if path else self.profile_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            key = self.runtime.profile_key if self.runtime.device else (
                self.snap.device_key or make_profile_key(
                    device=self.snap.device,
                    recognizer=self.snap.recognizer,
                    model=self.snap.model,
                    dtype=self.snap.dtype,
                )
            )
            self.snap.device_key = key
            self.snap.device = self.runtime.device or self.snap.device
            self.snap.recognizer = self.runtime.recognizer or self.snap.recognizer
            self.snap.model = self.runtime.model or self.snap.model
            self.snap.dtype = self.runtime.dtype or self.snap.dtype
            self._profiles[key] = self.snap.to_dict()
            payload = {"active_key": key, "profiles": self._profiles}
        dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return dest

    def switch_profile(self, *, device: str, recognizer: str = "", model: str = "", dtype: str = "") -> None:
        """设备/模型变化时切换或新建 profile，避免串台。"""
        if device:
            self.runtime.device = device
        if recognizer:
            self.runtime.recognizer = recognizer
        if model:
            self.runtime.model = model
        if dtype:
            self.runtime.dtype = dtype
        key = self.runtime.profile_key
        with self._lock:
            if key in self._profiles:
                self.snap = CostModelSnapshot.from_dict(self._profiles[key])
            else:
                self.snap = CostModelSnapshot(
                    device_key=key,
                    device=self.runtime.device,
                    recognizer=self.runtime.recognizer,
                    model=self.runtime.model,
                    dtype=self.runtime.dtype,
                )
                self._profiles[key] = self.snap.to_dict()

    def _ema(self, old: float, observed: float) -> float:
        a = self.alpha
        return a * float(observed) + (1.0 - a) * float(old)

    def _clip(self, observed: float, current_ema: float) -> tuple[float, float]:
        """返回 (clipped_for_ema, raw)。"""
        raw = max(0.0, float(observed))
        mult = self.max_outlier_multiplier
        if mult <= 0 or current_ema <= 0:
            return raw, raw
        cap = float(current_ema) * mult
        return min(raw, cap), raw

    def set_runtime(
        self,
        *,
        model_loaded: bool | None = None,
        device: str = "",
        recognizer: str = "",
        model: str = "",
        dtype: str = "",
    ) -> None:
        if model_loaded is not None:
            self.runtime.model_loaded = bool(model_loaded)
        touched = False
        if device:
            self.runtime.device = device
            touched = True
        if recognizer:
            self.runtime.recognizer = recognizer
            touched = True
        if model:
            self.runtime.model = model
            touched = True
        if dtype:
            self.runtime.dtype = dtype
            touched = True
        if touched and self.runtime.device:
            self.switch_profile(
                device=self.runtime.device,
                recognizer=self.runtime.recognizer,
                model=self.runtime.model,
                dtype=self.runtime.dtype,
            )

    def observe_model_load(
        self, seconds: float, *, success: bool = True, abort_reason: str = ""
    ) -> dict[str, float] | None:
        """单独更新 model_load EMA。timeout/OOM/abort 不入账。"""
        if not success or abort_reason:
            return {
                "raw_seconds": max(0.0, float(seconds)),
                "ema_observation": 0.0,
                "skipped": True,
                "abort_reason": abort_reason or "unsuccessful",
            }
        with self._lock:
            raw = max(0.0, float(seconds))
            clipped, _ = self._clip(raw, self.snap.model_load_seconds_ema)
            if raw > 0.5:
                self.snap.model_load_seconds_ema = self._ema(
                    self.snap.model_load_seconds_ema, clipped
                )
                self.snap.model_load_samples += 1
            self.runtime.model_loaded = True
        if self.auto_save:
            self.save()
        return {"raw_seconds": raw, "ema_observation": clipped, "skipped": False}

    def observe_formula(
        self,
        seconds: float,
        *,
        model_load_seconds: float = 0.0,
        success: bool = True,
        abort_reason: str = "",
    ) -> dict[str, float] | None:
        """仅 successful inference 进入 formula EMA；异常只留 telemetry。"""
        if not success or abort_reason:
            return {
                "raw_seconds": max(0.0, float(seconds)),
                "ema_observation": 0.0,
                "skipped": True,
                "abort_reason": abort_reason or "unsuccessful",
            }
        with self._lock:
            clipped, raw = self._clip(seconds, self.snap.formula_seconds_ema)
            self.snap.last_raw_formula_seconds = raw
            self.snap.last_clipped_formula_seconds = clipped
            self.snap.formula_seconds_ema = self._ema(self.snap.formula_seconds_ema, clipped)
            self.snap.formula_samples += 1
            self.runtime.model_loaded = True
        if model_load_seconds and model_load_seconds > 0.5:
            self.observe_model_load(model_load_seconds, success=True)
        elif self.auto_save:
            self.save()
        return {"raw_seconds": raw, "ema_observation": clipped, "skipped": False}

    def observe_page(
        self,
        seconds: float,
        *,
        model_load_seconds: float = 0.0,
        page_features: dict[str, Any] | None = None,
        from_cache: bool = False,
        success: bool = True,
        abort_reason: str = "",
    ) -> dict[str, float] | None:
        """cache hit / timeout / OOM / abort 不得进入 page inference EMA。"""
        _ = page_features
        if from_cache:
            return None
        if not success or abort_reason:
            return {
                "raw_seconds": max(0.0, float(seconds)),
                "ema_observation": 0.0,
                "skipped": True,
                "abort_reason": abort_reason or "unsuccessful",
            }
        with self._lock:
            clipped, raw = self._clip(seconds, self.snap.page_seconds_ema)
            self.snap.last_raw_page_seconds = raw
            self.snap.last_clipped_page_seconds = clipped
            self.snap.page_seconds_ema = self._ema(self.snap.page_seconds_ema, clipped)
            self.snap.page_samples += 1
            self.runtime.model_loaded = True
        if model_load_seconds and model_load_seconds > 0.5:
            self.observe_model_load(model_load_seconds, success=True)
        elif self.auto_save:
            self.save()
        return {"raw_seconds": raw, "ema_observation": clipped, "skipped": False}

    def observe_page_quality(self, *, formula_usable: int, page_usable: int) -> None:
        deficit = max(0, int(formula_usable) - int(page_usable))
        with self._lock:
            self.snap.page_usable_deficit_ema = self._ema(
                self.snap.page_usable_deficit_ema, float(deficit)
            )
            self.snap.page_quality_samples += 1
        if self.auto_save:
            self.save()

    def estimate_formula_unit(self) -> float:
        return float(self.snap.formula_seconds_ema)

    def estimate_page(self, page_features: dict[str, Any] | None = None) -> float:
        _ = page_features
        return float(self.snap.page_seconds_ema)

    def estimate_model_load(self) -> float:
        if self.runtime.model_loaded:
            return 0.0
        return float(self.snap.model_load_seconds_ema)

    def estimate_formula_batch(self, n: int) -> float:
        n = max(0, int(n))
        return self.estimate_model_load() + n * self.estimate_formula_unit()

    def estimate_page_job(self, *, cached: bool = False) -> float:
        if cached:
            return 0.0
        return self.estimate_model_load() + self.estimate_page()

    def page_usable_not_worse(self, *, max_deficit: int = 1) -> bool:
        if self.snap.page_quality_samples <= 0:
            return True
        return float(self.snap.page_usable_deficit_ema) <= float(max_deficit)
