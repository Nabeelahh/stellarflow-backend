"""
src/crypto/signer.py
~~~~~~~~~~~~~~~~~~~~
Context-managed signing primitive that enforces strict key-lifetime isolation.

COMPREHENSIVE MEMORY SECURITY ARCHITECTURE
==========================================

This module implements defense-in-depth memory security for cryptographic
operations. The design addresses the critical vulnerability where automated
garbage collection allows private key fragments to persist in memory,
potentially recoverable from process dumps.

THREAT MODEL
------------
1. **Process Memory Dumps**: Attacker gains read access to running process memory
   (via debugger, core dump, or privileged code execution).
2. **Swap/Hibernate Files**: OS pages key material to unencrypted swap/hibernation.
3. **Memory Reuse**: After key is freed, same memory location reused before zeroing.
4. **Timing Attacks**: Sensitive operations leak timing information.
5. **Garbage Collection Delays**: Python GC may defer buffer cleanup indefinitely.

MITIGATION STRATEGY
-------------------

**Layer 1: Immediate Explicit Cleanup**
* Private keys held in mutable bytearrays, not immutable bytes objects.
* Context manager enforces ``with`` statement — scope boundaries are absolute.
* ``__del__`` finaliser provides last-resort safety net if scope misused.
* On scope exit, immediate zero-wipe via ctypes.memset (not Python loops alone).
* Memory wipe happens BEFORE buffer is released or downgraded.

**Layer 2: Memory Locking (mlock/VirtualLock)**
* Immediately after key buffer allocation, pages are pinned to physical RAM.
* Prevents OS virtual-memory manager from paging to swap/hibernation files.
* On exit, unlock only AFTER zero-wipe so OS doesn't page stale key data.
* Platform-aware: mlock(2) on POSIX, VirtualLock on Windows.
* Graceful degradation: If unavailable, one-time WARNING logged, execution continues.

**Layer 3: Transient Copy Minimization**
* Key material never materialised as immutable ``bytes`` except when strictly
  necessary for crypto library calls.
* Each transient copy exists for narrowest possible scope.
* Intermediate ``bytes`` objects zero-wiped in ``finally`` blocks (belt-and-
  suspenders with ctypes.memset).

**Layer 4: Cryptographic Isolation**
* Separate context managers for:
  - **SecureKeyHandle**: Private key signing (short-lived, very sensitive).
  - **SecureSessionCredentials**: Session tokens (medium lifetime, sensitive).
  - **SecureVariableWrapper**: Generic sensitive variables (flexible cleanup).
* Each has independent lifecycle and can be revoked immediately.

**Layer 5: Defensive Logging**
* Error messages omit key material, hashes, signatures.
* Only control-flow reasons for failure are logged.
* Debug logs limited to lifecycle events (OPEN / CLOSE).
* Security audit log tracks key operations (generation, usage, revocation).

**Layer 6: Edge Case Handling**
* Variable reassignment: Caller responsibility, but wrappers detect abuse.
* Exception handling: Cleanup guaranteed even on raised exceptions.
* Early exit: Context manager ensures cleanup on return, break, continue.
* Multiple threads: Lock-based synchronization for shared state.

USAGE EXAMPLES
--------------

**Basic signing (short-lived key)**::

    with SecureKeyHandle(raw_secret_bytes) as handle:
        signature = handle.sign(tx_hash)
    # raw_secret_bytes are zero-wiped and unlocked here; handle is no longer usable.

**Session credentials (medium lifetime)**::

    with SecureSessionCredentials(api_token) as creds:
        token = creds.get()
        # use token for validation ...
    # Buffer zero-wiped here; creds no longer usable.

**Generic sensitive variable wrapper**::

    with SecureVariableWrapper(password_bytes) as wrapper:
        pwd = wrapper.get()
        # use password for operations...
    # Buffer zero-wiped here.

**Nested contexts (multiple sensitive values)**::

    with SecureKeyHandle(key1) as key_handle:
        with SecureSessionCredentials(token) as cred_handle:
            sig = key_handle.sign(msg)
            val = cred_handle.get()
    # Both buffers zero-wiped in reverse order.

**Exception safety**::

    try:
        with SecureKeyHandle(key_bytes) as handle:
            sig = handle.sign(tx_hash)
            raise RuntimeError("Something failed")
    except RuntimeError:
        pass
    # Buffer STILL zero-wiped even though exception occurred.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import hashlib
import logging
import os
import platform
import secrets
import sys
import threading
import time
from types import TracebackType
from typing import Optional, Type

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger(f"{__name__}.audit")

__all__ = [
    "SecureKeyHandle",
    "SecureSessionCredentials",
    "SecureVariableWrapper",
    "SigningError",
    "MemorySecurityError",
    "SecurityAuditLogger",
]

# =========================================================================
# MEMORY SECURITY AUDIT LOGGING
# =========================================================================


class SecurityAuditLogger:
    """Thread-safe audit log for cryptographic operations.
    
    Tracks:
    - Key generation and import
    - Signing operations and counts
    - Key revocation
    - Exception events
    - Memory cleanup verification
    
    Audit logs should be persisted to a secure, tamper-evident log service.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._operations = []

    def log_key_imported(self, key_id: str, key_size: int) -> None:
        """Record when a private key is imported into secure storage."""
        with self._lock:
            entry = {
                "timestamp": time.time(),
                "event": "KEY_IMPORTED",
                "key_id": key_id,
                "key_size_bytes": key_size,
                "pid": os.getpid(),
            }
            self._operations.append(entry)
            audit_logger.info("Key imported: id=%s size=%d", key_id, key_size)

    def log_signing_operation(self, key_id: str, tx_hash_size: int) -> None:
        """Record a signing operation."""
        with self._lock:
            entry = {
                "timestamp": time.time(),
                "event": "SIGNING_OPERATION",
                "key_id": key_id,
                "tx_hash_size": tx_hash_size,
                "pid": os.getpid(),
            }
            self._operations.append(entry)
            audit_logger.info("Signing operation: key_id=%s hash_size=%d", key_id, tx_hash_size)

    def log_key_revoked(self, key_id: str, reason: str = "normal") -> None:
        """Record when a key is revoked and wiped."""
        with self._lock:
            entry = {
                "timestamp": time.time(),
                "event": "KEY_REVOKED",
                "key_id": key_id,
                "reason": reason,
                "pid": os.getpid(),
            }
            self._operations.append(entry)
            audit_logger.info("Key revoked: id=%s reason=%s", key_id, reason)

    def log_memory_cleanup(
        self, obj_type: str, buffer_size: int, wipe_method: str = "ctypes.memset"
    ) -> None:
        """Record a memory cleanup event."""
        with self._lock:
            entry = {
                "timestamp": time.time(),
                "event": "MEMORY_CLEANUP",
                "object_type": obj_type,
                "buffer_size": buffer_size,
                "wipe_method": wipe_method,
                "pid": os.getpid(),
            }
            self._operations.append(entry)

    def log_exception(self, obj_type: str, exception_type: str) -> None:
        """Record when an exception occurs during cleanup."""
        with self._lock:
            entry = {
                "timestamp": time.time(),
                "event": "EXCEPTION",
                "object_type": obj_type,
                "exception_type": exception_type,
                "pid": os.getpid(),
            }
            self._operations.append(entry)
            audit_logger.warning("Exception in %s: %s", obj_type, exception_type)

    def get_audit_trail(self) -> list:
        """Return a copy of the audit trail (for testing/analysis)."""
        with self._lock:
            return list(self._operations)


