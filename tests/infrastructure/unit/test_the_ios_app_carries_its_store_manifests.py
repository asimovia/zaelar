"""V2-870 — the iOS app carries what App Review reads: Info.plist keys, the privacy manifest and the entitlements.

Parsed with plistlib (and `plutil -lint` where it exists, i.e. on a Mac): a manifest that does not parse is refused at
upload, and a missing key is a rejection that arrives days later. The entitlements are a TEMPLATE on purpose (the host
is deployment data and a personal team cannot sign Associated Domains), so its placeholder must survive.
"""
from __future__ import annotations

import plistlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[3] / "mobile-app" / "ios" / "App"
INFO = APP / "App" / "Info.plist"
PRIVACY = APP / "App" / "PrivacyInfo.xcprivacy"
ENTITLEMENTS = APP / "App" / "App.entitlements.template"
PBXPROJ = APP / "App.xcodeproj" / "project.pbxproj"
# The location plugin links the "always" API even though the app only asks while in use: without that purpose
# string App Store Connect flags the upload (ITMS-90683).
PURPOSE_KEYS = ("NSMicrophoneUsageDescription", "NSLocationWhenInUseUsageDescription",
                "NSLocationAlwaysAndWhenInUseUsageDescription")


def _plist(p: Path) -> dict:
    return plistlib.loads(p.read_bytes())


@pytest.mark.parametrize("path", [INFO, PRIVACY, ENTITLEMENTS])
def test_every_manifest_parses(path: Path) -> None:
    assert isinstance(_plist(path), dict)
    if shutil.which("plutil"):
        r = subprocess.run(["plutil", "-lint", str(path)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr


def test_info_plist_answers_what_review_asks() -> None:
    info = _plist(INFO)
    assert info["CFBundleDisplayName"] == "Zaelar"
    assert info["ITSAppUsesNonExemptEncryption"] is False
    assert info["UIRequiresFullScreen"] is True
    assert info["LSApplicationCategoryType"] == "public.app-category.productivity"
    assert info["UISupportedInterfaceOrientations"] == ["UIInterfaceOrientationPortrait"]
    for key in PURPOSE_KEYS:
        assert info.get(key, "").strip(), f"{key} is missing: iOS kills the app when the permission is first asked"
    assert "NSCameraUsageDescription" not in info, "nothing uses the camera: review asks why a permission is declared"
    assert info["CFBundleShortVersionString"] == "$(MARKETING_VERSION)"
    assert info["CFBundleVersion"] == "$(CURRENT_PROJECT_VERSION)"
    assert "UIBackgroundModes" not in info, "no background mode until background voice ships (review asks why)"


def test_the_project_targets_the_iphone_and_is_versioned_by_the_script() -> None:
    pbx = PBXPROJ.read_text()
    families = set(re.findall(r"TARGETED_DEVICE_FAMILY = \"?([^;\"]+)\"?;", pbx))
    assert families and families <= {"1", "1,2"}, families   # iPhone now; iPad joins the same target later
    assert all(re.fullmatch(r"\d+(\.\d+){0,2}", v) for v in re.findall(r"CURRENT_PROJECT_VERSION = ([^;]+);", pbx))
    assert "PrivacyInfo.xcprivacy in Resources" in pbx, "the privacy manifest must be bundled, not just present"


def test_the_privacy_manifest_declares_no_tracking_and_the_store_labels() -> None:
    p = _plist(PRIVACY)
    assert p["NSPrivacyTracking"] is False and p["NSPrivacyTrackingDomains"] == []
    assert p["NSPrivacyAccessedAPITypes"] == [{"NSPrivacyAccessedAPIType": "NSPrivacyAccessedAPICategoryUserDefaults",
                                               "NSPrivacyAccessedAPITypeReasons": ["CA92.1"]}]
    kinds = {d["NSPrivacyCollectedDataType"].removeprefix("NSPrivacyCollectedDataType"): d
             for d in p["NSPrivacyCollectedDataTypes"]}
    assert set(kinds) == {"EmailAddress", "Name", "PreciseLocation", "Contacts", "AudioData", "OtherUserContent",
                          "CustomerSupport", "SearchHistory", "UserID", "ProductInteraction", "OtherDiagnosticData"}
    for name, d in kinds.items():
        assert d["NSPrivacyCollectedDataTypeLinked"] is True, name
        assert d["NSPrivacyCollectedDataTypeTracking"] is False, name
        assert "NSPrivacyCollectedDataTypePurposeAppFunctionality" in d["NSPrivacyCollectedDataTypePurposes"], name


def test_the_entitlements_are_a_template_without_push_yet() -> None:
    e = _plist(ENTITLEMENTS)
    assert e["com.apple.developer.associated-domains"] == ["applinks:__APP_LINKS_HOST__",
                                                           "webcredentials:__APP_LINKS_HOST__"]
    assert "aps-environment" not in e, "native push brings its own entitlement with its own step"


def test_every_purpose_string_is_translated() -> None:
    for lang in ("en", "es"):
        strings = (APP / "App" / f"{lang}.lproj" / "InfoPlist.strings").read_text()
        for key in PURPOSE_KEYS:
            assert f'"{key}" = "' in strings, f"{key} has no {lang} sentence"
