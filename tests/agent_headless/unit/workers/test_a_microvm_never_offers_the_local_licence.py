"""A microVM is a container: the local-licence worker rung is never offered inside one (V2-913, S4).

The last rung of the worker chain is the CLI's own browser login (`licencia-claude`, `local_only`), which cannot exist
inside a container. The chain drops it when `config.doctor.hardware()` says `container` — and a Firecracker microVM
built from an OCI image has neither `/.dockerenv` nor a docker cgroup, so the old check answered `False` there and a
new hosted account's chain ended in a rung that could only fail. Pinned here: the runtime's env markers and its init
file each make it a container; a plain host stays a host; and the chain, through the REAL detector, drops the rung.

Disarm: empty `doctor._RUNTIME_ENV` → the env cases red; drop `/.fly/init` from `doctor._RUNTIME_FILES` → the init case
red; drop the `local_only` filter in `providers.chain` → the chain case red.
"""
from __future__ import annotations

import os

import pytest

import config.doctor as doctor
from nucleo.workers import providers as prov


@pytest.fixture
def host(monkeypatch):
    """A plain host: no runtime env marker, no runtime file, no docker cgroup."""
    for var in doctor._RUNTIME_ENV:
        monkeypatch.delenv(var, raising=False)
    real_exists = os.path.exists
    files: set[str] = set()
    monkeypatch.setattr(doctor.os.path, "exists",
                        lambda p: p in files if p in doctor._RUNTIME_FILES else real_exists(p))
    monkeypatch.setattr(doctor, "Path", lambda p: type("P", (), {"exists": lambda s: False})())
    return files


def test_a_plain_host_is_not_a_container(host):
    assert doctor._in_container() is False


@pytest.mark.parametrize("var", ["FLY_MACHINE_ID", "KUBERNETES_SERVICE_HOST", "container"])
def test_a_runtime_env_marker_makes_it_a_container(host, monkeypatch, var):
    monkeypatch.setenv(var, "x")
    assert doctor._in_container() is True


@pytest.mark.parametrize("marker", ["/.fly/init", "/run/.containerenv", "/.dockerenv"])
def test_a_runtime_file_makes_it_a_container(host, marker):
    host.add(marker)
    assert doctor._in_container() is True


def test_inside_a_microvm_the_chain_never_ends_in_the_local_licence(host, monkeypatch):
    import config.v2 as v2
    monkeypatch.setattr(v2, "get", lambda k: {"base_url": "https://api.z.ai/api/anthropic", "model": "glm-5.3"}
                        if k == "code_agent" else {})
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    assert prov.chain()[-1]["name"] == "licencia-claude", "on a host the licence closes the chain"
    monkeypatch.setenv("FLY_MACHINE_ID", "m-1")
    assert "licencia-claude" not in [t["name"] for t in prov.chain()]
