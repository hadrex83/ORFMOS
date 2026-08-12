# ======================================================================================
# ORFMOS BIOS DEVELOPMENT v0.1
# CELL 1 — RUNTIME + PINNED GITHUB BOOT SURFACE + POWER-GATED KERNEL START
# ======================================================================================

import sys
import subprocess
import importlib.util
import hashlib
import base64
import requests
import io
import json
import html as html_lib
import time
import traceback
import threading
import re
import os
import math
import functools
import ssl
import secrets
import shlex
import tempfile
from datetime import datetime, timezone, timedelta

if importlib.util.find_spec("gradio") is None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "gradio"])

import gradio as gr

from google.colab import auth
import google.auth
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

# Accepted boot presentation currently published to GitHub.
# Pin the commit + SHA256 so mutable main is not silently execution/presentation authority.
BOOT_OWNER = "hadrex83"
BOOT_REPO = "ORFMOS"
BOOT_REF = "a6ef30a42771bee3630cd4c1890a2dfc38cdd9e0"
BOOT_PATH = "index.html"
EXPECTED_BOOT_SHA256 = "d44f3f45878d4951da06d90f95af44e2de4f14c36f434561f275624b08c217b2"


# Existing Kernel -> presentation telemetry contract.
# The Kernel already writes this stable Drive object; the BIOS notebook is only a consumer.
BOOT_STATE_FILE_ID = "1zmlpThp1a6g8hHcHpbFWdB2mVjWqtxLL"
BOOT_STATE_SCHEMA = "ORF_BOOT_STATE_V0_1"
BOOT_POLL_SECONDS = 1.0
BOOT_MIN_DISPLAY_SECONDS = 0.0
BOOT_READY_ELIGIBLE_SECONDS = 3.0  # Guaranteed post-POWER BIOS-request window before READY handoff.
BOOT_READY_STABLE_FALLBACK_SECONDS = 10.0
BOOT_READY_CONFIRMATIONS_REQUIRED = 3

# Development-only Cloud ORFMOS kernel execution capability.
# The loader no longer invokes this automatically: the boot-screen POWER event
# requests the start through request_dev_kernel_power_start().
DEV_AUTOBOOT_KERNEL = True
DEV_AUTOBOOT_DELAY_SECONDS = 2.0
DEV_KERNEL_MONITOR_SECONDS = 1.0
ORF_KERNEL_REBOOT_REQUEST_SCHEMA = "ORF_KERNEL_REBOOT_REQUEST_V0_1"
DEV_KERNEL_NOTEBOOK_FILE_ID = "12Bata4yo_V9nDt5lc5X5d-hBnU3P6Sh6"
DEV_KERNEL_CODE_CELL_SHA256 = "fdf315d92c71f204dd9249d53292d003c451e2e36f85df7f92e83f0101c67c7f"
DEV_KERNEL_BOOTSTRAP_FILE_ID = "1--rLiKr3Xri79h3WZffcc0ZwnjaEFncx"
DEV_KERNEL_BOOTSTRAP_SHA256 = "31754259bb263a9b673cc3a85d36eb7f472da04a8bf58c424212e18ecbf60503"

# Capturable Kernel-loader execution residue.  The same record is emitted to
# Cell 4 stdout and retained in shared runtime globals so presentation logic can
# correlate what the human saw with what the heartbeat later observes.
ORF_KERNEL_LOADER_CAPTURE_SCHEMA = "ORF_KERNEL_LOADER_CAPTURE_V0_1"
if "ORF_KERNEL_LOADER_CAPTURE" not in globals():
    ORF_KERNEL_LOADER_CAPTURE = []

def _emit_kernel_loader_capture(event, **fields):
    record = {
        "schema": ORF_KERNEL_LOADER_CAPTURE_SCHEMA,
        "event": str(event),
        "utc": datetime.now(timezone.utc).isoformat(),
        "monotonic_ns": time.monotonic_ns(),
    }
    record.update(fields)
    ORF_KERNEL_LOADER_CAPTURE.append(record)
    if len(ORF_KERNEL_LOADER_CAPTURE) > 64:
        del ORF_KERNEL_LOADER_CAPTURE[:-64]
    print(
        "ORF_KERNEL_LOADER_CAPTURE " + json.dumps(
            record, separators=(",", ":"), sort_keys=True, default=str
        ),
        flush=True,
    )
    return record

# BIOS-owned dual source selection.
# Kernel distribution and ORFMOS root distribution are independent choices.
# The mutable Kernel recovery selector ORF_RUNTIME_TARGET.json remains a separate
# authority and is intentionally NOT merged into this contract.
ROOT_SELECTION_SCHEMA = "ORF_BIOS_SOURCE_SELECTION_STATE_V0_1"
BIOS_SOURCE_SELECTION_SCHEMA = "ORF_BIOS_SOURCE_SELECTION_V0_1"
RUNTIME_TARGET_FILE_ID = "1vP_WFUXDaFtcFcwq6GidpGf-WwsqmlI_"  # stable BIOS selection authority object
RUNTIME_TARGET_SCHEMA = BIOS_SOURCE_SELECTION_SCHEMA
ROOT_RESOLUTION_MODE = "BIOS_DUAL_SOURCE_SELECTION"

SOURCE_PROVIDER_DRIVE = "DRIVE"
SOURCE_PROVIDER_GITHUB = "GITHUB"
SOURCE_PROVIDERS = (SOURCE_PROVIDER_DRIVE, SOURCE_PROVIDER_GITHUB)
BIOS_DEFAULT_SOURCE_PROVIDER = SOURCE_PROVIDER_GITHUB

# Drive Kernel = current known-good sealed Drive notebook/runtime tree.
DEFAULT_RUNTIME_ROOT_FOLDER_ID = "1_Co_oQ1Gc6uJm4C6vckJh7r370G7CVcH"
KERNEL_NOTEBOOK_NAME = "ORF Kernel.ipynb"
KERNEL_LOADER_FOLDER_NAME = "loader"
REQUIRED_RUNTIME_ROOT_CHILDREN = (
    "loader",
    "kernel",
    "presentation",
    "dispatcher",
    "call_library",
    "callable_manifests",
    "governance_callables",
)

# GitHub Kernel = provider-neutral portable Kernel package.
KERNEL_GITHUB_OWNER = "hadrex83"
KERNEL_GITHUB_REPO = "ORFMOS"
KERNEL_GITHUB_REF = "7ffc762de4aef2b8cf48e22b072af478cc62c0fd"
KERNEL_GITHUB_PREFIX = "kernel/v0.2.1"
KERNEL_GITHUB_MANIFEST_SHA256 = "33d8e2aec60835331588b48aa957a0e04083424e8884f629e66d3e7e05f19a44"
KERNEL_GITHUB_ENTRYPOINT_CELL_SHA256 = "80c4a62c84eff8eaf08e5acfdda99a68765c3cccb847a07cbb70d1674a9d75d3"
KERNEL_LOCAL_STAGE_ROOT = "/content/.orf_kernel_source"
KERNEL_LOCAL_CANDIDATE_ROOT = "/content/.orf_kernel_candidate"

# Maintenance authority v0.1. The private KORF keystore never enters this module.
# This public certificate was extracted from an already-signed KORF artifact and
# is pinned by certificate + public-key SHA256 digests.
ORF_MAINTENANCE_SESSION_SCHEMA = "ORF_MAINTENANCE_SESSION_V0_1"
ORF_MAINTENANCE_CHALLENGE_SCHEMA = "ORF_MAINTENANCE_CHALLENGE_V0_1"
ORF_MAINTENANCE_KERNEL_CANDIDATE_SCHEMA = "ORF_MAINTENANCE_KERNEL_CANDIDATE_V0_1"
ORF_MAINTENANCE_SESSION_SECONDS = 15 * 60
ORF_MAINTENANCE_CHALLENGE_SECONDS = 2 * 60
ORF_MAINTENANCE_SHUTDOWN_ARM_SECONDS = 15

# Ordered shutdown / quiesce contract. Shutdown is a system transition, not an
# immediate transport drop: close the mutation gate, let accepted writes drain,
# notify all BIOS clients from one server-owned deadline, then release Colab.
ORF_SYSTEM_QUIESCE_SCHEMA = "ORF_SYSTEM_QUIESCE_V0_1"
ORF_MAINTENANCE_SHUTDOWN_COUNTDOWN_SECONDS = 10.0
ORF_MAINTENANCE_SHUTDOWN_DRAIN_GRACE_SECONDS = 5.0
ORF_MAINTENANCE_SHUTDOWN_CLIENT_HANDOFF_SECONDS = 3.0
_ORF_SYSTEM_QUIESCE_PENDING_STATES = {"QUIESCING", "DRAINING", "CLIENT_BOOT", "RUNTIME_RELEASE"}

_ORF_SYSTEM_WRITE_LOCK = globals().get("_ORF_SYSTEM_WRITE_LOCK") or threading.RLock()
_ORF_SYSTEM_WRITE_TLS = globals().get("_ORF_SYSTEM_WRITE_TLS") or threading.local()
globals()["_ORF_SYSTEM_WRITE_LOCK"] = _ORF_SYSTEM_WRITE_LOCK
globals()["_ORF_SYSTEM_WRITE_TLS"] = _ORF_SYSTEM_WRITE_TLS
if "__ORF_SYSTEM_ACTIVE_WRITES__" not in globals():
    globals()["__ORF_SYSTEM_ACTIVE_WRITES__"] = 0

_existing_quiesce = dict(globals().get("__ORF_SYSTEM_QUIESCE__") or {})
if str(_existing_quiesce.get("state") or "").upper() not in _ORF_SYSTEM_QUIESCE_PENDING_STATES:
    globals()["__ORF_SYSTEM_QUIESCE__"] = {
        "schema": ORF_SYSTEM_QUIESCE_SCHEMA,
        "state": "RUNNING",
        "writes_enabled": True,
        "requested_utc": None,
        "deadline_utc": None,
        "deadline_monotonic": None,
        "session_id": None,
        "drain_state": "IDLE",
        "clients_return_to_boot": False,
    }


def system_quiesce_status():
    with _ORF_SYSTEM_WRITE_LOCK:
        rec = dict(globals().get("__ORF_SYSTEM_QUIESCE__") or {})
        state = str(rec.get("state") or "RUNNING").upper()
        deadline = rec.get("deadline_monotonic")
        try:
            remaining = max(0, int(math.ceil(float(deadline) - time.monotonic()))) if deadline else 0
        except Exception:
            remaining = 0
        active_writes = max(0, int(globals().get("__ORF_SYSTEM_ACTIVE_WRITES__") or 0))
        return {
            "schema": ORF_SYSTEM_QUIESCE_SCHEMA,
            "state": state,
            "writes_enabled": bool(rec.get("writes_enabled", state == "RUNNING")),
            "active_writes": active_writes,
            "countdown_seconds": remaining,
            "requested_utc": rec.get("requested_utc"),
            "deadline_utc": rec.get("deadline_utc"),
            "session_id": rec.get("session_id"),
            "drain_state": str(rec.get("drain_state") or "IDLE"),
            "drain_timed_out": bool(rec.get("drain_timed_out")),
            "clients_return_to_boot": bool(rec.get("clients_return_to_boot")),
            "reason": rec.get("reason"),
        }


def _set_system_quiesce_state(state, **fields):
    with _ORF_SYSTEM_WRITE_LOCK:
        rec = dict(globals().get("__ORF_SYSTEM_QUIESCE__") or {})
        rec.setdefault("schema", ORF_SYSTEM_QUIESCE_SCHEMA)
        rec["state"] = str(state).upper()
        rec.update(fields)
        globals()["__ORF_SYSTEM_QUIESCE__"] = rec
    return system_quiesce_status()


def _begin_system_quiesce(session_id, reason="MAINTENANCE_RUNTIME_SHUTDOWN"):
    now = datetime.now(timezone.utc)
    with _ORF_SYSTEM_WRITE_LOCK:
        current = dict(globals().get("__ORF_SYSTEM_QUIESCE__") or {})
        current_state = str(current.get("state") or "RUNNING").upper()
        if current_state in _ORF_SYSTEM_QUIESCE_PENDING_STATES:
            return system_quiesce_status()
        deadline_monotonic = time.monotonic() + ORF_MAINTENANCE_SHUTDOWN_COUNTDOWN_SECONDS
        record = {
            "schema": ORF_SYSTEM_QUIESCE_SCHEMA,
            "state": "QUIESCING",
            "writes_enabled": False,
            "requested_utc": now.isoformat(),
            "deadline_utc": (now + timedelta(seconds=ORF_MAINTENANCE_SHUTDOWN_COUNTDOWN_SECONDS)).isoformat(),
            "deadline_monotonic": deadline_monotonic,
            "session_id": session_id,
            "reason": str(reason),
            "drain_state": "WAITING_FOR_COUNTDOWN",
            "drain_timed_out": False,
            "clients_return_to_boot": False,
        }
        globals()["__ORF_SYSTEM_QUIESCE__"] = record
    _emit_kernel_loader_capture(
        "SYSTEM_QUIESCE_STARTED",
        session_id=session_id,
        countdown_seconds=ORF_MAINTENANCE_SHUTDOWN_COUNTDOWN_SECONDS,
        active_writes=system_quiesce_status().get("active_writes"),
    )
    return system_quiesce_status()


def _system_write_begin(operation):
    depth = int(getattr(_ORF_SYSTEM_WRITE_TLS, "depth", 0) or 0)
    if depth > 0:
        _ORF_SYSTEM_WRITE_TLS.depth = depth + 1
        return
    with _ORF_SYSTEM_WRITE_LOCK:
        status = system_quiesce_status()
        if not status.get("writes_enabled") or str(status.get("state") or "RUNNING").upper() != "RUNNING":
            _emit_kernel_loader_capture(
                "SYSTEM_WRITE_REJECTED_QUIESCE",
                operation=str(operation),
                shutdown_state=status.get("state"),
                countdown_seconds=status.get("countdown_seconds"),
            )
            raise RuntimeError(
                f"SYSTEM_QUIESCING: new writes are locked during runtime shutdown ({operation})"
            )
        globals()["__ORF_SYSTEM_ACTIVE_WRITES__"] = int(
            globals().get("__ORF_SYSTEM_ACTIVE_WRITES__") or 0
        ) + 1
        _ORF_SYSTEM_WRITE_TLS.depth = 1


