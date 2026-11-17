// VolumeSlider — the agent's voice volume as a small slider beside the 🔊 (services/volume.js is its one door; his
// voice — «sube tu volumen», «volumen al 30 %» — takes the same one, through services/self-controls.js). Desktop: over
// the orb's lid, shown by a wheel notch or a right click on the 🔊 and by a voice order. Phone: one line over the
// dock, shown by a voice order, and a permanent row in Settings next to the speaker switch (`always`).
import { h } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import { t } from "../core/i18n.js?v=1";
import * as volume from "../services/volume.js?v=1";

export function VolumeSlider(cls, always = false) {
  return h("label", { class: () => cls + (always || volume.shown() ? " show" : "") },
    h("span", { class: "vol-t" }, () => t("controls.volume_label")),
    h("input", { type: "range", min: "0", max: "100", step: "5", "aria-label": () => t("controls.volume_label"),
      ref: (el) => createEffect(() => { el.value = String(volume.level()); }),
      onInput: (e) => volume.setLevel(e.target.value) }),
    h("b", { class: "vol-n" }, () => `${volume.level()} %`),
  );
}

/** The desktop 🔊's hand: a wheel notch moves the level by 5 (and shows it), a right click just shows it. */
export const volumeHands = {
  onWheel: (e) => volume.setLevel(volume.level() + (e.deltaY < 0 ? 5 : -5)),
  onContextmenu: (e) => { e.preventDefault(); volume.reveal(); },
};
