"""Settings › Voice › Voice recognition, RENDERED (V2-651 F1, operator 2026-11-18).

The page is drawn with the ONE Settings layout (breadcrumb, header, label left / field right, Cancel + Save) from the
real `settings/voice-id.js`, beside the real orb bar, over the real `voice-lock.js` store. Pinned:
  · the page's shape: crumb Settings › Voice › Voice recognition, the switch row, Cancel + Save disabled until edited,
    the kept voice's state, and «Train my voice»;
  · the switch is a MIRROR of the bar's: a click on the bar moves the box (and leaves nothing to save); Save on the
    page moves the bar and the stored setting;
  · «Train my voice» replaces the kept voice with the one just learned (and its date), and a failed training keeps
    the old one;
  · the panel lists the page right after Voice and wires it.
Disarms: the mirror effect removed, and a training whose result is not kept — each served in place of the real module.
"""
from __future__ import annotations

import json
from pathlib import Path

from tests.browser.unit.mobile.phone_page import PACK, open_phone

ROOT = Path(__file__).resolve().parents[4]
ES = PACK["es"]
OLD = {"pitch": {"m": 120, "s": 10}, "centroid": {"m": 900, "s": 80}, "rms": {"m": 0.1}, "learned_at": 1000}
NEW = {"pitch": {"m": 210, "s": 12}, "centroid": {"m": 1800, "s": 90}, "rms": {"m": 0.2}}

SETUP = """
  localStorage.setItem('hb_voice_lock', '0');
  localStorage.setItem('zaelar_spk_profile', '%s');
  const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = '/frontend/app/styles.css'; document.head.append(l);
  window.__lock = await import('/frontend/app/services/voice-lock.js?v=1');
  const { Orb } = await import('/frontend/app/components/Orb.js?v=3');
  document.body.append(Orb());
  const vid = await import('/frontend/app/components/settings/voice-id.js?v=1');
  const host = document.createElement('div'); host.id = 'host'; document.body.append(host);
  host.innerHTML = vid.sec_voiceid();
  vid.wireVoiceId(host.querySelector('.set-page'));
  // the session's trainer, stood in: it reports progress and hands back the voice it «heard» (or fails)
  window.__trainWith = (r) => window.__lock.useTrainer(async ({ onProgress }) => { onProgress(2, 4); return r; });
""" % json.dumps(OLD)

_PAGE = """() => { const p = document.querySelector('[data-settings-page="voiceid"]');
  const q = (s) => p.querySelector(s);
  return { crumb: [...q('.set-crumb').children].map(c => c.textContent).filter(x => x !== '›'),
           title: q('.set-title').textContent, label: q('label[for="cf_vid_lock"]').textContent,
           box: q('#cf_vid_lock').checked, save: q('[data-set-save]').disabled, cancel: q('[data-set-cancel]').disabled,
           state: q('#cf_vid_state').textContent, train: q('.cf-vid-train').textContent,
           status: q('.set-status').textContent, lock: window.__lock.voiceLock(),
           stored: localStorage.getItem('hb_voice_lock'),
           orb: document.querySelector('#orbwrap [data-ctl="lock"]').className,
           profile: JSON.parse(localStorage.getItem('zaelar_spk_profile') || 'null') }; }"""


def _served(rel: str, old: str, new: str) -> tuple:
    src = (ROOT / rel).read_text(encoding="utf-8")
    assert old in src, f"the disarm of {rel} did not land"
    bad = src.replace(old, new)
    return (lambda url: url.split("?")[0].endswith("/" + rel)), \
        (lambda r: r.fulfill(status=200, content_type="text/javascript", body=bad))


def _mirror(tab) -> tuple[dict, dict]:
    tab.click('#orbwrap [data-ctl="lock"]')
    tab.wait_for_timeout(100)
    after_bar = tab.evaluate(_PAGE)
    tab.click("#cf_vid_lock")                      # off again, on the page
    tab.click('[data-settings-page="voiceid"] [data-set-save]')
    tab.wait_for_timeout(150)
    return after_bar, tab.evaluate(_PAGE)


