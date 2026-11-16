package com.zaelar.app;

import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebViewClient;

/**
 * Capacitor's WebView client with one difference: which HTTP answers of the main frame bring up the bundled page
 * (`server.errorPath`, `www/index.html`, which retries on its own).
 *
 * Capacitor 7 shows it for ANY main-frame status of 400 or more, so a page the engine meant to show (a 404, a sign-in
 * answer) is replaced by the retry page. Here only 502, 503 and 504 do it: the origin is up but what is behind it is
 * not answering yet (an engine still starting), which is exactly what the retry page is for. Every other status is
 * shown as the engine sent it — the same as iOS (`NavigationFilter.swift`).
 *
 * Network errors (no answer at all) keep Capacitor's behaviour: the retry page.
 */
public class GatewayErrorWebViewClient extends BridgeWebViewClient {

    public GatewayErrorWebViewClient(Bridge bridge) {
        super(bridge);
    }

    static boolean isGatewayStatus(int status) {
        return status == 502 || status == 503 || status == 504;
    }

    /**
     * Capacitor's own handling (its WebView listeners, then errorPath for the main frame) only for a gateway status.
     * Any other status reaches no listener: none of the app's plugins registers one, and Capacitor keeps the list
     * package-private, so it cannot be walked from here.
     */
    @Override
    public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse errorResponse) {
        if (isGatewayStatus(errorResponse.getStatusCode())) {
            super.onReceivedHttpError(view, request, errorResponse);
        }
    }
}
