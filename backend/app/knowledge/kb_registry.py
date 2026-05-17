"""Knowledge-base ↔ ES index registry — single source of truth."""

from __future__ import annotations

KB_TO_INDEX: dict[str, str] = {
    "qa": "qa_chunks",
    "ticket": "ticket_knowledge",
    "sales": "sales_knowledge",
    "ops": "ops_knowledge",
}

INDEX_TO_KB: dict[str, str] = {v: k for k, v in KB_TO_INDEX.items()}


def get_index_for_kb(kb: str) -> str:
    """Get ES index name for a knowledge base code. Falls back to qa_chunks."""
    return KB_TO_INDEX.get(kb, "qa_chunks")


def get_kb_for_index(index: str) -> str:
    """Get knowledge base code from an ES index name. Falls back to 'qa'."""
    return INDEX_TO_KB.get(index, "qa")


def validate_kb(kb: str) -> str:
    """Normalize a knowledge-base code, defaulting unknown values to 'qa'."""
    return kb if kb in KB_TO_INDEX else "qa"