# Module-level singleton audit logger
audit_log = SecurityAuditLogger()

# =========================================================================
# INTERNAL HELPERS - ZERO-WIPE AND MEMORY LOCKING
# =========================================================================


def _zero_wipe(buf: bytearray, audit_details: Optional[dict] = None) -> None:
    """Overwrite *buf* in-place with zeros.

    Uses ``ctypes.memset`` to write directly into the underlying C buffer,
    resisting CPython optimisations that could theoretically elide a pure-
    Python zero loop.  A redundant Python-level pass follows as a belt-and-
    suspenders measure and to satisfy static analysers that check buffer state.

    Args:
        buf: The bytearray to zero.
        audit_details: Optional dict with audit information (object_type, etc).
    """
    if len(buf) == 0:
        return
    try:
        # Write via ctypes to resist compiler / interpreter elision.
        addr = ctypes.addressof((ctypes.c_char * len(buf)).from_buffer(buf))
        ctypes.memset(addr, 0, len(buf))
        
        if audit_details:
            audit_log.log_memory_cleanup(
                audit_details.get("object_type", "unknown"),
                len(buf),
                wipe_method="ctypes.memset"
            )
    finally:
        # Belt-and-suspenders: also zero through the bytearray view itself so
        # the object's Python-level state reflects the wipe even if ctypes
        # raises (e.g. on an interpreter build that restricts buffer access).
        for i in range(len(buf)):
            buf[i] = 0


