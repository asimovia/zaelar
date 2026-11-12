package com.zaelar.app;

import android.os.Bundle;
import android.view.ViewGroup;
import android.webkit.WebSettings;
import android.webkit.WebView;
import androidx.activity.OnBackPressedCallback;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import com.getcapacitor.BridgeActivity;

/**
 * The app is one full-screen WebView (Capacitor's bridge activity) showing the engine's `/m` shell — the Android twin
 * of `ios/App/App/MainViewController.swift` + `AppDelegate.swift`. Native code here is limited to the phone's hands:
 *
 *   · {@link InAppPlugin} injects the app's own glue (`www/in-app.js`) at document start, on the engine's origin only;
 *   · {@link ExternalWindowChromeClient} sends every new window (`window.open`, `target="_blank"`) to the system
 *     browser, as WKWebView does on iOS — the shell relies on it for the account page;
 *   · the WebView sits between the system bars and above the keyboard (Android 15 draws apps edge-to-edge, and the
 *     shell's `env(safe-area-inset-*)` reads 0 inside an Android WebView), on the app's dark background;
 *   · Back goes back in the WebView's history and, at its start, sends the app to the background (Capacitor's App
 *     plugin would do nothing there; its own handler is off in `capacitor.config.ts`).
 *
 * Voice v1 runs inside the WebView (WebRTC): Chromium itself puts the audio in communication mode with echo
 * cancellation and the speaker as the default route, and Capacitor's chrome client asks for the microphone the first
 * time the page wants it.
 */
public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // Registered before the bridge exists: plugins load before the WebView loads the first page, so the
        // document-start script is in place for it.
        registerPlugin(InAppPlugin.class);
        super.onCreate(savedInstanceState);

        WebView webView = bridge.getWebView();
        WebSettings settings = webView.getSettings();
        settings.setSupportMultipleWindows(true);
        settings.setJavaScriptCanOpenWindowsAutomatically(true);
        webView.setWebChromeClient(new ExternalWindowChromeClient(bridge));

        // Edge-to-edge on every Android version (15 imposes it anyway), so the insets below are the same everywhere.
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
        fitBetweenBarsAndAboveKeyboard(webView);
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                if (webView.canGoBack()) webView.goBack();
                else moveTaskToBack(true);   // like Home: the session and the shell stay as they were
            }
        });
        // Light icons on the dark shell (the same as the light status bar on iOS).
        WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView()).setAppearanceLightStatusBars(false);
        WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView()).setAppearanceLightNavigationBars(false);
    }

    /**
     * Margins from the system bars, the display cutout and the keyboard. The keyboard wins at the bottom: with it up
     * the WebView shrinks to the space above the keys, which is what the shell expects (iOS: Keyboard `resize: native`).
     */
    private static void fitBetweenBarsAndAboveKeyboard(WebView webView) {
        ViewCompat.setOnApplyWindowInsetsListener(webView, (v, windowInsets) -> {
            Insets bars = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout());
            Insets ime = windowInsets.getInsets(WindowInsetsCompat.Type.ime());
            ViewGroup.MarginLayoutParams mlp = (ViewGroup.MarginLayoutParams) v.getLayoutParams();
            mlp.leftMargin = bars.left;
            mlp.topMargin = bars.top;
            mlp.rightMargin = bars.right;
            mlp.bottomMargin = Math.max(bars.bottom, ime.bottom);
            v.setLayoutParams(mlp);
            return WindowInsetsCompat.CONSUMED;
        });
        ViewCompat.requestApplyInsets(webView);
    }
}
