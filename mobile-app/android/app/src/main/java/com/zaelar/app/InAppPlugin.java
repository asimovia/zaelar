package com.zaelar.app;

import android.net.Uri;
import com.getcapacitor.Logger;
import com.getcapacitor.Plugin;
import com.getcapacitor.annotation.CapacitorPlugin;
import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewFeature;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import org.json.JSONObject;

/**
 * Injects the app's own glue (`www/in-app.js`, bundled as `public/in-app.js`) at document start into the main frame
 * of every page of the configured engine's origin — the Android twin of the `WKUserScript` in
 * `MainViewController.swift`. The script receives that origin as `ZAELAR_APP_ORIGIN` and checks it again itself, and
 * `ZAELAR_APP_PLATFORM` = "android": it runs before Capacitor's own bridge script, so it cannot ask the bridge.
 *
 * A plugin, not activity code, because Capacitor loads plugins before the WebView loads its first page: a
 * document-start script added later would miss it. The plugin exposes no methods to the page.
 */
@CapacitorPlugin(name = "ZaelarInApp")
public class InAppPlugin extends Plugin {

    @Override
    public void load() {
        String origin = origin(getBridge().getServerUrl());
        if (origin.isEmpty()) {
            Logger.warn("[zaelar] no server url: in-app.js not injected");
            return;
        }
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
            Logger.warn("[zaelar] this WebView has no document-start scripts: in-app.js not injected");
            return;
        }
        String glue = asset("public/in-app.js");
        if (glue == null) {
            Logger.error("[zaelar] in-app.js missing from the bundle");
            return;
        }
        markNavigationHosts();
        String source = "(function (ZAELAR_APP_ORIGIN, ZAELAR_APP_PLATFORM) {\n" + glue + "\n})(" + JSONObject.quote(origin) + ", \"android\");";
        try {
            WebViewCompat.addDocumentStartJavaScript(getBridge().getWebView(), source, Collections.singleton(origin));
        } catch (IllegalArgumentException e) {
            Logger.error("[zaelar] in-app.js not injected for " + origin, e);
        }
    }

    /**
     * The hosts the WebView may open in-page (`ZAELAR_ALLOW_NAVIGATION`, e.g. the sign-in page on the website) learn
     * they are inside the app the way they do on iOS, where Capacitor injects its bridge into every page: the website
     * asks `window.Capacitor.isNativePlatform()` before any of its scripts and then drops its cookie bar and draws as
     * an app screen. On Android Capacitor injects the bridge on the engine's origin only, so these hosts get a marker
     * with that one answer — no plugins, nothing native reachable from them.
     */
    private void markNavigationHosts() {
        String[] hosts = getBridge().getConfig().getAllowNavigation();
        if (hosts == null || hosts.length == 0) return;
        java.util.Set<String> rules = new java.util.HashSet<>();
        for (String h : hosts) rules.add(h.startsWith("http") ? h : "https://" + h);
        String marker = "if (!window.Capacitor) window.Capacitor = Object.freeze({ isNativePlatform: function () { return true; },"
            + " getPlatform: function () { return 'android'; }, Plugins: Object.freeze({}) });";
        try {
            WebViewCompat.addDocumentStartJavaScript(getBridge().getWebView(), marker, rules);
        } catch (IllegalArgumentException e) {
            Logger.error("[zaelar] navigation hosts not marked: " + rules, e);
        }
    }

    /** `scheme://host[:port]` — the same string a page reads as `location.origin`. */
    static String origin(String url) {
        if (url == null) return "";
        Uri u = Uri.parse(url);
        if (u.getScheme() == null || u.getHost() == null) return "";
        return u.getScheme() + "://" + u.getHost() + (u.getPort() != -1 ? ":" + u.getPort() : "");
    }

    private String asset(String path) {
        try (InputStream in = getContext().getAssets().open(path)) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            for (int n; (n = in.read(buf)) > 0; ) out.write(buf, 0, n);
            return out.toString(StandardCharsets.UTF_8.name());
        } catch (Exception e) {
            return null;
        }
    }
}
