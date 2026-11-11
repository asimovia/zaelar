"""The voice job's thread asks the OS for interactive priority (V2-887).

The voice job runs as a thread of the engine's process (`JobExecutorType.THREAD`), so `nice` cannot single it out: the
workers are niced (`nucleo/workers/envelope.preexec`), the server's own background threads are not. On macOS a thread
can declare its own QoS class; `USER_INTERACTIVE` is the class the scheduler keeps on the performance cores and serves
first under CPU contention. It does not help against paging (memory is the host's), which is why the ears also never
wait in a pool (`voice/engine/speech/vad/silero.py`). Elsewhere this is a no-op: Linux has no per-thread class an
unprivileged process can raise, and a hosted deployment gives the voice a dedicated CPU instead.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import sys

from loguru import logger

QOS_CLASS_USER_INTERACTIVE = 0x21


def _libc():
    return ctypes.CDLL(ctypes.util.find_library("c") or "libc.dylib", use_errno=True)


def interactive() -> bool:
    """Raise the CALLING thread to USER_INTERACTIVE. True when the OS accepted it; never raises."""
    if sys.platform != "darwin":
        return False
    try:
        fn = _libc().pthread_set_qos_class_self_np
        fn.argtypes, fn.restype = [ctypes.c_uint, ctypes.c_int], ctypes.c_int
        return fn(QOS_CLASS_USER_INTERACTIVE, 0) == 0
    except Exception as e:  # noqa: BLE001 — a priority hint never stops the voice
        logger.debug(f"thread_qos: interactive class not set: {e!r}")
        return False


def current() -> int | None:
    """The calling thread's QoS class (macOS), for tests and diagnostics."""
    if sys.platform != "darwin":
        return None
    try:
        lib = _libc()
        lib.pthread_self.restype = ctypes.c_void_p          # a pointer: the default int restype would truncate it
        lib.pthread_get_qos_class_np.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_int)]
        qos, rel = ctypes.c_uint(0), ctypes.c_int(0)
        if lib.pthread_get_qos_class_np(lib.pthread_self(), ctypes.byref(qos), ctypes.byref(rel)) != 0:
            return None
        return qos.value
    except Exception as e:  # noqa: BLE001
        logger.debug(f"thread_qos: class unreadable: {e!r}")
        return None