def _system_write_end(operation):
    depth = int(getattr(_ORF_SYSTEM_WRITE_TLS, "depth", 0) or 0)
    if depth <= 0:
        return
    if depth > 1:
        _ORF_SYSTEM_WRITE_TLS.depth = depth - 1
        return
    _ORF_SYSTEM_WRITE_TLS.depth = 0
    with _ORF_SYSTEM_WRITE_LOCK:
        globals()["__ORF_SYSTEM_ACTIVE_WRITES__"] = max(
            0, int(globals().get("__ORF_SYSTEM_ACTIVE_WRITES__") or 0) - 1
        )


def _system_write_operation(operation):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            _system_write_begin(operation)
            try:
                return fn(*args, **kwargs)
            finally:
                _system_write_end(operation)
        return wrapped
    return decorator
ORF_MAINTAINER_CERT_SHA256 = "fd3b4b032600ec158ede387ed04661da9f3a7aaa45472ce323a3e79b0ade89d9"
ORF_MAINTAINER_PUBLIC_KEY_SHA256 = "976d0195b498a18915fc203cf1fe08eb3618fe3a97aa62b31a1008a822ffe705"
ORF_MAINTAINER_CERT_DN = "CN=KORF Grandpa Boot v0.1, O=ORF, C=US"
ORF_MAINTAINER_CERT_PEM = """-----BEGIN CERTIFICATE-----
MIIDHjCCAgagAwIBAgIJALSEYdMnGg3nMA0GCSqGSIb3DQEBCwUAMDwxCzAJBgNV
BAYTAlVTMQwwCgYDVQQKEwNPUkYxHzAdBgNVBAMTFktPUkYgR3JhbmRwYSBCb290
IHYwLjEwIBcNMjYwNzMwMjIyMTUxWhgPMjA1MzEyMTUyMjIxNTFaMDwxCzAJBgNV
BAYTAlVTMQwwCgYDVQQKEwNPUkYxHzAdBgNVBAMTFktPUkYgR3JhbmRwYSBCb290
IHYwLjEwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQCpRYSms9pwBfle
oLvCQqN/HDH+xfdRWeAR68YU2/GHWwLyxWwrr8VeeF/qlvZTJlq3j4zwnlLF7Exi
tDUyJg1THp9KaA/f6OGD428FpTb1fUs08PRE6B7S1BRA3xNrpILs9ImCWbG/myi9
UmdKAZ5RYmEJQ/K8ehgUT7R3VIhm4DGUKx6+eTIdmB8sVFJf9k0/stcSOqCwHNMM
PyfMUxoiY+HFtFh8+M4JfeV99JumaaCBucjQJlIKFgIu3PZ6WR+bOV3p1v05yW8D
ty2OFAnMGHlgZWZW0zp4HBVGkXPJQGs3hSdbLnIgAgLxHUw6rxd8ARburbb4qntG
xyqDXJv7AgMBAAGjITAfMB0GA1UdDgQWBBRyI+lWfGAMJWLbPplqP3C96RabIDAN
BgkqhkiG9w0BAQsFAAOCAQEAZUnYLMRc1KJVQl/ThBSLqGqagntpsIu5xbsusJMI
UKjMrGeJq3afMbWh4VMdpGjXs/6B28OucLO2mLINxAZpvVRWp7YA4oOeoy1Bw1E0
6siOAtdWG1sOlt93cm685LIZXlaZshPrhYtc5OeJmYk5O4mPluyZon8BWrJSBZ4n
vGr3/yTnLn8hA2m9I3gblDFNO/qbzAGmGpR1qHi0335FiSOvO9O/g/gCtlQ9/Enu
oKfthfnrMxyLChFywyOeRxP+8mlsfcmvlopUyXN6nihQriqzfAp2JIDOdLql/A4q
BGGOkqNmSNSbYNTFYVt7e+wXh0wclrrJBM/qe7k/P7LVZg==
-----END CERTIFICATE-----
"""

# ORFMOS root source is independent from Kernel source.
ORFMOS_DRIVE_SOURCE_ROOT_FOLDER_ID = "1BKjCdQJg3xs6e7vYAlyf6ucoSS_t-2Vb"
ORFMOS_DRIVE_SOURCE_ROOT_NAME = "ORFMOS_SOURCE_ROOT"
ORFMOS_GITHUB_OWNER = "hadrex83"
ORFMOS_GITHUB_REPO = "ORFMOS"
ORFMOS_GITHUB_REF = "main"
ORFMOS_GITHUB_PATH = ""
REQUIRED_ORFMOS_SOURCE_ROOT_CHILDREN = (
    "bios",
    "kernel",
    "modules",
    "shared",
    "manifests",
)

# Provider-neutral Kernel resources remain distinct from source distribution.
# Protected signing authority and mutable recovery authority stay off GitHub.
SIGNING_KEYSTORE_DRIVE_FILE_ID = "1ir2pOT6uzEIY2vyXgZwjAjKgIVyCgzso"
SIGNING_RESOLVER_DRIVE_FILE_ID = "1Pjw50ctbSSR7Bzj5DHfuttwuO3j7aJH6"
ORF_RUNTIME_RECOVERY_TARGET_DRIVE_FILE_ID = "1YgJuOe51OmmlCvE2mzRPlsXZr7GoEPJE"
ORF_RECOVERY_ROOT_FOLDER_ID = "1BFN6nyD1LWemWHm6ilcPkwhcD5b_MDjn"

from pathlib import Path
import shutil

# Fail closed if the embedded public identity ever drifts from the pinned signer.
_orf_cert_der = ssl.PEM_cert_to_DER_cert(ORF_MAINTAINER_CERT_PEM)
_orf_cert_sha = hashlib.sha256(_orf_cert_der).hexdigest()
if _orf_cert_sha != ORF_MAINTAINER_CERT_SHA256:
    raise RuntimeError(
        f"Pinned KORF maintainer certificate mismatch: {_orf_cert_sha} != {ORF_MAINTAINER_CERT_SHA256}"
    )

if "DRIVE" not in globals():
    print("Authenticating BIOS presentation to Drive API...")
    auth.authenticate_user()
    DRIVE = build("drive", "v3", cache_discovery=False)
else:
    print("BIOS Drive API client: REUSING LOADER SESSION")

# Google API transports are not safely shared across Python threads.  UI
# callbacks use the loader-thread client; the resident Kernel monitor gets its
# own service when a user-requested reboot resolves Drive boot material.
_ORF_BIOS_DRIVE_THREAD_LOCAL = globals().get(
    "_ORF_BIOS_DRIVE_THREAD_LOCAL"
) or threading.local()
globals()["_ORF_BIOS_DRIVE_THREAD_LOCAL"] = _ORF_BIOS_DRIVE_THREAD_LOCAL

def _bios_drive_service():
    if threading.current_thread() is threading.main_thread():
        return DRIVE
    service = getattr(_ORF_BIOS_DRIVE_THREAD_LOCAL, "service", None)
    if service is None:
        credentials, _ = google.auth.default()
        service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        _ORF_BIOS_DRIVE_THREAD_LOCAL.service = service
    return service


def _drive_read_bytes(file_id):
    request = _bios_drive_service().files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()


def _drive_write_bytes(file_id, payload, mime_type="application/json"):
    media = MediaIoBaseUpload(io.BytesIO(payload), mimetype=mime_type, resumable=False)
    return _bios_drive_service().files().update(
        fileId=file_id,
        media_body=media,
        fields="id,name,mimeType,modifiedTime,size",
    ).execute()


def read_boot_state():
    # Same-runtime Kernel state is live authority. Drive is previous-boot fallback.
    local_state = globals().get("ORF_BOOT_LAST_STATE")
    if isinstance(local_state, dict) and local_state.get("schema") == BOOT_STATE_SCHEMA:
        state = dict(local_state)
        state["_bios_transport"] = "LOCAL_SHARED_RUNTIME"
        return state

    raw = _drive_read_bytes(BOOT_STATE_FILE_ID)
    state = json.loads(raw.decode("utf-8"))
    if state.get("schema") != BOOT_STATE_SCHEMA:
        raise RuntimeError(f"Unexpected boot-state schema: {state.get('schema')!r}")
    state["_bios_transport"] = "DRIVE_API_FALLBACK"
    return state


def _drive_list_children(parent_id):
    result = _bios_drive_service().files().list(
        q=f"'{parent_id}' in parents and trashed = false",
        fields="files(id,name,mimeType,modifiedTime,parents,size,md5Checksum,version)",
        pageSize=100,
    ).execute()
    return result.get("files", [])


def _extract_drive_folder_id(value):
    value = str(value or "").strip()
    if not value:
        raise RuntimeError("Drive folder selection is empty.")
    match = re.search(r"/folders/([A-Za-z0-9_-]+)", value)
    return match.group(1) if match else value


def _verify_runtime_root(folder_id):
    folder_id = _extract_drive_folder_id(folder_id)
    meta = _bios_drive_service().files().get(
        fileId=folder_id,
        fields="id,name,mimeType,modifiedTime,parents",
    ).execute()
    if meta.get("mimeType") != "application/vnd.google-apps.folder":
        raise RuntimeError(f"Selected Kernel Drive root is not a folder: {folder_id}")

    children = _drive_list_children(folder_id)
    by_name = {}
    for item in children:
        by_name.setdefault(str(item.get("name") or ""), []).append(item)
    missing = [name for name in REQUIRED_RUNTIME_ROOT_CHILDREN if len(by_name.get(name, [])) != 1]
    if missing:
        raise RuntimeError(
            "Kernel Drive root lacks required unique structure: " + ", ".join(missing)
        )

    loader_folder = by_name[KERNEL_LOADER_FOLDER_NAME][0]
    if loader_folder.get("mimeType") != "application/vnd.google-apps.folder":
        raise RuntimeError("Selected Kernel Drive root 'loader' child is not a folder.")
    loader_children = _drive_list_children(loader_folder["id"])
    kernel_matches = [
        item for item in loader_children
        if str(item.get("name") or "") == KERNEL_NOTEBOOK_NAME
    ]
    if len(kernel_matches) != 1:
        raise RuntimeError(
            f"Expected exactly one {KERNEL_NOTEBOOK_NAME!r} under loader; found {len(kernel_matches)}"
        )
    kernel_notebook = kernel_matches[0]
    return {
        "folder_id": folder_id,
        "folder_name": meta.get("name") or folder_id,
        "folder_modified_time": meta.get("modifiedTime"),
        "loader_folder_id": loader_folder["id"],
        "kernel_notebook_file_id": kernel_notebook["id"],
        "kernel_notebook_name": kernel_notebook.get("name"),
    }


def _verify_orfmos_drive_source_root(folder_id=ORFMOS_DRIVE_SOURCE_ROOT_FOLDER_ID):
    folder_id = _extract_drive_folder_id(folder_id)
    meta = _bios_drive_service().files().get(
        fileId=folder_id,
        fields="id,name,mimeType,modifiedTime,parents",
    ).execute()
    if meta.get("mimeType") != "application/vnd.google-apps.folder":
        raise RuntimeError(f"ORFMOS Drive source root is not a folder: {folder_id}")
    children = _drive_list_children(folder_id)
    by_name = {}
    for item in children:
        by_name.setdefault(str(item.get("name") or ""), []).append(item)
    missing = [name for name in REQUIRED_ORFMOS_SOURCE_ROOT_CHILDREN if len(by_name.get(name, [])) != 1]
    if missing:
        raise RuntimeError(
            "ORFMOS Drive source root lacks required structure: " + ", ".join(missing)
        )
    return {
        "folder_id": folder_id,
        "folder_name": meta.get("name") or ORFMOS_DRIVE_SOURCE_ROOT_NAME,
        "folder_modified_time": meta.get("modifiedTime"),
        "children": {name: by_name[name][0] for name in REQUIRED_ORFMOS_SOURCE_ROOT_CHILDREN},
    }


