"""Role→permission_level matrix + ES filter builder — Spec §5.3/§5.4.

Usage (to be invoked by Phase 3 hybrid_search at the highest level, so that
downstream retrieval CANNOT bypass the guard).
"""

from __future__ import annotations

from typing import Any

from app.auth.claims import Role, UserClaims

ROLE_LEVEL_MATRIX: dict[str, list[str]] = {
    Role.GUEST.value: ["L1"],
    Role.EMPLOYEE.value: ["L1", "L2"],
    Role.ADMIN.value: ["L1", "L2", "L3"],
}


def build_es_filter(claims: UserClaims) -> dict[str, Any]:
    """Build the Elasticsearch `bool.filter` clause for permission_level.

    ABAC placeholder: `claims.dept` is intentionally unused for MVP per Spec
    §5.3, but kept in the signature so future code can extend without API
    breakage.
    """
    allowed = ROLE_LEVEL_MATRIX[claims.role.value]
    return {"bool": {"filter": [{"terms": {"permission_level": allowed}}]}}