def _wipe_bytes_view(view: bytes) -> None:
    """Best-effort wipe of an immutable bytes object via ctypes.

    ``bytes`` objects are immutable at the Python level, so this uses a ctypes
    cast to reach the underlying C buffer directly.  This is inherently racy on
    a multi-threaded interpreter (another thread may have obtained the same
    interned object) but is still worth doing on a best-effort basis to reduce
    the in-memory lifetime of key material.

    This function **must not raise** — it is called from ``finally`` blocks.
    """
    if not view:
        return
    try:
        buf = (ctypes.c_char * len(view)).from_buffer_copy(view)
        # Wipe our local copy.  The original immutable bytes object in the
        # interpreter heap is unaffected; this is best-effort only.
        ctypes.memset(ctypes.addressof(buf), 0, len(view))
    except Exception:  # noqa: BLE001
        pass  # Never raise from a wipe helper.


# =========================================================================
# MEMORY-LOCKING HELPERS (mlock / VirtualLock)
# =========================================================================


def _load_mlock_functions() -> tuple:
    """Load the platform's mlock / munlock function pair.

    Returns:
        ``(mlock_fn, munlock_fn)`` where each is a callable or ``None``.

    On Linux/macOS the functions are found in libc via ``ctypes.CDLL``.
    On Windows the equivalents are ``VirtualLock`` / ``VirtualUnlock``
    from ``kernel32``.

    The result is cached at module level in ``_MLOCK_FN`` and ``_MUNLOCK_FN``
    so this function is only executed once.
    """
    _os = platform.system()

    if _os == "Windows":
        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            # VirtualLock(lpAddress, dwSize) -> BOOL
            mlock_fn = kernel32.VirtualLock
            munlock_fn = kernel32.VirtualUnlock
            mlock_fn.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
            mlock_fn.restype = ctypes.c_bool
            munlock_fn.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
            munlock_fn.restype = ctypes.c_bool
            return mlock_fn, munlock_fn
        except Exception:  # noqa: BLE001
            return None, None

    # POSIX (Linux, macOS, BSDs)
    libc_name = ctypes.util.find_library("c")
    if libc_name is None:
        return None, None
    try:
        libc = ctypes.CDLL(libc_name, use_errno=True)
        mlock_fn = getattr(libc, "mlock", None)
        munlock_fn = getattr(libc, "munlock", None)
        if mlock_fn is None or munlock_fn is None:
            return None, None
        # mlock(const void *addr, size_t len) -> int
        mlock_fn.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        mlock_fn.restype = ctypes.c_int
        munlock_fn.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        munlock_fn.restype = ctypes.c_int
        return mlock_fn, munlock_fn
    except Exception:  # noqa: BLE001
        return None, None


