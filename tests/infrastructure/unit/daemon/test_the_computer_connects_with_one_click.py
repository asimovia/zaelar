"""«Conecta tu ordenador» without a terminal and without typing a path (operator, 2026-10-22).

The screen used to send a person to a terminal (`./zaelar restart`, `make daemon`) and make them paste a folder's
full path. Now «Conectar» asks the engine to start the daemon it carries, and «Elegir carpeta…» asks the daemon
to open the system's own folder dialog — the chosen folder still goes through `roots.grant`, so the dialog is a
way IN, never a way AROUND the permission circuit.
"""
from __future__ import annotations

import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from daemon import picker
from server import daemon_api

SAME = {"Sec-Fetch-Site": "same-origin"}


def _app(tmp_path, monkeypatch, *, cloud=False):
    monkeypatch.setattr(daemon_api, "_state_dir", lambda: tmp_path / "config" / "daemon")
    monkeypatch.setattr(daemon_api, "_is_cloud", lambda: cloud)
    monkeypatch.setattr(daemon_api, "_last_start", [0.0])
    app = FastAPI()
    app.include_router(daemon_api.router)
    return TestClient(app)


def test_connect_starts_the_daemon_this_engine_carries(tmp_path, monkeypatch):
    spawned = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: spawned.append((cmd, kw)))
    r = _app(tmp_path, monkeypatch).post("/api/daemon/start", headers=SAME)
    assert r.json() == {"ok": True, "started": True}
    cmd, kw = spawned[0]
    assert cmd[1:] == ["-m", "daemon"] and kw.get("cwd")


def test_a_second_click_does_not_start_a_second_daemon(tmp_path, monkeypatch):
    spawned = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: spawned.append(cmd))
    c = _app(tmp_path, monkeypatch)
    c.post("/api/daemon/start", headers=SAME)
    assert c.post("/api/daemon/start", headers=SAME).json().get("starting") and len(spawned) == 1


def test_a_daemon_that_already_answers_is_left_alone(tmp_path, monkeypatch):
    spawned = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: spawned.append(cmd))
    monkeypatch.setattr(daemon_api, "_daemon_config", lambda: {"token": "t", "port": 45817})

    async def _healthy(cfg, path, payload=None, **kw):
        return 200, {"ok": True}
    monkeypatch.setattr(daemon_api, "_call", _healthy)
    assert _app(tmp_path, monkeypatch).post("/api/daemon/start", headers=SAME).json()["started"] is False
    monkeypatch.setattr(daemon_api, "_daemon_config", lambda: {"token": "t", "port": 45817})
    assert not spawned


def test_the_cloud_and_another_site_cannot_start_it(tmp_path, monkeypatch):
    spawned = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: spawned.append(cmd))
    assert _app(tmp_path, monkeypatch, cloud=True).post("/api/daemon/start", headers=SAME).status_code == 409
    assert _app(tmp_path, monkeypatch).post("/api/daemon/start",
                                            headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert not spawned


def test_the_pick_waits_for_the_person_not_the_network(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(daemon_api, "_daemon_config", lambda: {"token": "t", "port": 45817})

    async def _daemon(cfg, path, payload=None, *, timeout=daemon_api._TIMEOUT_S):
        seen.update(path=path, payload=payload, timeout=timeout)
        return 200, {"ok": True, "roots": ["/x"]}
    monkeypatch.setattr(daemon_api, "_call", _daemon)
    r = _app(tmp_path, monkeypatch).post("/api/daemon/permissions/pick", json={"prompt": "Choose"}, headers=SAME)
    assert r.json()["ok"] and seen["path"] == "/permissions/pick" and seen["payload"]["prompt"] == "Choose"
    assert seen["timeout"] > picker.TIMEOUT_S


# ── the daemon side ────────────────────────────────────────────────────────────────────────────────────────

def test_a_prompt_cannot_close_the_dialog_script():
    p = picker._clean('Choose"); do shell script "rm -rf ~" --\\n$(x)`y`')
    assert not any(ch in p for ch in "\"'\\`$\n")


@pytest.mark.parametrize("returncode,out,expected", [(0, "/Users/x/Docs/\n", "/Users/x/Docs"), (1, "", "")])
def test_a_cancel_is_nothing_and_a_choice_is_its_path(monkeypatch, returncode, out, expected):
    monkeypatch.setattr(picker, "_command", lambda prompt: ["dialog"])
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, returncode, stdout=out, stderr=""))
    assert picker.choose_folder("x") == expected


def test_the_picked_folder_goes_through_the_same_boundary(monkeypatch):
    from daemon.fs import refusal, roots
    from daemon.http import routes
    monkeypatch.setattr(picker, "choose_folder", lambda prompt="": "/Users/x/.ssh")

    def _refuse(path):
        raise refusal.Refusal("sensitive", "that folder holds credentials")
    monkeypatch.setattr(roots, "grant", _refuse)
    with pytest.raises(refusal.Refusal):
        routes.pick(type("R", (), {"_caller": lambda self: "test"})(), {"prompt": "x"})
    monkeypatch.setattr(picker, "choose_folder", lambda prompt="": "")
    monkeypatch.setattr(roots, "roots", lambda: [])
    assert routes.pick(type("R", (), {"_caller": lambda self: "test"})(), {})["cancelled"] is True


def test_a_cloud_account_is_recognised_without_a_stub(monkeypatch):
    """Live 2026-10-23: `_is_cloud` imported a module that does not exist, so it always said «local» and the cloud
    showed the icon and the self-host screen. Every other test here stubs `_is_cloud`; this one does not."""
    monkeypatch.setenv("ZAELAR_USER_ID", "f075b277-0000-0000-0000-000000000000")
    assert daemon_api._is_cloud() is True
    monkeypatch.delenv("ZAELAR_USER_ID")
    assert daemon_api._is_cloud() is False
