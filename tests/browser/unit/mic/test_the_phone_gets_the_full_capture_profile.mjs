// ============================================================================
// test_the_phone_gets_the_full_capture_profile.mjs — V2-812 T-08.
//
// THE BUG. The «is it a Mac» check matched iPhone/iPad, so the phone opened its mic with echo cancellation ONLY —
// no noise suppression, no gain control — in exactly the place (a car) where it needs both.
//
// Drives the REAL `frontend/app/services/mic-profile.js` (or the copy named by MIC_PROFILE, which is how the pytest
// disarm points it at a mutated module) with fake navigators of each platform.
// ============================================================================
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";

const target = process.env.MIC_PROFILE
  ? pathToFileURL(process.env.MIC_PROFILE).href
  : new URL("../../../../frontend/app/services/mic-profile.js", import.meta.url).href;
const { platformKind, defaultMicMode, captureConstraints } = await import(target);

const sup = (extra = {}) => ({ getSupportedConstraints: () => ({ echoCancellation: true, noiseSuppression: true,
                                                                   autoGainControl: true, ...extra }) });
const FULL = { echoCancellation: true, noiseSuppression: true, autoGainControl: true };

const iphone = { platform: "iPhone", maxTouchPoints: 5, mediaDevices: sup({ voiceIsolation: true }),
                 userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1" };
const ipadDesktopMode = { platform: "MacIntel", maxTouchPoints: 5, mediaDevices: sup(),
                          userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15" };
const android = { platform: "Linux armv81", maxTouchPoints: 5, userAgentData: { mobile: true, platform: "Android" },
                  mediaDevices: sup(), userAgent: "Mozilla/5.0 (Linux; Android 15; Pixel 9) Chrome/141 Mobile Safari/537.36" };
const macChrome = { platform: "MacIntel", maxTouchPoints: 0, userAgentData: { mobile: false, platform: "macOS" },
                    mediaDevices: sup(), userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/141" };
const macSafari = { platform: "MacIntel", maxTouchPoints: 0, mediaDevices: sup({ voiceIsolation: true }),
                    userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15" };
const windows = { platform: "Win32", maxTouchPoints: 0, mediaDevices: sup(),
                  userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141" };

// 1 · phones and tablets get the FULL profile (the bug: iPhone got «isolate»)
for (const [name, nav] of [["iPhone", iphone], ["iPad (desktop mode)", ipadDesktopMode], ["Android", android]]) {
  assert.equal(platformKind(nav), "mobile", `${name} must be detected as mobile`);
  assert.equal(defaultMicMode(nav), "full", `${name} must default to the full profile`);
  const c = captureConstraints(defaultMicMode(nav), nav);
  for (const [k, v] of Object.entries(FULL)) assert.equal(c[k], v, `${name}: ${k} must be ${v}`);
}

// 2 · a desktop Mac keeps «isolate» on purpose (let macOS Voice Isolation work without browser NS on top)
for (const [name, nav] of [["Mac Chrome", macChrome], ["Mac Safari", macSafari]]) {
  assert.equal(platformKind(nav), "mac", `${name} is a desktop Mac`);
  assert.equal(defaultMicMode(nav), "isolate", `${name} keeps the isolate profile`);
  assert.equal(captureConstraints("isolate", nav).noiseSuppression, false);
}
assert.equal(defaultMicMode(windows), "full", "Windows/Linux keep the full profile");

// 3 · voiceIsolation only where the browser reports it — never blind
assert.equal(captureConstraints("full", iphone).voiceIsolation, true, "supported → asked");
assert.equal(captureConstraints("isolate", macSafari).voiceIsolation, true, "supported on Mac Safari → asked");
assert.equal("voiceIsolation" in captureConstraints("full", android), false, "unsupported → not asked");
assert.equal("voiceIsolation" in captureConstraints("isolate", macChrome), false, "Chrome ignores it → not asked");
assert.equal("voiceIsolation" in captureConstraints("raw", iphone), false, "raw means no processing at all");
assert.equal("voiceIsolation" in captureConstraints("full", {}), false, "no mediaDevices → not asked, no throw");

console.log("ok — capture profile per platform");
