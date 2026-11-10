"""nucleo/energy/account.py — "does this process run with an account identity" accessor. A single
truthy env check behind one accessor, so every gate that needs to distinguish "a hosted account
instance" from "self-host" (energy metering, centralized observability, provider control) reads the
SAME function instead of each re-parsing ZAELAR_USER_ID on its own.

ZAELAR_USER_ID is set by the hosting deployment's environment — self-host never sets it.
"""
from __future__ import annotations

import os


def is_cloud_account() -> bool:
    return bool(my_user_id())


def my_user_id() -> str:
    return (os.getenv("ZAELAR_USER_ID") or "").strip()


# Where the holder of an account manages it. ONE place knows it; the
# interface reads it from `/api/config` and `/api/energy` instead of carrying its own literal, so a deployment
# that serves its account page elsewhere sets `ZAELAR_ACCOUNT_URL` and every link follows.
_ACCOUNT_URL_ENV = "ZAELAR_ACCOUNT_URL"
_DEFAULT_ACCOUNT_URL = "https://zaelar.com/account"


def account_url() -> str:
    """The account page, or `""` without a cloud account — self-host has no account page to link to."""
    if not is_cloud_account():
        return ""
    return (os.getenv(_ACCOUNT_URL_ENV) or "").strip() or _DEFAULT_ACCOUNT_URL


# Where the holder of an account ends their session. A deployment that puts a login in front of the engine sets
# `ZAELAR_LOGOUT_URL` to a page the browser NAVIGATES to (GET, same tab) that ends the session and lands on its login;
# the interface's profile menu offers «Log out» only when it is set. No default: a self-hosted engine has no login.
_LOGOUT_URL_ENV = "ZAELAR_LOGOUT_URL"


def logout_url() -> str:
    """The deployment's log-out page, or `""` when none is set — the menu then has no «Log out»."""
    return (os.getenv(_LOGOUT_URL_ENV) or "").strip()
