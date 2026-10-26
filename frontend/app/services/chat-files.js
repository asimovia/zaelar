// chat-files — files added to the chat (V2-809). One upload per file through the ONE upload door
// (`POST /api/files/upload?source=chat`), the file as a RAW body so the server can refuse the size and the disk
// headroom before a byte is written and can stream it to disk. XMLHttpRequest and not fetch: it is the browser
// API that reports UPLOAD progress and can be aborted mid-body.
//
// Nothing waits forever: the upload has a STALL clock (no progress for `upload_stall_s` → aborted, said so) and
// the reading that follows has its own deadline (the server's `process_timeout_s` plus a margin). Every wait ends
// in a visible outcome. The bytes never travel over the LiveKit data channel — the message carries a reference.

// The limits are the server's (`GET /api/files/limits`, from `config/attachments.default.json`). These defaults
// are only what the composer uses if that read fails; the server refuses again either way.
const FALLBACK = { max_file_bytes: 200 * 1048576, max_files_per_message: 10, max_message_bytes: 500 * 1048576,
                   upload_stall_s: 30, process_timeout_s: 90 };
let _limits = null;

export async function limits() {
  if (_limits) return _limits;
  try {
    const r = await fetch("/api/files/limits", { cache: "no-store" });
    const d = r.ok ? await r.json() : null;
    _limits = { ...FALLBACK, ...(d && typeof d.max_file_bytes === "number" ? d : {}) };
  } catch (_) { _limits = { ...FALLBACK }; }
  return _limits;
}

// The kinds the chat takes. The browser's word is only a pre-filter so a refusal is instant; the server decides
// from the bytes.
const IMG = /\.(png|jpe?g|gif|webp)$/i, PDF = /\.pdf$/i, TXT = /\.(txt|md|markdown|csv)$/i;
export function kindOf(file) {
  const n = (file && file.name) || "", ty = (file && file.type) || "";
  if (/^image\/(png|jpeg|gif|webp)$/i.test(ty) || IMG.test(n)) return "image";
  if (ty === "application/pdf" || PDF.test(n)) return "pdf";
  if (TXT.test(n)) return "text";
  return null;
}

export function fmtSize(n) {
  n = Number(n) || 0;
  if (n >= 1048576) return (n / 1048576).toFixed(n >= 10485760 ? 0 : 1) + " MB";
  return Math.max(1, Math.round(n / 1024)) + " KB";
}

// The refusal codes the server answers with → their i18n key. One map, so a code and its message cannot drift.
export const REASON_KEY = {
  too_large: "chat.attachTooLarge", type: "chat.attachType", disk_full: "chat.attachDiskFull",
  stalled: "chat.attachStalled", timeout: "chat.attachTimeout", failed: "chat.attachFailed",
};

// Upload ONE file. `onState({phase, pct})` reports `up` (with pct) then `reading`. Resolves to
// `{ok:true, ref}` or `{ok:false, reason}`; a cancel resolves `{ok:false, reason:"cancelled"}`. Never rejects.
export function upload(file, { onState, lim } = {}) {
  const L = lim || FALLBACK;
  const xhr = new XMLHttpRequest();
  let settled = false, timer = null, last = Date.now(), phase = "up", readingSince = 0, why = null;
  const done = new Promise((resolve) => {
    const finish = (out) => { if (settled) return; settled = true; clearInterval(timer); resolve(out); };
    xhr.open("POST", "/api/files/upload?source=chat");
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.setRequestHeader("X-File-Name", encodeURIComponent(file.name || "archivo"));
    xhr.upload.onprogress = (e) => {
      last = Date.now();
      if (e.lengthComputable && onState) onState({ phase: "up", pct: Math.round((e.loaded / e.total) * 100) });
    };
    xhr.upload.onload = () => {
      phase = "reading"; readingSince = Date.now();
      if (onState) onState({ phase: "reading", pct: 100 });
    };
    xhr.onload = () => {
      let d = null; try { d = JSON.parse(xhr.responseText || "null"); } catch (_) {}
      if (xhr.status >= 200 && xhr.status < 300 && d && d.episode_id) return finish({ ok: true, ref: d });
      finish({ ok: false, reason: (d && d.reason) || (xhr.status === 413 ? "too_large" : "failed") });
    };
    xhr.onerror = () => finish({ ok: false, reason: "failed" });
    xhr.onabort = () => finish({ ok: false, reason: why || "cancelled" });
    // THE CLOCK. The upload phase is bounded by its PROGRESS (a big file on a slow line is fine while it moves);
    // the reading phase by the server's own deadline plus one stall window for the answer to travel back.
    timer = setInterval(() => {
      const now = Date.now();
      if (phase === "up" && now - last > L.upload_stall_s * 1000) { why = "stalled"; xhr.abort(); }
      else if (phase === "reading" && now - readingSince > (L.process_timeout_s + L.upload_stall_s) * 1000) { why = "timeout"; xhr.abort(); }
    }, 1000);
    xhr.send(file);
  });
  return { done, cancel: () => { if (!settled) { why = "cancelled"; xhr.abort(); } } };
}

// He removed a chip that had already uploaded: the turn stops seeing it (the file stays stored).
export function detach(episodeId) {
  return fetch(`/api/files/attached/${encodeURIComponent(episodeId)}`, { method: "DELETE" }).catch(() => null);
}
