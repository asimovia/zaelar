// mobile/app/shell/keyboard.js — the on-screen keyboard, for every card at once (V2-813).
//
// Measured on an iPhone 14 and a Pixel 7 (2026-10-26): with a text field focused inside a card, the keyboard took
// the bottom ~330px and the dock stayed on top of what was left, so the agenda's «Nueva cita» lost its Save and
// Cancel, and every editor in every card had the same shape. Both browsers now resize only the VISUAL viewport
// (iOS always, Chrome on Android since 108), so nothing in the layout moves on its own: the deck kept its full
// height and its bottom half sat under the keyboard.
//
// So one rule, here and not in sixteen widgets: while a field INSIDE A CARD has focus and the visual viewport is
// clearly shorter than the screen, the root wears `zm-kbd`, the deck is laid over the visible part only
// (`--zm-vvh`/`--zm-vvt`), the dock steps aside, and the focused field is brought into view. The chat sheet keeps its
// own composer and is left alone: only focus inside `.zm-deck` counts.

const MIN_KEYBOARD_PX = 120;     // a shorter shrink is browser chrome sliding, not a keyboard

function editable(el) {
  if (!el || !el.closest || !el.closest(".zm-deck")) return false;
  if (el.isContentEditable) return true;
  if (el.tagName === "TEXTAREA") return true;
  if (el.tagName !== "INPUT") return false;
  return !/^(checkbox|radio|range|button|submit|reset|file|color)$/i.test(el.type || "");
}

export function initKeyboard() {
  const vv = window.visualViewport;
  if (!vv) return;
  const root = document.documentElement;
  let full = Math.max(window.innerHeight, vv.height);

  const apply = () => {
    if (!root.classList.contains("zm-kbd")) full = Math.max(full, window.innerHeight, vv.height);
    const open = editable(document.activeElement) && vv.height < full - MIN_KEYBOARD_PX;
    root.classList.toggle("zm-kbd", open);
    if (open) {
      root.style.setProperty("--zm-vvh", vv.height + "px");
      root.style.setProperty("--zm-vvt", vv.offsetTop + "px");
      const el = document.activeElement;
      requestAnimationFrame(() => { try { el.scrollIntoView({ block: "nearest" }); } catch (_) { /* detached */ } });
    }
  };
  vv.addEventListener("resize", apply);
  vv.addEventListener("scroll", apply);
  window.addEventListener("resize", apply);
  document.addEventListener("focusin", () => setTimeout(apply, 50));
  document.addEventListener("focusout", () => setTimeout(apply, 50));
  window.addEventListener("orientationchange", () => { full = 0; setTimeout(apply, 300); });
}
