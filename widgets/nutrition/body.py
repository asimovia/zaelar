"""Nutrition — the body log and the profile: what the daily targets are computed from (V2-899).

The latest weighed row is the profile's weight (source: every write to /api/body re-read it), so the targets follow
the scale. The profile takes only values in range; a field sent empty goes back to the formula.
"""
from __future__ import annotations

from . import data as _d
from .actions import _find, _sync_profile_weight, _to_bin


def _body_fields(p: dict) -> dict:
    lims = {"weight_kg": (20, 400), "body_fat_pct": (2, 70), "muscle_mass_kg": (5, 200), "waist_cm": (30, 250)}
    return {k: _d._num(p.get(k), *lims[k]) for k in _d.BODY_FIELDS if k in p}


def _a_log_weight(action: str, p: dict) -> dict:
    db = _d.load()
    f = _body_fields(p)
    if not any(v is not None for v in f.values()):
        return {"ok": False, "error": "invalid_measure", "hint": "weight_kg 20-400 (or body_fat_pct, muscle_mass_kg, waist_cm)"}
    row = {"id": _d.next_id(db, "b"), "measured_at": _d.clean_when(p.get("measured_at"), _d.now_local()),
           **{k: f.get(k) for k in _d.BODY_FIELDS}, "notes": str(p.get("notes") or "")[:200] or None}
    db["body"].append(row)
    if row.get("body_fat_pct") is not None:
        db["profile"]["body_fat_pct"] = row["body_fat_pct"]
    _sync_profile_weight(db)
    _d.save(db)
    return {"ok": True, "entry_id": row["id"], "weight_kg": row.get("weight_kg")}


def _a_edit_weight(action: str, p: dict) -> dict:
    db = _d.load()
    row = _find(db["body"], p.get("entry_id"))
    if not row:
        return {"ok": False, "error": "entry_not_found"}
    f = _body_fields(p)
    bad = [k for k in f if f[k] is None and p.get(k) not in (None, "")]
    if bad:
        return {"ok": False, "error": "invalid_measure", "fields": bad}
    row.update(f)
    when = _d.clean_when(p.get("measured_at"))
    if when:
        row["measured_at"] = when
    if "notes" in p:
        row["notes"] = str(p.get("notes") or "")[:200] or None
    _sync_profile_weight(db)
    _d.save(db)
    return {"ok": True, "entry_id": row["id"]}


def _a_delete_weight(action: str, p: dict) -> dict:
    db = _d.load()
    row = _find(db["body"], p.get("entry_id"))
    if not row:
        return {"ok": False, "error": "entry_not_found"}
    db["body"] = [b for b in db["body"] if b is not row]
    _to_bin(db, "weight", row)
    _sync_profile_weight(db)
    _d.save(db)
    return {"ok": True, "deleted": row["id"], "undo": {"action": "restore", "payload": {"id": row["id"]}}}


def _a_set_profile(action: str, p: dict) -> dict:
    db = _d.load()
    prof = db["profile"]
    changed, bad = [], []
    for k, (lo, hi) in _d.PROFILE_NUM.items():
        if k not in p:
            continue
        if p[k] in (None, ""):
            prof.pop(k, None)                # cleared: back to the formula / the default
            changed.append(k)
            continue
        n = _d._num(p[k], lo, hi)
        if n is None:
            bad.append(k)
            continue
        prof[k] = int(n) if k in ("age", "target_calories", "target_protein_g") else round(n, 2)
        changed.append(k)
    if "goal" in p:
        if p["goal"] in _d.GOALS:
            prof["goal"] = p["goal"]
            changed.append("goal")
        else:
            bad.append("goal")
    if "sex" in p:
        if p["sex"] in _d.SEXES:
            prof["sex"] = p["sex"]
            changed.append("sex")
        else:
            bad.append("sex")
    if changed:
        _d.save(db)
    return {"ok": not bad, "changed": changed, "invalid": bad, "targets": _d.targets(prof)}
