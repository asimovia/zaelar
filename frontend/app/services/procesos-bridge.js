// procesos-bridge.js — the ONE file that knows both sides of the «Procesos» column: the component
// (`frontend/side/procesos/`, which imports nothing) and the store, api, words and process entries. Nothing else
// imports the component (a static test holds it).
import { mount } from "../../side/procesos/procesos.js";
import { createEffect, untrack } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "./api.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { TRASH_ICON } from "../lib/icons.js?v=1";
import { ProcessEntry } from "../components/ProcessEntry.js?v=1";

// `track` names what a callback follows; its first run only subscribes (the component paints itself at mount), and
// `fn` runs untracked so nothing read while painting subscribes it to more.
const follow = (track, fn) => {
  let first = true;
  return createEffect(() => { track(); if (first) first = false; else untrack(fn); });
};

export const mountProcesos = (host) => mount(host, {
  t, lang: store.lang, rows: store.taskRows, scope: store.taskScope, showAll: store.taskShowAll,
  setScope: store.setTaskScope, setShowAll: store.setTaskShowAll, fetchScope: store.fetchTaskScope,
  fetchLive: store.fetchTasks, reopen: api.taskReopen, removeScheduled: (id) => api.cronAction("remove", id),
  // The card opens through the desktop's house door, the one every other card takes.
  openCard: (id) => { try { document.dispatchEvent(new CustomEvent("hb:open-card", { detail: { id } })); } catch (_) {} },
  entry: ProcessEntry, icons: { trash: TRASH_ICON },
  // `t()` reads the bundle's revision: a bundle that changed redraws the words.
  watch: (fn) => follow(() => { store.taskRows(); store.taskScope(); store.taskShowAll(); t("chat.tabTasks"); }, fn),
  onLiveChange: (fn) => follow(store.tasks, fn),
});