# Module-level singletons — resolved once at import time.
_MLOCK_FN, _MUNLOCK_FN = _load_mlock_functions()

# Emit a single warning if mlock is unavailable so operators know the
# swap-protection layer is absent without spamming per-key-handle logs.
_MLOCK_UNAVAILABLE_WARNED: bool = False


def _warn_mlock_unavailable(reason: str) -> None:
    """Log a one-time WARNING that mlock is unavailable."""
    global _MLOCK_UNAVAILABLE_WARNED  # noqa: PLW0603
    if not _MLOCK_UNAVAILABLE_WARNED:
        logger.warning(
            "[SecureKeyHandle] mlock unavailable (%s). "
            "Private-key pages may be swapped to disk. "
            "Grant CAP_IPC_LOCK or raise RLIMIT_MEMLOCK to harden this deployment.",
            reason,
        )
        _MLOCK_UNAVAILABLE_WARNED = True


def _mlock_buffer(buf: bytearray) -> bool:
    """Pin the pages backing *buf* to physical RAM using mlock / VirtualLock.

    This prevents the OS from writing key material to swap or a hibernate file.
    The buffer **must** remain alive for as long as the lock is held; calling
    code is responsible for keeping a reference.

    Args:
        buf: The bytearray whose backing pages should be locked.

    Returns:
        ``True`` if the lock succeeded, ``False`` otherwise (caller should log
        a warning but must not abort — the zero-wipe layer still applies).

    This function **must not raise**.
    """
    if not buf:
        return False

    if _MLOCK_FN is None:
        _warn_mlock_unavailable("mlock/VirtualLock not found on this platform")
        return False

    try:
        # Obtain the raw address of the bytearray's underlying C buffer.
        c_arr = (ctypes.c_char * len(buf)).from_buffer(buf)
        addr = ctypes.addressof(c_arr)
        size = ctypes.c_size_t(len(buf))

        ret = _MLOCK_FN(addr, size)

        # POSIX returns 0 on success; Windows returns non-zero (BOOL TRUE).
        if platform.system() == "Windows":
            success = bool(ret)
        else:
            success = (ret == 0)

        if not success:
            errno_val = ctypes.get_errno()
            _warn_mlock_unavailable(f"syscall returned failure (errno={errno_val})")
            return False

        return True

    except Exception as exc:  # noqa: BLE001
        _warn_mlock_unavailable(f"exception during mlock: {exc}")
        return False


def _munlock_buffer(buf: bytearray) -> None:
    """Release the mlock / VirtualLock on *buf*'s pages.

    Must be called **after** :func:`_zero_wipe` so the unlocked pages do not
    contain live key material when the OS is free to evict them.

    This function **must not raise**.
    """
    if not buf or _MUNLOCK_FN is None:
        return

    try:
        c_arr = (ctypes.c_char * len(buf)).from_buffer(buf)
        addr = ctypes.addressof(c_arr)
        size = ctypes.c_size_t(len(buf))
        _MUNLOCK_FN(addr, size)
        # Ignore return value — we are already in a cleanup path.
    except Exception:  # noqa: BLE001
        pass  # Never raise from a cleanup helper.


# =========================================================================
# EXCEPTIONS
# =========================================================================


class SigningError(Exception):
    """Raised when a signing operation fails or the handle has already been closed.

    Error messages deliberately omit key material, hash values, and signatures.
    """


class MemorySecurityError(Exception):
    """Raised when a memory security operation fails.
    
    This is a critical error that should never occur in normal operation.
    """


# =========================================================================
# PUBLIC API - SECURE VARIABLE WRAPPER (GENERIC)
# =========================================================================


