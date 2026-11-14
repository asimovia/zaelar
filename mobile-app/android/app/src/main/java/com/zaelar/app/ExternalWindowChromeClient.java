package com.zaelar.app;

import android.Manifest;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Message;
import android.webkit.PermissionRequest;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebChromeClient;
import com.getcapacitor.Logger;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.core.content.ContextCompat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Capacitor's chrome client (microphone and location permissions, file chooser) plus one rule: a new window — a
 * `window.open(url)`, a `target="_blank"` link, or `window.open("")` whose location the page sets afterwards — opens
 * in the system browser and never inside the app, as on iOS. The shell opens the account page this way, so the app
 * itself never shows a purchase path (App Store 3.1.3(f); Play's payments policy is the same).
 *
 * The new window is a throwaway WebView that is never shown: its first navigation is handed to the browser and it is
 * destroyed. The opener only sees a window that went away.
 *
 * It also answers the page's camera/microphone requests itself. Capacitor's version keeps ONE pending listener: when
 * the page asks twice before the person answers the system dialog (the shell does, on its first voice start), both
 * dialog results reach the second request, which is granted twice and the WebView throws — the app crashed the first
 * time anyone allowed the microphone. Here every pending request is answered exactly once, a permission the app
 * already holds is granted without a dialog, and a request the page withdrew is dropped.
 */
public class ExternalWindowChromeClient extends BridgeWebChromeClient {

    private final Bridge bridge;
    private final ActivityResultLauncher<String[]> mediaPermissionLauncher;
    private final List<PermissionRequest> pendingMedia = new ArrayList<>();
    private boolean mediaDialogOpen = false;

    public ExternalWindowChromeClient(Bridge bridge) {
        super(bridge);
        this.bridge = bridge;
        this.mediaPermissionLauncher = bridge.registerForActivityResult(
            new ActivityResultContracts.RequestMultiplePermissions(),
            this::onMediaPermissionResult
        );
    }

    @Override
    public void onPermissionRequest(final PermissionRequest request) {
        String[] needed = runtimePermissionsFor(request);
        if (needed.length == 0 || allGranted(needed)) {
            answer(request, true);
            return;
        }
        pendingMedia.add(request);
        if (mediaDialogOpen) return; // the dialog already on screen answers this one too
        mediaDialogOpen = true;
        mediaPermissionLauncher.launch(needed);
    }

    @Override
    public void onPermissionRequestCanceled(PermissionRequest request) {
        pendingMedia.remove(request);
    }

    private void onMediaPermissionResult(Map<String, Boolean> results) {
        mediaDialogOpen = false;
        List<PermissionRequest> waiting = new ArrayList<>(pendingMedia);
        pendingMedia.clear();
        for (PermissionRequest request : waiting) {
            // Judged per request against what the app now holds, not against the dialog's own map: a later request
            // may need a permission the dialog did not ask for.
            String[] needed = runtimePermissionsFor(request);
            if (allGranted(needed)) {
                answer(request, true);
            } else if (isSubset(needed, results.keySet())) {
                answer(request, false);
            } else {
                onPermissionRequest(request); // asks again for what this one needs
            }
        }
    }

    private static String[] runtimePermissionsFor(PermissionRequest request) {
        Set<String> out = new LinkedHashSet<>();
        List<String> resources = Arrays.asList(request.getResources());
        if (resources.contains(PermissionRequest.RESOURCE_VIDEO_CAPTURE)) out.add(Manifest.permission.CAMERA);
        if (resources.contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) {
            out.add(Manifest.permission.MODIFY_AUDIO_SETTINGS);
            out.add(Manifest.permission.RECORD_AUDIO);
        }
        return out.toArray(new String[0]);
    }

    private boolean allGranted(String[] permissions) {
        for (String p : permissions) {
            if (ContextCompat.checkSelfPermission(bridge.getContext(), p) != PackageManager.PERMISSION_GRANTED) return false;
        }
        return true;
    }

    private static boolean isSubset(String[] permissions, Set<String> asked) {
        for (String p : permissions) if (!asked.contains(p)) return false;
        return true;
    }

    private static void answer(PermissionRequest request, boolean grant) {
        try {
            if (grant) request.grant(request.getResources());
            else request.deny();
        } catch (IllegalStateException alreadyAnswered) {
            // The WebView already settled it (withdrawn or answered): nothing left to do, and never a crash.
            Logger.warn("[zaelar] media permission request already answered");
        }
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
