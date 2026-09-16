"""内部 Provider 目录。新 backend 在这里登记，不必改 Router / Core。"""
from __future__ import annotations

from app.core.providers.descriptor import (
    Capability,
    IsolationMode,
    ProviderDescriptor,
    ProviderType,
    RuntimeKind,
)
from app.core.providers.incubator import (
    DOCLING_VLM,
    MARKER,
    PP_STRUCTURE,
    DoclingVlmProvider,
    MarkerIncubatorProvider,
    PPStructureTableProvider,
)
from app.core.providers.promotion import PromotionTrack
from app.core.providers.registry import ProviderRegistry

DOCLING = ProviderDescriptor(
    id="parser.docling",
    version="1.0",
    provider_type=ProviderType.PARSER,
    capabilities=(
        Capability.PARSE_STRUCTURE,
        Capability.PARSE_TEXT,
        Capability.TABLE_STRUCTURE,
        Capability.READING_ORDER,
    ),
    runtime=(RuntimeKind.CPU, RuntimeKind.CUDA),
    dependencies=("docling",),
    isolation_mode=IsolationMode.INPROCESS,
    license_class="mit",
    track=PromotionTrack.DEFAULT_ELIGIBLE,
)

MINERU = ProviderDescriptor(
    id="parser.mineru",
    version="1.0",
    provider_type=ProviderType.PARSER,
    capabilities=(
        Capability.PARSE_STRUCTURE,
        Capability.PARSE_TEXT,
        Capability.TABLE_STRUCTURE,
        Capability.READING_ORDER,
    ),
    runtime=(RuntimeKind.CPU, RuntimeKind.CUDA),
    dependencies=("mineru",),
    isolation_mode=IsolationMode.SUBPROCESS,
    license_class="agpl-3.0",
    track=PromotionTrack.SUPPORTED,
)

DEEPSEEK_OCR2 = ProviderDescriptor(
    id="formula.deepseek_ocr2",
    version="1.0",
    provider_type=ProviderType.FORMULA,
    capabilities=(Capability.FORMULA_RECOGNITION,),
    runtime=(RuntimeKind.CUDA, RuntimeKind.CPU),
    dependencies=("torch",),
    supported_inputs=("image", "pdf"),
    output_contract="latex",
    isolation_mode=IsolationMode.DAEMON,
    license_class="source-available",
    track=PromotionTrack.SUPPORTED,
)

DEEPSEEK_API_VISION = ProviderDescriptor(
    id="vision.deepseek_api",
    version="1.0",
    provider_type=ProviderType.VISION,
    capabilities=(Capability.VISION_PAGE, Capability.VISION_REGION),
    runtime=(RuntimeKind.API,),
    network_required=True,
    dependencies=("deepseek-api",),
    isolation_mode=IsolationMode.API,
    license_class="proprietary-api",
    track=PromotionTrack.SUPPORTED,
)

DEEPSEEK_WEB_VISION = ProviderDescriptor(
    id="vision.deepseek_web",
    version="1.0",
    provider_type=ProviderType.VISION,
    capabilities=(Capability.VISION_PAGE,),
    runtime=(RuntimeKind.BROWSER,),
    network_required=True,
    dependencies=("playwright",),
    isolation_mode=IsolationMode.BROWSER,
    license_class="proprietary-site",
    experimental=True,
    default_enabled=True,
    track=PromotionTrack.EXPERIMENTAL,
)

# 兼容旧测试名
MARKER_STUB = MARKER


def register_internal_providers(registry: ProviderRegistry) -> None:
    from app.core.providers.parser import (
        DeepSeekApiVisionProvider,
        DeepSeekOCR2FormulaProvider,
        DeepSeekWebVisionProvider,
        DoclingParserProvider,
        MineruParserProvider,
    )

    docling = DoclingParserProvider()
    mineru = MineruParserProvider()
    formula = DeepSeekOCR2FormulaProvider()
    vision_api = DeepSeekApiVisionProvider()
    vision_web = DeepSeekWebVisionProvider()
    pp_structure = PPStructureTableProvider()
    docling_vlm = DoclingVlmProvider()
    marker = MarkerIncubatorProvider()

    DoclingParserProvider.descriptor = DOCLING
    MineruParserProvider.descriptor = MINERU
    DeepSeekOCR2FormulaProvider.descriptor = DEEPSEEK_OCR2
    DeepSeekApiVisionProvider.descriptor = DEEPSEEK_API_VISION
    DeepSeekWebVisionProvider.descriptor = DEEPSEEK_WEB_VISION
    PPStructureTableProvider.descriptor = PP_STRUCTURE
    DoclingVlmProvider.descriptor = DOCLING_VLM
    MarkerIncubatorProvider.descriptor = MARKER

    registry.register(DOCLING, factory=lambda: docling, available_fn=docling.available)
    registry.register(MINERU, factory=lambda: mineru, available_fn=mineru.available)
    registry.register(DEEPSEEK_OCR2, factory=lambda: formula, available_fn=formula.available)
    registry.register(
        DEEPSEEK_API_VISION, factory=lambda: vision_api, available_fn=vision_api.available
    )
    registry.register(
        DEEPSEEK_WEB_VISION, factory=lambda: vision_web, available_fn=vision_web.available
    )
    registry.register(
        PP_STRUCTURE,
        factory=lambda: pp_structure,
        available_fn=pp_structure.available,
        enabled=False,
    )
    registry.register(
        DOCLING_VLM,
        factory=lambda: docling_vlm,
        available_fn=docling_vlm.available,
        enabled=False,
    )
    registry.register(
        MARKER,
        factory=lambda: marker,
        available_fn=marker.available,
        enabled=False,
    )
