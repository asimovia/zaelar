"""Which card is at full screen now — one reader for every door (`at_full_screen`, node 2.927). The show/close
resolution and the canvas verdict that lived here were the old turn's and went with it (INI-078 L1)."""
from __future__ import annotations


def at_full_screen() -> str:
    """The card at full screen NOW, or "": the canvas report (`state.maximized_widget`), else the full screen his own
    order set and nothing undid (`canvas_focus.ordered_fullscreen`). ONE reader for every door — the verdict completion
    read focus instead and «go back to normal size» found no target with two cards open (node 2.927)."""
    try:
        from memory import api as _memapi
        maxw = str(((_memapi.state() or {}).get("maximized_widget") or "")).strip()
        if maxw:
            return maxw
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"show_target: canvas report unreadable — {e}")
    try:
        from nucleo import canvas_focus as _cf
        return str(_cf.ordered_fullscreen() or "").strip()
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"show_target: ordered full screen unreadable — {e}")
        return ""

