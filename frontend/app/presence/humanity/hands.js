// hands.js — a raised hand, a wave, a thumbs-up: DECLARED, not built. MediaPipe's hand models (Hand Landmarker 7.8 MB,
// Gesture Recognizer 8.4 MB) are each over the public repository's file limit and would add a second network per frame
// on top of the face's. The temperament already answers a `hand` event (temperament.js ANSWERS.hand); a future
// detector only has to emit `{type: "hand", t}` through perceive's caller. Until then nothing here runs or loads.

/** False until a hand detector ships: the camera never asks for one. */
export const HANDS_AVAILABLE = false;
export function createHands() { return null; }
