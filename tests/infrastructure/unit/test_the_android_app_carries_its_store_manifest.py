"""V2-870 — the Android app carries what Google Play reads: the manifest's permissions, the target API, the app id and a
release build that is never signed from the repository.

Play refuses an upload whose target API is below the year's floor, and every permission in the manifest must match
the Data safety form and the store listing: a permission added here without its declaration is a rejection that arrives
days later. The set is exact on purpose — notifications, background location, Bluetooth and the camera come with the
features that use them (and with their own Play declarations), never ahead of them.
"""
from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ANDROID = ROOT / "mobile-app" / "android"
MANIFEST = ANDROID / "app" / "src" / "main" / "AndroidManifest.xml"
APP_GRADLE = ANDROID / "app" / "build.gradle"
VARIABLES = ANDROID / "variables.gradle"
NS = "{http://schemas.android.com/apk/res/android}"
TARGET_FLOOR = 36   # Google Play: new apps and updates target API 36 from 2026-08-31 (extension to 2026-11-01)

PERMISSIONS = {"INTERNET", "RECORD_AUDIO", "MODIFY_AUDIO_SETTINGS", "ACCESS_COARSE_LOCATION", "ACCESS_FINE_LOCATION"}


def _manifest() -> ET.Element:
    return ET.parse(MANIFEST).getroot()


def test_the_manifest_asks_for_exactly_what_the_app_uses() -> None:
    declared = {p.get(f"{NS}name").removeprefix("android.permission.") for p in _manifest().iter("uses-permission")}
    assert declared == PERMISSIONS, declared ^ PERMISSIONS
    features = {f.get(f"{NS}name"): f.get(f"{NS}required") for f in _manifest().iter("uses-feature")}
    assert all(v == "false" for v in features.values()), "a required feature hides the app from phones without it"


def test_the_application_keeps_its_session_on_the_device() -> None:
    app = _manifest().find("application")
    assert app.get(f"{NS}allowBackup") == "false", "a cloud backup would carry the session cookie to another device"
    activity = app.find("activity")
    assert activity.get(f"{NS}windowSoftInputMode") == "adjustResize"
    assert activity.get(f"{NS}screenOrientation") == "portrait"


def test_the_app_id_and_the_target_api_are_what_play_expects() -> None:
    gradle = APP_GRADLE.read_text()
    assert 'applicationId "com.zaelar.app"' in gradle, "the app id is fixed forever: changing it is a new app"
    variables = VARIABLES.read_text()
    target = int(re.search(r"targetSdkVersion = (\d+)", variables).group(1))
    compile_ = int(re.search(r"compileSdkVersion = (\d+)", variables).group(1))
    assert target >= TARGET_FLOOR and compile_ >= target, (target, compile_)


def test_the_release_is_signed_only_from_the_environment() -> None:
    gradle = APP_GRADLE.read_text()
    assert "System.getenv('ANDROID_UPLOAD_KEYSTORE')" in gradle
    assert "signingConfigs.debug" not in gradle, "a release signed with the debug key is refused by Play"
    tracked = subprocess.run(["git", "ls-files", "mobile-app"], cwd=ROOT, capture_output=True, text=True).stdout
    assert not re.search(r"\.(jks|keystore)$", tracked, re.M), "a keystore never enters the repository"


def test_the_glue_is_injected_on_the_engine_origin_only() -> None:
    plugin = (ANDROID / "app/src/main/java/com/zaelar/app/InAppPlugin.java").read_text()
    assert 'asset("public/in-app.js")' in plugin
    assert "Collections.singleton(origin)" in plugin, "the glue must never run on another site the WebView opens"