def _github_raw_bytes(owner, repo, ref, path):
    path = str(path or "").lstrip("/")
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
    response = requests.get(url, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(
            f"GitHub source fetch failed ({response.status_code}) for {owner}/{repo}@{ref}:{path}"
        )
    return bytes(response.content)


def _default_github_kernel_authority():
    return {
        "owner": KERNEL_GITHUB_OWNER,
        "repo": KERNEL_GITHUB_REPO,
        "ref": KERNEL_GITHUB_REF,
        "prefix": KERNEL_GITHUB_PREFIX,
        "manifest_sha256": KERNEL_GITHUB_MANIFEST_SHA256,
        "entrypoint_cell_sha256": KERNEL_GITHUB_ENTRYPOINT_CELL_SHA256,
        "source": "BASE_PIN",
        "activation_state": "BASELINE",
    }


def _active_github_kernel_authority():
    override = globals().get("__ORF_ACTIVE_GITHUB_KERNEL_AUTHORITY__")
    if isinstance(override, dict) and str(override.get("activation_state") or "").upper() == "RUNTIME_ACTIVE":
        record = dict(override)
        for key, value in _default_github_kernel_authority().items():
            record.setdefault(key, value)
        return record
    return _default_github_kernel_authority()


def _safe_kernel_prefix(prefix):
    prefix = str(prefix or "").strip().strip("/")
    parts = Path(prefix).parts
    if not prefix or Path(prefix).is_absolute() or ".." in parts:
        raise RuntimeError(f"Unsafe Kernel GitHub path: {prefix!r}")
    return "/".join(parts)


def _maintenance_session_record():
    rec = dict(globals().get("__ORF_MAINTENANCE_SESSION__") or {})
    if str(rec.get("state") or "").upper() == "ACTIVE":
        expires = float(rec.get("expires_monotonic") or 0.0)
        if expires <= time.monotonic():
            rec["state"] = "EXPIRED"
            rec["expired_utc"] = datetime.now(timezone.utc).isoformat()
            globals()["__ORF_MAINTENANCE_SESSION__"] = rec
            _emit_kernel_loader_capture(
                "MAINTENANCE_SESSION_EXPIRED",
                session_id=rec.get("session_id"),
            )
    return rec


def maintenance_session_status():
    rec = _maintenance_session_record()
    active = str(rec.get("state") or "").upper() == "ACTIVE"
    expires = float(rec.get("expires_monotonic") or 0.0)
    candidate = dict(globals().get("__ORF_MAINTENANCE_KERNEL_CANDIDATE__") or {})
    active_kernel = _active_github_kernel_authority()
    return {
        "schema": ORF_MAINTENANCE_SESSION_SCHEMA,
        "state": "ACTIVE" if active else str(rec.get("state") or "LOCKED").upper(),
        "active": active,
        "session_id": rec.get("session_id"),
        "armed_utc": rec.get("armed_utc"),
        "expires_in_seconds": max(0, int(expires - time.monotonic())) if active else 0,
        "signer_dn": ORF_MAINTAINER_CERT_DN,
        "certificate_sha256": ORF_MAINTAINER_CERT_SHA256,
        "public_key_sha256": ORF_MAINTAINER_PUBLIC_KEY_SHA256,
        "kernel_candidate": {
            "state": str(candidate.get("state") or "IDLE"),
            "version": candidate.get("version"),
            "manifest_sha256": candidate.get("manifest_sha256"),
            "ref": candidate.get("ref"),
            "prefix": candidate.get("prefix"),
        },
        "active_kernel": {
            "source": active_kernel.get("source"),
            "ref": active_kernel.get("ref"),
            "prefix": active_kernel.get("prefix"),
            "manifest_sha256": active_kernel.get("manifest_sha256"),
        },
        "runtime_shutdown": system_quiesce_status(),
    }


def _require_maintenance_session(action):
    status = maintenance_session_status()
    if not status.get("active"):
        raise RuntimeError(f"Maintenance authority required for {action}")
    return status


def issue_maintenance_challenge():
    issued_utc = datetime.now(timezone.utc).isoformat()
    nonce = secrets.token_urlsafe(32)
    challenge = (
        "ORFMOS_MAINTENANCE_CHALLENGE_V0_1\n"
        f"nonce={nonce}\n"
        f"issued_utc={issued_utc}\n"
        f"expires_seconds={ORF_MAINTENANCE_CHALLENGE_SECONDS}\n"
        f"signer_cert_sha256={ORF_MAINTAINER_CERT_SHA256}\n"
    )
    record = {
        "schema": ORF_MAINTENANCE_CHALLENGE_SCHEMA,
        "state": "ISSUED",
        "challenge_id": secrets.token_hex(12),
        "challenge": challenge,
        "issued_utc": issued_utc,
        "issued_monotonic": time.monotonic(),
        "expires_monotonic": time.monotonic() + ORF_MAINTENANCE_CHALLENGE_SECONDS,
        "consumed": False,
    }
    globals()["__ORF_MAINTENANCE_CHALLENGE__"] = record
    _emit_kernel_loader_capture(
        "MAINTENANCE_CHALLENGE_ISSUED",
        challenge_id=record["challenge_id"],
        expires_seconds=ORF_MAINTENANCE_CHALLENGE_SECONDS,
        signer_cert_sha256=ORF_MAINTAINER_CERT_SHA256,
    )
    return dict(record)


def _verify_korf_challenge_signature(challenge_text, signature_bytes):
    with tempfile.TemporaryDirectory(prefix="orf_maint_verify_") as tmp:
        tmp = Path(tmp)
        cert_path = tmp / "maintainer_cert.pem"
        pub_path = tmp / "maintainer_pub.pem"
        challenge_path = tmp / "challenge.bin"
        sig_path = tmp / "signature.bin"
        cert_path.write_text(ORF_MAINTAINER_CERT_PEM, encoding="utf-8")
        challenge_path.write_bytes(str(challenge_text).encode("utf-8"))
        sig_path.write_bytes(bytes(signature_bytes))
        extract = subprocess.run(
            ["openssl", "x509", "-pubkey", "-noout", "-in", str(cert_path), "-out", str(pub_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if extract.returncode != 0:
            raise RuntimeError(f"Unable to resolve pinned maintainer public key: {extract.stderr.strip()}")
        verify = subprocess.run(
            ["openssl", "dgst", "-sha256", "-verify", str(pub_path), "-signature", str(sig_path), str(challenge_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return verify.returncode == 0


def verify_and_arm_maintenance(signature_b64):
    record = dict(globals().get("__ORF_MAINTENANCE_CHALLENGE__") or {})
    if str(record.get("state") or "").upper() != "ISSUED" or record.get("consumed"):
        raise RuntimeError("No unconsumed maintenance challenge is active")
    if float(record.get("expires_monotonic") or 0.0) <= time.monotonic():
        record["state"] = "EXPIRED"
        globals()["__ORF_MAINTENANCE_CHALLENGE__"] = record
        raise RuntimeError("Maintenance challenge expired")
    try:
        signature = base64.b64decode(str(signature_b64 or "").strip(), validate=True)
    except Exception as exc:
        raise RuntimeError("Maintenance signature must be standard Base64") from exc
    if not signature:
        raise RuntimeError("Maintenance signature is empty")
    if not _verify_korf_challenge_signature(record.get("challenge") or "", signature):
        _emit_kernel_loader_capture(
            "MAINTENANCE_SIGNATURE_REJECTED",
            challenge_id=record.get("challenge_id"),
        )
        raise RuntimeError("KORF maintenance signature verification failed")
    record["consumed"] = True
    record["state"] = "VERIFIED"
    globals()["__ORF_MAINTENANCE_CHALLENGE__"] = record
    session = {
        "schema": ORF_MAINTENANCE_SESSION_SCHEMA,
        "state": "ACTIVE",
        "session_id": "ORF_MAINT_" + secrets.token_hex(8),
        "armed_utc": datetime.now(timezone.utc).isoformat(),
        "armed_monotonic": time.monotonic(),
        "expires_monotonic": time.monotonic() + ORF_MAINTENANCE_SESSION_SECONDS,
        "signer_dn": ORF_MAINTAINER_CERT_DN,
        "signer_cert_sha256": ORF_MAINTAINER_CERT_SHA256,
        "challenge_id": record.get("challenge_id"),
    }
    globals()["__ORF_MAINTENANCE_SESSION__"] = session
    globals().pop("__ORF_MAINTENANCE_SHUTDOWN_ARM__", None)
    _emit_kernel_loader_capture(
        "MAINTENANCE_AUTHORITY_ACTIVE",
        session_id=session["session_id"],
        expires_seconds=ORF_MAINTENANCE_SESSION_SECONDS,
        signer_cert_sha256=ORF_MAINTAINER_CERT_SHA256,
    )
    return maintenance_session_status()


def revoke_maintenance_session(reason="USER_REVOKE"):
    rec = _maintenance_session_record()
    if rec:
        rec["state"] = "REVOKED"
        rec["revoked_utc"] = datetime.now(timezone.utc).isoformat()
        rec["revoke_reason"] = str(reason or "USER_REVOKE")
        globals()["__ORF_MAINTENANCE_SESSION__"] = rec
    globals().pop("__ORF_MAINTENANCE_SHUTDOWN_ARM__", None)
    _emit_kernel_loader_capture(
        "MAINTENANCE_AUTHORITY_REVOKED",
        session_id=rec.get("session_id") if rec else None,
        reason=str(reason or "USER_REVOKE"),
    )
    return maintenance_session_status()


def _validate_github_kernel_source():
    authority = _active_github_kernel_authority()
    manifest_path = f"{authority['prefix']}/ORF_KERNEL_BOOT_MANIFEST.json"
    raw = _github_raw_bytes(authority["owner"], authority["repo"], authority["ref"], manifest_path)
    observed = hashlib.sha256(raw).hexdigest()
    expected = str(authority.get("manifest_sha256") or "").lower()
    if observed != expected:
        raise RuntimeError(
            f"GitHub Kernel manifest SHA256 mismatch: {observed} != {expected}"
        )
    manifest = json.loads(raw.decode("utf-8"))
    if manifest.get("schema") != "ORF_KERNEL_BOOT_MANIFEST_V0_2":
        raise RuntimeError(f"Unexpected GitHub Kernel manifest schema: {manifest.get('schema')!r}")
    return {
        "provider": SOURCE_PROVIDER_GITHUB,
        "owner": authority["owner"],
        "repo": authority["repo"],
        "ref": authority["ref"],
        "path": authority["prefix"],
        "manifest_sha256": observed,
        "kernel_version": manifest.get("version"),
        "validation_state": "VERIFIED",
        "authority_source": authority.get("source"),
    }

def _validate_github_root_source():
    # Repository existence is sufficient at this migration stage. The selected
    # root provider is independent from protected signing/recovery authorities.
    raw = _github_raw_bytes(ORFMOS_GITHUB_OWNER, ORFMOS_GITHUB_REPO, BOOT_REF, BOOT_PATH)
    observed = hashlib.sha256(raw).hexdigest()
    if observed != EXPECTED_BOOT_SHA256:
        raise RuntimeError("ORFMOS GitHub repository verification failed at pinned boot sentinel")
    return {
        "provider": SOURCE_PROVIDER_GITHUB,
        "owner": ORFMOS_GITHUB_OWNER,
        "repo": ORFMOS_GITHUB_REPO,
        "ref": ORFMOS_GITHUB_REF,
        "path": ORFMOS_GITHUB_PATH,
        "validation_state": "REPOSITORY_RESOLVED",
        "structure_state": "MIGRATION_READY",
    }


def _read_bios_source_selection_payload():
    raw = _drive_read_bytes(RUNTIME_TARGET_FILE_ID)
    observed_sha = hashlib.sha256(raw).hexdigest()
    target = json.loads(raw.decode("utf-8"))
    return target, observed_sha


def _migrate_or_normalize_source_selection(target):
    schema = str((target or {}).get("schema") or "")
    if schema == BIOS_SOURCE_SELECTION_SCHEMA:
        kernel_provider = str((target.get("kernel_source") or {}).get("provider") or SOURCE_PROVIDER_GITHUB).upper()
        root_provider = str((target.get("root_source") or {}).get("provider") or SOURCE_PROVIDER_GITHUB).upper()
        apply_sequence = int(target.get("apply_sequence") or 0)
        migrated_from = None
        drive_kernel_root = str((target.get("kernel_source") or {}).get("drive_runtime_root_folder_id") or DEFAULT_RUNTIME_ROOT_FOLDER_ID)
    elif schema in {"ORF_RUNTIME_TARGET_V0_1", "ORF_RUNTIME_TARGET_V0_2"}:
        kernel_provider = SOURCE_PROVIDER_DRIVE
        root_provider = SOURCE_PROVIDER_DRIVE
        apply_sequence = 0
        migrated_from = schema
        drive_kernel_root = str(target.get("root_folder_id") or DEFAULT_RUNTIME_ROOT_FOLDER_ID)
    else:
        raise RuntimeError(f"Unexpected BIOS source-selection schema: {schema!r}")

    if kernel_provider not in SOURCE_PROVIDERS or root_provider not in SOURCE_PROVIDERS:
        raise RuntimeError("Unsupported BIOS source provider in selection authority")
    return {
        "kernel_provider": kernel_provider,
        "root_provider": root_provider,
        "apply_sequence": apply_sequence,
        "migrated_from": migrated_from,
        "drive_kernel_root": drive_kernel_root,
    }


def read_root_selection_state():
    target, target_sha = _read_bios_source_selection_payload()
    normalized = _migrate_or_normalize_source_selection(target)
    kernel_provider = normalized["kernel_provider"]
    root_provider = normalized["root_provider"]
    github_kernel_authority = _active_github_kernel_authority()

    drive_kernel = None
    if kernel_provider == SOURCE_PROVIDER_DRIVE:
        drive_kernel = _verify_runtime_root(normalized["drive_kernel_root"])
        kernel_state = "VERIFIED"
        kernel_label = drive_kernel["folder_name"]
        kernel_notebook_id = drive_kernel["kernel_notebook_file_id"]
        kernel_notebook_name = drive_kernel["kernel_notebook_name"]
        kernel_relative_path = f"{KERNEL_LOADER_FOLDER_NAME}/{KERNEL_NOTEBOOK_NAME}"
    else:
        kernel_state = str((target.get("kernel_source") or {}).get("validation_state") or "SELECTED")
        kernel_label = f"{github_kernel_authority['owner']}/{github_kernel_authority['repo']}"
        kernel_notebook_id = None
        kernel_notebook_name = KERNEL_NOTEBOOK_NAME
        kernel_relative_path = f"{github_kernel_authority['prefix']}/{KERNEL_NOTEBOOK_NAME}"

    if root_provider == SOURCE_PROVIDER_DRIVE:
        drive_root = _verify_orfmos_drive_source_root()
        root_state = "VERIFIED"
        root_label = drive_root["folder_name"]
        root_drive_id = drive_root["folder_id"]
        current_runtime = {
            "folder_id": root_drive_id,
            "state": "RESOLVED",
            "object_id": root_drive_id,
            "object_name": root_label,
            "object_mime_type": "application/vnd.google-apps.folder",
        }
    else:
        root_state = str((target.get("root_source") or {}).get("validation_state") or "REPOSITORY_RESOLVED")
        root_label = f"{ORFMOS_GITHUB_OWNER}/{ORFMOS_GITHUB_REPO}"
        root_drive_id = None
        current_runtime = {
            "folder_id": None,
            "state": "REPOSITORY_RESOLVED",
            "object_id": f"github:{root_label}@{ORFMOS_GITHUB_REF}",
            "object_name": root_label,
            "object_mime_type": "GITHUB_REPOSITORY",
        }

    return {
        "schema": ROOT_SELECTION_SCHEMA,
        "mode": ROOT_RESOLUTION_MODE,
        "authority": "BIOS_DUAL_SOURCE_SELECTION_PLUS_PROVIDER_VERIFICATION",
        "kernel_source": {
            "provider": kernel_provider,
            "selection_state": kernel_state,
            "display_name": kernel_label,
            "drive_runtime_root_folder_id": normalized["drive_kernel_root"] if kernel_provider == SOURCE_PROVIDER_DRIVE else None,
            "github_owner": github_kernel_authority["owner"] if kernel_provider == SOURCE_PROVIDER_GITHUB else None,
            "github_repo": github_kernel_authority["repo"] if kernel_provider == SOURCE_PROVIDER_GITHUB else None,
            "github_ref": github_kernel_authority["ref"] if kernel_provider == SOURCE_PROVIDER_GITHUB else None,
            "github_path": github_kernel_authority["prefix"] if kernel_provider == SOURCE_PROVIDER_GITHUB else None,
            "manifest_sha256": github_kernel_authority["manifest_sha256"] if kernel_provider == SOURCE_PROVIDER_GITHUB else None,
        },
        "root_source": {
            "provider": root_provider,
            "selection_state": root_state,
            "display_name": root_label,
            "drive_folder_id": root_drive_id,
            "github_owner": ORFMOS_GITHUB_OWNER if root_provider == SOURCE_PROVIDER_GITHUB else None,
            "github_repo": ORFMOS_GITHUB_REPO if root_provider == SOURCE_PROVIDER_GITHUB else None,
            "github_ref": ORFMOS_GITHUB_REF if root_provider == SOURCE_PROVIDER_GITHUB else None,
            "github_path": ORFMOS_GITHUB_PATH if root_provider == SOURCE_PROVIDER_GITHUB else None,
        },
        # Compatibility fields retained for existing BIOS BOOT/rail renderers.
        "active_root": {
            "root_id": root_label,
            "drive_folder_id": root_drive_id,
            "root_class": "ORFMOS_SOURCE_ROOT",
            "target_stage": "ORFMOS_ROOT_SOURCE",
            "selection_state": root_state,
        },
        "current_runtime": current_runtime,
        "kernel": {
            "source_provider": kernel_provider,
            "loader_folder_id": (drive_kernel or {}).get("loader_folder_id") if drive_kernel else None,
            "notebook_file_id": kernel_notebook_id,
            "notebook_name": kernel_notebook_name,
            "relative_path": kernel_relative_path,
        },
        "fallback_root": {
            "state": "DRIVE_AVAILABLE",
            "root_id": ORFMOS_DRIVE_SOURCE_ROOT_FOLDER_ID,
        },
        "selection": {
            "kernel_provider": kernel_provider,
            "root_provider": root_provider,
            "apply_sequence": normalized["apply_sequence"],
            "migrated_from": normalized["migrated_from"],
        },
        "runtime_target": {
            "drive_file_id": RUNTIME_TARGET_FILE_ID,
            "schema": str(target.get("schema") or ""),
            "observed_sha256": target_sha,
            "drive_mount_required": False,
            "recovery_mode": "RESET_KERNEL_AFTER_SOURCE_APPLY",
            "migrated_from": normalized["migrated_from"],
        },
        "mutation": {
            "state": "SELECTABLE",
            "writes_enabled": True,
            "authority_file_id": RUNTIME_TARGET_FILE_ID,
        },
    }


@_system_write_operation("BIOS_SOURCE_SELECTION_APPLY")
def apply_bios_source_selection(kernel_provider, root_provider):
    kernel_provider = str(kernel_provider or "").strip().upper()
    root_provider = str(root_provider or "").strip().upper()
    if kernel_provider not in SOURCE_PROVIDERS:
        raise RuntimeError(f"Unsupported Kernel source provider: {kernel_provider!r}")
    if root_provider not in SOURCE_PROVIDERS:
        raise RuntimeError(f"Unsupported ORFMOS root source provider: {root_provider!r}")

    current_target, _ = _read_bios_source_selection_payload()
    normalized = _migrate_or_normalize_source_selection(current_target)
    apply_sequence = int(normalized.get("apply_sequence") or 0) + 1

    if kernel_provider == SOURCE_PROVIDER_DRIVE:
        kernel_verified = _verify_runtime_root(normalized.get("drive_kernel_root") or DEFAULT_RUNTIME_ROOT_FOLDER_ID)
        kernel_record = {
            "provider": SOURCE_PROVIDER_DRIVE,
            "validation_state": "VERIFIED",
            "mode": "SEALED_DRIVE_NOTEBOOK",
            "drive_runtime_root_folder_id": kernel_verified["folder_id"],
            "drive_notebook_file_id": kernel_verified["kernel_notebook_file_id"],
            "notebook_relative_path": f"{KERNEL_LOADER_FOLDER_NAME}/{KERNEL_NOTEBOOK_NAME}",
            "code_cell_sha256": DEV_KERNEL_CODE_CELL_SHA256,
        }
    else:
        verified = _validate_github_kernel_source()
        kernel_record = {
            **verified,
            "mode": "PORTABLE_VERIFIED_TREE",
            "entrypoint": f"{verified['path']}/{KERNEL_NOTEBOOK_NAME}",
        }

    if root_provider == SOURCE_PROVIDER_DRIVE:
        root_verified = _verify_orfmos_drive_source_root()
        root_record = {
            "provider": SOURCE_PROVIDER_DRIVE,
            "validation_state": "VERIFIED",
            "mode": "DRIVE_ORFMOS_SOURCE_ROOT",
            "drive_folder_id": root_verified["folder_id"],
            "root_name": root_verified["folder_name"],
            "required_children": list(REQUIRED_ORFMOS_SOURCE_ROOT_CHILDREN),
        }
    else:
        root_record = {
            **_validate_github_root_source(),
            "mode": "GITHUB_ORFMOS_SOURCE_ROOT",
        }

    payload = {
        "schema": BIOS_SOURCE_SELECTION_SCHEMA,
        "selection_mode": "INDEPENDENT_KERNEL_AND_ORFMOS_ROOT_PROVIDERS",
        "kernel_source": kernel_record,
        "root_source": root_record,
        "apply_sequence": apply_sequence,
        "selected_utc": datetime.now(timezone.utc).isoformat(),
        "recovery_authority": {
            "separate": True,
            "selector_drive_file_id": ORF_RUNTIME_RECOVERY_TARGET_DRIVE_FILE_ID,
        },
    }
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _drive_write_bytes(RUNTIME_TARGET_FILE_ID, raw, "application/json")
    globals()["__ORF_BIOS_SOURCE_SELECTION_CACHE__"] = payload
    return read_root_selection_state()


# Backward-compatible name retained for any old presentation code loaded in a
# still-live runtime. New UI uses apply_bios_source_selection().
def select_runtime_root(root_value):
    return apply_bios_source_selection(SOURCE_PROVIDER_DRIVE, SOURCE_PROVIDER_DRIVE)


def resolve_selected_kernel_source_provider():
    return str(read_root_selection_state().get("kernel_source", {}).get("provider") or SOURCE_PROVIDER_GITHUB).upper()


def resolve_selected_kernel_notebook_file_id():
    state = read_root_selection_state()
    provider = str(state.get("kernel_source", {}).get("provider") or SOURCE_PROVIDER_GITHUB).upper()
    if provider == SOURCE_PROVIDER_DRIVE:
        kernel_id = str(state.get("kernel", {}).get("notebook_file_id") or "").strip()
        if not kernel_id:
            raise RuntimeError("Selected Drive Kernel did not resolve an ORF Kernel notebook.")
        return kernel_id
    authority = _active_github_kernel_authority()
    return (
        f"github://{authority['owner']}/{authority['repo']}@{authority['ref']}/"
        f"{authority['prefix']}/{KERNEL_NOTEBOOK_NAME}"
    )


def safe_read_root_selection_state():
    github_kernel_authority = _active_github_kernel_authority()
    try:
        return read_root_selection_state()
    except Exception as exc:
        return {
            "schema": ROOT_SELECTION_SCHEMA,
            "mode": ROOT_RESOLUTION_MODE,
            "authority": "UNRESOLVED",
            "kernel_source": {
                "provider": SOURCE_PROVIDER_GITHUB,
                "selection_state": "DEFAULT_GITHUB_FALLBACK",
                "display_name": f"{github_kernel_authority['owner']}/{github_kernel_authority['repo']}",
                "github_owner": github_kernel_authority["owner"],
                "github_repo": github_kernel_authority["repo"],
                "github_ref": github_kernel_authority["ref"],
                "github_path": github_kernel_authority["prefix"],
                "manifest_sha256": github_kernel_authority["manifest_sha256"],
            },
            "root_source": {
                "provider": SOURCE_PROVIDER_GITHUB,
                "selection_state": "DEFAULT_GITHUB_FALLBACK",
                "display_name": f"{ORFMOS_GITHUB_OWNER}/{ORFMOS_GITHUB_REPO}",
                "github_owner": ORFMOS_GITHUB_OWNER,
                "github_repo": ORFMOS_GITHUB_REPO,
                "github_ref": ORFMOS_GITHUB_REF,
                "github_path": ORFMOS_GITHUB_PATH,
            },
            "active_root": {
                "root_id": None,
                "drive_folder_id": None,
                "root_class": "ORFMOS_SOURCE_ROOT",
                "target_stage": "ORFMOS_ROOT_SOURCE",
                "selection_state": "FAILED",
            },
            "current_runtime": {
                "folder_id": None,
                "state": "DEFAULT_GITHUB_FALLBACK",
                "object_id": f"github:{ORFMOS_GITHUB_OWNER}/{ORFMOS_GITHUB_REPO}@{ORFMOS_GITHUB_REF}",
                "object_name": f"{ORFMOS_GITHUB_OWNER}/{ORFMOS_GITHUB_REPO}",
                "object_mime_type": "GITHUB_REPOSITORY",
            },
            "kernel": {
                "source_provider": SOURCE_PROVIDER_GITHUB,
                "notebook_file_id": None,
                "notebook_name": KERNEL_NOTEBOOK_NAME,
                "relative_path": f"{github_kernel_authority['prefix']}/{KERNEL_NOTEBOOK_NAME}",
            },
            "fallback_root": {"state": "DRIVE_AVAILABLE", "root_id": ORFMOS_DRIVE_SOURCE_ROOT_FOLDER_ID},
            "selection": {"kernel_provider": SOURCE_PROVIDER_GITHUB, "root_provider": SOURCE_PROVIDER_GITHUB, "apply_sequence": 0},
            "runtime_target": {"drive_file_id": RUNTIME_TARGET_FILE_ID, "schema": None, "observed_sha256": None},
            "mutation": {"state": "SELECTABLE", "writes_enabled": True},
            "error": f"{type(exc).__name__}: {exc}",
        }


def _extract_one_code_cell(notebook_bytes, label):
    notebook = json.loads(notebook_bytes.decode("utf-8"))
    code_cells = []
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)
        source = str(source)
        if source.strip():
            code_cells.append(source)
    if len(code_cells) != 1:
        raise RuntimeError(f"{label}: expected 1 non-empty code cell, found {len(code_cells)}")
    return code_cells[0]


def _stage_github_kernel_tree(authority=None, final_root=None, activate=True):
    authority = dict(authority or _active_github_kernel_authority())
    owner = str(authority.get("owner") or KERNEL_GITHUB_OWNER)
    repo = str(authority.get("repo") or KERNEL_GITHUB_REPO)
    ref = str(authority.get("ref") or KERNEL_GITHUB_REF)
    prefix = _safe_kernel_prefix(authority.get("prefix") or KERNEL_GITHUB_PREFIX)
    expected_manifest_sha = str(authority.get("manifest_sha256") or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha):
        raise RuntimeError("Kernel manifest authority requires an expected SHA256")

    manifest_rel = f"{prefix}/ORF_KERNEL_BOOT_MANIFEST.json"
    manifest_bytes = _github_raw_bytes(owner, repo, ref, manifest_rel)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_sha != expected_manifest_sha:
        raise RuntimeError(
            f"GitHub Kernel manifest SHA256 mismatch: {manifest_sha} != {expected_manifest_sha}"
        )
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if manifest.get("schema") != "ORF_KERNEL_BOOT_MANIFEST_V0_2":
        raise RuntimeError("GitHub Kernel portable manifest schema mismatch")

    target_root = Path(final_root or KERNEL_LOCAL_STAGE_ROOT)
    stage_root = Path(str(target_root) + f".stage.{time.monotonic_ns()}")
    if stage_root.exists():
        shutil.rmtree(stage_root)
    (stage_root / "bootstrap").mkdir(parents=True, exist_ok=True)
    (stage_root / "modules").mkdir(parents=True, exist_ok=True)
    (stage_root / "ORF_KERNEL_BOOT_MANIFEST.json").write_bytes(manifest_bytes)

    entry = manifest.get("entrypoint") or {}
    entry_rel = str(entry.get("path") or KERNEL_NOTEBOOK_NAME)
    entry_bytes = _github_raw_bytes(owner, repo, ref, f"{prefix}/{entry_rel}")
    if hashlib.sha256(entry_bytes).hexdigest() != str(entry.get("sha256") or "").lower():
        raise RuntimeError("GitHub Kernel entrypoint SHA256 mismatch")
    (stage_root / entry_rel).write_bytes(entry_bytes)

    bootstrap = manifest.get("bootstrap") or {}
    bootstrap_rel = str(bootstrap.get("path") or "bootstrap/ORF_KERNEL_BOOTSTRAP.py")
    bootstrap_bytes = _github_raw_bytes(owner, repo, ref, f"{prefix}/{bootstrap_rel}")
    if hashlib.sha256(bootstrap_bytes).hexdigest() != str(bootstrap.get("sha256") or "").lower():
        raise RuntimeError("GitHub Kernel bootstrap SHA256 mismatch")
    bootstrap_path = stage_root / bootstrap_rel
    bootstrap_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_path.write_bytes(bootstrap_bytes)

    for module in manifest.get("modules") or []:
        file_name = str(module.get("file_name") or "")
        if not file_name or "/" in file_name or "\\" in file_name:
            raise RuntimeError(f"Unsafe Kernel module name in manifest: {file_name!r}")
        module_bytes = _github_raw_bytes(owner, repo, ref, f"{prefix}/modules/{file_name}")
        actual = hashlib.sha256(module_bytes).hexdigest()
        expected = str(module.get("sha256") or "").lower()
        if actual != expected:
            raise RuntimeError(f"GitHub Kernel module SHA256 mismatch for {file_name}: {actual} != {expected}")
        (stage_root / "modules" / file_name).write_bytes(module_bytes)

    if target_root.exists():
        shutil.rmtree(target_root)
    stage_root.replace(target_root)
    if activate:
        globals()["ORF_KERNEL_SOURCE_ROOT"] = str(target_root)
        globals()["ORF_KERNEL_EXPECTED_MANIFEST_SHA256"] = manifest_sha
    return target_root, manifest

@_system_write_operation("MAINTENANCE_KERNEL_STAGE")
def maintenance_stage_github_kernel_manifest(ref, prefix, manifest_sha256):
    _require_maintenance_session("KERNEL_MANIFEST_STAGE")
    ref = str(ref or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", ref):
        raise RuntimeError("Kernel update ref must be an immutable 40-character Git commit SHA")
    prefix = _safe_kernel_prefix(prefix)
    manifest_sha256 = str(manifest_sha256 or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", manifest_sha256):
        raise RuntimeError("Kernel update requires the expected 64-character manifest SHA256")
    authority = {
        "owner": KERNEL_GITHUB_OWNER,
        "repo": KERNEL_GITHUB_REPO,
        "ref": ref.lower(),
        "prefix": prefix,
        "manifest_sha256": manifest_sha256,
        "source": "MAINTENANCE_GATE",
        "activation_state": "CANDIDATE",
    }
    candidate_root, manifest = _stage_github_kernel_tree(
        authority=authority,
        final_root=KERNEL_LOCAL_CANDIDATE_ROOT,
        activate=False,
    )
    entry_rel = str((manifest.get("entrypoint") or {}).get("path") or KERNEL_NOTEBOOK_NAME)
    entry_source = _extract_one_code_cell((candidate_root / entry_rel).read_bytes(), "ORF candidate Kernel notebook")
    authority["entrypoint_cell_sha256"] = hashlib.sha256(entry_source.encode("utf-8")).hexdigest()
    candidate = {
        "schema": ORF_MAINTENANCE_KERNEL_CANDIDATE_SCHEMA,
        "state": "STAGED_VERIFIED",
        "version": manifest.get("version"),
        "kernel_id": manifest.get("kernel_id"),
        "owner": authority["owner"],
        "repo": authority["repo"],
        "ref": authority["ref"],
        "prefix": authority["prefix"],
        "manifest_sha256": authority["manifest_sha256"],
        "entrypoint_cell_sha256": authority["entrypoint_cell_sha256"],
        "module_count": len(manifest.get("modules") or []),
        "staged_utc": datetime.now(timezone.utc).isoformat(),
        "local_candidate_root": str(candidate_root),
        "authority": authority,
    }
    globals()["__ORF_MAINTENANCE_KERNEL_CANDIDATE__"] = candidate
    _emit_kernel_loader_capture(
        "MAINTENANCE_KERNEL_MANIFEST_STAGED",
        version=candidate.get("version"),
        ref=authority["ref"],
        prefix=authority["prefix"],
        manifest_sha256=authority["manifest_sha256"],
        module_count=candidate["module_count"],
    )
    return dict(candidate)


@_system_write_operation("MAINTENANCE_KERNEL_APPLY")
def maintenance_apply_staged_kernel():
    _require_maintenance_session("KERNEL_MANIFEST_APPLY")
    candidate = dict(globals().get("__ORF_MAINTENANCE_KERNEL_CANDIDATE__") or {})
    if str(candidate.get("state") or "").upper() != "STAGED_VERIFIED":
        raise RuntimeError("No verified Kernel candidate is staged")
    authority = dict(candidate.get("authority") or {})
    previous = _active_github_kernel_authority()
    authority["activation_state"] = "RUNTIME_ACTIVE"
    authority["activated_utc"] = datetime.now(timezone.utc).isoformat()
    authority["previous_authority"] = previous
    globals()["__ORF_ACTIVE_GITHUB_KERNEL_AUTHORITY__"] = authority
    candidate["state"] = "APPLY_REQUESTED"
    candidate["applied_utc"] = authority["activated_utc"]
    globals()["__ORF_MAINTENANCE_KERNEL_CANDIDATE__"] = candidate
    reboot = request_dev_kernel_reboot("MAINTENANCE_KERNEL_MANIFEST_APPLY")
    _emit_kernel_loader_capture(
        "MAINTENANCE_KERNEL_MANIFEST_APPLY_REQUESTED",
        version=candidate.get("version"),
        ref=authority.get("ref"),
        prefix=authority.get("prefix"),
        manifest_sha256=authority.get("manifest_sha256"),
        reboot_sequence=reboot.get("sequence"),
    )
    return {
        "state": "APPLY_REQUESTED",
        "candidate": candidate,
        "active_authority": _active_github_kernel_authority(),
        "reboot": reboot,
    }


@_system_write_operation("MAINTENANCE_KERNEL_ROLLBACK")
def maintenance_rollback_kernel():
    _require_maintenance_session("KERNEL_ROLLBACK")
    active = dict(globals().get("__ORF_ACTIVE_GITHUB_KERNEL_AUTHORITY__") or {})
    previous = dict(active.get("previous_authority") or {})
    if not active:
        raise RuntimeError("No maintenance Kernel override is active")
    if previous and str(previous.get("source") or "") != "BASE_PIN":
        previous["activation_state"] = "RUNTIME_ACTIVE"
        globals()["__ORF_ACTIVE_GITHUB_KERNEL_AUTHORITY__"] = previous
    else:
        globals().pop("__ORF_ACTIVE_GITHUB_KERNEL_AUTHORITY__", None)
    reboot = request_dev_kernel_reboot("MAINTENANCE_KERNEL_ROLLBACK")
    _emit_kernel_loader_capture(
        "MAINTENANCE_KERNEL_ROLLBACK_REQUESTED",
        target_ref=_active_github_kernel_authority().get("ref"),
        target_prefix=_active_github_kernel_authority().get("prefix"),
        reboot_sequence=reboot.get("sequence"),
    )
    return {
        "state": "ROLLBACK_REQUESTED",
        "active_authority": _active_github_kernel_authority(),
        "reboot": reboot,
    }


def maintenance_arm_runtime_shutdown():
    status = _require_maintenance_session("COLAB_RUNTIME_SHUTDOWN_ARM")
    record = {
        "state": "ARMED",
        "session_id": status.get("session_id"),
        "armed_utc": datetime.now(timezone.utc).isoformat(),
        "armed_monotonic": time.monotonic(),
        "expires_monotonic": time.monotonic() + ORF_MAINTENANCE_SHUTDOWN_ARM_SECONDS,
    }
    globals()["__ORF_MAINTENANCE_SHUTDOWN_ARM__"] = record
    _emit_kernel_loader_capture(
        "MAINTENANCE_RUNTIME_SHUTDOWN_ARMED",
        session_id=status.get("session_id"),
        expires_seconds=ORF_MAINTENANCE_SHUTDOWN_ARM_SECONDS,
    )
    return {
        "state": "ARMED",
        "expires_in_seconds": ORF_MAINTENANCE_SHUTDOWN_ARM_SECONDS,
    }


def maintenance_execute_runtime_shutdown():
    status = _require_maintenance_session("COLAB_RUNTIME_SHUTDOWN")
    armed = dict(globals().get("__ORF_MAINTENANCE_SHUTDOWN_ARM__") or {})
    if str(armed.get("state") or "").upper() != "ARMED":
        raise RuntimeError("Runtime shutdown is not armed")
    if armed.get("session_id") != status.get("session_id"):
        raise RuntimeError("Runtime shutdown arm belongs to a different maintenance session")
    if float(armed.get("expires_monotonic") or 0.0) <= time.monotonic():
        globals().pop("__ORF_MAINTENANCE_SHUTDOWN_ARM__", None)
        raise RuntimeError("Runtime shutdown arm expired")
    globals().pop("__ORF_MAINTENANCE_SHUTDOWN_ARM__", None)

    quiesce = _begin_system_quiesce(status.get("session_id"))
    _emit_kernel_loader_capture(
        "MAINTENANCE_RUNTIME_SHUTDOWN_COMMITTED",
        session_id=status.get("session_id"),
        action="QUIESCE_DRAIN_CLIENT_BOOT_COLAB_UNASSIGN",
        countdown_seconds=ORF_MAINTENANCE_SHUTDOWN_COUNTDOWN_SECONDS,
    )

    def _shutdown_worker():
        try:
            # Courtesy/countdown window also serves as the write-drain window.
            while True:
                rec = dict(globals().get("__ORF_SYSTEM_QUIESCE__") or {})
                deadline = float(rec.get("deadline_monotonic") or 0.0)
                if not deadline or time.monotonic() >= deadline:
                    break
                time.sleep(min(0.10, max(0.01, deadline - time.monotonic())))

            _set_system_quiesce_state(
                "DRAINING",
                drain_state="FINAL_DRAIN",
                clients_return_to_boot=True,
                countdown_completed_utc=datetime.now(timezone.utc).isoformat(),
            )
            _emit_kernel_loader_capture(
                "SYSTEM_SHUTDOWN_COUNTDOWN_COMPLETE",
                active_writes=system_quiesce_status().get("active_writes"),
            )

            drain_deadline = time.monotonic() + ORF_MAINTENANCE_SHUTDOWN_DRAIN_GRACE_SECONDS
            while system_quiesce_status().get("active_writes", 0) > 0 and time.monotonic() < drain_deadline:
                time.sleep(0.05)

            remaining_writes = int(system_quiesce_status().get("active_writes") or 0)
            drained = remaining_writes == 0
            _set_system_quiesce_state(
                "CLIENT_BOOT",
                drain_state="COMPLETE" if drained else "TIMEOUT",
                drain_timed_out=not drained,
                remaining_writes_at_release=remaining_writes,
                clients_return_to_boot=True,
                client_boot_utc=datetime.now(timezone.utc).isoformat(),
            )
            _emit_kernel_loader_capture(
                "SYSTEM_WRITE_DRAIN_COMPLETE" if drained else "SYSTEM_WRITE_DRAIN_TIMEOUT",
                remaining_writes=remaining_writes,
                grace_seconds=ORF_MAINTENANCE_SHUTDOWN_DRAIN_GRACE_SECONDS,
            )
            _emit_kernel_loader_capture(
                "SYSTEM_CLIENT_BOOT_HANDOFF_WINDOW_OPEN",
                handoff_seconds=ORF_MAINTENANCE_SHUTDOWN_CLIENT_HANDOFF_SECONDS,
                expected_heartbeat_opportunities=max(2, int(ORF_MAINTENANCE_SHUTDOWN_CLIENT_HANDOFF_SECONDS // max(0.25, BOOT_POLL_SECONDS))),
            )

            # Keep the backend alive long enough for multiple BIOS heartbeat cycles.
            # The previous 1.5s/single-opportunity path could deactivate its own Gradio
            # timer on the same tick that changed surface ownership, leaving a prior
            # inline BIOS owner latched in the browser.
            time.sleep(ORF_MAINTENANCE_SHUTDOWN_CLIENT_HANDOFF_SECONDS)
            _set_system_quiesce_state(
                "RUNTIME_RELEASE",
                drain_state="COMPLETE" if drained else "TIMEOUT",
                clients_return_to_boot=True,
                release_utc=datetime.now(timezone.utc).isoformat(),
            )
            _emit_kernel_loader_capture(
                "MAINTENANCE_RUNTIME_UNASSIGN_REQUESTED",
                remaining_writes=remaining_writes,
            )
            from google.colab import runtime as _colab_runtime
            _colab_runtime.unassign()
        except Exception as exc:
            _set_system_quiesce_state(
                "FAILED",
                writes_enabled=False,
                drain_state="FAILED",
                clients_return_to_boot=True,
                failure=f"{type(exc).__name__}: {exc}",
            )
            _emit_kernel_loader_capture(
                "MAINTENANCE_RUNTIME_SHUTDOWN_FAILED",
                error=f"{type(exc).__name__}: {exc}",
            )

    threading.Thread(target=_shutdown_worker, name="orf-colab-quiesce-unassign", daemon=True).start()
    return {
        "state": "SHUTDOWN_COUNTDOWN",
        "action": "QUIESCE_DRAIN_CLIENT_BOOT_COLAB_UNASSIGN",
        "countdown_seconds": int(ORF_MAINTENANCE_SHUTDOWN_COUNTDOWN_SECONDS),
        "writes_enabled": False,
        "message": (
            f"Runtime shutdown accepted. New writes are locked; pending writes may finish. "
            f"Clients return to boot in {int(ORF_MAINTENANCE_SHUTDOWN_COUNTDOWN_SECONDS)}s."
        ),
        "quiesce": quiesce,
    }


def _drive_find_child(parent_id, name):
    matches = [item for item in _drive_list_children(parent_id) if str(item.get("name") or "") == str(name)]
    if len(matches) != 1:
        raise RuntimeError(f"Drive source path component {name!r} under {parent_id} resolved {len(matches)} objects")
    return matches[0]


def _drive_resolve_relative_file(root_folder_id, resource_ref):
    rel = Path(str(resource_ref or ""))
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise RuntimeError(f"Unsafe ORFMOS resource ref: {resource_ref}")
    parent = root_folder_id
    for index, part in enumerate(rel.parts):
        item = _drive_find_child(parent, part)
        is_last = index == len(rel.parts) - 1
        if is_last:
            if item.get("mimeType") == "application/vnd.google-apps.folder":
                raise RuntimeError(f"ORFMOS resource ref resolves to a folder: {resource_ref}")
            return item["id"]
        if item.get("mimeType") != "application/vnd.google-apps.folder":
            raise RuntimeError(f"ORFMOS resource path component is not a folder: {part}")
        parent = item["id"]
    raise RuntimeError(f"Unable to resolve ORFMOS resource ref: {resource_ref}")


def _portable_recovery_manifest_bytes(file_id):
    source = json.loads(_drive_read_bytes(file_id).decode("utf-8"))
    portable = json.loads(json.dumps(source))
    portable["schema"] = "ORF_RECOVERY_DEPENDENCY_MANIFEST_V0_2"
    portable["authority"] = "ORF_RESOURCE_REF_PLUS_SHA256"
    portable["drive_mount_required"] = False
    for dep in portable.get("dependencies") or []:
        drive_id = str(dep.pop("drive_file_id", "") or "").strip()
        runtime_name = str(dep.get("runtime_name") or "resource.bin")
        if drive_id:
            dep["resource_ref"] = f"recovery/objects/{drive_id}/{runtime_name}"
    protected = portable.get("protected_authority") or {}
    protected.pop("keystore_drive_file_id", None)
    protected["keystore_resource_ref"] = "signing/ORF_RELEASE_SIGNING.jks"
    portable["protected_authority"] = protected
    return (json.dumps(portable, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _portable_recovery_target_bytes():
    source = json.loads(_drive_read_bytes(ORF_RUNTIME_RECOVERY_TARGET_DRIVE_FILE_ID).decode("utf-8"))
    if source.get("schema") == "ORF_RUNTIME_TARGET_V0_2" and source.get("dependency_manifest_ref"):
        return (json.dumps(source, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_id = str(source.get("dependency_manifest_drive_file_id") or "").strip()
    if not manifest_id:
        raise RuntimeError("Recovery target lacks dependency manifest authority")
    manifest_bytes = _portable_recovery_manifest_bytes(manifest_id)
    portable = {
        "schema": "ORF_RUNTIME_TARGET_V0_2",
        "target_stage": source.get("target_stage"),
        "request_id": source.get("request_id"),
        "dependency_manifest_ref": f"recovery/manifests/{manifest_id}.json",
        "dependency_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "drive_mount_required": False,
        "source_authority": "BIOS_RECOVERY_ADAPTER",
    }
    return (json.dumps(portable, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _bios_resource_read(resource_ref):
    resource_ref = str(resource_ref or "").strip().lstrip("/")
    if resource_ref == "signing/ORF_RELEASE_SIGNING.jks":
        return _drive_read_bytes(SIGNING_KEYSTORE_DRIVE_FILE_ID)
    if resource_ref == "signing/ORF_SIGNING_RESOLVER.py":
        return _drive_read_bytes(SIGNING_RESOLVER_DRIVE_FILE_ID)
    if resource_ref == "recovery/ORF_RUNTIME_TARGET.json":
        return _portable_recovery_target_bytes()
    manifest_match = re.fullmatch(r"recovery/manifests/([A-Za-z0-9_-]+)\.json", resource_ref)
    if manifest_match:
        return _portable_recovery_manifest_bytes(manifest_match.group(1))
    object_match = re.fullmatch(r"recovery/objects/([A-Za-z0-9_-]+)/.+", resource_ref)
    if object_match:
        return _drive_read_bytes(object_match.group(1))

    root_state = read_root_selection_state()
    root_provider = str(root_state.get("root_source", {}).get("provider") or SOURCE_PROVIDER_GITHUB).upper()
    if root_provider == SOURCE_PROVIDER_DRIVE:
        file_id = _drive_resolve_relative_file(ORFMOS_DRIVE_SOURCE_ROOT_FOLDER_ID, resource_ref)
        return _drive_read_bytes(file_id)
    return _github_raw_bytes(
        ORFMOS_GITHUB_OWNER, ORFMOS_GITHUB_REPO, ORFMOS_GITHUB_REF, resource_ref
    )


def _drive_ensure_folder(parent_id, name):
    matches = [
        item for item in _drive_list_children(parent_id)
        if str(item.get("name") or "") == str(name)
        and item.get("mimeType") == "application/vnd.google-apps.folder"
    ]
    if len(matches) > 1:
        raise RuntimeError(f"Ambiguous Drive persistence folder: {name}")
    if matches:
        return matches[0]["id"]
    created = _bios_drive_service().files().create(
        body={
            "name": str(name),
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        },
        fields="id,name,mimeType",
    ).execute()
    return created["id"]


def _drive_upsert_bytes(parent_id, name, data, mime_type="application/octet-stream"):
    matches = [
        item for item in _drive_list_children(parent_id)
        if str(item.get("name") or "") == str(name)
        and item.get("mimeType") != "application/vnd.google-apps.folder"
    ]
    if len(matches) > 1:
        raise RuntimeError(f"Ambiguous Drive persistence object: {name}")
    media = MediaIoBaseUpload(io.BytesIO(bytes(data)), mimetype=mime_type, resumable=False)
    if matches:
        return _bios_drive_service().files().update(
            fileId=matches[0]["id"], media_body=media,
            fields="id,name,mimeType,modifiedTime,size",
        ).execute()
    return _bios_drive_service().files().create(
        body={"name": str(name), "parents": [parent_id]},
        media_body=media,
        fields="id,name,mimeType,modifiedTime,size",
    ).execute()


@_system_write_operation("BIOS_PERSIST_WRITE")
def _bios_persist_write(resource_ref, data):
    resource_ref = str(resource_ref or "").strip().lstrip("/")
    rel = Path(resource_ref)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise RuntimeError(f"Unsafe ORF persistence ref: {resource_ref}")
    parent = ORF_RECOVERY_ROOT_FOLDER_ID
    parts = list(rel.parts)
    if parts and parts[0] == "recovery":
        parts = parts[1:]
    if not parts:
        raise RuntimeError("ORF persistence ref has no file name")
    for folder_name in parts[:-1]:
        parent = _drive_ensure_folder(parent, folder_name)
    result = _drive_upsert_bytes(parent, parts[-1], bytes(data))
    return {
        "resource_ref": resource_ref,
        "transport": "BIOS_DRIVE_RECOVERY_PERSISTENCE",
        "drive_file_id": result.get("id"),
        "size_bytes": len(data),
        "sha256": hashlib.sha256(bytes(data)).hexdigest(),
    }


# Install provider-neutral resource/persistence hooks. The portable Kernel uses
# these; the legacy Drive Kernel ignores them.
globals()["ORF_BIOS_RESOURCE_READ"] = _bios_resource_read
globals()["ORF_BIOS_PERSIST_WRITE"] = _bios_persist_write

def _dev_load_kernel_cell_source():
    """Resolve the applied Kernel provider and return one verified executable cell."""
    provider = resolve_selected_kernel_source_provider()

    if provider == SOURCE_PROVIDER_DRIVE:
        kernel_notebook_file_id = resolve_selected_kernel_notebook_file_id()
        raw = _drive_read_bytes(kernel_notebook_file_id)
        source = _extract_one_code_cell(raw, "ORF Drive Kernel notebook")
        source_sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if source_sha != DEV_KERNEL_CODE_CELL_SHA256:
            raise RuntimeError(
                "ORF Drive Kernel notebook cell SHA256 mismatch: "
                f"{source_sha} != {DEV_KERNEL_CODE_CELL_SHA256}"
            )
        if DEV_KERNEL_BOOTSTRAP_FILE_ID not in source:
            raise RuntimeError("Expected Kernel bootstrap Drive ID not found in sealed cell.")
        if DEV_KERNEL_BOOTSTRAP_SHA256 not in source:
            raise RuntimeError("Expected Kernel bootstrap SHA256 not found in sealed cell.")
        globals()["ORF_SELECTED_KERNEL_SOURCE_INFO"] = {
            "provider": SOURCE_PROVIDER_DRIVE,
            "notebook_ref": kernel_notebook_file_id,
            "bootstrap_ref": DEV_KERNEL_BOOTSTRAP_FILE_ID,
            "bootstrap_sha256": DEV_KERNEL_BOOTSTRAP_SHA256,
        }
        return source, source_sha, kernel_notebook_file_id

    authority = _active_github_kernel_authority()
    stage_root, manifest = _stage_github_kernel_tree(authority=authority)
    entry_rel = str((manifest.get("entrypoint") or {}).get("path") or KERNEL_NOTEBOOK_NAME)
    entry_bytes = (stage_root / entry_rel).read_bytes()
    source = _extract_one_code_cell(entry_bytes, "ORF GitHub Kernel notebook")
    source_sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
    expected_cell_sha = str(authority.get("entrypoint_cell_sha256") or "").lower()
    if expected_cell_sha and source_sha != expected_cell_sha:
        raise RuntimeError(
            "ORF GitHub Kernel entrypoint cell SHA256 mismatch: "
            f"{source_sha} != {expected_cell_sha}"
        )
    notebook_ref = resolve_selected_kernel_notebook_file_id()
    globals()["ORF_SELECTED_KERNEL_SOURCE_INFO"] = {
        "provider": SOURCE_PROVIDER_GITHUB,
        "notebook_ref": notebook_ref,
        "bootstrap_ref": f"{authority['owner']}/{authority['repo']}@{authority['ref']}:{authority['prefix']}/bootstrap/ORF_KERNEL_BOOTSTRAP.py",
        "bootstrap_sha256": str((manifest.get("bootstrap") or {}).get("sha256") or ""),
        "manifest_sha256": authority["manifest_sha256"],
        "local_stage_root": str(stage_root),
        "authority_source": authority.get("source"),
    }
    return source, source_sha, notebook_ref

@_system_write_operation("KERNEL_REBOOT_REQUEST")
def request_dev_kernel_reboot(reason="BIOS_RESET_BUTTON"):
    """Post a reboot request for the resident monitor; do not execute Kernel here."""
    previous = globals().get("__ORF_KERNEL_REBOOT_REQUEST__") or {}
    previous_state = str(previous.get("state") or "").upper()
    if previous_state in {"REQUESTED", "RUNNING"}:
        _emit_kernel_loader_capture(
            "KERNEL_REBOOT_REQUEST_DUPLICATE",
            request_sequence=int(previous.get("sequence") or 0),
            request_state=previous_state,
        )
        return dict(previous)

    sequence = int(previous.get("sequence") or 0) + 1
    record = {
        "schema": ORF_KERNEL_REBOOT_REQUEST_SCHEMA,
        "sequence": sequence,
        "state": "REQUESTED",
        "reason": str(reason or "BIOS_RESET_BUTTON"),
        "requested_utc": datetime.now(timezone.utc).isoformat(),
        "requested_monotonic_ns": time.monotonic_ns(),
    }
    globals()["__ORF_KERNEL_REBOOT_REQUEST__"] = record

    prior = dict(globals().get("ORF_BOOT_LAST_STATE") or {})
    prior.update({
        "state": "RESETTING",
        "status": "RESETTING",
        "phase": "KERNEL_REBOOT_REQUESTED",
        "ready": False,
        "kernel_alive": False,
        "message": "Kernel reboot requested; resident monitor is taking ownership.",
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "_bios_transport": "LOCAL_SHARED_RUNTIME",
    })
    globals()["ORF_BOOT_LAST_STATE"] = prior
    _emit_kernel_loader_capture(
        "KERNEL_REBOOT_REQUESTED",
        request_sequence=sequence,
        reason=record["reason"],
    )
    return dict(record)


def _set_kernel_reboot_request_state(state, **fields):
    record = dict(globals().get("__ORF_KERNEL_REBOOT_REQUEST__") or {})
    record.setdefault("schema", ORF_KERNEL_REBOOT_REQUEST_SCHEMA)
    record["state"] = str(state)
    record.update(fields)
    globals()["__ORF_KERNEL_REBOOT_REQUEST__"] = record
    return record


def _dev_kernel_reboot_from_monitor(request_record):
    """Execute one verified same-runtime Kernel reboot from monitor ownership."""
    request_sequence = int((request_record or {}).get("sequence") or 0)
    _set_kernel_reboot_request_state(
        "RUNNING", started_utc=datetime.now(timezone.utc).isoformat()
    )
    _emit_kernel_loader_capture(
        "KERNEL_REBOOT_MONITOR_BEGIN", request_sequence=request_sequence
    )
    _set_kernel_power_start_record(
        "RESTARTING",
        started_utc=datetime.now(timezone.utc).isoformat(),
        reboot_request_sequence=request_sequence,
        error=None,
    )
    globals()["__ORF_KERNEL_DEV_AUTOSTARTED__"] = False
    try:
        result = dev_autoboot_kernel()
    except Exception as exc:
        failed_state = dict(globals().get("ORF_BOOT_LAST_STATE") or {})
        rich_failure = str(failed_state.get("message") or "")
        if "\n" not in rich_failure:
            rich_failure = _orf_kernel_execution_failure_message(exc)
        failed_state.update({
            "state": "FAILED",
            "status": "FAILED",
            "phase": "KERNEL_REBOOT_FAILED",
            "ready": False,
            "kernel_alive": False,
            "message": rich_failure,
            "updated_utc": datetime.now(timezone.utc).isoformat(),
            "_bios_transport": "LOCAL_SHARED_RUNTIME",
        })
        globals()["ORF_BOOT_LAST_STATE"] = failed_state
        _set_kernel_reboot_request_state(
            "FAILED",
            completed_utc=datetime.now(timezone.utc).isoformat(),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        _set_kernel_power_start_record(
            "FAILED",
            completed_utc=datetime.now(timezone.utc).isoformat(),
            reboot_request_sequence=request_sequence,
            error=f"{type(exc).__name__}: {exc}",
        )
        _emit_kernel_loader_capture(
            "KERNEL_REBOOT_MONITOR_FAILED",
            request_sequence=request_sequence,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        print("ORF DEV KERNEL REBOOT FAILED:", f"{type(exc).__name__}: {exc}", flush=True)
        traceback.print_exc()
        return False

    _set_kernel_reboot_request_state(
        "COMPLETE",
        completed_utc=datetime.now(timezone.utc).isoformat(),
        boot_id=(result or {}).get("boot_id"),
        heartbeat_sequence=(result or {}).get("heartbeat_sequence"),
    )
    _set_kernel_power_start_record(
        "RUNNING",
        completed_utc=datetime.now(timezone.utc).isoformat(),
        boot_id=(result or {}).get("boot_id"),
        heartbeat_sequence=(result or {}).get("heartbeat_sequence"),
        reboot_request_sequence=request_sequence,
        monitor_alive=True,
        error=None,
    )
    _emit_kernel_loader_capture(
        "KERNEL_REBOOT_MONITOR_COMPLETE",
        request_sequence=request_sequence,
        boot_id=(result or {}).get("boot_id"),
        heartbeat_sequence=(result or {}).get("heartbeat_sequence"),
    )
    return True



# ---- Presentation-safe Kernel execution failure evidence ------------------------
# The active Kernel may intentionally publish a concise failure message before
# re-raising its original exception.  BIOS owns the outer execution boundary, so
# preserve bounded, credential-redacted evidence here for the boot surface.
ORF_KERNEL_FAILURE_OUTPUT_MAX_CHARS = 4800
ORF_KERNEL_FAILURE_OUTPUT_MAX_LINES = 36


def _orf_kernel_failure_text(value):
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="replace")
    return str(value)


def _orf_kernel_failure_redact(value):
    text = _orf_kernel_failure_text(value)
    patterns = [
        (r'(?i)(pass:)[^\s]+', r'\1<REDACTED>'),
        (r'(?i)((?:password|passwd|token|secret|credential)\s*[=:]\s*)[^\s]+', r'\1<REDACTED>'),
        (r'(?i)(--(?:ks-pass|key-pass|storepass|keypass)\s+)([^\s]+)', r'\1<REDACTED>'),
        (r'(?i)(-(?:storepass|keypass)\s+)([^\s]+)', r'\1<REDACTED>'),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text


def _orf_kernel_failure_command(command):
    if isinstance(command, (list, tuple)):
        values = [str(v) for v in command]
        output = []
        redact_next = False
        sensitive = {
            "--ks-pass", "--key-pass", "--storepass", "--keypass",
            "-storepass", "-keypass",
        }
        for value in values:
            if redact_next:
                output.append("<REDACTED>")
                redact_next = False
                continue
            if value.lower() in sensitive:
                output.append(value)
                redact_next = True
                continue
            output.append(_orf_kernel_failure_redact(value))
        try:
            return " ".join(shlex.quote(v) for v in output)
        except Exception:
            return " ".join(output)
    return _orf_kernel_failure_redact(command)


def _orf_kernel_failure_output_tail(value):
    text = _orf_kernel_failure_redact(value).replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines()
    if len(lines) > ORF_KERNEL_FAILURE_OUTPUT_MAX_LINES:
        omitted = len(lines) - ORF_KERNEL_FAILURE_OUTPUT_MAX_LINES
        lines = [f"… {omitted} earlier line(s) omitted …"] + lines[-ORF_KERNEL_FAILURE_OUTPUT_MAX_LINES:]
    text = "\n".join(lines).strip()
    if len(text) > ORF_KERNEL_FAILURE_OUTPUT_MAX_CHARS:
        text = "… earlier output omitted …\\n" + text[-ORF_KERNEL_FAILURE_OUTPUT_MAX_CHARS:]
    return text


def _orf_kernel_request_context():
    path = "/content/ORF_RUNTIME_REQUEST.json"
    try:
        if not os.path.isfile(path):
            return {}
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            return {}
        return {
            "request_id": str(value.get("request_id") or "").strip(),
            "capability": str(value.get("capability") or "").strip(),
        }
    except Exception:
        return {}


def _orf_kernel_execution_failure_message(exc):
    prior = dict(globals().get("ORF_BOOT_LAST_STATE") or {})
    prior_phase = str(prior.get("phase") or "").strip()
    recovery_like = "RECOVERY" in prior_phase.upper()
    label = "Recovery failed" if recovery_like else "Kernel execution failed"
    lines = [f"{label}: {type(exc).__name__}"]
    if prior_phase:
        lines.append(f"Phase: {prior_phase}")

    context = _orf_kernel_request_context()
    if context.get("capability"):
        lines.append(f"Capability: {context['capability']}")
    if context.get("request_id"):
        lines.append(f"Request: {context['request_id']}")

    if isinstance(exc, subprocess.CalledProcessError):
        lines.append(f"Return code: {exc.returncode}")
        command = _orf_kernel_failure_command(getattr(exc, "cmd", None))
        if command:
            lines.append(f"Command: {command}")
        raw_output = getattr(exc, "output", None)
        if not raw_output:
            raw_output = getattr(exc, "stderr", None)
        output = _orf_kernel_failure_output_tail(raw_output)
        if output:
            lines.append("Output tail:")
            lines.append(output)
    else:
        detail = _orf_kernel_failure_redact(exc).strip()
        if detail:
            lines.append(f"Detail: {detail}")

    lines.append("Diagnostic evidence captured by BIOS outer execution boundary.")
    return "\n".join(lines)


def _orf_publish_kernel_execution_failure(exc):
    message = _orf_kernel_execution_failure_message(exc)
    failed_state = dict(globals().get("ORF_BOOT_LAST_STATE") or {})
    failed_state.update({
        "state": "FAILED",
        "status": "FAILED",
        "phase": str(failed_state.get("phase") or "KERNEL_EXECUTION"),
        "ready": False,
        "kernel_alive": False,
        "message": message,
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "_bios_transport": "LOCAL_SHARED_RUNTIME",
    })
    globals()["ORF_BOOT_LAST_STATE"] = failed_state
    globals()["ORF_KERNEL_LAST_EXECUTION_FAILURE"] = {
        "schema": "ORF_KERNEL_EXECUTION_FAILURE_EVIDENCE_V0_1",
        "exception_type": type(exc).__name__,
        "message": message,
        "presentation_safe": True,
        "updated_utc": failed_state["updated_utc"],
    }
    return message

def dev_autoboot_kernel():
    """
    Development-only Kernel invocation.

    A runtime latch prevents re-execution if the BIOS presentation cell is rerun.
    The exact sealed Kernel notebook cell is executed inline by the one-cell BIOS
    loader after all ordered BIOS modules have completed.
    """
    global __ORF_KERNEL_DEV_AUTOSTARTED__

    if not DEV_AUTOBOOT_KERNEL:
        print("ORF DEV KERNEL AUTOBOOT: DISABLED")
        return {"state": "DISABLED"}

    if globals().get("__ORF_KERNEL_DEV_AUTOSTARTED__", False):
        print("ORF DEV KERNEL AUTOBOOT: ALREADY STARTED")
        return {"state": "ALREADY_STARTED"}

    kernel_notebook_file_id = resolve_selected_kernel_notebook_file_id()
    _emit_kernel_loader_capture(
        "SOURCE_VERIFY_BEGIN",
        notebook_file_id=kernel_notebook_file_id,
    )
    source, source_sha, kernel_notebook_file_id = _dev_load_kernel_cell_source()
    _emit_kernel_loader_capture(
        "SOURCE_VERIFIED",
        notebook_file_id=kernel_notebook_file_id,
        source_sha256=source_sha,
    )

    source_info = dict(globals().get("ORF_SELECTED_KERNEL_SOURCE_INFO") or {})
    print("ORF DEV KERNEL AUTOBOOT: VERIFIED", flush=True)
    print("Kernel provider :", source_info.get("provider") or resolve_selected_kernel_source_provider())
    print("Kernel notebook :", kernel_notebook_file_id)
    print("Kernel cell SHA :", source_sha)
    print("Bootstrap ref   :", source_info.get("bootstrap_ref"))
    print("Bootstrap SHA   :", source_info.get("bootstrap_sha256"))
    print("Execution       : CURRENT COLAB RUNTIME / DEVELOPMENT ONLY")

    _emit_kernel_loader_capture(
        "EXEC_BEGIN",
        notebook_file_id=kernel_notebook_file_id,
        source_sha256=source_sha,
    )
    try:
        exec(
            compile(
                source,
                "<ORF_KERNEL_NOTEBOOK_CELL:ONE_CELL_MODULAR_LOADER_RUNNER>",
                "exec",
            ),
            globals(),
            globals(),
        )
    except Exception as exc:
        # Permit an intentional retry after a failed development start.
        __ORF_KERNEL_DEV_AUTOSTARTED__ = False
        rich_failure = _orf_publish_kernel_execution_failure(exc)
        _emit_kernel_loader_capture(
            "EXEC_FAILED",
            error_type=type(exc).__name__,
            error=rich_failure.splitlines()[0],
            rich_failure=True,
        )
        print("ORF KERNEL EXECUTION FAILURE EVIDENCE:", flush=True)
        print(rich_failure, flush=True)
        raise

    _emit_kernel_loader_capture(
        "EXEC_RETURNED",
        notebook_file_id=kernel_notebook_file_id,
        source_sha256=source_sha,
    )

    monitor_tick = globals().get("orf_kernel_monitor_tick")
    if not callable(monitor_tick):
        __ORF_KERNEL_DEV_AUTOSTARTED__ = False
        _emit_kernel_loader_capture(
            "MONITOR_CONTRACT_MISSING",
            required_callable="orf_kernel_monitor_tick",
        )
        raise RuntimeError(
            "ORF Kernel bootstrap returned without resident monitor contract: "
            "orf_kernel_monitor_tick"
        )

    first_pulse = monitor_tick()
    __ORF_KERNEL_DEV_AUTOSTARTED__ = True
    _emit_kernel_loader_capture(
        "MONITOR_READY",
        boot_id=(first_pulse or {}).get("boot_id"),
        boot_sequence=(first_pulse or {}).get("sequence"),
        heartbeat_sequence=(first_pulse or {}).get("heartbeat_sequence"),
        heartbeat_utc=(first_pulse or {}).get("heartbeat_utc"),
        kernel_alive=bool((first_pulse or {}).get("kernel_alive")),
    )

    return {
        "state": "MONITORING",
        "kernel_notebook_file_id": kernel_notebook_file_id,
        "kernel_cell_sha256": source_sha,
        "boot_id": (first_pulse or {}).get("boot_id"),
        "heartbeat_sequence": (first_pulse or {}).get("heartbeat_sequence"),
    }


def _dev_kernel_monitor_worker():
    """Resident monitor: pulse current Kernel and own requested same-runtime reboots."""
    _emit_kernel_loader_capture(
        "MONITOR_WORKER_ENTER",
        notebook_file_id=resolve_selected_kernel_notebook_file_id(),
        cadence_seconds=float(DEV_KERNEL_MONITOR_SECONDS),
    )

    try:
        if not callable(globals().get("orf_kernel_monitor_tick")):
            raise RuntimeError(
                "ORF Kernel monitor worker started before inline Kernel bootstrap "
                "established orf_kernel_monitor_tick"
            )
        if not globals().get("__ORF_KERNEL_DEV_AUTOSTARTED__", False):
            raise RuntimeError(
                "ORF Kernel monitor worker started before inline Kernel boot completed"
            )

        _emit_kernel_loader_capture(
            "WORKER_MONITORING",
            result_state="MONITORING",
            cadence_seconds=float(DEV_KERNEL_MONITOR_SECONDS),
        )

        last_reported_state = None
        while True:
            time.sleep(float(DEV_KERNEL_MONITOR_SECONDS))

            quiesce = system_quiesce_status()
            if str(quiesce.get("state") or "RUNNING").upper() != "RUNNING":
                if last_reported_state != "__QUIESCED__":
                    _emit_kernel_loader_capture(
                        "KERNEL_MONITOR_QUIESCED",
                        shutdown_state=quiesce.get("state"),
                        active_writes=quiesce.get("active_writes"),
                    )
                last_reported_state = "__QUIESCED__"
                continue

            reboot_request = dict(globals().get("__ORF_KERNEL_REBOOT_REQUEST__") or {})
            if str(reboot_request.get("state") or "").upper() == "REQUESTED":
                _dev_kernel_reboot_from_monitor(reboot_request)
                last_reported_state = None
                continue

            monitor_tick = globals().get("orf_kernel_monitor_tick")
            if not callable(monitor_tick):
                _emit_kernel_loader_capture(
                    "MONITOR_CONTRACT_TEMPORARILY_MISSING",
                    request_state=str(reboot_request.get("state") or "NONE"),
                )
                continue

            _system_write_begin("KERNEL_MONITOR_PULSE")
            try:
                pulse = monitor_tick()
            finally:
                _system_write_end("KERNEL_MONITOR_PULSE")
            heartbeat_sequence = int((pulse or {}).get("heartbeat_sequence") or 0)
            pulse_state = str((pulse or {}).get("state") or "UNKNOWN")
            if heartbeat_sequence <= 3 or pulse_state != last_reported_state or heartbeat_sequence % 10 == 0:
                _emit_kernel_loader_capture(
                    "MONITOR_PULSE",
                    boot_id=(pulse or {}).get("boot_id"),
                    boot_sequence=(pulse or {}).get("sequence"),
                    heartbeat_sequence=heartbeat_sequence,
                    heartbeat_utc=(pulse or {}).get("heartbeat_utc"),
                    kernel_alive=bool((pulse or {}).get("kernel_alive")),
                    state=pulse_state,
                    phase=(pulse or {}).get("phase"),
                )
            last_reported_state = pulse_state
    except Exception as exc:
        _emit_kernel_loader_capture(
            "MONITOR_WORKER_FAILED",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        print(
            "ORF DEV KERNEL MONITOR FAILED:",
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        traceback.print_exc()


def start_dev_kernel_monitor():
    """Start only the recurring monitor after the loader's inline Kernel boot."""
    global __ORF_KERNEL_DEV_AUTOSTART_THREAD_STARTED__
    global __ORF_KERNEL_DEV_AUTOSTART_THREAD__

    if not callable(globals().get("orf_kernel_monitor_tick")):
        raise RuntimeError(
            "Cannot start ORF Kernel monitor before inline Kernel boot establishes "
            "orf_kernel_monitor_tick"
        )

    existing_thread = globals().get("__ORF_KERNEL_DEV_AUTOSTART_THREAD__")
    if existing_thread is not None and existing_thread.is_alive():
        print("ORF DEV KERNEL MONITOR THREAD: ALREADY LIVE", flush=True)
        return existing_thread

    __ORF_KERNEL_DEV_AUTOSTART_THREAD_STARTED__ = True
    __ORF_KERNEL_DEV_AUTOSTART_THREAD__ = threading.Thread(
        target=_dev_kernel_monitor_worker,
        name="ORF_DEV_KERNEL_MONITOR",
        daemon=True,
    )
    __ORF_KERNEL_DEV_AUTOSTART_THREAD__.start()
    print(
        "ORF DEV KERNEL MONITOR STARTED:",
        f"{DEV_KERNEL_MONITOR_SECONDS:.1f}s pulse / bootstrap already complete",
        flush=True,
    )
    return __ORF_KERNEL_DEV_AUTOSTART_THREAD__


ORF_KERNEL_POWER_START_SCHEMA = "ORF_KERNEL_POWER_START_V0_2"
if "__ORF_KERNEL_POWER_START_LOCK__" not in globals():
    __ORF_KERNEL_POWER_START_LOCK__ = threading.Lock()
if "__ORF_KERNEL_POWER_START_RECORD__" not in globals():
    __ORF_KERNEL_POWER_START_RECORD__ = {
        "schema": ORF_KERNEL_POWER_START_SCHEMA,
        "sequence": 0,
        "state": "OFF",
        "reason": "WAITING_FOR_POWER",
        "requested_utc": None,
        "started_utc": None,
        "completed_utc": None,
        "error": None,
    }


def _set_kernel_power_start_record(state, **fields):
    previous = dict(globals().get("__ORF_KERNEL_POWER_START_RECORD__") or {})
    record = {
        "schema": ORF_KERNEL_POWER_START_SCHEMA,
        "sequence": int(previous.get("sequence") or 0),
        "state": str(state or "UNKNOWN").upper(),
        "reason": previous.get("reason"),
        "requested_utc": previous.get("requested_utc"),
        "started_utc": previous.get("started_utc"),
        "completed_utc": previous.get("completed_utc"),
        "error": previous.get("error"),
    }
    record.update(fields)
    globals()["__ORF_KERNEL_POWER_START_RECORD__"] = record
    return dict(record)


def read_dev_kernel_power_start_record():
    return dict(globals().get("__ORF_KERNEL_POWER_START_RECORD__") or {})


def _dev_kernel_power_start_worker(reason):
    _set_kernel_power_start_record(
        "BOOTING",
        reason=str(reason or "BOOT_POWER_BUTTON"),
        started_utc=datetime.now(timezone.utc).isoformat(),
        error=None,
    )
    _emit_kernel_loader_capture(
        "POWER_KERNEL_BOOT_BEGIN",
        reason=str(reason or "BOOT_POWER_BUTTON"),
    )
    try:
        result = dev_autoboot_kernel()
        monitor_thread = start_dev_kernel_monitor()
        if monitor_thread is None or not monitor_thread.is_alive():
            raise RuntimeError("ORF Kernel monitor thread failed to establish after power start")
        record = _set_kernel_power_start_record(
            "RUNNING",
            reason=str(reason or "BOOT_POWER_BUTTON"),
            completed_utc=datetime.now(timezone.utc).isoformat(),
            boot_id=(result or {}).get("boot_id"),
            heartbeat_sequence=(result or {}).get("heartbeat_sequence"),
            monitor_thread=str(getattr(monitor_thread, "name", "")),
            monitor_alive=bool(monitor_thread.is_alive()),
            error=None,
        )
        _emit_kernel_loader_capture(
            "POWER_KERNEL_BOOT_COMPLETE",
            reason=str(reason or "BOOT_POWER_BUTTON"),
            boot_id=(result or {}).get("boot_id"),
            heartbeat_sequence=(result or {}).get("heartbeat_sequence"),
            monitor_alive=bool(monitor_thread.is_alive()),
        )
        return record
    except Exception as exc:
        record = _set_kernel_power_start_record(
            "FAILED",
            reason=str(reason or "BOOT_POWER_BUTTON"),
            completed_utc=datetime.now(timezone.utc).isoformat(),
            error=f"{type(exc).__name__}: {exc}",
        )
        _emit_kernel_loader_capture(
            "POWER_KERNEL_BOOT_FAILED",
            reason=str(reason or "BOOT_POWER_BUTTON"),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        print(
            "ORF DEV KERNEL POWER START FAILED:",
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        traceback.print_exc()
        return record


def request_dev_kernel_power_start(reason="BOOT_POWER_BUTTON"):
    """POWER edge: cold-start a stopped Kernel or reboot an already-live Kernel."""
    global __ORF_KERNEL_POWER_START_THREAD__

    reason = str(reason or "BOOT_POWER_BUTTON")
    lock = globals()["__ORF_KERNEL_POWER_START_LOCK__"]
    with lock:
        existing_monitor = globals().get("__ORF_KERNEL_DEV_AUTOSTART_THREAD__")
        if (
            globals().get("__ORF_KERNEL_DEV_AUTOSTARTED__", False)
            and existing_monitor is not None
            and existing_monitor.is_alive()
        ):
            # A rerun of the BIOS loader can inherit a resident Kernel that is already
            # READY.  POWER must still create a new boot edge, otherwise READY can win
            # before the operator has time to request BIOS.  Hand the reboot to the
            # resident monitor and hold the power-start record non-RUNNING until the
            # new Kernel boot completes.
            reboot_request = request_dev_kernel_reboot(reason=reason)
            previous = read_dev_kernel_power_start_record()
            sequence = int(previous.get("sequence") or 0) + 1
            record = {
                "schema": ORF_KERNEL_POWER_START_SCHEMA,
                "sequence": sequence,
                "state": "RESTART_REQUESTED",
                "reason": reason,
                "requested_utc": datetime.now(timezone.utc).isoformat(),
                "started_utc": None,
                "completed_utc": None,
                "reboot_request_sequence": int((reboot_request or {}).get("sequence") or 0),
                "monitor_thread": str(getattr(existing_monitor, "name", "")),
                "monitor_alive": True,
                "error": None,
            }
            globals()["__ORF_KERNEL_POWER_START_RECORD__"] = record
            _emit_kernel_loader_capture(
                "POWER_KERNEL_RESTART_REQUESTED",
                request_sequence=sequence,
                reboot_request_sequence=record["reboot_request_sequence"],
                reason=reason,
            )
            return dict(record)

        existing_start = globals().get("__ORF_KERNEL_POWER_START_THREAD__")
        if existing_start is not None and existing_start.is_alive():
            return read_dev_kernel_power_start_record()

        previous = read_dev_kernel_power_start_record()
        sequence = int(previous.get("sequence") or 0) + 1
        record = {
            "schema": ORF_KERNEL_POWER_START_SCHEMA,
            "sequence": sequence,
            "state": "REQUESTED",
            "reason": reason,
            "requested_utc": datetime.now(timezone.utc).isoformat(),
            "started_utc": None,
            "completed_utc": None,
            "error": None,
        }
        globals()["__ORF_KERNEL_POWER_START_RECORD__"] = record
        _emit_kernel_loader_capture(
            "POWER_KERNEL_BOOT_REQUESTED",
            request_sequence=sequence,
            reason=reason,
        )
        __ORF_KERNEL_POWER_START_THREAD__ = threading.Thread(
            target=_dev_kernel_power_start_worker,
            args=(reason,),
            name=f"ORF_KERNEL_POWER_START_{sequence}",
            daemon=True,
        )
        __ORF_KERNEL_POWER_START_THREAD__.start()
        globals()["__ORF_KERNEL_POWER_START_THREAD__"] = __ORF_KERNEL_POWER_START_THREAD__
        return dict(record)


def safe_read_boot_state():
    try:
        return read_boot_state()
    except Exception as exc:
        return {
            "schema": BOOT_STATE_SCHEMA,
            "boot_id": "ORF_BOOT_STATE_READ_FAILED",
            "sequence": -1,
            "state": "FAILED",
            "phase": "PRESENTATION_STATE_READ",
            "progress": 0,
            "message": f"Boot state read failed: {type(exc).__name__}: {exc}",
            "node": "BIOS_PRESENTATION",
            "ready": False,
        }

BOOT_RAW_URL = (
    f"https://raw.githubusercontent.com/"
    f"{BOOT_OWNER}/{BOOT_REPO}/{BOOT_REF}/{BOOT_PATH}"
)

print("=" * 92)
print("ORFMOS BIOS DEVELOPMENT v0.1")
print("=" * 92)
print("Gradio version :", gr.__version__)
print("Boot source    :", f"{BOOT_OWNER}/{BOOT_REPO}@{BOOT_REF[:12]}/{BOOT_PATH}")

response = requests.get(BOOT_RAW_URL, timeout=30)
response.raise_for_status()
BOOT_HTML_BYTES = response.content
BOOT_HTML_SHA256 = hashlib.sha256(BOOT_HTML_BYTES).hexdigest()

if BOOT_HTML_SHA256 != EXPECTED_BOOT_SHA256:
    raise RuntimeError(
        "ORF BOOT SOURCE HASH MISMATCH\n"
        f"Expected: {EXPECTED_BOOT_SHA256}\n"
        f"Observed: {BOOT_HTML_SHA256}"
    )

# Preserve the accepted GitHub bytes as the presentation source.
# Only a transient state-init script is injected into the development host copy.
BOOT_HTML_TEXT = BOOT_HTML_BYTES.decode("utf-8")

# The durable Drive object is useful as a previous-boot health record, but on a
# new Colab runtime it is history rather than proof that the current Kernel is
# READY. Preserve it as the freshness baseline while presenting a cold-start
# WAITING state until this runtime publishes its own Kernel observation.
BOOT_INITIAL_STATE = safe_read_boot_state()
BOOT_INITIAL_PRESENTATION_STATE = dict(BOOT_INITIAL_STATE or {})
_previous_boot_state = str(BOOT_INITIAL_STATE.get("state") or "UNKNOWN").upper()
_previous_boot_phase = str(BOOT_INITIAL_STATE.get("phase") or "UNKNOWN").upper()
_previous_boot_ready = bool(BOOT_INITIAL_STATE.get("ready"))
BOOT_INITIAL_PRESENTATION_STATE.update({
    "state": "WAITING",
    "phase": "SCANNING",
    "progress": 0.0,
    "message": (
        f"Previous boot {_previous_boot_state}; scanning for current Kernel signal"
        if _previous_boot_state != "UNKNOWN"
        else "Scanning for current Kernel signal"
    ),
    "ready": False,
    "kernel_alive": False,
    "heartbeat_sequence": 0,
    "heartbeat_utc": None,
    "_bios_previous_state": _previous_boot_state,
    "_bios_previous_phase": _previous_boot_phase,
    "_bios_previous_ready": _previous_boot_ready,
    "_bios_previous_boot_id": BOOT_INITIAL_STATE.get("boot_id"),
    "_bios_previous_sequence": BOOT_INITIAL_STATE.get("sequence"),
    "_bios_previous_updated_utc": BOOT_INITIAL_STATE.get("updated_utc"),
})
ROOT_INITIAL_STATE = safe_read_root_selection_state()

_initial_state_json = json.dumps(
    BOOT_INITIAL_PRESENTATION_STATE,
    separators=(",", ":"),
    ensure_ascii=False,
).replace("</", "<\\/")

_initial_state_script = f"""
<script>
window.addEventListener("load", function() {{
  try {{
    if (window.ORF_BOOT && typeof window.ORF_BOOT.update === "function") {{
      window.ORF_BOOT.update({_initial_state_json});
    }}
  }} catch (error) {{
    console.error("ORF BIOS initial boot-state handoff failed", error);
  }}
}});
</script>
"""

if "</body>" in BOOT_HTML_TEXT:
    BOOT_HOST_HTML = BOOT_HTML_TEXT.replace(
        "</body>",
        _initial_state_script + "\n</body>",
        1,
    )
else:
    BOOT_HOST_HTML = BOOT_HTML_TEXT + _initial_state_script

# srcdoc is same-origin with the Gradio host, allowing the host to call
# frame.contentWindow.ORF_BOOT.update(...) on later polling ticks.
BOOT_SRCDOC = html_lib.escape(BOOT_HOST_HTML, quote=True)

print("Boot bytes     :", len(BOOT_HTML_BYTES))
print("Boot SHA256    :", BOOT_HTML_SHA256)
print("Boot authority : PINNED + VERIFIED")
print("Previous boot  :", BOOT_INITIAL_STATE.get("state"))
print("Previous phase :", BOOT_INITIAL_STATE.get("phase"))
print("Boot display   :", BOOT_INITIAL_PRESENTATION_STATE.get("state"))
print("Display phase  :", BOOT_INITIAL_PRESENTATION_STATE.get("phase"))
print("Boot sequence  :", BOOT_INITIAL_STATE.get("sequence"))
print("State source   :", BOOT_STATE_FILE_ID)
print("Kernel source  :", ROOT_INITIAL_STATE.get("kernel_source", {}).get("provider"))
print("Kernel state   :", ROOT_INITIAL_STATE.get("kernel_source", {}).get("selection_state"))
print("Kernel path    :", ROOT_INITIAL_STATE.get("kernel", {}).get("relative_path"))
print("Root source    :", ROOT_INITIAL_STATE.get("root_source", {}).get("provider"))
print("Root state     :", ROOT_INITIAL_STATE.get("root_source", {}).get("selection_state"))
print("Active root    :", ROOT_INITIAL_STATE.get("active_root", {}).get("root_id"))
print("Root authority :", ROOT_INITIAL_STATE.get("authority"))
print("Root mode      :", ROOT_RESOLUTION_MODE)
print("Runtime        : READY")
