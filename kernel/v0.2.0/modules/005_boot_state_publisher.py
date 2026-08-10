# ORF KERNEL — BOOT STATE PUBLISHER
# Provider-neutral lifecycle + liveness publication surface.
# Live state is local shared runtime authority. BIOS may optionally supply a
# presentation/persistence sink, but the Kernel performs no cloud/auth I/O.

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import platform
import shutil
import time
import uuid

ORF_BOOT_STATE_SCHEMA = "ORF_BOOT_STATE_V0_1"
ORF_BOOT_NODE_ID = str(globals().get("ORF_KERNEL_NODE_ID") or "COLAB_KERNEL")
ORF_BOOT_LOCAL_PATH = Path(
    globals().get("ORF_KERNEL_BOOT_STATE_PATH")
    or "/content/.orf_runtime/ORF_BOOT_STATE.json"
)

def _orf_boot_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _orf_runtime_environment_snapshot() -> dict:
    snapshot = {
        "schema": "ORF_RUNTIME_ENVIRONMENT_V0_1",
        "provider": str(globals().get("ORF_RUNTIME_PROVIDER") or "COLAB"),
        "node": ORF_BOOT_NODE_ID,
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "cpu_percent": None,
        "memory_total_bytes": None,
        "memory_available_bytes": None,
        "memory_percent": None,
        "disk_path": "/content",
        "disk_total_bytes": None,
        "disk_free_bytes": None,
        "disk_percent": None,
        "process_rss_bytes": None,
        "process_uptime_seconds": None,
    }
    try:
        import psutil
        proc = psutil.Process(os.getpid())
        vm = psutil.virtual_memory()
        snapshot["cpu_percent"] = round(float(psutil.cpu_percent(interval=0.05)), 1)
        snapshot["memory_total_bytes"] = int(vm.total)
        snapshot["memory_available_bytes"] = int(vm.available)
        snapshot["memory_percent"] = round(float(vm.percent), 1)
        snapshot["process_rss_bytes"] = int(proc.memory_info().rss)
        snapshot["process_uptime_seconds"] = max(
            0.0, round(float(time.time() - proc.create_time()), 1)
        )
    except Exception:
        pass
    try:
        disk = shutil.disk_usage("/content")
        used = int(disk.total - disk.free)
        snapshot["disk_total_bytes"] = int(disk.total)
        snapshot["disk_free_bytes"] = int(disk.free)
        snapshot["disk_percent"] = round((used / disk.total) * 100.0, 1) if disk.total else None
    except Exception:
        pass
    return snapshot

_ORF_BOOT_SEQUENCE = 0
_ORF_BOOT_ID = "ORF_BOOT_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid.uuid4().hex[:8]
ORF_BOOT_SERVICE_STATES = {}
ORF_BOOT_LAST_STATE = None

ORF_KERNEL_MONITOR_SCHEMA = "ORF_KERNEL_MONITOR_V0_1"
ORF_KERNEL_MONITOR_ACTIVE = False
ORF_KERNEL_HEARTBEAT_SEQUENCE = 0
ORF_KERNEL_HEARTBEAT_UTC = None
ORF_KERNEL_MONITOR_STARTED_UTC = None

def _orf_local_state_write(payload: dict) -> None:
    try:
        ORF_BOOT_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        ORF_BOOT_LOCAL_PATH.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"ORF BOOT LOCAL STATE WARNING: {type(exc).__name__}: {exc}")

def _orf_emit_state(payload: dict) -> None:
    _orf_local_state_write(payload)
    sink = globals().get("ORF_BIOS_BOOT_STATE_SINK")
    if callable(sink):
        try:
            sink(dict(payload))
        except Exception as exc:
            print(f"ORF BOOT STATE SINK WARNING: {type(exc).__name__}: {exc}")

def orf_publish_boot_state(
    state: str,
    phase: str,
    progress: float,
    message: str,
    *,
    ready: bool = False,
    service_states: dict | None = None,
    advance_sequence: bool = True,
) -> dict:
    global _ORF_BOOT_SEQUENCE, ORF_BOOT_LAST_STATE
    if advance_sequence:
        _ORF_BOOT_SEQUENCE += 1
    payload = {
        "schema": ORF_BOOT_STATE_SCHEMA,
        "boot_id": _ORF_BOOT_ID,
        "sequence": _ORF_BOOT_SEQUENCE,
        "state": str(state),
        "phase": str(phase),
        "progress": max(0.0, min(1.0, float(progress))),
        "message": str(message),
        "node": ORF_BOOT_NODE_ID,
        "ready": bool(ready),
        "updated_utc": _orf_boot_utc_now(),
        "kernel_id": (globals().get("manifest") or {}).get("kernel_id"),
        "kernel_version": (globals().get("manifest") or {}).get("version"),
        "services": dict(service_states if service_states is not None else ORF_BOOT_SERVICE_STATES),
        "runtime_environment": _orf_runtime_environment_snapshot(),
        "kernel_alive": bool(ORF_KERNEL_MONITOR_ACTIVE),
        "heartbeat_sequence": int(ORF_KERNEL_HEARTBEAT_SEQUENCE),
        "heartbeat_utc": ORF_KERNEL_HEARTBEAT_UTC,
        "monitor_schema": ORF_KERNEL_MONITOR_SCHEMA,
        "monitor_mode": "LOCAL_SHARED_RUNTIME_TICK" if ORF_KERNEL_MONITOR_ACTIVE else "BOOTSTRAP",
        "monitor_started_utc": ORF_KERNEL_MONITOR_STARTED_UTC,
        "_bios_transport": "LOCAL_SHARED_RUNTIME",
    }
    ORF_BOOT_LAST_STATE = payload
    _orf_emit_state(payload)
    return payload

