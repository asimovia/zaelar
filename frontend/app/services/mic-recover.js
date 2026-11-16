// ============================================================================
// mic-recover.js — THE RED MIC IS A BUTTON (V2-910, operator 2026-11-16).
//
// «Si no hay micro utilizable, el icono en rojo y tachado; tocarlo lo recupera.» One door both shells call from the
// tap, so it runs inside the gesture. What it does depends on WHY the mic is unusable (`store.micHealth().reason`):
//   · no_agent           → a new room with fresh bounds (the engine counts the unserved rooms on its own side);
//   · permission_denied,
//     no_device          → ask the browser once more (it may allow it now); when the system no longer asks, ONE
//                          sentence says where to allow it (`mic-denial.settingsHint`) and the native app opens its
//                          own settings page;
//   · anything else      → take the device again (`revive`, forced past its bound), or start the session that is not
//                          there; a revive that fails restarts the session.
// No session internals are imported: the session engine hands in what it owns, and a node test drives it.
// ============================================================================
import * as store from "../core/store.js?v=2";
import * as api from "./api.js?v=2";
import { t } from "../core/i18n.js?v=1";
import * as health from "./device-health.js?v=1";
import * as micDenial from "./mic-denial.js?v=1";

/** `{ started, start, stop, revive, resetRetries, probe }` from the session engine → the tap's `recover(reason)`. */
export function createMicRecover({ started, start, stop, revive, resetRetries,
                                   probe = () => navigator.mediaDevices.getUserMedia({ audio: true }),
                                   open = (url) => { window.location.href = url; } }) {
  return async function recover(reason = "tap") {
    const h = store.micHealth();
    try { api.clientLog("🎙️ mic recover", { text: `${reason}:${h.reason || "ok"}`, state: "recover:" + (h.reason || "ok") }); } catch (_) {}
    micDenial.gesture();
    if (h.reason === "no_agent") {
      health.setCondition("mic", "no_agent", false, "tap: a new room");
      resetRetries();
      store.setMicBlocked({ show: false, msg: "" });
      await stop();
      return start();
    }
    if (h.reason === "permission_denied" || h.reason === "no_device") {
      try {
        const s = await probe();
        s.getTracks().forEach((tr) => tr.stop());
        health.micCaptureResult(null);
        store.setMicBlocked({ show: false, msg: "" });
        await stop();
        return start();
      } catch (err) {
        health.micCaptureResult(err);
        const how = micDenial.settingsHint();
        store.setMicBlocked({ show: true, msg: t(how.key) });
        if (how.open) { try { open(how.open); } catch (_) {} }
        return false;
      }
    }
    if (!started()) return start();
    if (await revive(reason, { force: true })) return true;
    await stop();
    return start();
  };
}
