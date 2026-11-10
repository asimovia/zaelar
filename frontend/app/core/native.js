// native.js — is this page running inside the native companion app (V2-870)? Capacitor injects its bridge into every
// page the app's WebView loads; a browser has none. One helper, so every in-app difference reads the same fact.
export const inNativeApp = () => globalThis.Capacitor?.isNativePlatform?.() === true;
