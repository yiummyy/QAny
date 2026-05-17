"""Tool: Citation verification — programmatic anchor-to-chunk semantic validation.

Replaces "LLM checking LLM" with deterministic embedding-based similarity,
providing sentence-level trust granularity. (Spec: citation-verification)
"""

from __future__ import annotations

import logging
import re

import numpy as np

from app.harness.models import CitationReport, OrphanClaim, VerifiedCitation

logger = logging.getLogger(__name__)

# Thresholds
CITATION_VERIFIED = 0.75
CITATION_SUSPICIOUS = 0.55

ANCHOR_RE = re.compile(r"\[S(\d+)\]")


def extract_anchors(text: str) -> list[tuple[str, str, str]]:
    """Extract [S1]/[S2]/... anchors and their containing sentences.

    Returns: [(anchor, original_sentence, sentence_without_anchor), ...]
    """
    sentences = _split_sentences(text)
    results: list[tuple[str, str, str]] = []

    for sent in sentences:
        matches = ANCHOR_RE.findall(sent)
        if not matches:
            continue
        clean_sent = ANCHOR_RE.sub("", sent).strip()
        for m in matches:
            anchor = f"S{m}"
            # Avoid duplicates per sentence
            if not any(r[0] == anchor and r[1] == sent for r in results):
                results.append((anchor, sent, clean_sent))

    return results


def map_anchors_to_chunks(
    anchors: list[str],
    chunks: list[dict],
) -> dict[str, dict]:
    """Map anchor labels to chunk dicts. S1 → chunks[0], S2 → chunks[1], etc."""
    mapping: dict[str, dict] = {}
    for anchor in anchors:
        idx = int(anchor[1:]) - 1  # S1 → 0
        if 0 <= idx < len(chunks):
            mapping[anchor] = chunks[idx]
    return mapping


async def verify_citations(
    answer: str,
    chunks: list[dict],
) -> CitationReport:
    """Verify citation anchors in answer against source chunks via embedding similarity.

    Returns CitationReport with verified/unverified/orphan_claims.
    """
    if not answer or not chunks:
        return CitationReport()

    try:
        from app.knowledge.embedder import encode

        # Step 1: Extract anchors
        anchored = extract_anchors(answer)
        used_anchors = list({a for a, _, _ in anchored})
        anchor_set = set(used_anchors)

        # Step 2: Map anchors → chunks
        anchor_to_chunk = map_anchors_to_chunks(used_anchors, chunks)

        verified: list[VerifiedCitation] = []
        unverified: list[VerifiedCitation] = []

        if anchored and anchor_to_chunk:
            sentences = [s for _, _, s in anchored]
            sent_embs = await encode(sentences)

            for i, (anchor, orig_sent, clean_sent) in enumerate(anchored):
                chunk = anchor_to_chunk.get(anchor)
                if not chunk:
                    unverified.append(VerifiedCitation(
                        anchor=anchor, sentence=orig_sent,
                        chunk_id="", similarity=0.0,
                        status="mismatched",
                    ))
                    continue

                chunk_emb = await encode([chunk.get("content", "")])
                similarity = float(np.dot(sent_embs[i], chunk_emb[0]))

                if similarity >= CITATION_VERIFIED:
                    status = "verified"
                elif similarity >= CITATION_SUSPICIOUS:
                    status = "suspicious"
                else:
                    status = "mismatched"

                entry = VerifiedCitation(
                    anchor=anchor, sentence=orig_sent,
                    chunk_id=chunk.get("chunk_id", ""),
                    similarity=round(similarity, 4),
                    status=status,
                )

                if status == "verified":
                    verified.append(entry)
                else:
                    unverified.append(entry)

        # Step 3: Detect orphan claims (factual statements without anchors)
        orphan_claims = _detect_orphan_claims(answer, anchor_set)

        # Step 4: Compute coverage and overall score
        total_claim_sentences = len(anchored) + len(orphan_claims)
        coverage = len(anchored) / max(total_claim_sentences, 1)

        verified_score = (
            sum(v.similarity for v in verified) / max(len(verified), 1)
            if verified else 0.0
        )
        overall_score = coverage * 0.3 + verified_score * 0.7

        return CitationReport(
            verified=verified,
            unverified=unverified,
            orphan_claims=orphan_claims,
            coverage=round(coverage, 4),
            overall_score=round(overall_score, 4),
        )

    except Exception as exc:
        logger.warning("Citation verification failed: %s", exc)
        return CitationReport()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences by Chinese/English punctuation."""
    # Split on common sentence delimiters while keeping the delimiter
    parts = re.split(r"(?<=[。！？；.!?;])\s*", text)
    return [p.strip() for p in parts if p.strip()]


def _detect_orphan_claims(
    answer: str,
    used_anchors: set[str],
) -> list[OrphanClaim]:
    """Detect factual claims without source citation anchors."""
    sentences = _split_sentences(answer)
    orphans: list[OrphanClaim] = []

    for sent in sentences:
        if any(f"[{a}]" in sent or f"[{a[1:]}]" in sent for a in used_anchors):
            continue
        if _is_filler(sent):
            continue

        claim_type = _classify_claim(sent)
        if claim_type:
            orphans.append(OrphanClaim(sentence=sent, claim_type=claim_type))

    return orphans


def _is_filler(sentence: str) -> bool:
    """Check if a sentence is connective/filler text with no factual claim."""
    filler_patterns = [
        r"^(您好|欢迎|请|如有|如需|希望|祝您|感谢|以上|综上|总结|注意).*$",
        r"^(根据|依据|参考|详见|具体|详细).*$",
        r"^[，。！？,.!?\s]*$",
    ]
    return any(re.match(p, sentence) for p in filler_patterns)


def _classify_claim(sentence: str) -> str | None:
    """Classify the type of factual claim in a sentence."""
    if re.search(r"\d{4}年|\d{1,2}月\d{1,2}日", sentence):
        return "日期"
    if re.search(r"\d+", sentence):
        return "数字"
    if re.search(r"规定|政策|制度|办法|条例|标准|流程|规范|章程", sentence):
        return "规定"
    if re.search(r"《[^》]+》", sentence):
        return "名称"
    return "其他"
