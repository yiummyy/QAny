"""Vision LLM integration — describe images extracted from documents.

Calls a multimodal LLM (qwen-vl via DashScope by default) to generate
textual descriptions of images/charts/tables. Descriptions are embedded
alongside document text so they can be retrieved by the RAG pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.knowledge.parsers.models import ParsedBlock
from app.prompts.renderer import render

logger = logging.getLogger(__name__)

# DashScope multimodal API endpoint
_DASHSCOPE_OMNI_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# Default vision model
DEFAULT_VISION_MODEL = "qwen-vl-max"

# Maximum images to describe per document (safety limit)
MAX_IMAGES_PER_DOC = 20

# Maximum context characters to include around the image
MAX_CONTEXT_CHARS = 500


async def describe_images(
    blocks: list[ParsedBlock],
    max_images: int = MAX_IMAGES_PER_DOC,
    model: str = "",
    api_key: str = "",
) -> list[ParsedBlock]:
    """Fill in ``content`` for image-type ParsedBlocks using a vision LLM.

    Non-image blocks pass through unchanged. Images beyond *max_images* are
    skipped (described as "[图片未识别]").

    Returns a new list — the input is not mutated.
    """
    image_blocks = [(i, b) for i, b in enumerate(blocks) if b.block_type == "image"]
    if not image_blocks:
        return list(blocks)

    settings = get_settings()
    actual_key = api_key or (
        settings.dashscope_api_key.get_secret_value()
        if settings.dashscope_api_key
        else ""
    )
    actual_model = model or DEFAULT_VISION_MODEL

    if not actual_key:
        logger.warning("No vision API key configured — skipping %d image(s)", len(image_blocks))
        result = list(blocks)
        for i, b in image_blocks:
            result[i] = _skip_block(b, "未配置视觉模型API密钥")
        return result

    # Limit images
    to_describe = image_blocks[:max_images]
    skipped = image_blocks[max_images:]

    # Describe in parallel (limited to 3 concurrent to avoid rate limits)
    semaphore = asyncio.Semaphore(3)

    async def _describe_one(idx: int, block: ParsedBlock) -> ParsedBlock:
        async with semaphore:
            context = _build_context(blocks, idx)
            return await _call_vision_api(block, context, actual_key, actual_model)

    tasks = [_describe_one(i, b) for i, b in to_describe]

    # Build result list
    result = list(blocks)
    described = await asyncio.gather(*tasks)

    for (orig_idx, _), block in zip(to_describe, described):
        result[orig_idx] = block

    for i, b in skipped:
        result[i] = _skip_block(b, f"超过单文档图片上限({max_images}张)")

    return result


def describe_images_sync(
    blocks: list[ParsedBlock],
    max_images: int = MAX_IMAGES_PER_DOC,
    model: str = "",
    api_key: str = "",
) -> list[ParsedBlock]:
    """Synchronous wrapper for ``describe_images``."""
    return asyncio.run(describe_images(blocks, max_images, model, api_key))


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _build_context(blocks: list[ParsedBlock], image_idx: int) -> str:
    """Collect adjacent text blocks as context for the image."""
    texts: list[str] = []
    # Before
    for i in range(image_idx - 1, max(image_idx - 3, -1), -1):
        if blocks[i].block_type == "text" and blocks[i].content:
            texts.insert(0, blocks[i].content)
    # After
    for i in range(image_idx + 1, min(image_idx + 3, len(blocks))):
        if blocks[i].block_type == "text" and blocks[i].content:
            texts.append(blocks[i].content)

    context = " ".join(texts)
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "..."
    return context


async def _call_vision_api(
    block: ParsedBlock,
    context: str,
    api_key: str,
    model: str,
) -> ParsedBlock:
    """Call the multimodal API to describe a single image."""
    if not block.image_base64:
        return _skip_block(block, "图片数据为空")

    prompt = render("describe_image", context=context or "无上下文")

    # Build multimodal message: image + text
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{block.metadata.get('img_format', 'png')};base64,{block.image_base64}"
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }
    ]

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{_DASHSCOPE_OMNI_BASE}/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": 1000,
                    "temperature": 0.1,
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )

            if resp.status_code != 200:
                error_text = resp.text[:200] if resp.text else f"HTTP {resp.status_code}"
                logger.warning("Vision API error: %s", error_text)
                return _skip_block(block, f"视觉API调用失败: {error_text}")

            data = resp.json()
            description = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not description or not description.strip():
                return _skip_block(block, "视觉API返回空描述")

            logger.info(
                "Image described: page=%d, desc_len=%d",
                block.page,
                len(description),
            )

            return ParsedBlock(
                content=f"[图片描述] {description.strip()}",
                block_type="image",
                section=block.section,
                page=block.page,
                bbox=block.bbox,
                image_base64="",  # don't carry base64 past this point
                metadata={
                    **block.metadata,
                    "content_type": "image_description",
                    "vision_model": model,
                },
            )

    except httpx.TimeoutException:
        return _skip_block(block, "视觉API超时")
    except httpx.ConnectError:
        return _skip_block(block, "视觉API连接失败")
    except Exception as exc:
        logger.exception("Vision API unexpected error")
        return _skip_block(block, f"视觉API异常: {str(exc)[:100]}")


def _skip_block(block: ParsedBlock, reason: str) -> ParsedBlock:
    """Return a copy of the image block marked as skipped."""
    return ParsedBlock(
        content=f"[图片未识别: {reason}]",
        block_type="image",
        section=block.section,
        page=block.page,
        bbox=block.bbox,
        metadata={
            **block.metadata,
            "content_type": "image_skipped",
            "skip_reason": reason,
        },
    )
