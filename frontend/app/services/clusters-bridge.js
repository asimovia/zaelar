// clusters-bridge.js — the ONE file that imports the «Clusters» column (frontend/side/clusters/): it hands it the store, the words, the reactivity.
import { mount } from "../../side/clusters/clusters.js";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";
export function mountClusters(host) {
  document.head.append(Object.assign(document.createElement("link"), { rel: "stylesheet", href: "/static/side/clusters/clusters.css?v=1" }));
  return mount(host, { clusters: store.clusters, confirm: store.clusterConfirm, t, watch: createEffect, refresh: store.fetchClusters,
                       connect: store.clusterConnect, disconnect: store.clusterDisconnect, resolve: store.clusterConfirmResolve });
}