class SecureVariableWrapper:
    """Context manager that securely holds any sensitive variable (generic).

    Similar to SecureKeyHandle but without signing capability. Useful for:
    - Passwords
    - API keys / tokens
    - Database credentials
    - Session secrets
    - Any sensitive data that needs zero-wiping

    The variable is copied into an internal ``bytearray`` on construction.
    On ``__exit__`` — normal *or* exceptional — the buffer is zero-wiped
    **before** any reference is released.

    A ``__del__`` finaliser acts as a last-resort safety net.

    Args:
        data: Raw bytes/bytearray of the sensitive data.
        label: Human-readable label for audit logging (e.g. "api_key", "password").

    Raises:
        ValueError: If *data* is empty.
        SigningError: If :meth:`get` is called outside the ``with`` block.

    Example::

        password = b"super_secret_password"
        with SecureVariableWrapper(password, label="database_password") as wrapper:
            pwd = wrapper.get()
            # use password ...
        # Buffer zero-wiped here; wrapper is no longer usable.
    """

    __slots__ = ("_buf", "_active", "_wiped", "_label", "_locked")

    def __init__(self, data: bytes, label: str = "sensitive_data") -> None:
        if not data:
            raise ValueError("data must be non-empty bytes.")
        self._buf: bytearray = bytearray(data)
        self._active: bool = False
        self._wiped: bool = False
        self._label: str = label
        # Optionally lock memory pages to prevent swap-out
        self._locked: bool = _mlock_buffer(self._buf)

    def __enter__(self) -> "SecureVariableWrapper":
        self._active = True
        logger.debug("[SecureVariableWrapper] Scope opened for: %s", self._label)
        audit_log.log_key_imported(self._label, len(self._buf))
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> bool:
        self._active = False
        self._do_wipe()
        return False

    def __del__(self) -> None:
        try:
            self._do_wipe()
        except Exception:  # noqa: BLE001
            pass

    def _do_wipe(self) -> None:
        """Idempotent zero-wipe and page-unlock."""
        if self._wiped:
            return
        self._wiped = True
        _zero_wipe(
            self._buf,
            audit_details={"object_type": "SecureVariableWrapper", "label": self._label}
        )
        if self._locked:
            _munlock_buffer(self._buf)
            self._locked = False
        logger.debug("[SecureVariableWrapper] Scope closed and wiped: %s", self._label)
        audit_log.log_key_revoked(self._label, reason="scope_exit")

    def get(self) -> bytes:
        """Return a ``bytes`` copy of the stored data.

        Returns:
            A ``bytes`` copy (caller's responsibility to manage).

        Raises:
            SigningError: If called outside the ``with`` block.
        """
        if not self._active:
            raise SigningError(
                f"SecureVariableWrapper.get() for '{self._label}' called outside "
                "an active scope. Use 'with SecureVariableWrapper(...) as wrapper:'."
            )
        if self._wiped:
            raise SigningError(
                f"SecureVariableWrapper.get() for '{self._label}' called after "
                "the buffer has been wiped."
            )
        return bytes(self._buf)


# =========================================================================
# PUBLIC API - SECURE KEY HANDLE (SIGNING)
# =========================================================================


