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
                "NSLocationAlwaysAndWhenInUseUsageDescription", "NSBluetoothAlwaysUsageDescription",
                "NSMotionUsageDescription", "NSCameraUsageDescription")


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
    # V2-928 T10: the camera serves the face that looks at the person (on the device), photos shared with the agent and
    # video calls; review reads the sentence against what the app does, so it names all three.
    cam = info["NSCameraUsageDescription"].lower()
    assert all(w in cam for w in ("face", "photo", "video call")), cam
    assert "never leave" in cam, "the face's frames are processed on the phone and the sentence says so"
    assert "NSPhotoLibraryUsageDescription" not in info and "NSPhotoLibraryAddUsageDescription" not in info, \
        "nothing reads or saves the photo library (the picker needs no permission): review asks why it is declared"
    assert info["CFBundleShortVersionString"] == "$(MARKETING_VERSION)"
    assert info["CFBundleVersion"] == "$(CURRENT_PROJECT_VERSION)"
    # V2-890: the two modes an activity the person starts needs (route + heart-rate strap with the screen locked), and
    # audio: a voice conversation the person started keeps going with the screen locked, as in any calling app.
    # Review asks what each mode is for; none is declared ahead of the feature that uses it.
    assert info["UIBackgroundModes"] == ["location", "bluetooth-central", "audio"]


def test_the_head_motion_bridge_is_a_method_of_the_device_plugin_and_reaches_the_page() -> None:
    swift = (APP / "App" / "DevicePlugin.swift").read_text()
    for name in ("headMotionAvailable", "startHeadMotion", "stopHeadMotion"):
        assert f'CAPPluginMethod(name: "{name}"' in swift and f"@objc func {name}(" in swift, name
    assert "CMHeadphoneMotionManager" in swift and 'notifyListeners("headMotion"' in swift
    glue = (APP.parent.parent / "www" / "in-app.js").read_text()
    assert "native.headMotion" in glue and "platform !== 'ios'" in glue, "Android answers available() = false"


def test_the_audio_bridge_reads_the_route_and_never_sets_a_level() -> None:
    """`window.ZaelarNative.audio`: route, speaker, route changes and interruptions from the app's own plugin, built
    into the target and registered; it never touches a level or the session's category (WebKit owns the session)."""
    swift = (APP / "App" / "AudioPlugin.swift").read_text()
    for name in ("available", "route", "setSpeaker"):
        assert f'CAPPluginMethod(name: "{name}"' in swift and f"@objc func {name}(" in swift, name
    assert 'jsName = "ZaelarAudio"' in swift
    assert 'notifyListeners("audioRoute"' in swift and 'notifyListeners("audioInterruption"' in swift
    assert "routeChangeNotification" in swift and "interruptionNotification" in swift
    code = "\n".join(l for l in swift.splitlines() if not l.strip().startswith("///") and not l.strip().startswith("//"))
    for banned in ("setCategory", "setActive", "outputVolume", "MPVolumeView"):
        assert banned not in code, f"the audio bridge must not {banned}: the session is WebKit's, the volume the person's"
    assert "AudioPlugin.swift in Sources" in PBXPROJ.read_text(), "the plugin must be compiled into the app"
    assert "registerPluginInstance(AudioPlugin())" in (APP / "App" / "MainViewController.swift").read_text()
    glue = (APP.parent.parent / "www" / "in-app.js").read_text()
    for name in ("available:", "route:", "setSpeaker:", "onRouteChange:", "onInterruption:"):
        assert name in glue.split("native.audio")[1], name


def test_the_project_targets_the_iphone_and_is_versioned_by_the_script() -> None:
    pbx = PBXPROJ.read_text()
    families = set(re.findall(r"TARGETED_DEVICE_FAMILY = \"?([^;\"]+)\"?;", pbx))
    assert families and families <= {"1", "1,2"}, families   # iPhone now; iPad joins the same target later
    assert all(re.fullmatch(r"\d+(\.\d+){0,2}", v) for v in re.findall(r"CURRENT_PROJECT_VERSION = ([^;]+);", pbx))
    assert "PrivacyInfo.xcprivacy in Resources" in pbx, "the privacy manifest must be bundled, not just present"


def test_the_privacy_manifest_declares_no_tracking_and_the_store_labels() -> None:
    p = _plist(PRIVACY)
    # PhotosorVideos (V2-928 T10): a photo the person shares with the agent is sent and kept. The face's camera frames,
    # the head's motion and a live video call are processed in real time and never stored: not collected.
    assert p["NSPrivacyTracking"] is False and p["NSPrivacyTrackingDomains"] == []
    assert p["NSPrivacyAccessedAPITypes"] == [{"NSPrivacyAccessedAPIType": "NSPrivacyAccessedAPICategoryUserDefaults",
                                               "NSPrivacyAccessedAPITypeReasons": ["CA92.1"]}]
    kinds = {d["NSPrivacyCollectedDataType"].removeprefix("NSPrivacyCollectedDataType"): d
             for d in p["NSPrivacyCollectedDataTypes"]}
    assert set(kinds) == {"EmailAddress", "Name", "CoarseLocation", "PreciseLocation", "Health", "Fitness", "Contacts", "AudioData", "PhotosorVideos", "OtherUserContent",
                          "CustomerSupport", "SearchHistory", "UserID", "ProductInteraction", "OtherDiagnosticData"}
    for name, d in kinds.items():
        assert d["NSPrivacyCollectedDataTypeLinked"] is True, name
        assert d["NSPrivacyCollectedDataTypeTracking"] is False, name
        assert "NSPrivacyCollectedDataTypePurposeAppFunctionality" in d["NSPrivacyCollectedDataTypePurposes"], name


def test_the_entitlements_are_a_template_without_push_yet() -> None:
    e = _plist(ENTITLEMENTS)
    # The hosts are deployment data: the template carries a marker, the archive script writes one applinks: and one
    # webcredentials: line per host of ZAELAR_APP_LINKS_HOST in its place.
    assert e["com.apple.developer.associated-domains"] == []
    assert "<!--ASSOCIATED_DOMAINS-->" in ENTITLEMENTS.read_text()
    script = (APP.parent.parent / "scripts" / "ios-archive.sh").read_text()
    assert "<string>applinks:$h</string>" in script and "<string>webcredentials:$h</string>" in script
    assert "aps-environment" not in e, "native push brings its own entitlement with its own step"


def test_every_purpose_string_is_translated() -> None:
    for lang in ("en", "es"):
        strings = (APP / "App" / f"{lang}.lproj" / "InfoPlist.strings").read_text()
        for key in PURPOSE_KEYS:
            assert f'"{key}" = "' in strings, f"{key} has no {lang} sentence"
