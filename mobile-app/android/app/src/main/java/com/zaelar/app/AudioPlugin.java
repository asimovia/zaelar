package com.zaelar.app;

import android.content.Context;
import android.media.AudioDeviceCallback;
import android.media.AudioDeviceInfo;
import android.media.AudioManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * The voice's audio as the phone sees it ({@code window.ZaelarNative.audio}, through {@code www/in-app.js}) — the
 * Android twin of {@code AudioPlugin.swift}: where the sound goes, forcing the loudspeaker, and the events that stop the
 * conversation from outside (a call ringing or answered).
 *
 * It does NOT set a level: the WebView honours the page's own element volume (engine {@code services/volume.js}), and
 * {@link AudioManager}'s stream volumes are the person's system volume. Chromium puts the audio in communication mode
 * for the WebRTC call itself; this plugin reads that state and only picks the communication device when asked.
 * A call is seen through the audio mode (ringtone / in call), which needs no phone-state permission.
 */
@CapacitorPlugin(name = "ZaelarAudio")
public class AudioPlugin extends Plugin {

    private AudioManager am;
    private boolean speakerForced = false;
    private boolean inCall = false;
    private final Handler main = new Handler(Looper.getMainLooper());

    private final AudioDeviceCallback devices = new AudioDeviceCallback() {
        @Override public void onAudioDevicesAdded(AudioDeviceInfo[] added) { tellRoute("device_added"); }
        @Override public void onAudioDevicesRemoved(AudioDeviceInfo[] removed) { tellRoute("device_removed"); }
    };

    @Override
    public void load() {
        am = (AudioManager) getContext().getSystemService(Context.AUDIO_SERVICE);
        if (am == null) return;
        am.registerAudioDeviceCallback(devices, main);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            am.addOnModeChangedListener(getContext().getMainExecutor(), this::modeChanged);
            am.addOnCommunicationDeviceChangedListener(getContext().getMainExecutor(), d -> tellRoute("override"));
        }
    }

    @Override
    protected void handleOnDestroy() {
        if (am != null) am.unregisterAudioDeviceCallback(devices);
    }

    @PluginMethod
    public void available(PluginCall call) {
        JSObject r = new JSObject();
        r.put("available", am != null);
        r.put("level", false);
        r.put("route", true);
        r.put("speaker", true);
        r.put("interruptions", Build.VERSION.SDK_INT >= Build.VERSION_CODES.S);
        call.resolve(r);
    }

    @PluginMethod
    public void route(PluginCall call) {
        call.resolve(describe());
    }

    /** {@code {on: true}} sends the voice to the loudspeaker; {@code false} hands the choice back to the system. */
    @PluginMethod
    public void setSpeaker(PluginCall call) {
        boolean on = Boolean.TRUE.equals(call.getBoolean("on", true));
        if (am == null) { call.reject("no audio service", "speaker_refused"); return; }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (on) {
                AudioDeviceInfo speaker = null;
                for (AudioDeviceInfo d : am.getAvailableCommunicationDevices()) {
                    if (d.getType() == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER) { speaker = d; break; }
                }
                if (speaker == null || !am.setCommunicationDevice(speaker)) {
                    call.reject("speaker override refused", "speaker_refused"); return;
                }
            } else {
                am.clearCommunicationDevice();
            }
        } else {
            am.setSpeakerphoneOn(on);
        }
        speakerForced = on;
        call.resolve(describe());
    }

    private void modeChanged(int mode) {
        boolean call = mode == AudioManager.MODE_RINGTONE || mode == AudioManager.MODE_IN_CALL
                || (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && mode == AudioManager.MODE_CALL_SCREENING);
        if (call == inCall) return;
        inCall = call;
        JSObject e = new JSObject();
        e.put("phase", call ? "began" : "ended");
        e.put("t", System.currentTimeMillis());
        if (call) e.put("reason", "call"); else e.put("shouldResume", true);
        notifyListeners("audioInterruption", e);
    }

    private void tellRoute(String reason) {
        JSObject r = describe();
        r.put("reason", reason);
        notifyListeners("audioRoute", r);
    }

    /** The current output as one word the page can act on, plus what the system calls it. */
    private JSObject describe() {
        JSObject r = new JSObject();
        AudioDeviceInfo out = null;
        if (am != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) out = am.getCommunicationDevice();
        if (out == null && am != null) out = loudestOutput();
        r.put("output", out == null ? "none" : kind(out.getType()));
        r.put("name", out == null ? "" : String.valueOf(out.getProductName()));
        r.put("speakerForced", speakerForced);
        r.put("mode", am == null ? -1 : am.getMode());
        return r;
    }

    /** Without a communication device (before Android 12): a headset beats the speaker, as the system routes it. */
    private AudioDeviceInfo loudestOutput() {
        AudioDeviceInfo best = null;
        int rank = -1;
        for (AudioDeviceInfo d : am.getDevices(AudioManager.GET_DEVICES_OUTPUTS)) {
            String k = kind(d.getType());
            int r = k.equals("bluetooth") ? 4 : k.equals("headphones") || k.equals("usb") ? 3
                    : k.equals("speaker") && am.isSpeakerphoneOn() ? 5 : k.equals("earpiece") ? 2 : k.equals("speaker") ? 1 : 0;
            if (r > rank) { rank = r; best = d; }
        }
        return best;
    }

    static String kind(int type) {
        switch (type) {
            case AudioDeviceInfo.TYPE_BUILTIN_SPEAKER: return "speaker";
            case AudioDeviceInfo.TYPE_BUILTIN_EARPIECE: return "earpiece";
            case AudioDeviceInfo.TYPE_BLUETOOTH_A2DP:
            case AudioDeviceInfo.TYPE_BLUETOOTH_SCO:
            case AudioDeviceInfo.TYPE_BLE_HEADSET:
            case AudioDeviceInfo.TYPE_BLE_SPEAKER: return "bluetooth";
            case AudioDeviceInfo.TYPE_WIRED_HEADPHONES:
            case AudioDeviceInfo.TYPE_WIRED_HEADSET: return "headphones";
            case AudioDeviceInfo.TYPE_USB_DEVICE:
            case AudioDeviceInfo.TYPE_USB_HEADSET: return "usb";
            default: return "other";
        }
    }
}