def _retrain(tab, result) -> dict:
    tab.evaluate("(r) => window.__trainWith(r)", result)
    tab.click('[data-settings-page="voiceid"] .cf-vid-train')
    tab.wait_for_timeout(200)
    return tab.evaluate(_PAGE)


def test_the_page_is_drawn_with_the_settings_layout():
    with open_phone(SETUP, width=1280, height=800) as tab:
        tab.wait_for_timeout(300)
        p = tab.evaluate(_PAGE)
        assert p["crumb"] == [ES["config.tab.settings"], ES["config.sec.voice"], ES["config.sec.voiceid"]], p["crumb"]
        assert p["title"] == ES["config.voiceid.title"] and p["label"] == ES["config.voiceid.lock"], p
        assert p["save"] and p["cancel"], "Cancel + Save wait for an edit"
        assert p["state"].startswith(ES["config.voiceid.state_learned"].split("{when}")[0]), p["state"]
        assert p["train"] == ES["config.voiceid.train_btn"] and not p["box"]
        assert not tab._errors, tab._errors


def test_the_switch_mirrors_the_bar_both_ways():
    with open_phone(SETUP, width=1280, height=800) as tab:
        tab.wait_for_timeout(300)
        bar, page = _mirror(tab)
        assert bar["box"] and bar["lock"] and bar["save"], f"a click on the bar moves the box, nothing to save: {bar}"
        assert not page["lock"] and page["stored"] == "0" and " off" in page["orb"], f"Save moves the bar: {page}"
        assert page["status"].startswith("✓"), page
        assert not tab._errors, tab._errors


def test_training_replaces_the_voice_and_a_failed_one_keeps_it():
    with open_phone(SETUP, width=1280, height=800) as tab:
        tab.wait_for_timeout(300)
        bad = _retrain(tab, {"ok": False, "why": "timeout"})
        assert bad["profile"]["pitch"]["m"] == 120 and bad["status"].startswith("✗"), bad
        assert bad["status"] == "✗ " + ES["config.voiceid.train_fail_timeout"], bad["status"]
        good = _retrain(tab, {"ok": True, "profile": NEW})
        assert good["profile"]["pitch"]["m"] == 210, f"the new voice replaces the old: {good['profile']}"
        assert good["profile"]["learned_at"] > OLD["learned_at"], "and carries when it was learned"
        assert good["status"] == "✓ " + ES["config.voiceid.train_ok"], good["status"]
        assert tab.evaluate("() => window.__lock.voiceEnrolled()") is True
        assert not tab._errors, tab._errors


def test_the_disarm_a_page_without_the_mirror_is_red():
    route = _served("frontend/app/components/settings/voice-id.js", "box.checked = on; ", "")
    with open_phone(SETUP, width=1280, height=800, routes=[route]) as tab:
        tab.wait_for_timeout(300)
        bar, _ = _mirror(tab)
        assert not bar["box"], "without the mirror the bar's click never reaches the box — the check above sees it"


def test_the_disarm_a_training_that_keeps_nothing_is_red():
    route = _served("frontend/app/services/voice-lock.js", "saveProfile({ ...r.profile", "void ({ ...r.profile")
    with open_phone(SETUP, width=1280, height=800, routes=[route]) as tab:
        tab.wait_for_timeout(300)
        good = _retrain(tab, {"ok": True, "profile": NEW})
        assert good["profile"]["pitch"]["m"] == 120, "with the save disarmed the old voice stays — the check sees it"


def test_the_panel_lists_and_wires_the_page_after_voice():
    src = (ROOT / "frontend/app/components/ConfigPanel.js").read_text(encoding="utf-8")
    i, j = src.index('{ id: "voice", icon'), src.index('{ id: "voiceid", icon')
    assert 0 < j - i < 80, "Voice recognition sits right after Voice"
    assert "voiceid: () => S.sec_voiceid()" in src and 'activeSec === "voiceid") wireVoiceId(pg' in src
    s = (ROOT / "frontend/app/services/session-lk.js").read_text(encoding="utf-8")
    assert "vlock.useTrainer(" in s and '_endTrain({ ok: false, why: "stopped" })' in s, "the session owns the trainer"