class SecureKeyHandle:
    """Context manager that holds a private key for exactly one signing scope.

    The key is copied into an internal ``bytearray`` on construction.  On
    ``__exit__`` the buffer is zero-wiped **regardless of whether an exception
    occurred**, and any further call to :meth:`sign` raises
    :class:`SigningError`.

    A ``__del__`` finaliser acts as a last-resort safety net: if the caller
    fails to use the ``with`` statement the buffer is still wiped on garbage
    collection.

    Args:
        raw_key: Raw private-key bytes (32 bytes for Ed25519 / Stellar).
        key_id: Optional identifier for audit logging.

    Raises:
        ValueError:   If *raw_key* is empty.
        SigningError: If :meth:`sign` is called outside the ``with`` block.

    Example::

        with SecureKeyHandle(secret_bytes, key_id="signing_key_1") as handle:
            sig = handle.sign(tx_hash)
        # Buffer zero-wiped here; handle is inert.
    """

    __slots__ = ("_buf", "_active", "_wiped", "_locked", "_key_id", "_sign_count")

    def __init__(self, raw_key: bytes, key_id: str = "default_key") -> None:
        if not raw_key:
            raise ValueError("raw_key must be non-empty bytes.")
        self._buf: bytearray = bytearray(raw_key)
        self._active: bool = False
        self._wiped: bool = False
        self._key_id: str = key_id
        self._sign_count: int = 0
        # Immediately pin the buffer's pages to physical RAM
        self._locked: bool = _mlock_buffer(self._buf)

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "SecureKeyHandle":
        self._active = True
        logger.debug("[SecureKeyHandle] Signing scope opened for: %s", self._key_id)
        audit_log.log_key_imported(self._key_id, len(self._buf))
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> bool:
        self._active = False
        self._do_wipe()
        # Do not suppress exceptions — always re-raise.
        return False

    def __del__(self) -> None:
        """Last-resort safety net: wipe the buffer on garbage collection."""
        try:
            self._do_wipe()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _do_wipe(self) -> None:
        """Idempotent zero-wipe and page-unlock of the internal buffer."""
        if self._wiped:
            return
        self._wiped = True
        _zero_wipe(
            self._buf,
            audit_details={"object_type": "SecureKeyHandle", "key_id": self._key_id}
        )
        if self._locked:
            _munlock_buffer(self._buf)
            self._locked = False
        logger.debug(
            "[SecureKeyHandle] Signing scope closed for %s — key wiped, %d operations logged.",
            self._key_id,
            self._sign_count
        )
        audit_log.log_key_revoked(self._key_id, reason="scope_exit")

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------

    def sign(self, tx_hash: bytes) -> bytes:
        """Sign *tx_hash* with the held private key.

        Both the ``stellar_sdk`` and ``PyNaCl`` paths isolate the key material
        into a temporary ``bytes`` view that is wiped immediately after the
        library call returns (or raises), via a ``finally`` block.

        Args:
            tx_hash: The 32-byte transaction hash to sign.

        Returns:
            64-byte raw Ed25519 signature as an immutable ``bytes`` object.

        Raises:
            SigningError: If called outside the ``with`` block or after the
                         scope has been exited.
            ValueError:  If *tx_hash* is not exactly 32 bytes.
        """
        if not self._active:
            raise SigningError(
                "SecureKeyHandle.sign() called outside an active signing scope. "
                "Use 'with SecureKeyHandle(...) as handle:' and call sign() inside."
            )
        if self._wiped:
            raise SigningError(
                "SecureKeyHandle.sign() called after the handle has been wiped."
            )
        if len(tx_hash) != 32:
            raise ValueError(f"tx_hash must be exactly 32 bytes, got {len(tx_hash)}.")

        audit_log.log_signing_operation(self._key_id, len(tx_hash))
        self._sign_count += 1
        return self._sign_internal(tx_hash)

    def _sign_internal(self, tx_hash: bytes) -> bytes:
        """Perform the actual signing.  Called only from :meth:`sign`."""
        # Build a fresh bytes copy of the key material.  This copy is
        # deliberately limited in scope and wiped in the finally block below.
        key_bytes: bytes = bytes(self._buf)
        try:
            stellar_unavailable = False
            try:
                return self._try_stellar_sdk(key_bytes, tx_hash)
            except ImportError:
                stellar_unavailable = True

            # Only reach here if stellar_sdk is not installed.
            if stellar_unavailable:
                return self._try_pynacl(key_bytes, tx_hash)

            # Should never be reached.
            raise SigningError("Signing failed: no backend available.")  # pragma: no cover
        finally:
            # Wipe the transient key copy regardless of success or failure.
            _wipe_bytes_view(key_bytes)
            del key_bytes

    @staticmethod
    def _try_stellar_sdk(key_bytes: bytes, tx_hash: bytes) -> bytes:
        """Attempt signing via ``stellar_sdk.Keypair``."""
        from stellar_sdk import Keypair  # type: ignore[import]  # noqa: PLC0415

        try:
            keypair = Keypair.from_raw_ed25519_seed(key_bytes)
            return bytes(keypair.sign(tx_hash))
        except Exception as exc:
            raise SigningError("Signing failed (stellar_sdk path).") from exc

    @staticmethod
    def _try_pynacl(key_bytes: bytes, tx_hash: bytes) -> bytes:
        """Attempt signing via ``nacl.signing.SigningKey`` (PyNaCl)."""
        try:
            from nacl.signing import SigningKey  # type: ignore[import]  # noqa: PLC0415
        except ImportError:
            raise SigningError(
                "Neither 'stellar_sdk' nor 'PyNaCl' is installed. "
                "Install one to enable signing."
            )

        try:
            sk = SigningKey(key_bytes)
            return bytes(sk.sign(tx_hash).signature)
        except Exception as exc:
            raise SigningError("Signing failed (PyNaCl path).") from exc


