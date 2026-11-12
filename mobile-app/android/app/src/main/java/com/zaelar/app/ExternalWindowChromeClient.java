package com.zaelar.app;

import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;
import android.os.Message;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebChromeClient;
import com.getcapacitor.Logger;

/**
 * Capacitor's chrome client (microphone and location permissions, file chooser) plus one rule: a new window — a
 * `window.open(url)`, a `target="_blank"` link, or `window.open("")` whose location the page sets afterwards — opens
 * in the system browser and never inside the app, as on iOS. The shell opens the account page this way, so the app
 * itself never shows a purchase path (App Store 3.1.3(f); Play's payments policy is the same).
 *
 * The new window is a throwaway WebView that is never shown: its first navigation is handed to the browser and it is
 * destroyed. The opener only sees a window that went away.
 */
public class ExternalWindowChromeClient extends BridgeWebChromeClient {

    private final Bridge bridge;

    public ExternalWindowChromeClient(Bridge bridge) {
        super(bridge);
        this.bridge = bridge;
    }

    @Override
    public boolean onCreateWindow(WebView view, boolean isDialog, boolean isUserGesture, Message resultMsg) {
        WebView popup = new WebView(view.getContext());
        popup.setWebViewClient(new WebViewClient() {
            private boolean handed = false;

            @Override
            public boolean shouldOverrideUrlLoading(WebView w, WebResourceRequest request) {
                hand(w, request.getUrl());
                return true;
            }

            @Override
            public void onPageStarted(WebView w, String url, android.graphics.Bitmap favicon) {
                if (url != null && !url.isEmpty() && !"about:blank".equals(url)) hand(w, Uri.parse(url));
            }

            private void hand(WebView w, Uri url) {
                if (handed) return;
                handed = true;
                w.stopLoading();
                openInBrowser(url);
                w.post(w::destroy);
            }
        });
        WebView.WebViewTransport transport = (WebView.WebViewTransport) resultMsg.obj;
        transport.setWebView(popup);
        resultMsg.sendToTarget();
        return true;
    }

    private void openInBrowser(Uri url) {
        String scheme = url.getScheme();
        if (scheme == null || !(scheme.equals("https") || scheme.equals("http") || scheme.equals("mailto") || scheme.equals("tel"))) {
            Logger.warn("[zaelar] new window with scheme " + scheme + " not opened");
            return;
        }
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, url).addCategory(Intent.CATEGORY_BROWSABLE);
            bridge.getActivity().startActivity(intent);
        } catch (ActivityNotFoundException e) {
            Logger.error("[zaelar] no app can open " + url, e);
        }
    }
}