def orf_service_transition(
    service_id: str,
    service_state: str,
    *,
    message: str = "",
    phase: str | None = None,
    progress: float | None = None,
) -> dict:
    ORF_BOOT_SERVICE_STATES[str(service_id)] = {
        "state": str(service_state),
        "message": str(message),
        "updated_utc": _orf_boot_utc_now(),
    }
    if phase is not None and progress is not None:
        return orf_publish_boot_state(
            "STARTING" if service_state not in {"READY", "FAILED"} else service_state,
            phase,
            progress,
            message or f"{service_id}: {service_state}",
            ready=(service_state == "READY"),
        )
    return dict(ORF_BOOT_SERVICE_STATES[str(service_id)])

def orf_kernel_monitor_tick() -> dict:
    global ORF_KERNEL_MONITOR_ACTIVE
    global ORF_KERNEL_HEARTBEAT_SEQUENCE
    global ORF_KERNEL_HEARTBEAT_UTC
    global ORF_KERNEL_MONITOR_STARTED_UTC
    global ORF_BOOT_LAST_STATE

    now = _orf_boot_utc_now()
    if ORF_KERNEL_MONITOR_STARTED_UTC is None:
        ORF_KERNEL_MONITOR_STARTED_UTC = now
    ORF_KERNEL_MONITOR_ACTIVE = True
    ORF_KERNEL_HEARTBEAT_SEQUENCE += 1
    ORF_KERNEL_HEARTBEAT_UTC = now

    last = dict(ORF_BOOT_LAST_STATE or {})
    state = str(last.get("state") or "STARTING")
    phase = str(last.get("phase") or "KERNEL_MONITOR")
    progress = float(last.get("progress") or 0.0)
    message = str(last.get("message") or "Kernel monitor active")
    ready = bool(last.get("ready")) or state.upper() == "READY"

    payload = dict(last)
    payload.update({
        "schema": ORF_BOOT_STATE_SCHEMA,
        "boot_id": _ORF_BOOT_ID,
        "sequence": _ORF_BOOT_SEQUENCE,
        "state": state,
        "phase": phase,
        "progress": max(0.0, min(1.0, progress)),
        "message": message,
        "node": ORF_BOOT_NODE_ID,
        "ready": ready,
        "updated_utc": now,
        "kernel_id": (globals().get("manifest") or {}).get("kernel_id"),
        "kernel_version": (globals().get("manifest") or {}).get("version"),
        "services": dict(ORF_BOOT_SERVICE_STATES),
        "kernel_alive": True,
        "heartbeat_sequence": int(ORF_KERNEL_HEARTBEAT_SEQUENCE),
        "heartbeat_utc": ORF_KERNEL_HEARTBEAT_UTC,
        "monitor_schema": ORF_KERNEL_MONITOR_SCHEMA,
        "monitor_mode": "LOCAL_SHARED_RUNTIME_TICK",
        "monitor_started_utc": ORF_KERNEL_MONITOR_STARTED_UTC,
        "_bios_transport": "LOCAL_SHARED_RUNTIME",
    })
    ORF_BOOT_LAST_STATE = payload
    _orf_emit_state(payload)
    return payload

def orf_kernel_monitor_snapshot() -> dict:
    return {
        "schema": ORF_KERNEL_MONITOR_SCHEMA,
        "active": bool(ORF_KERNEL_MONITOR_ACTIVE),
        "heartbeat_sequence": int(ORF_KERNEL_HEARTBEAT_SEQUENCE),
        "heartbeat_utc": ORF_KERNEL_HEARTBEAT_UTC,
        "monitor_started_utc": ORF_KERNEL_MONITOR_STARTED_UTC,
        "boot_id": _ORF_BOOT_ID,
        "boot_sequence": int(_ORF_BOOT_SEQUENCE),
        "state": (ORF_BOOT_LAST_STATE or {}).get("state"),
        "phase": (ORF_BOOT_LAST_STATE or {}).get("phase"),
    }

orf_publish_boot_state(
    "CONNECTING",
    "KERNEL_MANIFEST",
    0.10,
    "Kernel manifest verified; loading ORF services",
)
