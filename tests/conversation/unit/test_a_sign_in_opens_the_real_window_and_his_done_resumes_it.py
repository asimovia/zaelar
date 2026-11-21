"""A sign-in is a HANDOFF that has to happen, not a label (V2-176): the conversation host's `sign_in(site, done)` act
opens the site's real login window through the browser owner's mailbox, and his «done» resumes the task that waited.

Measured in `cancel-subscription-before-charge__es` (2026-08-20): «abre la web de Netflix y me dices cuando esté en el
login» → «Aquí lo tienes», and nothing had been opened, so «ya he entrado» had no task to resume. What is measured
here is the boundary — the order queued to the browser owner — never a Chromium started in a test.
"""
from __future__ import annotations

import pytest

from nucleo.conversation_host import acts_tasks
from widgets.navegador import tasks as navtasks


@pytest.fixture
def queued(monkeypatch):
    sent: list[tuple] = []
    monkeypatch.setattr("widgets.supervisor.enqueue", lambda wid, action, payload: sent.append((wid, action, payload)) or True)
    monkeypatch.setattr("nucleo.consequence.passes", lambda *a, **k: True)
    navtasks._tasks.clear()
    yield sent
    navtasks._tasks.clear()


def test_the_window_opens_on_the_site_he_named(queued):
    r = acts_tasks.run("sign_in", {"site": "netflix.com"})
    assert r.status == "ok" and r.data["opened_for"] == "netflix.com" and r.data["task"]
    assert [(w, a) for w, a, _p in queued] == [("navegador", "authenticate")]
    assert queued[0][2]["url"] == "https://netflix.com" and queued[0][2]["task_id"] == r.data["task"]


def test_no_site_opens_nothing(queued):
    """Bug from 2026-07-23: with no site this once opened a default site nobody asked for."""
    r = acts_tasks.run("sign_in", {"site": ""})
    assert r.status == "failed" and r.data["reason"] == "no_site_recognised" and not queued


def test_his_done_resumes_the_task_that_waited(queued):
    tid = navtasks.create("Iniciar sesión · netflix.com")
    navtasks._tasks[tid]["awaiting_login"] = True
    r = acts_tasks.run("sign_in", {"done": True})
    assert r.status == "ok" and r.data["resumed"] == tid
    assert [(a, p["task_id"]) for _w, a, p in queued] == [("auth_done", tid)]


def test_his_done_with_nothing_waiting_is_said_as_that(queued):
    r = acts_tasks.run("sign_in", {"done": True})
    assert r.status == "failed" and r.data["reason"] == "nothing_waited" and not queued