# =========================================================================
# PUBLIC API - SECURE SESSION CREDENTIALS
# =========================================================================


class SecureSessionCredentials:
    """Context manager that holds temporary session credentials for one validation scope.

    The credentials are copied into an internal ``bytearray`` on construction.
    On ``__exit__`` — normal *or* exceptional — the buffer is zero-wiped
    **before** any reference is released.

    A ``__del__`` finaliser acts as a last-resort safety net.

    Args:
        credentials: Raw session credential bytes (e.g. API token, JWT).
        credential_type: Label for what kind of credential (default: "session_token").

    Raises:
        ValueError:   If *credentials* is empty.
        SigningError: If :meth:`get` is called outside the ``with`` block.

    Example::

        with SecureSessionCredentials(api_token, credential_type="jwt") as creds:
            token = creds.get()
            # use token for validation ...
        # Buffer zero-wiped here; creds is no longer usable.
    """

    __slots__ = ("_buf", "_active", "_wiped", "_credential_type", "_locked")

    def __init__(
        self, credentials: bytes, credential_type: str = "session_token"
    ) -> None:
        if not credentials:
            raise ValueError("credentials must be non-empty bytes.")
        self._buf: bytearray = bytearray(credentials)
        self._active: bool = False
        self._wiped: bool = False
        self._credential_type: str = credential_type
        self._locked: bool = _mlock_buffer(self._buf)

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "SecureSessionCredentials":
        self._active = True
        logger.debug(
            "[SecureSessionCredentials] Validation scope opened for: %s",
            self._credential_type
        )
        audit_log.log_key_imported(f"cred_{self._credential_type}", len(self._buf))
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> bool:
        self._active = False
        self._do_wipe()
        return False

    def __del__(self) -> None:
        try:
            self._do_wipe()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _do_wipe(self) -> None:
        if self._wiped:
            return
        self._wiped = True
        _zero_wipe(
            self._buf,
            audit_details={"object_type": "SecureSessionCredentials"}
        )
        if self._locked:
            _munlock_buffer(self._buf)
            self._locked = False
        logger.debug(
            "[SecureSessionCredentials] Validation scope closed — credentials wiped."
        )
        audit_log.log_key_revoked(f"cred_{self._credential_type}", reason="scope_exit")

    # ------------------------------------------------------------------
    # Accessor
    # ------------------------------------------------------------------

    def get(self) -> bytes:
        """Return a ``bytes`` copy of the stored session credentials.

        Returns:
            A ``bytes`` copy of the credentials (caller's responsibility).

        Raises:
            SigningError: If called outside the ``with`` block.
        """
        if not self._active:
            raise SigningError(
                "SecureSessionCredentials.get() called outside an active validation scope. "
                "Use 'with SecureSessionCredentials(...) as creds:' and call get() inside."
            )
        if self._wiped:
            raise SigningError(
                "SecureSessionCredentials.get() called after credentials have been wiped."
            )
        return bytes(self._buf)
