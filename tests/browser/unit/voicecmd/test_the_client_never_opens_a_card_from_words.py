"""Exposes the «the client never opens a card from words» contract to pytest (V2-807 T-05; the .mjs MOUNTS
the real `sse.js` and says why)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_the_client_never_opens_a_card_from_words.mjs")
ENGINE = Path(__file__).resolve().parents[4]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_client_never_opens_a_card_from_words():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_no_frontend_module_reads_words_to_pick_a_card():
    """The structural half: nothing under `frontend/` asks the catalogue which card a sentence names. The one
    lookup left (`Deck.js`) resolves an id the ENGINE sent, never a transcript."""
    offenders = []
    for p in (ENGINE / "frontend").rglob("*.js"):
        src = p.read_text("utf-8", errors="ignore")
        if "identifyWidget(" in src.replace("export async function identifyWidget(", ""):
            offenders.append(str(p.relative_to(ENGINE)))
    assert offenders == [], f"a client module maps words to a card again: {offenders}"
    assert not (ENGINE / "frontend/app/services/voiceCommands.js").exists()
