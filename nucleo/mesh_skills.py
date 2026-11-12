"""nucleo/mesh_skills.py — what an agent's own A2A card says it can do, ONE skill at a time.

`mesh_agents.serve` asks an agent's FIRST declared skill: an agent declaring `search`, `book` and `book-by-phone`
answered every booking errand with a search. The skill is the caller's choice from what the card declares. Price is
per SKILL: its own `pricing`, else the card's; unknown is not free (read through `mesh_agents._tier_is_free`, so the
two rules cannot disagree). No agent and no skill is named here: pure functions over a card the caller holds.
"""
from __future__ import annotations

_DESC_MAX = 220


def skills_of(card: dict | None) -> list[dict]:
    """The card's skills, trimmed for a worker's context: `[{id, name, free, describes}]`, in the card's order."""
    out = []
    for s in ((card or {}).get("skills") or []):
        if not isinstance(s, dict) or not str(s.get("id") or "").strip():
            continue
        desc = " ".join(str(s.get("description") or "").split())
        out.append({"id": str(s["id"]).strip(), "name": str(s.get("name") or "").strip()[:80],
                    "free": is_free(card, str(s["id"]).strip()),
                    "describes": desc[:_DESC_MAX] + ("…" if len(desc) > _DESC_MAX else "")})
    return out


def skill_of(card: dict | None, skill_id: str) -> dict | None:
    """The declared skill `skill_id`, or None when the card does not declare it."""
    sid = str(skill_id or "").strip()
    for s in ((card or {}).get("skills") or []):
        if isinstance(s, dict) and str(s.get("id") or "").strip() == sid and sid:
            return s
    return None


def path_of(card: dict | None, skill_id: str) -> str:
    """`/v1/<skill-id>` for a DECLARED skill (the mesh convention), "" for one the card does not declare."""
    return f"/v1/{str(skill_id).strip().strip('/')}" if skill_of(card, skill_id) else ""


def is_free(card: dict | None, skill_id: str) -> bool:
    """True only when THIS skill's price is unambiguously zero — its own `pricing`, else the card's."""
    from nucleo.mesh_agents import _tier_is_free
    skill = skill_of(card, skill_id) or {}
    for pricing in (skill.get("pricing"), (card or {}).get("pricing")):
        tiers = pricing if isinstance(pricing, list) else [pricing] if isinstance(pricing, dict) else []
        verdicts = [_tier_is_free(t) for t in tiers]
        if any(v is True for v in verdicts):
            return True
        if any(v is False for v in verdicts):
            return False
    return False
