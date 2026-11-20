// apps-bridge.js — the ONE file that imports the side panel's widget catalogue (`side/apps/`) and wires it to the store
// (the sub-tab, which the voice's «apps-custom» alias also sets), `/widgets/registry`, the strings and the one door a
// widget opens through (`hb:open-card`). show/hide run untracked: the shell's effect never subscribes to their reads.
import { createEffect, untrack } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "./api.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { APPS_ICON } from "../lib/icons.js?v=1";
import { mount } from "../../side/apps/apps.js";

export function mountAppsTab(host) {
  const tab = mount(host, { t, icon: APPS_ICON, load: async () => ((await api.getWidgetsRegistry()) || {}).registry,
    open: (id) => document.dispatchEvent(new CustomEvent("hb:open-card", { detail: { id } })),
    scope: store.appsScope, setScope: store.setAppsScope,
    onChange: (fn) => createEffect(() => { store.appsScope(); t("chat.appsSystem"); untrack(fn); }) });
  return { show: () => untrack(tab.show), hide: () => untrack(tab.hide), unmount: tab.unmount };
}
