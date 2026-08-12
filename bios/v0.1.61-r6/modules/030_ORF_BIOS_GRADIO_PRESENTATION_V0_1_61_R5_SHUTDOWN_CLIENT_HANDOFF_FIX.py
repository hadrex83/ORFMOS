import time
import uuid
import json
import copy
import re
import secrets
import threading
from datetime import datetime, timezone

BIOS_VERSION = "0.1.61"
# ======================================================================================
# CELL 3 — GRADIO BIOS PRESENTATION
# ======================================================================================

# Preserve the prior presentation object before this module constructs a new
# generation in the same Colab runtime.  Cell 4 retires it only after the new
# generation is published, giving the old surface time to redirect cleanly.
__ORF_BIOS_PREVIOUS_DEMO__ = globals().get("demo")
__ORF_BIOS_PREVIOUS_PRESENTATION_GENERATION__ = globals().get(
    "ORF_BIOS_PRESENTATION_GENERATION_ID"
)

ORF_BIOS_PRESENTATION_SCHEMA = "ORF_BIOS_PRESENTATION_GENERATION_V0_1"
ORF_BIOS_USER_ACTIVITY_SCHEMA = "ORF_BIOS_USER_ACTIVITY_V0_1"
BOOT_BIOS_REQUEST_WINDOW_SECONDS = max(0.0, float(globals().get("BOOT_READY_ELIGIBLE_SECONDS", 3.0)))


def _record_user_interaction(action):
    """Record one real browser/control -> Python runtime interaction."""
    previous = globals().get("__ORF_BIOS_USER_ACTIVITY__") or {}
    sequence = int(previous.get("sequence") or 0) + 1
    record = {
        "schema": ORF_BIOS_USER_ACTIVITY_SCHEMA,
        "sequence": sequence,
        "action": str(action or "UNKNOWN"),
        "last_interaction_utc": datetime.now(timezone.utc).isoformat(),
        "last_interaction_monotonic": time.monotonic(),
    }
    globals()["__ORF_BIOS_USER_ACTIVITY__"] = record
    return record


def _with_user_activity(action, fn):
    """Wrap an existing Gradio callback without creating a parallel control path."""
    def _wrapped(*args, **kwargs):
        _record_user_interaction(action)
        return fn(*args, **kwargs)
    return _wrapped


def _new_presentation_generation_id():
    return f"ORF_BIOS_PRESENTATION_{uuid.uuid4().hex[:16]}"


# ======================================================================================
# DEVICE SESSION / PROFILE / TELEMETRY PROBE v0.2
# ======================================================================================
ORF_DEVICE_SESSION_SCHEMA = "ORF_DEVICE_SESSION_V0_1"
ORF_DEVICE_PROFILE_SCHEMA = "ORF_DEVICE_PROFILE_V0_1"
ORF_DEVICE_TELEMETRY_SCHEMA = "ORF_DEVICE_TELEMETRY_V0_1"
ORF_DEVICE_OBSERVATION_EXPORT_SCHEMA = "ORF_DEVICE_OBSERVATION_EXPORT_V0_1"
ORF_DEVICE_OBSERVATIONS_ROOT_FOLDER_ID = "1fEZ5t_keh_SG0aXfIh6vFVoQWQbdHKP2"
ORF_DEVICE_SESSION_STALE_SECONDS = 18.0
ORF_DEVICE_SESSION_RETENTION_SECONDS = 900.0

_ORF_DEVICE_SESSION_LOCK = globals().get("_ORF_DEVICE_SESSION_LOCK") or threading.RLock()
_ORF_DEVICE_SESSIONS = globals().get("_ORF_DEVICE_SESSIONS") or {}
globals()["_ORF_DEVICE_SESSION_LOCK"] = _ORF_DEVICE_SESSION_LOCK
globals()["_ORF_DEVICE_SESSIONS"] = _ORF_DEVICE_SESSIONS


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _parse_utc(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _orf_session_is_fresh(record, now=None):
    now = now or datetime.now(timezone.utc)
    seen = _parse_utc((record or {}).get("last_seen_utc"))
    if seen is None:
        return False
    return max(0.0, (now - seen).total_seconds()) <= ORF_DEVICE_SESSION_STALE_SECONDS


def _orf_session_prune():
    now = datetime.now(timezone.utc)
    with _ORF_DEVICE_SESSION_LOCK:
        remove = []
        for session_id, record in _ORF_DEVICE_SESSIONS.items():
            seen = _parse_utc(record.get("last_seen_utc"))
            age = (now - seen).total_seconds() if seen else 1e12
            if age > ORF_DEVICE_SESSION_RETENTION_SECONDS:
                remove.append(session_id)
            elif age > ORF_DEVICE_SESSION_STALE_SECONDS:
                record["session_state"] = "STALE"
                record["telemetry_state"] = "STALE"
        for session_id in remove:
            _ORF_DEVICE_SESSIONS.pop(session_id, None)


def _orf_session_summary():
    _orf_session_prune()
    now = datetime.now(timezone.utc)
    with _ORF_DEVICE_SESSION_LOCK:
        fresh = [copy.deepcopy(v) for v in _ORF_DEVICE_SESSIONS.values() if _orf_session_is_fresh(v, now)]
    clients = {str(v.get("client_instance_id") or v.get("session_id")) for v in fresh}
    telemetry = [v for v in fresh if str(v.get("telemetry_state") or "").upper() == "ACTIVE"]
    return {
        "connected_devices": len(clients),
        "active_sessions": len(fresh),
        "telemetry_streams": len(telemetry),
    }


def _request_network_observations(request):
    if request is None:
        return {}
    headers = {}
    try:
        raw_headers = dict(request.headers or {})
        for key in ("x-forwarded-for", "x-real-ip", "cf-connecting-ip", "forwarded", "user-agent"):
            if raw_headers.get(key):
                headers[key] = raw_headers.get(key)
    except Exception:
        pass
    peer = None
    try:
        peer = request.client.host if request.client else None
    except Exception:
        pass
    return {
        "peer_address": peer,
        "forwarding_headers": headers,
        "observation_authority": "NETWORK_TRANSPORT_OBSERVATION_ONLY",
    }


def _new_device_session(client_instance_id, request, profile=None, telemetry=None):
    now = _utc_now_iso()
    session_id = f"ORF_DEVICE_SESSION_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_{uuid.uuid4().hex[:10]}"
    return {
        "schema": ORF_DEVICE_SESSION_SCHEMA,
        "session_id": session_id,
        "session_token": secrets.token_urlsafe(24),
        "session_state": "ACTIVE",
        "client_instance_id": str(client_instance_id or "UNRESOLVED"),
        "device_id": None,
        "connected_utc": now,
        "last_seen_utc": now,
        "sequence": 0,
        "profile_state": "NOT_COLLECTED",
        "profile_sequence": 0,
        "profile_received_utc": None,
        "telemetry_state": "INACTIVE",
        "telemetry_sequence": 0,
        "telemetry_received_utc": None,
        "device_profile_state": "NOT_REPORTED",
        "device_profile_sequence": 0,
        "device_profile_received_utc": None,
        "device_telemetry_state": "INACTIVE",
        "device_telemetry_sequence": 0,
        "device_telemetry_received_utc": None,
        "network_observations": _request_network_observations(request),
        "client_profile": copy.deepcopy(profile or {}),
        "telemetry": copy.deepcopy(telemetry or {}),
        "device_profile": {},
        "device_telemetry": {},
        "drive_observation_folder_id": None,
        "drive_observation_folder_name": None,
        "export_sequence": 0,
    }


def _session_to_state(state, record):
    state = copy.deepcopy(state)
    record = copy.deepcopy(record or {})
    link = state["device_link"]
    fresh = _orf_session_is_fresh(record)
    link.update({
        "pairing_state": "OBSERVED",
        "connection_state": "CONNECTED" if fresh else "STALE",
        "client_instance_id": record.get("client_instance_id"),
        "peer_address": (record.get("network_observations") or {}).get("peer_address"),
        "session_id": record.get("session_id"),
        "session_state": "ACTIVE" if fresh else str(record.get("session_state") or "STALE"),
        "probe_stream": "ACTIVE" if fresh else "STALE",
        "sequence": record.get("sequence"),
        "last_seen_utc": record.get("last_seen_utc"),
        "profile_state": record.get("profile_state", "NOT_COLLECTED"),
        "telemetry_state": record.get("telemetry_state", "INACTIVE"),
        "telemetry_sequence": record.get("telemetry_sequence", 0),
        "device_profile_state": record.get("device_profile_state", "NOT_REPORTED"),
        "device_telemetry_state": record.get("device_telemetry_state", "INACTIVE"),
        "device_telemetry_sequence": record.get("device_telemetry_sequence", 0),
        "device_id": record.get("device_id"),
    })
    state["session_observations"] = {
        "network": copy.deepcopy(record.get("network_observations") or {}),
        "client_profile": copy.deepcopy(record.get("client_profile") or {}),
        "telemetry": copy.deepcopy(record.get("telemetry") or {}),
        "device_profile": copy.deepcopy(record.get("device_profile") or {}),
        "device_telemetry": copy.deepcopy(record.get("device_telemetry") or {}),
        "profile_received_utc": record.get("profile_received_utc"),
        "telemetry_received_utc": record.get("telemetry_received_utc"),
        "device_profile_received_utc": record.get("device_profile_received_utc"),
        "device_telemetry_received_utc": record.get("device_telemetry_received_utc"),
    }
    # Device-reported profile/telemetry is a stronger observation source than browser hints,
    # but remains explicitly provenance-labeled until a later pairing/authentication layer binds it.
    native_profile = record.get("device_profile") or {}
    native_telem = record.get("device_telemetry") or {}
    if native_profile:
        native_identity = native_profile.get("identity") or {}
        native_android = native_profile.get("android") or {}
        native_cpu = native_profile.get("cpu") or {}
        native_memory = native_profile.get("memory") or {}
        native_storage = native_profile.get("storage") or {}
        native_display = native_profile.get("display") or {}
        device_id = native_profile.get("device_id") or record.get("device_id")
        if device_id:
            state["device_link"]["device_id"] = device_id
            record["device_id"] = device_id
        label = " ".join(str(x).strip() for x in (native_identity.get("manufacturer"), native_identity.get("model")) if str(x or "").strip())
        if label:
            state["identity"]["device"] = label
        abis = native_cpu.get("supported_abis") or []
        if abis:
            state["identity"]["architecture"] = str(abis[0])
        if native_android:
            release = native_android.get("release") or "?"
            api = native_android.get("sdk_int")
            state["identity"]["compatibility_host"] = f"ANDROID {release}" + (f" / API {api}" if api is not None else "")
        state["identity"]["authority"] = "DEVICE_REPORTED_PROFILE"
        state["system"]["cpu"]["model"] = native_cpu.get("soc_model") or native_cpu.get("hardware") or native_identity.get("hardware") or "UNRESOLVED"
        state["system"]["cpu"]["cores"] = native_cpu.get("available_processors")
        state["system"]["memory"]["total"] = native_memory.get("total_bytes", "UNAVAILABLE")
        state["system"]["memory"]["available"] = native_memory.get("available_bytes", "UNAVAILABLE")
        state["system"]["memory"]["utilization"] = native_memory.get("utilization_percent")
        state["system"]["storage"]["total"] = native_storage.get("total_bytes", "UNAVAILABLE")
        state["system"]["storage"]["available"] = native_storage.get("available_bytes", "UNAVAILABLE")
        state["system"]["storage"]["utilization"] = native_storage.get("utilization_percent")
        state["system"]["display"]["width"] = native_display.get("width_px")
        state["system"]["display"]["height"] = native_display.get("height_px")
        state["system"]["display"]["orientation"] = native_display.get("orientation") or "UNRESOLVED"
        state["system"]["display"]["profile"] = "DEVICE_REPORTED"
    if native_telem:
        nt_mem = native_telem.get("memory") or {}
        nt_storage = native_telem.get("storage") or {}
        nt_battery = native_telem.get("battery") or {}
        nt_thermal = native_telem.get("thermal") or {}
        state["system"]["memory"]["available"] = nt_mem.get("available_bytes", state["system"]["memory"].get("available"))
        state["system"]["memory"]["utilization"] = nt_mem.get("utilization_percent", state["system"]["memory"].get("utilization"))
        state["system"]["storage"]["available"] = nt_storage.get("available_bytes", state["system"]["storage"].get("available"))
        state["system"]["storage"]["utilization"] = nt_storage.get("utilization_percent", state["system"]["storage"].get("utilization"))
        state["system"]["cpu"]["utilization"] = (native_telem.get("process") or {}).get("cpu_percent")
        state["system"]["cpu"]["thermal_state"] = nt_thermal.get("status_name") or "UNAVAILABLE"
        state["system"]["power"]["source"] = nt_battery.get("power_source") or "UNAVAILABLE"
        state["system"]["power"]["battery_percent"] = nt_battery.get("level_percent")
        state["system"]["power"]["charging"] = nt_battery.get("charging")

    # Browser-visible display facts are observations, not durable hardware authority.
    prof = record.get("client_profile") or {}
    screen = prof.get("screen") or {}
    if screen.get("width") is not None:
        state["system"]["display"]["width"] = screen.get("width")
    if screen.get("height") is not None:
        state["system"]["display"]["height"] = screen.get("height")
    if prof.get("orientation"):
        state["system"]["display"]["orientation"] = prof.get("orientation")
    return state


def _refresh_state_session_snapshot(state):
    session_id = ((state or {}).get("device_link") or {}).get("session_id")
    if not session_id:
        return state
    _orf_session_prune()
    with _ORF_DEVICE_SESSION_LOCK:
        record = copy.deepcopy(_ORF_DEVICE_SESSIONS.get(session_id))
    if not record:
        state = copy.deepcopy(state)
        state["device_link"]["connection_state"] = "NOT_CONNECTED"
        state["device_link"]["session_state"] = "EXPIRED"
        state["device_link"]["probe_stream"] = "INACTIVE"
        return state
    return _session_to_state(state, record)


def ingest_device_client_probe(payload_json, current_session_id, state, request: gr.Request):
    try:
        payload = json.loads(str(payload_json or "{}"))
    except Exception as exc:
        raise gr.Error(f"Invalid device probe payload: {exc}")
    client_instance_id = str(payload.get("client_instance_id") or "").strip()
    if not client_instance_id:
        raise gr.Error("Device probe missing client_instance_id")
    kind = str(payload.get("kind") or "TELEMETRY").upper()
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    telemetry = payload.get("telemetry") if isinstance(payload.get("telemetry"), dict) else {}
    device_profile = payload.get("device_profile") if isinstance(payload.get("device_profile"), dict) else {}
    device_telemetry = payload.get("device_telemetry") if isinstance(payload.get("device_telemetry"), dict) else {}
    if device_profile and device_profile.get("schema") != ORF_DEVICE_PROFILE_SCHEMA:
        raise gr.Error(f"Unexpected device profile schema: {device_profile.get('schema')!r}")
    if device_telemetry and device_telemetry.get("schema") != ORF_DEVICE_TELEMETRY_SCHEMA:
        raise gr.Error(f"Unexpected device telemetry schema: {device_telemetry.get('schema')!r}")
    now = _utc_now_iso()

    with _ORF_DEVICE_SESSION_LOCK:
        record = _ORF_DEVICE_SESSIONS.get(str(current_session_id or ""))
        if not record:
            record = _new_device_session(client_instance_id, request, profile, telemetry)
            _ORF_DEVICE_SESSIONS[record["session_id"]] = record
        record["last_seen_utc"] = now
        record["session_state"] = "ACTIVE"
        record["sequence"] = int(record.get("sequence") or 0) + 1
        record["network_observations"] = _request_network_observations(request)
        if profile:
            record["client_profile"] = copy.deepcopy(profile)
            record["profile_state"] = "COLLECTED"
            record["profile_sequence"] = int(record.get("profile_sequence") or 0) + 1
            record["profile_received_utc"] = now
        if telemetry:
            record["telemetry"] = copy.deepcopy(telemetry)
            record["telemetry_state"] = "ACTIVE"
            record["telemetry_sequence"] = int(record.get("telemetry_sequence") or 0) + 1
            record["telemetry_received_utc"] = now
        if device_profile:
            record["device_profile"] = copy.deepcopy(device_profile)
            record["device_profile_state"] = "REPORTED"
            record["device_profile_sequence"] = int(record.get("device_profile_sequence") or 0) + 1
            record["device_profile_received_utc"] = now
            reported_id = str(device_profile.get("device_id") or "").strip()
            if reported_id:
                record["device_id"] = reported_id
        if device_telemetry:
            record["device_telemetry"] = copy.deepcopy(device_telemetry)
            record["device_telemetry_state"] = "ACTIVE"
            record["device_telemetry_sequence"] = int(record.get("device_telemetry_sequence") or 0) + 1
            record["device_telemetry_received_utc"] = now
            reported_id = str(device_telemetry.get("device_id") or "").strip()
            if reported_id and not record.get("device_id"):
                record["device_id"] = reported_id
        record["last_probe_kind"] = kind
        snapshot = copy.deepcopy(record)

    state = _session_to_state(state, snapshot)
    return (
        snapshot["session_id"],
        state,
        render_header(state),
        render_page(state),
        render_rail(state),
        render_bottom(state),
    )


def _safe_drive_folder_component(value):
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "UNRESOLVED"))
    return value[:120] or "UNRESOLVED"


@_system_write_operation("DEVICE_OBSERVATION_EXPORT")
def export_current_device_observation(current_session_id):
    session_id = str(current_session_id or "").strip()
    if not session_id:
        return '<div class="orf-export-status amber">NO ACTIVE DEVICE SESSION TO EXPORT</div>'
    with _ORF_DEVICE_SESSION_LOCK:
        record = _ORF_DEVICE_SESSIONS.get(session_id)
        if not record:
            return '<div class="orf-export-status amber">SESSION EXPIRED / NOT FOUND</div>'
        record = copy.deepcopy(record)
    # Observation exports are analytical artifacts, never credential containers.
    if "session_token" in record:
        record["session_token"] = "REDACTED"

    client_id = str(record.get("client_instance_id") or "UNRESOLVED")
    folder_name = "ORF_CLIENT_" + _safe_drive_folder_component(client_id)
    folder_id = record.get("drive_observation_folder_id")
    if not folder_id:
        folder_id = _drive_ensure_folder(ORF_DEVICE_OBSERVATIONS_ROOT_FOLDER_ID, folder_name)

    now = datetime.now(timezone.utc)
    export_seq = int(record.get("export_sequence") or 0) + 1
    export_id = f"ORF_DEVICE_OBS_{now.strftime('%Y%m%dT%H%M%S%fZ')}_{uuid.uuid4().hex[:8]}"
    summary = _orf_session_summary()
    payload = {
        "schema": ORF_DEVICE_OBSERVATION_EXPORT_SCHEMA,
        "export_id": export_id,
        "exported_utc": now.isoformat(),
        "device_folder_key": client_id,
        "device_id": record.get("device_id"),
        "session": record,
        "runtime_session_summary": summary,
    }
    data = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
    file_name = f"{export_id}.json"
    result = _drive_upsert_bytes(folder_id, file_name, data, "application/json")

    with _ORF_DEVICE_SESSION_LOCK:
        live = _ORF_DEVICE_SESSIONS.get(session_id)
        if live:
            live["drive_observation_folder_id"] = folder_id
            live["drive_observation_folder_name"] = folder_name
            live["export_sequence"] = export_seq
            live["last_export_utc"] = now.isoformat()
            live["last_export_file_id"] = result.get("id")
            live["last_export_file_name"] = file_name

    return (
        '<div class="orf-export-status green">'
        f'EXPORTED • {_esc(file_name)}<br>'
        f'FOLDER • {_esc(folder_name)}<br>'
        f'DRIVE FILE ID • {_esc(result.get("id") or "UNRESOLVED")}'
        '</div>'
    )


CSS = r"""
#orfBootFront{display:block;}
#orfBiosSurface{display:none;}
#orfRootSelection{display:none;}
:root{
  --orf-bg0:#020405;
  --orf-bg1:#061016;
  --orf-panel:#071219;
  --orf-panel2:#091923;
  --orf-line:#16364c;
  --orf-line-hi:#2b6b91;
  --orf-blue:#58b8ff;
  --orf-green:#76ffae;
  --orf-amber:#ffcc67;
  --orf-red:#ff7b7b;
  --orf-muted:#668299;
  --orf-text:#dcecff;
}

body,.gradio-container{
  background:
    radial-gradient(circle at 45% 5%, rgba(30,111,170,.10), transparent 32%),
    linear-gradient(180deg,#071015,#020405 80%) !important;
  color:var(--orf-text)!important;
}
.gradio-container{
  max-width:none!important;
  padding:0!important;
}
footer{display:none!important}

/* ----- GitHub boot front door ----- */
.orf-boot-host{
  height:calc(100vh - 76px);
  min-height:480px;
  border:0;
  overflow:hidden;
  background:#020405;
}
.orf-boot-host iframe{
  display:block;
  width:100%;
  height:100%;
  border:0;
  background:#020405;
}
.orf-enter-row{
  background:#020405!important;
  border-top:1px solid #17364a!important;
  padding:7px 12px!important;
}
.orf-enter-bios button{
  min-height:45px!important;
  border-radius:0!important;
  border:1px solid #2d759e!important;
  background:linear-gradient(180deg,#0c2938,#06141c)!important;
  color:#8fd4ff!important;
  font:800 11px ui-monospace,SFMono-Regular,Menlo,monospace!important;
  letter-spacing:.12em!important;
}
.orf-transition-note{
  color:#5c8298;
  font:700 8px ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.09em;
  padding:3px 0 1px;
}
.orf-source-note{
  color:#43677d;
  font:600 8px ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.08em;
  padding-top:4px;
}

/* ----- BIOS shell ----- */
.orf-shell{
  border:1px solid var(--orf-line);
  background:rgba(2,5,8,.92);
}
.orf-header{
  min-height:76px;
  width:100%;
  min-width:0;
  box-sizing:border-box;
  overflow:hidden;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:18px;
  padding:9px 17px;
  border-bottom:1px solid var(--orf-line);
  background:linear-gradient(180deg,rgba(10,28,39,.92),rgba(4,10,14,.96));
}
.orf-bios-logo{
  flex:0 1 auto;
  min-width:0;
  display:flex;
  align-items:center;
  gap:8px;
  flex-basis:220px;
}
.orf-planet{
  width:46px;height:46px;border-radius:50%;
  border:3px solid #7cc7ff;
  box-shadow:0 0 14px rgba(88,184,255,.25), inset 0 0 12px rgba(88,184,255,.12);
  position:relative;
  background:transparent;
}
.orf-planet:after{
  content:"";
  position:absolute;
  left:-9px;right:-9px;top:19px;height:7px;
  border:2px solid #a9ddff;
  border-radius:50%;
  transform:rotate(-16deg);
  box-shadow:0 0 8px rgba(88,184,255,.28);
}
.orf-wordmark{
  font:800 28px/1 ui-sans-serif,system-ui;
  letter-spacing:.13em;
  color:#bfe4ff;
  text-shadow:0 0 14px rgba(88,184,255,.18);
}
.orf-header-center{
  flex:1 1 auto;
  min-width:0;
  overflow:hidden;
}
.orf-title{
  font:700 13px ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.16em;
}
.orf-sub{
  margin-top:5px;
  color:var(--orf-muted);
  font:600 9px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.11em;
  min-width:0;
  max-width:100%;
  white-space:normal;
  overflow-wrap:anywhere;
  word-break:break-word;
}
.orf-header-state{
  flex:0 1 auto;
  min-width:0;
  max-width:112px;
  text-align:right;
  font:700 10px/1.25 ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.1em;
  white-space:normal;
  overflow-wrap:anywhere;
  word-break:break-word;
}
.orf-ready,.green{color:var(--orf-green)!important}
.orf-active,.blue{color:var(--orf-blue)!important}
.orf-staged,.amber{color:var(--orf-amber)!important}
.orf-failed,.red{color:var(--orf-red)!important}
.orf-unavailable,.gray{color:#657582!important}

.orf-nav-wrap,.orf-workspace-wrap,.orf-rail-wrap{
  border-radius:0!important;
  border-color:var(--orf-line)!important;
  background:rgba(3,9,13,.86)!important;
}
.orf-nav-wrap{border-right:1px solid var(--orf-line)!important}
.orf-rail-wrap{border-left:1px solid var(--orf-line)!important}

.orf-nav-btn button{
  min-height:51px!important;
  border-radius:0!important;
  border:0!important;
  border-bottom:1px solid #0d2737!important;
  background:linear-gradient(90deg,#071219,#061016)!important;
  color:#7996aa!important;
  text-align:left!important;
  padding-left:16px!important;
  font:700 11px ui-monospace,SFMono-Regular,Menlo,monospace!important;
  letter-spacing:.10em!important;
}
.orf-nav-btn button:hover{
  background:linear-gradient(90deg,#0c2230,#07151d)!important;
  color:#bde6ff!important;
}
.orf-reset-kernel button{
  background:linear-gradient(90deg,#351316,#1b0b0f)!important;
  color:#ffaaa2!important;
  border-top:1px solid #743638!important;
  border-bottom:1px solid #743638!important;
  box-shadow:inset 3px 0 0 #df6666,0 0 18px rgba(223,102,102,.08)!important;
}
.orf-reset-kernel button:hover{
  background:linear-gradient(90deg,#552024,#241014)!important;
  color:#ffe0dc!important;
  box-shadow:inset 3px 0 0 #ff8580,0 0 22px rgba(255,110,105,.16)!important;
}
#orfKernelRestartModal{
  position:fixed;
  left:50%;
  top:50%;
  transform:translate(-50%,-50%);
  z-index:10000;
  width:min(460px,calc(100vw - 28px));
  max-height:calc(100dvh - 36px);
  box-sizing:border-box;
  padding:18px 16px 16px;
  overflow:auto;
  border:1px solid #743638;
  border-radius:12px;
  background:linear-gradient(180deg,rgba(42,14,18,.99),rgba(10,7,9,.995));
  box-shadow:0 18px 70px rgba(0,0,0,.62),0 0 30px rgba(225,90,90,.16);
}
#orfKernelRestartModal .orf-reset-confirm-title{
  color:#ffaaa2;
  font:800 13px ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.13em;
  text-align:center;
}
#orfKernelRestartModal .orf-reset-confirm-copy{
  color:#aebac3;
  margin:9px auto 0;
  max-width:390px;
  text-align:center;
  font:600 10px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.05em;
}
#orfKernelRestartModal .orf-reset-confirm-actions{
  display:flex;
  gap:8px;
  margin-top:14px;
}
#orfKernelRestartModal .orf-reset-native-button{
  flex:1 1 0;
  min-height:44px;
  border-radius:7px;
  font:800 12px ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.08em;
  cursor:pointer;
}
#orfKernelRestartModal .orf-reset-native-cancel{
  background:#071219;
  border:1px solid #24404f;
  color:#9bb8c9;
}
#orfKernelRestartModal .orf-reset-native-continue{
  background:linear-gradient(90deg,#4a181c,#250d11);
  border:1px solid #8d3e41;
  color:#ffd0cb;
}
#orfResetKernelCancelBridge,
#orfResetKernelContinueBridge,
#orfDeviceClientProbeBridge,
#orfDeviceClientPayloadBridge{
  position:fixed!important;
  left:-200vw!important;
  top:-200vh!important;
  width:1px!important;
  height:1px!important;
  min-width:1px!important;
  min-height:1px!important;
  opacity:0!important;
  overflow:hidden!important;
  pointer-events:none!important;
}
.orf-device-export-wrap{
  border:1px solid #16364c!important;
  background:rgba(5,14,20,.82)!important;
  padding:9px!important;
  margin-top:8px!important;
}
.orf-device-export-wrap button{
  min-height:44px!important;
  border:1px solid #2d759e!important;
  background:linear-gradient(180deg,#0b2634,#06141c)!important;
  color:#9fdcff!important;
  font:800 11px ui-monospace,SFMono-Regular,Menlo,monospace!important;
  letter-spacing:.09em!important;
}
.orf-export-status{
  margin-top:7px;
  font:700 9px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.04em;
  overflow-wrap:anywhere;
}
@media (max-width:520px){
  #orfKernelRestartModal{
    width:calc(100vw - 26px);
    padding:16px 12px 12px;
  }
}

.orf-page{padding:14px 16px 8px}
.orf-page-title{
  color:#c8eaff;
  font:700 14px ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.12em;
  margin:0 0 12px;
}
.orf-section{
  border:1px solid var(--orf-line);
  background:linear-gradient(180deg,rgba(7,18,25,.94),rgba(4,11,15,.94));
  margin-bottom:10px;
}
.orf-section-title{
  padding:7px 10px;
  border-bottom:1px solid var(--orf-line);
  background:#07151d;
  color:#79bce7;
  font:700 9px ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.15em;
}
.orf-row{
  min-height:29px;
  display:grid;
  grid-template-columns:minmax(142px,35%) 1fr;
  align-items:center;
  gap:12px;
  padding:4px 10px;
  border-bottom:1px solid rgba(22,54,76,.48);
  font:600 9px ui-monospace,SFMono-Regular,Menlo,monospace;
}
.orf-row:last-child{border-bottom:0}
.orf-key{color:#698399}
.orf-value{color:#d5eaff;overflow-wrap:anywhere}

.orf-service-row{
  display:grid;
  grid-template-columns:minmax(115px,1.1fr) minmax(75px,.7fr) minmax(118px,1fr);
  padding:7px 10px;
  border-bottom:1px solid rgba(22,54,76,.48);
  font:600 9px ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.04em;
}
.orf-service-row:last-child{border-bottom:0}
.orf-service-name{color:#a8c1d4}
.orf-service-authority{color:#5f7f94}

.orf-rail{padding:12px 10px}
.orf-rail-title{
  color:#77bce7;
  font:700 9px ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.14em;
  padding-bottom:7px;
  border-bottom:1px solid var(--orf-line);
  margin-bottom:6px;
}
.orf-rail-row{
  display:flex;
  justify-content:space-between;
  gap:8px;
  padding:5px 2px;
  border-bottom:1px solid rgba(22,54,76,.34);
  font:700 9px ui-monospace,SFMono-Regular,Menlo,monospace;
}
.orf-rail-key{color:#718ca0}
.orf-rail-val{color:#cfe8f9}

.orf-boot-control{
  border-radius:0!important;
  border:1px solid var(--orf-line)!important;
  background:#061016!important;
}
.orf-action button{
  min-height:41px!important;
  border-radius:0!important;
  font:700 10px ui-monospace,SFMono-Regular,Menlo,monospace!important;
  letter-spacing:.08em!important;
}
.orf-stage button{
  background:#332813!important;color:#ffd57d!important;border:1px solid #735c2b!important
}
.orf-discard button{
  background:#10171c!important;color:#8ca0ad!important;border:1px solid #2a3c49!important
}
.orf-apply button{
  background:#123422!important;color:#8effb5!important;border:1px solid #2b774d!important
}

.orf-bottom{
  min-height:43px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:14px;
  padding:7px 14px;
  border-top:1px solid var(--orf-line);
  background:#040b0f;
  color:#668499;
  font:700 9px ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.08em;
}
.orf-bottom strong{color:#bcd8e9}

@media(max-width:800px){
  .orf-header{padding:7px 9px;min-height:64px;gap:8px;align-items:flex-start}
  .orf-bios-logo{flex:0 1 145px;min-width:0}
  .orf-header-center{flex:1 1 118px;min-width:0}
  .orf-header-state{flex:0 1 82px;min-width:0;max-width:82px;font-size:8px;line-height:1.2;letter-spacing:.07em}
  .orf-planet{width:38px;height:38px;flex:0 0 38px}
  .orf-planet:after{top:15px}
  .orf-wordmark{font-size:22px;min-width:0}
  .orf-title{font-size:10px;line-height:1.2;overflow-wrap:anywhere}
  .orf-sub{font-size:7px;line-height:1.3;letter-spacing:.08em}
  .orf-page{padding:10px}
  .orf-row{grid-template-columns:minmax(120px,38%) 1fr;font-size:8px}
}


/* Responsive firmware footer: keep all status fields inside the frame. */
.orf-bottom{
  display:flex !important;
  align-items:flex-start;
  justify-content:flex-start;
  flex-wrap:wrap;
  gap:8px 18px;
  width:100%;
  box-sizing:border-box;
  overflow:hidden;
}

.orf-bottom span{
  min-width:0;
  max-width:100%;
  white-space:normal;
  overflow-wrap:anywhere;
  word-break:normal;
  line-height:1.15;
}

.orf-bottom strong{
  white-space:normal;
  overflow-wrap:anywhere;
}

@media (max-width: 760px){
  .orf-bottom{
    display:grid !important;
    grid-template-columns:repeat(2, minmax(0, 1fr));
    gap:10px 18px;
    padding:12px 16px !important;
  }

  .orf-bottom span{
    display:block;
  }
}

@media (max-width: 430px){
  .orf-bottom{
    grid-template-columns:1fr;
  }
}


/* Unified touch / mouse / keyboard interaction surface. */
button,
[role="button"]{
  cursor:pointer;
}

button:focus-visible,
[role="button"]:focus-visible,
.orf-kbd-focus{
  outline:2px solid #7fc9ff !important;
  outline-offset:-3px !important;
  box-shadow:
    inset 0 0 0 1px rgba(127,201,255,.45),
    0 0 0 1px rgba(127,201,255,.18) !important;
}

@media (hover:hover) and (pointer:fine){
  button:hover,
  [role="button"]:hover{
    filter:brightness(1.08);
  }
}

@media (pointer:coarse){
  button,
  [role="button"]{
    min-height:44px;
  }
}

/* ----- Dummy post-BIOS file loader test surface ----- */
.orf-loader-surface{
  position:fixed!important;
  inset:0!important;
  z-index:9999!important;
  overflow:auto!important;
  padding:28px!important;
  background:
    radial-gradient(circle at 50% 0%, rgba(30,111,170,.12), transparent 35%),
    linear-gradient(180deg,#071015,#020405 78%)!important;
}
.orf-loader-shell{
  max-width:980px;
  margin:0 auto;
  border:1px solid var(--orf-line-hi);
  background:rgba(2,5,8,.96);
  box-shadow:0 18px 60px rgba(0,0,0,.55);
}
.orf-loader-head{
  padding:18px 20px 14px;
  border-bottom:1px solid var(--orf-line);
}
.orf-loader-title{
  color:var(--orf-blue);
  font:900 18px ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.12em;
}
.orf-loader-sub{
  margin-top:6px;
  color:var(--orf-muted);
  font:700 10px ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.08em;
}
.orf-loader-status{
  margin-top:12px;
  padding:12px 14px;
  border:1px solid var(--orf-line);
  background:#03080b;
  color:var(--orf-green);
  font:700 11px ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.06em;
}
.orf-loader-body{
  padding:18px 20px 20px;
}
.orf-loader-note{
  color:var(--orf-muted);
  font:600 10px ui-monospace,SFMono-Regular,Menlo,monospace;
  line-height:1.6;
  margin-bottom:10px;
}

/* Boot front-door event bridges are backend controls, never visual controls. */
#orfBootPowerBridge,
#orfBootBiosRequestBridge,
#orfBootHomeReadyBridge {
  display:none !important;
  width:0 !important;
  height:0 !important;
  min-width:0 !important;
  min-height:0 !important;
  overflow:hidden !important;
  opacity:0 !important;
  pointer-events:none !important;
}

"""


def _esc(value):
    return html.escape(str(value if value is not None else "UNKNOWN"))


def _state_class(state):
    s = str(state).upper()
    if s in {"READY", "VERIFIED", "AVAILABLE", "COMPLETE", "OK"}:
        return "green"
    if s in {"ACTIVE", "STARTING", "RECOVERING", "CONNECTING"}:
        return "blue"
    if s in {"STAGED", "REVIEW_REQUIRED", "DEGRADED"}:
        return "amber"
    if s in {"FAILED", "ERROR", "BLOCKED"}:
        return "red"
    return "gray"


def _row(key, value, cls=None):
    cls = cls or _state_class(value)
    return (
        '<div class="orf-row">'
        f'<div class="orf-key">{_esc(key)}</div>'
        f'<div class="orf-value {cls}">{_esc(value)}</div>'
        '</div>'
    )


def _section(title, rows):
    return (
        '<section class="orf-section">'
        f'<div class="orf-section-title">{_esc(title)}</div>'
        + "".join(rows)
        + '</section>'
    )


def _maintenance_runtime_status():
    fn = globals().get("maintenance_session_status")
    if not callable(fn):
        return {
            "state": "LOCKED",
            "active": False,
            "session_id": None,
            "expires_in_seconds": 0,
            "signer_dn": "KORF SIGNER UNAVAILABLE",
            "certificate_sha256": "UNAVAILABLE",
            "public_key_sha256": "UNAVAILABLE",
            "kernel_candidate": {"state": "IDLE"},
            "active_kernel": {},
        }
    try:
        return dict(fn() or {})
    except Exception as exc:
        return {
            "state": "ERROR",
            "active": False,
            "session_id": None,
            "expires_in_seconds": 0,
            "signer_dn": "KORF SIGNER STATUS ERROR",
            "certificate_sha256": "UNAVAILABLE",
            "public_key_sha256": "UNAVAILABLE",
            "kernel_candidate": {"state": "ERROR"},
            "active_kernel": {},
            "error": f"{type(exc).__name__}: {exc}",
        }


def _sync_maintenance_state(state):
    state = copy.deepcopy(state)
    status = _maintenance_runtime_status()
    active = bool(status.get("active"))
    gate_state = "ACTIVE" if active else str(status.get("state") or "LOCKED").upper()
    security = state.setdefault("security", {})
    security["maintainer_gate"] = gate_state
    security["maintainer_authority"] = "KORF_SIGNER_CHALLENGE"
    security["maintainer_session"] = "ACTIVE" if active else "INACTIVE"
    maint = state.setdefault("maintenance", {})
    maint["state"] = gate_state
    maint["authority"] = "KORF_SIGNER_CHALLENGE"
    maint["session_id"] = status.get("session_id")
    maint["session_expires_in_seconds"] = int(status.get("expires_in_seconds") or 0)
    candidate = status.get("kernel_candidate") or {}
    maint["kernel_update"] = {
        "state": str(candidate.get("state") or "IDLE"),
        "candidate_version": candidate.get("version"),
        "candidate_manifest_sha256": candidate.get("manifest_sha256"),
    }
    shutdown = dict(status.get("runtime_shutdown") or {})
    shutdown_state = str(shutdown.get("state") or "RUNNING").upper()
    maint["runtime_shutdown"] = {
        **shutdown,
        "state": shutdown_state if shutdown_state != "RUNNING" else ("AVAILABLE" if active else "LOCKED"),
    }
    state.setdefault("runtime", {})["shutdown"] = shutdown or {
        "schema": "ORF_SYSTEM_QUIESCE_V0_1",
        "state": "RUNNING",
        "writes_enabled": True,
        "active_writes": 0,
        "countdown_seconds": 0,
        "drain_state": "IDLE",
        "clients_return_to_boot": False,
    }
    return state


def _maintenance_status_html(prefix="MAINTENANCE GATE"):
    status = _maintenance_runtime_status()
    state = str(status.get("state") or "LOCKED").upper()
    active = bool(status.get("active"))
    session = status.get("session_id") or "—"
    expires = int(status.get("expires_in_seconds") or 0)
    candidate = status.get("kernel_candidate") or {}
    active_kernel = status.get("active_kernel") or {}
    cls = "green" if active else ("red" if state == "ERROR" else "amber" if state in {"EXPIRED", "REVOKED"} else "gray")
    return f"""
    <div class="orf-loader-status">
      {prefix}<br>
      GATE • <span class="{cls}">{_esc(state)}</span><br>
      SESSION • {_esc(session)} • EXPIRES {expires}s<br>
      ACTIVE KERNEL • {_esc(active_kernel.get('prefix') or 'BASELINE')} • {_esc(str(active_kernel.get('manifest_sha256') or '')[:16] or '—')}<br>
      CANDIDATE • {_esc(candidate.get('state') or 'IDLE')} • {_esc(candidate.get('version') or '—')}
    </div>
    """


def _maintenance_sync_render(state):
    state = _sync_maintenance_state(state)
    return state, render_header(state), render_page(state), render_rail(state), render_bottom(state)


def _maintenance_issue_challenge(state):
    fn = globals().get("issue_maintenance_challenge")
    if not callable(fn):
        raise gr.Error("Maintenance challenge authority is unavailable")
    try:
        challenge = dict(fn() or {})
        state, header_html, page_html, rail_html, bottom_html = _maintenance_sync_render(state)
        return (
            state, header_html, page_html, rail_html, bottom_html,
            str(challenge.get("challenge") or ""),
            _maintenance_status_html("CHALLENGE ISSUED — SIGN EXACT TEXT"),
        )
    except Exception as exc:
        raise gr.Error(f"Maintenance challenge failed: {type(exc).__name__}: {exc}")


def _maintenance_verify_signature(signature_b64, state):
    fn = globals().get("verify_and_arm_maintenance")
    if not callable(fn):
        raise gr.Error("Maintenance verifier is unavailable")
    try:
        fn(signature_b64)
        state, header_html, page_html, rail_html, bottom_html = _maintenance_sync_render(state)
        return (
            state, header_html, page_html, rail_html, bottom_html,
            "",
            _maintenance_status_html("MAINTENANCE AUTHORITY ACTIVE"),
        )
    except Exception as exc:
        raise gr.Error(f"Maintenance verification failed: {type(exc).__name__}: {exc}")


def _maintenance_revoke(state):
    fn = globals().get("revoke_maintenance_session")
    if not callable(fn):
        raise gr.Error("Maintenance revoke authority is unavailable")
    try:
        fn("BIOS_MAINTENANCE_REVOKE")
        state, header_html, page_html, rail_html, bottom_html = _maintenance_sync_render(state)
        return (
            state, header_html, page_html, rail_html, bottom_html,
            "", "", _maintenance_status_html("MAINTENANCE AUTHORITY REVOKED"),
            gr.update(visible=False),
        )
    except Exception as exc:
        raise gr.Error(f"Maintenance revoke failed: {type(exc).__name__}: {exc}")


def _maintenance_stage_kernel(ref, prefix, manifest_sha256, state):
    fn = globals().get("maintenance_stage_github_kernel_manifest")
    if not callable(fn):
        raise gr.Error("Kernel manifest staging authority is unavailable")
    try:
        candidate = dict(fn(ref, prefix, manifest_sha256) or {})
        state, header_html, page_html, rail_html, bottom_html = _maintenance_sync_render(state)
        detail = (
            f"KERNEL CANDIDATE VERIFIED • v{candidate.get('version') or '?'} • "
            f"{candidate.get('module_count') or 0} modules • "
            f"SHA256 {str(candidate.get('manifest_sha256') or '')[:16]}…"
        )
        return state, header_html, page_html, rail_html, bottom_html, f'<div class="orf-loader-status">{_esc(detail)}</div>'
    except Exception as exc:
        raise gr.Error(f"Kernel manifest stage failed: {type(exc).__name__}: {exc}")


def _maintenance_apply_kernel(state):
    fn = globals().get("maintenance_apply_staged_kernel")
    if not callable(fn):
        raise gr.Error("Kernel apply authority is unavailable")
    try:
        result = dict(fn() or {})
        state, header_html, page_html, rail_html, bottom_html = _maintenance_sync_render(state)
        active = result.get("active_authority") or {}
        detail = f"KERNEL UPDATE APPLY REQUESTED • {active.get('prefix') or '?'} • RESTART OWNED BY KERNEL MONITOR"
        return state, header_html, page_html, rail_html, bottom_html, f'<div class="orf-loader-status green">{_esc(detail)}</div>'
    except Exception as exc:
        raise gr.Error(f"Kernel apply failed: {type(exc).__name__}: {exc}")


def _maintenance_rollback_kernel(state):
    fn = globals().get("maintenance_rollback_kernel")
    if not callable(fn):
        raise gr.Error("Kernel rollback authority is unavailable")
    try:
        result = dict(fn() or {})
        state, header_html, page_html, rail_html, bottom_html = _maintenance_sync_render(state)
        active = result.get("active_authority") or {}
        detail = f"KERNEL ROLLBACK REQUESTED • {active.get('prefix') or 'BASELINE'}"
        return state, header_html, page_html, rail_html, bottom_html, f'<div class="orf-loader-status amber">{_esc(detail)}</div>'
    except Exception as exc:
        raise gr.Error(f"Kernel rollback failed: {type(exc).__name__}: {exc}")


def _maintenance_arm_shutdown():
    fn = globals().get("maintenance_arm_runtime_shutdown")
    if not callable(fn):
        raise gr.Error("Runtime shutdown authority is unavailable")
    try:
        result = dict(fn() or {})
        seconds = int(result.get("expires_in_seconds") or 0)
        return (
            f'<div class="orf-loader-status amber">RUNTIME SHUTDOWN ARMED • CONFIRM WITHIN {seconds}s</div>',
            gr.update(visible=True),
        )
    except Exception as exc:
        raise gr.Error(f"Runtime shutdown arm failed: {type(exc).__name__}: {exc}")


def _maintenance_execute_shutdown():
    fn = globals().get("maintenance_execute_runtime_shutdown")
    if not callable(fn):
        raise gr.Error("Runtime shutdown authority is unavailable")
    try:
        result = dict(fn() or {})
        seconds = int(result.get("countdown_seconds") or 0)
        message = result.get("message") or "COLAB RUNTIME SHUTDOWN COMMITTED"
        return (
            '<div class="orf-loader-status amber">'
            f'SYSTEM SHUTDOWN STARTED • {seconds}s<br>'
            f'{_esc(message)}'
            '</div>'
        )
    except Exception as exc:
        raise gr.Error(f"Runtime shutdown failed: {type(exc).__name__}: {exc}")


def merge_live_boot_state(state, boot_state):
    """
    Overlay authoritative Kernel boot telemetry onto the BIOS presentation state.

    This does NOT make the BIOS presentation an execution authority. It only copies
    machine-readable telemetry already published by the Kernel into BIOS fields.
    UI selection and staged commands are preserved.
    """
    state = copy.deepcopy(state)
    boot_state = boot_state or {}

    telemetry = state.setdefault("telemetry", {})
    telemetry["source"] = boot_state.get("schema", BOOT_STATE_SCHEMA)
    telemetry["source_mode"] = str(boot_state.get("_bios_transport") or "UNKNOWN")
    telemetry["boot_state"] = boot_state.get("state", "UNKNOWN")
    telemetry["phase"] = boot_state.get("phase", "UNKNOWN")
    telemetry["progress"] = boot_state.get("progress", 0)
    telemetry["message"] = boot_state.get("message", "")
    telemetry["boot_id"] = boot_state.get("boot_id")
    telemetry["sequence"] = boot_state.get("sequence")
    telemetry["updated_utc"] = boot_state.get("updated_utc")
    telemetry["kernel_id"] = boot_state.get("kernel_id")
    telemetry["kernel_version"] = boot_state.get("kernel_version")
    telemetry["kernel_alive"] = bool(boot_state.get("kernel_alive"))
    telemetry["heartbeat_sequence"] = boot_state.get("heartbeat_sequence")
    telemetry["heartbeat_utc"] = boot_state.get("heartbeat_utc")
    telemetry["monitor_mode"] = boot_state.get("monitor_mode")
    telemetry["services"] = copy.deepcopy(boot_state.get("services") or {})
    telemetry["runtime_environment"] = copy.deepcopy(boot_state.get("runtime_environment") or {})

    # Existing BOOT page fields now reflect the live Kernel publication.
    last_boot = state["boot"]["last_boot"]
    last_boot["state"] = boot_state.get("state", last_boot.get("state", "UNKNOWN"))
    last_boot["sequence"] = boot_state.get("sequence", last_boot.get("sequence"))
    last_boot["boot_id"] = boot_state.get("boot_id", last_boot.get("boot_id"))

    # Kernel row in the runtime fabric follows the authoritative live state.
    state["runtime"]["kernel"]["state"] = boot_state.get(
        "state",
        state["runtime"]["kernel"]["state"],
    )

    # If the Kernel publishes named service telemetry, map known names into the
    # presentation fabric without inventing state.
    services = boot_state.get("services") or {}
    service_key_map = {
        "drive_api": "drive_api",
        "github": "github",
        "recovery": "recovery",
        "presentation_bridge": "presentation_bridge",
        "presentation": "presentation_bridge",
    }

    for source_key, target_key in service_key_map.items():
        raw = services.get(source_key)
        if raw is None:
            raw = services.get(source_key.upper())
        if raw is None:
            continue

        if isinstance(raw, dict):
            observed_state = raw.get("state")
        else:
            observed_state = raw

        if observed_state:
            state["runtime"][target_key]["state"] = str(observed_state).upper()

    return _sync_maintenance_state(state)




def _presentation_generation_status(presentation_generation_state):
    """Resolve this browser surface against the loader-owned active generation."""
    presentation_generation_state = presentation_generation_state or {}
    own_generation = str(
        presentation_generation_state.get("generation_id")
        if isinstance(presentation_generation_state, dict)
        else presentation_generation_state
        or ""
    )
    active = globals().get("__ORF_BIOS_ACTIVE_PRESENTATION__") or {}
    active_generation = str(active.get("generation_id") or "")
    active_url = str(active.get("active_url") or "")
    active_origin = str(active.get("active_origin") or "")
    active_state = str(active.get("state") or "UNPUBLISHED").upper()
    stability = str(active.get("stability") or "UNPROVEN").upper()
    generation_match = bool(
        own_generation and active_generation and own_generation == active_generation
    )
    active_owned = bool(generation_match and active_state == "ACTIVE")
    return {
        "own_generation": own_generation,
        "active_generation": active_generation,
        "active_url": active_url,
        "active_origin": active_origin,
        "active_state": active_state,
        "stability": stability,
        "generation_match": generation_match,
        "active_owned": active_owned,
        "health_failures": int(active.get("health_failures") or 0),
        "restart_count": int(active.get("restart_count") or 0),
    }




def _boot_sample_signature(boot_state):
    boot_state = boot_state or {}
    return (
        str(boot_state.get("boot_id") or ""),
        int(boot_state.get("sequence") or 0),
        str(boot_state.get("updated_utc") or ""),
        str(boot_state.get("state") or "").upper(),
        str(boot_state.get("phase") or "").upper(),
    )


def new_boot_freshness_state(initial_boot_state):
    initial_boot_state = initial_boot_state or {}
    initial_signature = _boot_sample_signature(initial_boot_state)

    return {
        "initial_signature": initial_signature,
        "initial_boot_id": str(initial_boot_state.get("boot_id") or ""),
        "initial_sequence": int(initial_boot_state.get("sequence") or 0),
        "initial_updated_utc": str(initial_boot_state.get("updated_utc") or ""),
        "initial_heartbeat_sequence": int(initial_boot_state.get("heartbeat_sequence") or 0),
        "initial_heartbeat_utc": str(initial_boot_state.get("heartbeat_utc") or ""),
        "active_boot_id": None,
        "max_sequence": int(initial_boot_state.get("sequence") or 0),
        "fresh_sample_seen": False,
        "fresh_reason": "INITIAL_SNAPSHOT_ONLY",
        "non_ready_seen": (
            str(initial_boot_state.get("state") or "").upper() != "READY"
        ),
        "last_ready_signature": None,
        "ready_confirmations": 0,
        "last_read_latency_ms": None,
        "gate_state": "WAITING_FOR_FRESH_SAMPLE",
    }


def evaluate_boot_freshness(boot_state, freshness, elapsed, read_latency_ms):
    """
    Evaluate whether a READY sample is fresh enough for a post-power handoff.

    The first Drive snapshot is never trusted merely because it says READY.
    Freshness is established by durable boot-state evidence:
      - a new boot_id, OR
      - sequence advancement, OR
      - updated_utc advancement, OR
      - observing a non-READY sample from the active boot cycle.

    Once a new boot_id is observed, READY from an older boot_id is rejected even
    if Drive briefly serves a regressed/stale object.

    For an already-running system that never emits a new boot cycle, a delayed
    fallback permits transition only after several consecutive identical READY
    reads beyond the larger fallback window.
    """
    freshness = copy.deepcopy(freshness or new_boot_freshness_state(boot_state))
    boot_state = boot_state or {}

    signature = _boot_sample_signature(boot_state)
    boot_id, sequence, updated_utc, state_name, _phase = signature
    ready = state_name == "READY"

    freshness["last_read_latency_ms"] = round(float(read_latency_ms), 1)

    initial_boot_id = freshness.get("initial_boot_id") or ""
    initial_sequence = int(freshness.get("initial_sequence") or 0)
    initial_updated_utc = freshness.get("initial_updated_utc") or ""
    initial_heartbeat_sequence = int(freshness.get("initial_heartbeat_sequence") or 0)
    initial_heartbeat_utc = freshness.get("initial_heartbeat_utc") or ""
    heartbeat_sequence = int(boot_state.get("heartbeat_sequence") or 0)
    heartbeat_utc = str(boot_state.get("heartbeat_utc") or "")

    # Strongest signal: the Kernel has started a different boot session.
    if boot_id and initial_boot_id and boot_id != initial_boot_id:
        if freshness.get("active_boot_id") != boot_id:
            freshness["active_boot_id"] = boot_id
            freshness["max_sequence"] = sequence
            freshness["ready_confirmations"] = 0
            freshness["last_ready_signature"] = None

        freshness["fresh_sample_seen"] = True
        freshness["fresh_reason"] = "NEW_BOOT_ID"

    # Same-session progression is also valid freshness evidence.  Kernel
    # liveness advances heartbeat_sequence/heartbeat_utc independently from
    # the boot lifecycle sequence, so the presentation-generation fence must
    # recognize a pulse newer than the launch snapshot.
    elif (
        heartbeat_sequence > initial_heartbeat_sequence
        or (heartbeat_utc and heartbeat_utc != initial_heartbeat_utc)
        or sequence > initial_sequence
        or (updated_utc and updated_utc != initial_updated_utc)
    ):
        freshness["fresh_sample_seen"] = True
        if heartbeat_sequence > initial_heartbeat_sequence:
            freshness["fresh_reason"] = "HEARTBEAT_SEQUENCE_ADVANCED"
        elif heartbeat_utc and heartbeat_utc != initial_heartbeat_utc:
            freshness["fresh_reason"] = "HEARTBEAT_UTC_ADVANCED"
        elif sequence > initial_sequence:
            freshness["fresh_reason"] = "SEQUENCE_ADVANCED"
        else:
            freshness["fresh_reason"] = "UPDATED_UTC_ADVANCED"
        if boot_id:
            freshness["active_boot_id"] = boot_id
        freshness["max_sequence"] = max(
            int(freshness.get("max_sequence") or 0),
            sequence,
        )

    # Any observed non-READY state proves the presentation has seen the boot
    # lifecycle rather than only the stale terminal READY snapshot.
    if not ready:
        freshness["non_ready_seen"] = True
        if boot_id:
            freshness["active_boot_id"] = boot_id
            freshness["max_sequence"] = max(
                int(freshness.get("max_sequence") or 0),
                sequence,
            )
        freshness["ready_confirmations"] = 0
        freshness["last_ready_signature"] = None
    else:
        if signature == freshness.get("last_ready_signature"):
            freshness["ready_confirmations"] = int(
                freshness.get("ready_confirmations") or 0
            ) + 1
        else:
            freshness["last_ready_signature"] = signature
            freshness["ready_confirmations"] = 1

    # Reject a READY object from an older session after a newer boot_id was seen.
    active_boot_id = freshness.get("active_boot_id")
    session_match = not active_boot_id or not boot_id or boot_id == active_boot_id

    fresh_ready = (
        ready
        and session_match
        and (
            bool(freshness.get("fresh_sample_seen"))
            or bool(freshness.get("non_ready_seen"))
        )
    )

    stable_ready_fallback = (
        ready
        and elapsed >= BOOT_READY_STABLE_FALLBACK_SECONDS
        and int(freshness.get("ready_confirmations") or 0)
            >= BOOT_READY_CONFIRMATIONS_REQUIRED
    )

    eligible = fresh_ready or stable_ready_fallback

    if eligible:
        freshness["gate_state"] = (
            "FRESH_READY"
            if fresh_ready
            else "STABLE_READY_FALLBACK"
        )
    elif active_boot_id and boot_id and boot_id != active_boot_id:
        freshness["gate_state"] = "STALE_SESSION_REJECTED"
    elif not ready:
        freshness["gate_state"] = "WAITING_FOR_READY"
    elif not (
        freshness.get("fresh_sample_seen")
        or freshness.get("non_ready_seen")
    ):
        freshness["gate_state"] = "READY_NOT_YET_FRESH"
    else:
        freshness["gate_state"] = "READY_CONFIRMING"

    return freshness, eligible


KERNEL_HEARTBEAT_STALE_SECONDS = max(3.5, float(BOOT_POLL_SECONDS) * 3.5)

def _kernel_heartbeat_status(boot_state):
    boot_state = boot_state or {}
    reported_alive = bool(boot_state.get("kernel_alive"))
    heartbeat_utc = str(boot_state.get("heartbeat_utc") or "").strip()
    age_seconds = None
    if heartbeat_utc:
        try:
            parsed = datetime.fromisoformat(heartbeat_utc.replace("Z", "+00:00"))
            age_seconds = max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())
        except Exception:
            age_seconds = None
    live = bool(
        reported_alive
        and age_seconds is not None
        and age_seconds <= KERNEL_HEARTBEAT_STALE_SECONDS
    )
    return live, age_seconds


def boot_presentation_state(boot_state, transition_complete=False):
    """Present Drive fallback as history until this runtime owns Kernel state."""
    visible = copy.deepcopy(boot_state or {})
    transport = str(visible.get("_bios_transport") or "").upper()
    if transport == "DRIVE_API_FALLBACK" and not bool(transition_complete):
        previous_state = str(visible.get("state") or "UNKNOWN").upper()
        previous_phase = str(visible.get("phase") or "UNKNOWN").upper()
        visible.update({
            "state": "WAITING",
            "phase": "SCANNING",
            "progress": 0.0,
            "message": (
                f"Previous boot {previous_state}; scanning for current Kernel signal"
                if previous_state != "UNKNOWN"
                else "Scanning for current Kernel signal"
            ),
            "ready": False,
            "kernel_alive": False,
            "_bios_kernel_live": False,
            "_bios_previous_state": previous_state,
            "_bios_previous_phase": previous_phase,
            "_bios_previous_ready": bool(boot_state.get("ready")),
            "_bios_previous_boot_id": boot_state.get("boot_id"),
            "_bios_previous_sequence": boot_state.get("sequence"),
            "_bios_previous_updated_utc": boot_state.get("updated_utc"),
        })
    return visible


def render_boot_gate_status(boot_state, freshness_state, transition_complete):
    boot_state = boot_state or {}
    freshness_state = freshness_state or {}
    state_name = str(boot_state.get("state") or "UNKNOWN").upper()
    kernel_live = bool(boot_state.get("_bios_kernel_live"))
    gate_state = str(freshness_state.get("gate_state") or "UNKNOWN")
    fresh_reason = str(freshness_state.get("fresh_reason") or "NONE")
    initial_hb = int(freshness_state.get("initial_heartbeat_sequence") or 0)
    observed_hb = int(boot_state.get("heartbeat_sequence") or 0)
    age = boot_state.get("_bios_heartbeat_age_seconds")
    age_text = "?" if age is None else f"{float(age):.1f}s"
    handoff = "ACCEPTED" if transition_complete else "ARMED"
    presentation_state = str(boot_state.get("_bios_presentation_stability") or "UNPUBLISHED")
    presentation_match = bool(boot_state.get("_bios_presentation_generation_match"))
    own_generation = str(boot_state.get("_bios_presentation_generation") or "")
    active_generation = str(boot_state.get("_bios_active_presentation_generation") or "")
    previous_state = str(boot_state.get("_bios_previous_state") or "").upper()
    previous_ready = bool(boot_state.get("_bios_previous_ready"))
    previous_note = (
        f" • PREVIOUS BOOT {previous_state}{' ✓' if previous_ready else ''}"
        if previous_state
        else ""
    )
    return f"""
    <div>
      <div class="orf-transition-note">
        BOOT {state_name} • KERNEL {'LIVE' if kernel_live else 'NOT LIVE'}
        • PRESENTATION {presentation_state} {'MATCH' if presentation_match else 'NOT-MATCHED'}
        • GATE {gate_state} • HANDOFF {handoff}{previous_note}
      </div>
      <div class="orf-source-note">
        PULSE {initial_hb} → {observed_hb} • AGE {age_text}
        • FRESHNESS {fresh_reason}
        • GEN {own_generation[-8:] or '?'} → {active_generation[-8:] or '?'}
        &nbsp;•&nbsp; BOOT SOURCE VERIFIED: {BOOT_OWNER}/{BOOT_REPO}@{BOOT_REF[:12]}
        &nbsp;•&nbsp; SHA256 {EXPECTED_BOOT_SHA256[:16]}…
      </div>
    </div>
    """


def bios_heartbeat(
    state,
    started_at,
    transition_complete,
    freshness_state,
    manual_view_state,
    presentation_generation_state,
    primary_surface_owner_state,
    boot_power_started_state,
    boot_target_state,
):
    """Single BIOS heartbeat with a power-gated boot front door."""
    read_started = time.monotonic()
    observed_boot_state = safe_read_boot_state()
    read_latency_ms = (time.monotonic() - read_started) * 1000.0

    state = merge_live_boot_state(state, observed_boot_state)
    state = _refresh_state_session_snapshot(state)

    shutdown_reader = globals().get("system_quiesce_status")
    shutdown_status = dict(shutdown_reader() or {}) if callable(shutdown_reader) else {
        "schema": "ORF_SYSTEM_QUIESCE_V0_1",
        "state": "RUNNING",
        "writes_enabled": True,
        "active_writes": 0,
        "countdown_seconds": 0,
        "drain_state": "IDLE",
        "clients_return_to_boot": False,
    }
    state.setdefault("runtime", {})["shutdown"] = copy.deepcopy(shutdown_status)
    state.setdefault("maintenance", {})["runtime_shutdown"] = copy.deepcopy(shutdown_status)

    power_started = bool(boot_power_started_state)
    boot_target = str(boot_target_state or BOOT_FRONT_DEFAULT_TARGET).upper()
    if boot_target not in {BOOT_FRONT_TARGET_DESKTOP, BOOT_FRONT_TARGET_BIOS}:
        boot_target = BOOT_FRONT_DEFAULT_TARGET

    presentation = _presentation_generation_status(presentation_generation_state)

    # Before POWER, prior Drive READY state is history only.  The boot screen owns
    # presentation and stays deterministically OFF regardless of old telemetry.
    if not power_started:
        boot_state = _boot_front_off_state()
        boot_state["_bios_presentation_generation"] = presentation["own_generation"]
        boot_state["_bios_active_presentation_generation"] = presentation["active_generation"]
        boot_state["_bios_active_presentation_url"] = presentation["active_url"]
        boot_state["_bios_active_presentation_origin"] = presentation["active_origin"]
        boot_state["_bios_presentation_generation_match"] = presentation["generation_match"]
        boot_state["_bios_presentation_stability"] = presentation["stability"]
        boot_state["_bios_presentation_health_failures"] = presentation["health_failures"]
        boot_state["_bios_presentation_restart_count"] = presentation["restart_count"]
        freshness_state = copy.deepcopy(freshness_state or new_boot_freshness_state(observed_boot_state))
        freshness_state["gate_state"] = "WAITING_FOR_POWER"
        freshness_state["fresh_reason"] = "POWER_NOT_REQUESTED"
        manual_view_state = {"manual_hold": False, "baseline": []}
        transition_complete = False
        show_root = False
        show_bios = False
        show_boot = True
        kernel_live = False
        heartbeat_age_seconds = None
        ready_now = False
    else:
        boot_state = copy.deepcopy(observed_boot_state or {})
        elapsed = max(0.0, time.monotonic() - float(started_at))
        freshness_state, _ = evaluate_boot_freshness(
            boot_state,
            freshness_state,
            elapsed,
            read_latency_ms,
        )

        state_name = str((boot_state or {}).get("state", "")).upper()
        kernel_live, heartbeat_age_seconds = _kernel_heartbeat_status(boot_state)
        boot_state["_bios_kernel_live"] = bool(kernel_live)
        boot_state["_bios_heartbeat_age_seconds"] = heartbeat_age_seconds
        boot_state["_bios_presentation_generation"] = presentation["own_generation"]
        boot_state["_bios_active_presentation_generation"] = presentation["active_generation"]
        boot_state["_bios_active_presentation_url"] = presentation["active_url"]
        boot_state["_bios_active_presentation_origin"] = presentation["active_origin"]
        boot_state["_bios_presentation_generation_match"] = presentation["generation_match"]
        boot_state["_bios_presentation_stability"] = presentation["stability"]
        boot_state["_bios_presentation_health_failures"] = presentation["health_failures"]
        boot_state["_bios_presentation_restart_count"] = presentation["restart_count"]

        start_record_reader = globals().get("read_dev_kernel_power_start_record")
        start_record = start_record_reader() if callable(start_record_reader) else {}
        power_runtime_state = str((start_record or {}).get("state") or "").upper()
        power_cycle_complete = power_runtime_state == "RUNNING"
        request_window_elapsed = elapsed >= BOOT_BIOS_REQUEST_WINDOW_SECONDS
        ready_now = (
            state_name == "READY"
            and kernel_live
            and power_cycle_complete
            and request_window_elapsed
        )
        boot_state["_bios_power_runtime_state"] = power_runtime_state or "UNKNOWN"
        boot_state["_bios_bios_request_window_seconds"] = BOOT_BIOS_REQUEST_WINDOW_SECONDS
        boot_state["_bios_bios_request_window_elapsed"] = bool(request_window_elapsed)
        manual_view_state = copy.deepcopy(manual_view_state or {})
        manual_hold = bool(manual_view_state.get("manual_hold"))
        current_signature = list(_boot_view_signature(boot_state))
        baseline_signature = list(manual_view_state.get("baseline") or [])

        if manual_hold:
            if baseline_signature and current_signature != baseline_signature:
                manual_hold = False
                manual_view_state = {
                    "manual_hold": False,
                    "baseline": current_signature,
                }
            else:
                manual_view_state = {
                    "manual_hold": True,
                    "baseline": baseline_signature or current_signature,
                }

        requested_surface_owner = str(primary_surface_owner_state or "AUTO").upper()
        show_root = requested_surface_owner == "ROOT_SELECTION"

        if show_root:
            show_boot = False
            show_bios = False
            freshness_state["gate_state"] = "ROOT_SELECTION_ACTIVE"
        elif manual_hold:
            show_boot = True
            show_bios = False
            freshness_state["gate_state"] = "MANUAL_BOOT_VIEW_HOLD"
        elif ready_now and boot_target == BOOT_FRONT_TARGET_BIOS:
            transition_complete = True
            show_boot = False
            show_bios = True
            if BOOT_FRONT_RUNTIME_CLASS == "COLD" and BOOT_FRONT_DEFAULT_TARGET == BOOT_FRONT_TARGET_BIOS:
                freshness_state["gate_state"] = "LIVE_READY_COLD_BIOS_HANDOFF"
                freshness_state["fresh_reason"] = "POWER_READY_COLD_DEFAULT_BIOS"
            else:
                freshness_state["gate_state"] = "LIVE_READY_BIOS_REQUESTED"
                freshness_state["fresh_reason"] = "POWER_READY_BIOS_OVERRIDE"
        elif ready_now:
            # DESKTOP is the warm-runtime default route. Keep BOOT visible while the browser
            # requests Home; navigation replaces this surface as soon as Home is READY.
            transition_complete = True
            show_boot = True
            show_bios = False
            freshness_state["gate_state"] = "LIVE_READY_DESKTOP_HANDOFF"
            freshness_state["fresh_reason"] = "POWER_READY_DEFAULT_DESKTOP"
        else:
            transition_complete = False
            show_boot = True
            show_bios = False
            start_state = power_runtime_state
            if start_state == "FAILED":
                freshness_state["gate_state"] = "POWER_KERNEL_START_FAILED"
            elif start_state in {"RESTART_REQUESTED", "RESTARTING"}:
                freshness_state["gate_state"] = "POWER_KERNEL_RESTARTING"
            elif start_state in {"REQUESTED", "BOOTING"}:
                freshness_state["gate_state"] = "POWER_KERNEL_STARTING"
            elif not request_window_elapsed:
                freshness_state["gate_state"] = "BIOS_REQUEST_WINDOW"
            elif state_name == "READY" and not kernel_live:
                freshness_state["gate_state"] = "READY_WAITING_FOR_LIVE_KERNEL"
            elif state_name == "READY" and start_state != "RUNNING":
                freshness_state["gate_state"] = "READY_WAITING_FOR_POWER_CYCLE"
            else:
                freshness_state["gate_state"] = "WAITING_FOR_LIVE_KERNEL_READY"

    boot_state["_bios_power_started"] = bool(power_started)
    boot_state["_bios_boot_target"] = boot_target
    boot_state["_bios_boot_default_target"] = BOOT_FRONT_DEFAULT_TARGET
    boot_state["_bios_runtime_boot_class"] = BOOT_FRONT_RUNTIME_CLASS
    boot_state["_bios_home_handoff_ready"] = bool(
        power_started and ready_now and boot_target == BOOT_FRONT_TARGET_DESKTOP
    )
    boot_state["_bios_kernel_live"] = bool(kernel_live)
    boot_state["_bios_heartbeat_age_seconds"] = heartbeat_age_seconds
    boot_state["_bios_ready_gate_state"] = freshness_state.get("gate_state")
    boot_state["_bios_fresh_reason"] = freshness_state.get("fresh_reason")
    boot_state["_bios_initial_heartbeat_sequence"] = freshness_state.get("initial_heartbeat_sequence")
    boot_state["_bios_observed_heartbeat_sequence"] = int(boot_state.get("heartbeat_sequence") or 0)
    shutdown_state = str(shutdown_status.get("state") or "RUNNING").upper()
    shutdown_pending = shutdown_state in {"QUIESCING", "DRAINING", "CLIENT_BOOT", "RUNTIME_RELEASE", "FAILED"}
    shutdown_force_boot = bool(shutdown_status.get("clients_return_to_boot")) or shutdown_state in {
        "DRAINING", "CLIENT_BOOT", "RUNTIME_RELEASE", "FAILED"
    }
    if shutdown_force_boot:
        show_root = False
        show_bios = False
        show_boot = True
        transition_complete = False

    boot_state["_bios_shutdown_state"] = shutdown_state
    boot_state["_bios_shutdown_pending"] = shutdown_pending
    boot_state["_bios_shutdown_remaining_seconds"] = int(shutdown_status.get("countdown_seconds") or 0)
    boot_state["_bios_shutdown_writes_enabled"] = bool(shutdown_status.get("writes_enabled"))
    boot_state["_bios_shutdown_active_writes"] = int(shutdown_status.get("active_writes") or 0)
    boot_state["_bios_shutdown_drain_state"] = str(shutdown_status.get("drain_state") or "IDLE")
    boot_state["_bios_shutdown_drain_timed_out"] = bool(shutdown_status.get("drain_timed_out"))
    boot_state["_bios_shutdown_clients_return_to_boot"] = bool(shutdown_status.get("clients_return_to_boot"))
    boot_state["_bios_surface_owner"] = (
        "ROOT_SELECTION" if show_root else ("BIOS" if show_bios else "BOOT")
    )

    presented_boot_state = (
        copy.deepcopy(boot_state)
        if not power_started
        else boot_presentation_state(boot_state, transition_complete)
    )

    return (
        state,
        presented_boot_state,
        render_header(state),
        render_page(state),
        render_rail(state),
        render_bottom(state),
        bool(transition_complete),
        freshness_state,
        manual_view_state,
        render_boot_gate_status(presented_boot_state, freshness_state, transition_complete),
        render_surface_owner_style(show_boot=show_boot, show_bios=show_bios, show_root=show_root),
        gr.update(active=(shutdown_state != "RUNTIME_RELEASE")),
    )

def render_header(state):
    ident = state["identity"]
    link = state["device_link"]
    mutation = state["ui"]["mutation_state"]
    machine_state = state.get("telemetry", {}).get("boot_state", "UNKNOWN")
    now = datetime.now().strftime("%H:%M")
    return f"""
    <div class="orf-shell orf-header">
      <div class="orf-bios-logo">
        <div class="orf-planet" aria-hidden="true"></div>
        <div class="orf-wordmark">BIOS</div>
      </div>
      <div class="orf-header-center">
        <div class="orf-title">ORFMOS CLOUD SYSTEM FIRMWARE</div>
        <div class="orf-sub">
          DEVICE: {_esc(ident["device"])} &nbsp;•&nbsp;
          ARCH: {_esc(ident["architecture"])} &nbsp;•&nbsp;
          LINK: {_esc(link["connection_state"])}
        </div>
      </div>
      <div class="orf-header-state">
        <div class="{_state_class(machine_state)}">● {_esc(machine_state)}</div>
        <div style="margin-top:4px;color:#6f8da1">DEVICE: {_esc(link["pairing_state"])}</div>
        <div style="margin-top:4px;color:#6f8da1">UI: {_esc(mutation)}</div>
        <div style="margin-top:4px;color:#587488">{now}</div>
      </div>
    </div>
    """


def render_system(state):
    ident = state["identity"]
    link = state["device_link"]
    sys = state["system"]
    own = state["ownership"]
    obs = state.get("session_observations") or {}
    net = obs.get("network") or {}
    profile = obs.get("client_profile") or {}
    telem = obs.get("telemetry") or {}
    device_profile = obs.get("device_profile") or {}
    device_telem = obs.get("device_telemetry") or {}
    dp_identity = device_profile.get("identity") or {}
    dp_android = device_profile.get("android") or {}
    dp_cpu = device_profile.get("cpu") or {}
    dp_memory = device_profile.get("memory") or {}
    dp_storage = device_profile.get("storage") or {}
    dp_display = device_profile.get("display") or {}
    dt_process = device_telem.get("process") or {}
    dt_battery = device_telem.get("battery") or {}
    dt_thermal = device_telem.get("thermal") or {}
    screen = profile.get("screen") or {}
    viewport = telem.get("viewport") or profile.get("viewport") or {}
    connection = telem.get("connection") or profile.get("connection") or {}
    battery = telem.get("battery") or {}
    summary = _orf_session_summary()
    return f"""
    <div class="orf-page">
      <div class="orf-page-title">SYSTEM OVERVIEW</div>
      {_section("DEVICE SESSION", [
          _row("CONNECTED DEVICES", summary["connected_devices"], "green" if summary["connected_devices"] else "gray"),
          _row("ACTIVE SESSIONS", summary["active_sessions"], "green" if summary["active_sessions"] else "gray"),
          _row("CLIENT INSTANCE", link.get("client_instance_id") or "UNRESOLVED", "blue"),
          _row("SESSION", link.get("session_id") or "UNRESOLVED", "blue"),
          _row("SESSION STATE", link.get("session_state") or "INACTIVE"),
          _row("BROWSER PROFILE", link.get("profile_state") or "NOT_COLLECTED"),
          _row("BROWSER TELEMETRY", link.get("telemetry_state") or "INACTIVE"),
          _row("DEVICE PROFILE", link.get("device_profile_state") or "NOT_REPORTED", "green" if link.get("device_profile_state") == "REPORTED" else "gray"),
          _row("DEVICE TELEMETRY", link.get("device_telemetry_state") or "INACTIVE", "green" if link.get("device_telemetry_state") == "ACTIVE" else "gray"),
          _row("DEVICE TELEMETRY SEQ", link.get("device_telemetry_sequence") or 0, "blue"),
          _row("LAST SEEN UTC", link.get("last_seen_utc") or "—", "blue"),
      ])}
      {_section("NETWORK OBSERVATIONS", [
          _row("PEER ADDRESS", net.get("peer_address") or "UNRESOLVED", "blue"),
          _row("X-FORWARDED-FOR", (net.get("forwarding_headers") or {}).get("x-forwarded-for") or "UNAVAILABLE", "blue"),
          _row("NETWORK AUTHORITY", net.get("observation_authority") or "UNRESOLVED", "gray"),
      ])}
      {_section("DEVICE-REPORTED PROFILE", [
          _row("DEVICE ID", device_profile.get("device_id") or "UNRESOLVED", "green" if device_profile.get("device_id") else "gray"),
          _row("PROVIDER", device_profile.get("profile_provider") or "UNAVAILABLE", "blue"),
          _row("AUTHORITY", device_profile.get("profile_authority") or "UNAVAILABLE", "gray"),
          _row("MANUFACTURER", dp_identity.get("manufacturer") or "UNAVAILABLE", "blue"),
          _row("MODEL", dp_identity.get("model") or "UNAVAILABLE", "blue"),
          _row("ANDROID", f'{dp_android.get("release", "?")} / API {dp_android.get("sdk_int", "?")}', "blue"),
          _row("SECURITY PATCH", dp_android.get("security_patch") or "UNAVAILABLE", "blue"),
          _row("SOC", dp_cpu.get("soc_model") or dp_cpu.get("hardware") or "UNAVAILABLE", "blue"),
          _row("ABI", ", ".join(str(x) for x in (dp_cpu.get("supported_abis") or [])) or "UNAVAILABLE", "blue"),
          _row("CPU CORES", dp_cpu.get("available_processors") if dp_cpu.get("available_processors") is not None else "UNAVAILABLE", "blue"),
          _row("RAM TOTAL", _fmt_bytes(dp_memory.get("total_bytes")), "blue"),
          _row("STORAGE TOTAL", _fmt_bytes(dp_storage.get("total_bytes")), "blue"),
          _row("DISPLAY", f'{dp_display.get("width_px", "?")}×{dp_display.get("height_px", "?")} @ {dp_display.get("density_dpi", "?")} dpi', "blue"),
          _row("SERVER RECEIVE UTC", obs.get("device_profile_received_utc") or "UNAVAILABLE", "blue"),
      ])}
      {_section("LIVE DEVICE TELEMETRY", [
          _row("RAM AVAILABLE", _fmt_bytes((device_telem.get("memory") or {}).get("available_bytes")), "blue"),
          _row("RAM UTILIZATION", _fmt_percent((device_telem.get("memory") or {}).get("utilization_percent")), "blue"),
          _row("STORAGE AVAILABLE", _fmt_bytes((device_telem.get("storage") or {}).get("available_bytes")), "blue"),
          _row("STORAGE UTILIZATION", _fmt_percent((device_telem.get("storage") or {}).get("utilization_percent")), "blue"),
          _row("CONSOLE PROCESS CPU", _fmt_percent(dt_process.get("cpu_percent")), "blue"),
          _row("CONSOLE PROCESS PSS", _fmt_bytes(dt_process.get("pss_bytes")), "blue"),
          _row("BATTERY", f'{round(float(dt_battery.get("level_percent")))}%' if dt_battery.get("level_percent") is not None else "UNAVAILABLE", "blue"),
          _row("POWER SOURCE", dt_battery.get("power_source") or "UNAVAILABLE", "blue"),
          _row("BATTERY TEMP", f'{dt_battery.get("temperature_c")} °C' if dt_battery.get("temperature_c") is not None else "UNAVAILABLE", "blue"),
          _row("THERMAL", dt_thermal.get("status_name") or "UNAVAILABLE", "blue"),
          _row("DEVICE UTC", device_telem.get("device_utc") or "UNAVAILABLE", "blue"),
          _row("SERVER RECEIVE UTC", obs.get("device_telemetry_received_utc") or "UNAVAILABLE", "blue"),
      ])}
      {_section("CLIENT / BROWSER PROFILE", [
          _row("USER AGENT", profile.get("user_agent") or "UNAVAILABLE", "blue"),
          _row("PLATFORM", profile.get("platform") or "UNAVAILABLE", "blue"),
          _row("LANGUAGE", profile.get("language") or "UNAVAILABLE", "blue"),
          _row("TIMEZONE", profile.get("timezone") or "UNAVAILABLE", "blue"),
          _row("SCREEN", f'{screen.get("width", "?")}×{screen.get("height", "?")} @ {profile.get("device_pixel_ratio", "?")}x', "blue"),
          _row("VIEWPORT", f'{viewport.get("width", "?")}×{viewport.get("height", "?")}', "blue"),
          _row("TOUCH POINTS", profile.get("max_touch_points") if profile.get("max_touch_points") is not None else "UNAVAILABLE", "blue"),
          _row("HW CONCURRENCY", profile.get("hardware_concurrency") if profile.get("hardware_concurrency") is not None else "UNAVAILABLE", "blue"),
          _row("DEVICE MEMORY HINT", profile.get("device_memory_gb") if profile.get("device_memory_gb") is not None else "UNAVAILABLE", "blue"),
      ])}
      {_section("LIVE CLIENT TELEMETRY", [
          _row("ONLINE", telem.get("online") if telem.get("online") is not None else "UNAVAILABLE"),
          _row("VISIBILITY", telem.get("visibility_state") or "UNAVAILABLE", "blue"),
          _row("NETWORK TYPE", connection.get("effective_type") or connection.get("type") or "UNAVAILABLE", "blue"),
          _row("NETWORK RTT", f'{connection.get("rtt_ms")} ms' if connection.get("rtt_ms") is not None else "UNAVAILABLE", "blue"),
          _row("DOWNLINK", f'{connection.get("downlink_mbps")} Mbps' if connection.get("downlink_mbps") is not None else "UNAVAILABLE", "blue"),
          _row("BATTERY", f'{round(float(battery.get("level"))*100)}%' if battery.get("level") is not None else "UNAVAILABLE", "blue"),
          _row("CHARGING", battery.get("charging") if battery.get("charging") is not None else "UNAVAILABLE", "blue"),
          _row("DEVICE UTC", telem.get("device_utc") or "UNAVAILABLE", "blue"),
          _row("SERVER RECEIVE UTC", obs.get("telemetry_received_utc") or "UNAVAILABLE", "blue"),
      ])}
      {_section("DEVICE IDENTITY", [
          _row("DEVICE", ident["device"], "blue"),
          _row("ARCHITECTURE", ident["architecture"], "blue"),
          _row("PLATFORM ROLE", ident["platform_role"], "green"),
          _row("COMPATIBILITY HOST", ident["compatibility_host"], "blue"),
          _row("IDENTITY AUTHORITY", ident["authority"], "blue"),
          _row("FIRMWARE", f'BIOS v{ident["firmware_version"]}', "blue"),
      ])}
      {_section("DEVICE HARDWARE", [
          _row("CPU", sys["cpu"]["model"], "blue"),
          _row("CPU CORES", sys["cpu"]["cores"] if sys["cpu"]["cores"] is not None else "PROBE PENDING", "gray"),
          _row("THERMAL STATE", sys["cpu"]["thermal_state"] if sys["cpu"]["thermal_state"] != "OK" else "PROBE PENDING", "gray"),
          _row("CPU UTILIZATION", _fmt_percent(sys["cpu"].get("utilization")), "blue"),
          _row("MEMORY TOTAL", _fmt_bytes(sys["memory"]["total"]) if isinstance(sys["memory"]["total"], (int, float)) else sys["memory"]["total"], "blue" if isinstance(sys["memory"]["total"], (int, float)) else "gray"),
          _row("MEMORY AVAILABLE", _fmt_bytes(sys["memory"]["available"]) if isinstance(sys["memory"]["available"], (int, float)) else sys["memory"]["available"], "blue" if isinstance(sys["memory"]["available"], (int, float)) else "gray"),
          _row("MEMORY UTILIZATION", _fmt_percent(sys["memory"].get("utilization")), "blue"),
          _row("STORAGE TOTAL", _fmt_bytes(sys["storage"]["total"]) if isinstance(sys["storage"]["total"], (int, float)) else sys["storage"]["total"], "blue" if isinstance(sys["storage"]["total"], (int, float)) else "gray"),
          _row("STORAGE AVAILABLE", _fmt_bytes(sys["storage"]["available"]) if isinstance(sys["storage"]["available"], (int, float)) else sys["storage"]["available"], "blue" if isinstance(sys["storage"]["available"], (int, float)) else "gray"),
          _row("STORAGE UTILIZATION", _fmt_percent(sys["storage"].get("utilization")), "blue"),
          _row("POWER SOURCE", sys["power"].get("source") or "UNAVAILABLE", "blue"),
          _row("BATTERY", f'{round(float(sys["power"].get("battery_percent")))}%' if sys["power"].get("battery_percent") is not None else "UNAVAILABLE", "blue"),
      ])}
      {_section("ORF OWNERSHIP", [
          _row("HOME ROLE", own["home_role"], "green"),
          _row("PACKAGE MANAGER", own["package_manager"], "blue"),
          _row("FILE SURFACE", own["file_surface"], "green"),
          _row("RUNTIME PROVIDER", own["runtime_provider"], "blue"),
          _row("EXECUTION AUTHORITY", own["execution_authority"], "green"),
      ])}
    </div>
    """


def render_boot(state):
    boot = state["boot"]
    root = state["root_selection"]
    active_root = root["active_root"]
    current_runtime = root["current_runtime"]
    kernel_root = root.get("kernel", {})
    fallback = root["fallback_root"]
    last = boot["last_boot"]
    selected = BOOT_TARGET_LABELS.get(
        boot["selected_target"], boot["selected_target"]
    )
    staged = state["ui"]["staged_changes"]
    staged_text = (
        BOOT_TARGET_LABELS.get(
            staged[-1]["requested_value"],
            staged[-1]["requested_value"],
        )
        if staged else "NONE"
    )
    return f"""
    <div class="orf-page">
      <div class="orf-page-title">BOOT CONFIGURATION</div>
      {_section("SOURCE SELECTION", [
          _row("KERNEL SOURCE", (root.get("kernel_source") or {}).get("provider") or "UNRESOLVED", "green"),
          _row("KERNEL STATE", (root.get("kernel_source") or {}).get("selection_state") or "UNKNOWN"),
          _row("KERNEL PATH", kernel_root.get("relative_path") or "—", "blue"),
          _row("ORFMOS ROOT SOURCE", (root.get("root_source") or {}).get("provider") or "UNRESOLVED", "green"),
          _row("ROOT STATE", (root.get("root_source") or {}).get("selection_state") or "UNKNOWN"),
          _row("ACTIVE ROOT", active_root["root_id"] or "UNRESOLVED", "blue"),
          _row("AUTHORITY", root["authority"], "blue"),
          _row("APPLY SEQUENCE", (root.get("selection") or {}).get("apply_sequence", 0), "blue"),
          _row("RECOVERY AUTHORITY", "SEPARATE", "green"),
      ])}
      {_section("CURRENT BOOT ROUTE", [
          _row("SELECTED TARGET", selected, "green"),
          _row("STAGED TARGET", staged_text, "amber" if staged else "gray"),
          _row("RUNTIME PROVIDER", boot["runtime_provider"], "blue"),
          _row("PRESENTATION", boot["presentation"], "green"),
      ])}
      {_section("LAST BOOT", [
          _row("STATE", last["state"]),
          _row("PHASE", state.get("telemetry", {}).get("phase"), "blue"),
          _row(
              "RECOVERY USED",
              "YES" if last["recovery_used"] else "NO",
              "amber" if last["recovery_used"] else "green",
          ),
          _row("SEQUENCE", last["sequence"], "blue"),
          _row("BOOT ID", last["boot_id"], "blue"),
          _row("MESSAGE", state.get("telemetry", {}).get("message"), "blue"),
      ])}
      {_section("MUTATION CONTRACT", [
          _row("MODE", "STAGE → REVIEW → APPLY", "amber"),
          _row("AUTHORITY", "SYNTHETIC ONLY IN v0.1", "blue"),
          _row("DEVICE MUTATION", "DISABLED", "green"),
      ])}
    </div>
    """



def _fmt_bytes(value):
    if value is None:
        return "UNAVAILABLE"
    value = float(value)
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    return f"{value:.1f} {units[idx]}"


def _fmt_percent(value):
    if value is None:
        return "UNAVAILABLE"
    return f"{float(value):.1f}%"


def _fmt_uptime(value):
    if value is None:
        return "UNAVAILABLE"
    seconds = int(float(value))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    return f"{minutes}m {secs:02d}s"


def render_runtime(state):
    runtime = state["runtime"]
    labels = {
        "kernel": "KERNEL",
        "drive_api": "DRIVE API",
        "github": "GITHUB",
        "recovery": "RECOVERY",
        "presentation_bridge": "PRESENTATION",
    }
    rows = []
    for key, label in labels.items():
        item = runtime[key]
        rows.append(
            '<div class="orf-service-row">'
            f'<div class="orf-service-name">{label}</div>'
            f'<div class="orf-value {_state_class(item["state"])}">{_esc(item["state"])}</div>'
            f'<div class="orf-service-authority">{_esc(item["authority"])}</div>'
            '</div>'
        )

    table = (
        '<section class="orf-section">'
        '<div class="orf-section-title">ORF EXECUTION FABRIC</div>'
        + "".join(rows)
        + '</section>'
    )

    return f"""
    <div class="orf-page">
      <div class="orf-page-title">RUNTIME</div>
      {table}
      {_section("COLAB KERNEL RUNTIME ENVIRONMENT", [
          _row("CONNECTED DEVICES", _orf_session_summary()["connected_devices"], "green" if _orf_session_summary()["connected_devices"] else "gray"),
          _row("ACTIVE SESSIONS", _orf_session_summary()["active_sessions"], "green" if _orf_session_summary()["active_sessions"] else "gray"),
          _row("TELEMETRY STREAMS", _orf_session_summary()["telemetry_streams"], "green" if _orf_session_summary()["telemetry_streams"] else "gray"),
          _row("PROVIDER", state.get("telemetry", {}).get("runtime_environment", {}).get("provider", "UNAVAILABLE"), "blue"),
          _row("CPU", _fmt_percent(state.get("telemetry", {}).get("runtime_environment", {}).get("cpu_percent")), "blue"),
          _row("RAM", _fmt_percent(state.get("telemetry", {}).get("runtime_environment", {}).get("memory_percent")), "blue"),
          _row("RAM AVAILABLE", _fmt_bytes(state.get("telemetry", {}).get("runtime_environment", {}).get("memory_available_bytes")), "blue"),
          _row("DISK", _fmt_percent(state.get("telemetry", {}).get("runtime_environment", {}).get("disk_percent")), "blue"),
          _row("DISK FREE", _fmt_bytes(state.get("telemetry", {}).get("runtime_environment", {}).get("disk_free_bytes")), "blue"),
          _row("PROCESS RSS", _fmt_bytes(state.get("telemetry", {}).get("runtime_environment", {}).get("process_rss_bytes")), "blue"),
          _row("RUNTIME UPTIME", _fmt_uptime(state.get("telemetry", {}).get("runtime_environment", {}).get("process_uptime_seconds")), "blue"),
          _row("PYTHON", state.get("telemetry", {}).get("runtime_environment", {}).get("python_version", "UNAVAILABLE"), "blue"),
      ])}
      {_section("LIVE KERNEL TELEMETRY", [
          _row("STATE", state.get("telemetry", {}).get("boot_state"), _state_class(state.get("telemetry", {}).get("boot_state"))),
          _row("PHASE", state.get("telemetry", {}).get("phase"), "blue"),
          _row("PROGRESS", f'{round(float(state.get("telemetry", {}).get("progress") or 0) * 100) if float(state.get("telemetry", {}).get("progress") or 0) <= 1 else round(float(state.get("telemetry", {}).get("progress") or 0))}%', "blue"),
          _row("SEQUENCE", state.get("telemetry", {}).get("sequence"), "blue"),
          _row("KERNEL ID", state.get("telemetry", {}).get("kernel_id"), "blue"),
          _row("KERNEL VERSION", state.get("telemetry", {}).get("kernel_version"), "blue"),
          _row("BOOT ID", state.get("telemetry", {}).get("boot_id"), "blue"),
          _row("KERNEL PULSE", "LIVE" if state.get("telemetry", {}).get("kernel_alive") else "NOT PROVEN", "green" if state.get("telemetry", {}).get("kernel_alive") else "amber"),
          _row("HEARTBEAT SEQ", state.get("telemetry", {}).get("heartbeat_sequence"), "blue"),
          _row("HEARTBEAT UTC", state.get("telemetry", {}).get("heartbeat_utc"), "blue"),
          _row("MONITOR MODE", state.get("telemetry", {}).get("monitor_mode") or "—", "blue"),
          _row("UPDATED UTC", state.get("telemetry", {}).get("updated_utc"), "blue"),
      ])}
      {_section("RUNTIME CONTRACT", [
          _row("STATE SOURCE", state.get("telemetry", {}).get("source", BIOS_SCHEMA), "blue"),
          _row("SOURCE MODE", state.get("telemetry", {}).get("source_mode", "SYNTHETIC"), "blue"),
          _row("EXECUTION AUTHORITY", "ORF", "green"),
          _row("PRESENTATION AUTHORITY", "NONAUTHORITATIVE", "blue"),
          _row("CURRENT PROVIDER", state["boot"]["runtime_provider"], "blue"),
      ])}
    </div>
    """


def render_recovery(state):
    rec = state["recovery"]
    sec = state["security"]
    return f"""
    <div class="orf-page">
      <div class="orf-page-title">RECOVERY</div>
      {_section("RECOVERY STATE", [
          _row("LAST KNOWN GOOD", rec["last_known_good"]),
          _row("DEPENDENCY PACKAGE", rec["dependency_package"]),
          _row("RUNTIME SNAPSHOT", rec["runtime_snapshot"]),
          _row("SIGNING AUTHORITY", rec["signing_authority"], "green"),
      ])}
      {_section("SECURITY GATES", [
          _row("MAINTAINER GATE", sec["maintainer_gate"], "gray"),
          _row("PACKAGE AUTHORITY", sec["package_authority"]),
          _row("INTEGRITY", sec["integrity"]),
      ])}
      {_section("RECOVERY ACTIONS", [
          _row("INSPECT LAST KNOWN GOOD", "AVAILABLE", "green"),
          _row("VERIFY RECOVERY ARTIFACTS", "AVAILABLE", "green"),
          _row("TEST HYDRATION", "LOCKED IN v0.1", "gray"),
          _row("RECONSTRUCT RUNTIME", "LOCKED IN v0.1", "gray"),
          _row("FACTORY RECOVERY", "LOCKED IN v0.1", "gray"),
      ])}
    </div>
    """


def render_maintenance(state):
    status = _maintenance_runtime_status()
    active = bool(status.get("active"))
    candidate = status.get("kernel_candidate") or {}
    active_kernel = status.get("active_kernel") or {}
    gate_state = "ACTIVE" if active else str(status.get("state") or "LOCKED").upper()
    return f"""
    <div class="orf-page">
      <div class="orf-page-title">MAINTENANCE</div>
      {_section("TRUSTED MAINTAINER SESSION", [
          _row("GATE", gate_state, "green" if active else "gray"),
          _row("AUTHORITY", "KORF SIGNER CHALLENGE", "blue"),
          _row("SIGNER", status.get("signer_dn") or "UNAVAILABLE", "blue"),
          _row("CERT SHA256", status.get("certificate_sha256") or "UNAVAILABLE", "blue"),
          _row("SESSION", status.get("session_id") or "NONE", "green" if active else "gray"),
          _row("EXPIRES", f"{int(status.get('expires_in_seconds') or 0)}s" if active else "—", "green" if active else "gray"),
      ])}
      {_section("KERNEL UPDATE AUTHORITY", [
          _row("ACTIVE SOURCE", active_kernel.get("source") or "BASE_PIN", "blue"),
          _row("ACTIVE REF", active_kernel.get("ref") or "UNRESOLVED", "blue"),
          _row("ACTIVE PATH", active_kernel.get("prefix") or "UNRESOLVED", "blue"),
          _row("ACTIVE MANIFEST", active_kernel.get("manifest_sha256") or "UNRESOLVED", "blue"),
          _row("CANDIDATE", candidate.get("state") or "IDLE", "green" if candidate.get("state") == "STAGED_VERIFIED" else "gray"),
          _row("CANDIDATE VERSION", candidate.get("version") or "—", "blue"),
          _row("CANDIDATE MANIFEST", candidate.get("manifest_sha256") or "—", "blue"),
      ])}
      {_section("TERMINAL RUNTIME CONTROL", [
          _row("COLAB RUNTIME SHUTDOWN", str((status.get("runtime_shutdown") or {}).get("state") or ("AVAILABLE" if active else "LOCKED")), "red" if active else "gray"),
          _row("WRITE GATE", "OPEN" if (status.get("runtime_shutdown") or {}).get("writes_enabled", True) else "LOCKED", "green" if (status.get("runtime_shutdown") or {}).get("writes_enabled", True) else "amber"),
          _row("ACTIVE WRITES", int((status.get("runtime_shutdown") or {}).get("active_writes") or 0), "amber" if int((status.get("runtime_shutdown") or {}).get("active_writes") or 0) else "green"),
          _row("ACTION", "10s QUIESCE → DRAIN → BOOT → DISCONNECT", "red" if active else "gray"),
          _row("PERSISTENCE", "NO MAINTENANCE SESSION SURVIVES COLD BOOT", "green"),
      ])}
    </div>
    """


def render_page(state):
    page = state["ui"]["active_page"]
    if page == "BOOT":
        return render_boot(state)
    if page == "RUNTIME":
        return render_runtime(state)
    if page == "RECOVERY":
        return render_recovery(state)
    if page == "MAINTENANCE":
        return render_maintenance(state)
    return render_system(state)


def render_rail(state):
    runtime = state["runtime"]
    sys = state["system"]
    sec = state["security"]
    link = state["device_link"]
    root = state["root_selection"]

    def rr(key, val):
        return (
            '<div class="orf-rail-row">'
            f'<span class="orf-rail-key">{_esc(key)}</span>'
            f'<span class="orf-rail-val {_state_class(val)}">{_esc(val)}</span>'
            '</div>'
        )

    return f"""
    <div class="orf-rail">
      <div class="orf-rail-title">LOCAL ORFMOS LINK</div>
      {rr("PAIR", link["pairing_state"])}
      {rr("LINK", link["connection_state"])}
      {rr("SESSION", link["session_state"])}
      {rr("PROBES", link["probe_stream"])}

      <div class="orf-rail-title" style="margin-top:14px">SOURCE CHAIN</div>
      {rr("KERNEL SRC", (root.get("kernel_source") or {}).get("provider") or "—")}
      {rr("KERNEL", (root.get("kernel_source") or {}).get("selection_state") or "—")}
      {rr("ROOT SRC", (root.get("root_source") or {}).get("provider") or "—")}
      {rr("ROOT", (root.get("root_source") or {}).get("selection_state") or "—")}

      <div class="orf-rail-title" style="margin-top:14px">CLOUD MACHINE STATE</div>
      {rr("KERNEL", runtime["kernel"]["state"])}
      {rr("DRIVE", runtime["drive_api"]["state"])}
      {rr("GITHUB", runtime["github"]["state"])}
      {rr("RECOVERY", runtime["recovery"]["state"])}
      {rr("PRESENT", runtime["presentation_bridge"]["state"])}

      <div class="orf-rail-title" style="margin-top:14px">BOOT TELEMETRY</div>
      {rr("PHASE", state.get("telemetry", {}).get("phase", "UNKNOWN"))}
      {rr("PROGRESS", f'{round(float(state.get("telemetry", {}).get("progress") or 0) * 100) if float(state.get("telemetry", {}).get("progress") or 0) <= 1 else round(float(state.get("telemetry", {}).get("progress") or 0))}%')}
      {rr("SEQ", state.get("telemetry", {}).get("sequence"))}

      <div class="orf-rail-title" style="margin-top:14px">COLAB RUNTIME</div>
      {rr("DEVICES", _orf_session_summary()["connected_devices"])}
      {rr("SESSIONS", _orf_session_summary()["active_sessions"])}
      {rr("CPU", _fmt_percent(state.get("telemetry", {}).get("runtime_environment", {}).get("cpu_percent")))}
      {rr("RAM", _fmt_percent(state.get("telemetry", {}).get("runtime_environment", {}).get("memory_percent")))}
      {rr("DISK", _fmt_percent(state.get("telemetry", {}).get("runtime_environment", {}).get("disk_percent")))}
      {rr("UP", _fmt_uptime(state.get("telemetry", {}).get("runtime_environment", {}).get("process_uptime_seconds")))}

      <div class="orf-rail-title" style="margin-top:14px">INTEGRITY</div>
      {rr("PACKAGE", sec["package_authority"])}
      {rr("SYSTEM", sec["integrity"])}
      {rr("GATE", sec["maintainer_gate"])}
    </div>
    """


def render_bottom(state):
    ui = state["ui"]
    staged_count = len(ui["staged_changes"])
    mode = ui["mutation_state"]

    if staged_count:
        return f"""
        <div class="orf-bottom">
          <span class="amber">{staged_count} CHANGE STAGED</span>
          <span>REVIEW &nbsp;•&nbsp; DISCARD &nbsp;•&nbsp; APPLY</span>
          <span>MAINTAINER: <strong>{_esc(state.get("security", {}).get("maintainer_gate") or "LOCKED")}</strong></span>
          <span>BIOS v{BIOS_VERSION}</span>
        </div>
        """

    return f"""
    <div class="orf-bottom">
      <span>◀ BACK &nbsp;&nbsp; ↑↓ SELECT &nbsp;&nbsp; ENTER OPEN</span>
      <span>PAGE: <strong>{_esc(ui["active_page"])}</strong></span>
      <span>DEVICE LINK: <strong>{_esc(state["device_link"]["connection_state"])}</strong></span>
      <span>MAINTAINER: <strong>{_esc(state.get("security", {}).get("maintainer_gate") or "LOCKED")}</strong></span>
      <span>BIOS v{BIOS_VERSION}</span>
    </div>
    """


def render_command(state):
    staged = state["ui"]["staged_changes"]
    if not staged:
        return {
            "schema": COMMAND_SCHEMA,
            "state": "NO_STAGED_COMMAND",
        }
    return staged[-1]


def render_surface_owner_style(show_boot=True, show_bios=False, show_root=False):
    """Backend-owned primary-surface display contract.

    BOOT, BIOS, and ROOT SELECTION are the only heartbeat-owned surfaces.
    Transient menus are deliberately excluded: RESET KERNEL owns its popup
    locally until CANCEL or CONTINUE resolves it, so the 1-second heartbeat
    cannot race the user and close a staged action.

    BOOT, BIOS, and ROOT SELECTION stay mounted for the lifetime of the
    presentation generation. The heartbeat emits one CSS ownership decision
    for all three surfaces so navigation cannot leave zero primary surfaces.
    """
    boot_display = "block" if show_boot else "none"
    bios_display = "block" if show_bios else "none"
    root_display = "block" if show_root else "none"
    if show_root:
        owner = "ROOT_SELECTION"
    elif show_bios and not show_boot:
        owner = "BIOS"
    else:
        owner = "BOOT"
    return f"""
    <style>
      #orfBootFront {{ display:{boot_display} !important; }}
      #orfBiosSurface {{ display:{bios_display} !important; }}
      #orfRootSelection {{ display:{root_display} !important; }}
    </style>
    <span style="display:none" data-orf-surface-owner="{owner}">{owner}</span>
    """


def boot_iframe_markup():
    return f"""
    <div class="orf-boot-host">
      <iframe
        id="orfBootFrame"
        srcdoc="{BOOT_SRCDOC}"
        title="ORFMOS Boot"
        allow="fullscreen"
      ></iframe>
    </div>
    """


def _show_reset_confirmation():
    return True


def _hide_reset_confirmation():
    return False


def confirm_kernel_reboot_and_close_prompt(boot_state):
    values = request_kernel_reboot_and_reset_boot_front(boot_state)
    return (*values, False)


def poll_boot_state():
    return safe_read_boot_state()


def evaluate_boot_transition(boot_state, started_at, already_complete):
    """
    Legacy visibility helper retained for compatibility.
    Active boot routing is owned by bios_heartbeat(): POWER gates execution,
    Runtime class owns the READY default: cold -> BIOS, warm -> DESKTOP;
    BIOS remains a pre-READY one-shot override for warm boots.
    """
    elapsed = max(0.0, time.monotonic() - float(started_at))
    state_name = str((boot_state or {}).get("state", "")).upper()
    ready = state_name == "READY"

    should_transition = ready

    if should_transition:
        return (
            gr.update(visible=False),
            gr.update(visible=True),
            True,
        )

    return (
        gr.update(visible=True),
        gr.update(visible=False),
        False,
    )



def _boot_view_signature(boot_state):
    boot_state = boot_state or {}
    # Manual boot-view hold follows lifecycle identity, not heartbeat counters.
    # sequence/signal_sequence/updated_utc are intentionally excluded so a live
    # Kernel pulse does not collapse the user's manual boot inspection surface.
    keys = (
        "state", "boot_id", "phase", "status", "generation",
    )
    return tuple(str(boot_state.get(key, "")) for key in keys)


def reset_boot_front_state(current_boot_state):
    current_boot_state = current_boot_state or {}
    return (
        time.monotonic(),
        False,
        new_boot_freshness_state(current_boot_state),
        {
            "manual_hold": True,
            "baseline": list(_boot_view_signature(current_boot_state)),
        },
    )


def request_kernel_reboot_and_reset_boot_front(current_boot_state):
    """Post a monitor-owned Kernel reboot request and return presentation to BOOT."""
    request_dev_kernel_reboot("BIOS_RESET_KERNEL_BUTTON")
    started_at, transition_complete, freshness, manual_view = reset_boot_front_state(
        current_boot_state
    )
    return (
        started_at,
        transition_complete,
        freshness,
        manual_view,
        "AUTO",
    )


def navigate(page, state):
    state = copy.deepcopy(state)
    state["ui"]["active_page"] = page
    if state["ui"]["mutation_state"] == "VERIFIED":
        state["ui"]["mutation_state"] = "VIEWING"

    selected = state["boot"]["selected_target"]

    return (
        state,
        render_header(state),
        render_page(state),
        render_rail(state),
        render_bottom(state),
        gr.update(visible=(page == "BOOT")),
        gr.update(value=selected),
        render_command(state),
        gr.update(visible=(page == "SYSTEM")),
        gr.update(visible=(page == "MAINTENANCE")),
    )


def stage_boot_target(target, state):
    state = copy.deepcopy(state)
    current = state["boot"]["selected_target"]

    if not target or target == current:
        state["ui"]["staged_changes"] = []
        state["ui"]["mutation_state"] = "VIEWING"
    else:
        command = new_bios_command(
            action="SET_BOOT_TARGET",
            target="boot.selected_target",
            requested_value=target,
            requires_maintainer=False,
        )
        state["ui"]["staged_changes"] = [command]
        state["ui"]["mutation_state"] = "STAGED"

    return (
        state,
        render_header(state),
        render_page(state),
        render_rail(state),
        render_bottom(state),
        render_command(state),
    )


def discard_staged(state):
    state = copy.deepcopy(state)
    state["ui"]["staged_changes"] = []
    state["ui"]["mutation_state"] = "VIEWING"
    current = state["boot"]["selected_target"]

    return (
        state,
        render_header(state),
        render_page(state),
        render_rail(state),
        render_bottom(state),
        gr.update(value=current),
        render_command(state),
    )


def apply_staged(state):
    state = copy.deepcopy(state)
    staged = state["ui"]["staged_changes"]

    if staged:
        command = staged[-1]
        if command["action"] == "SET_BOOT_TARGET":
            state["boot"]["selected_target"] = command["requested_value"]

    state["ui"]["staged_changes"] = []
    state["ui"]["mutation_state"] = "VERIFIED"
    current = state["boot"]["selected_target"]

    receipt = {
        "schema": COMMAND_SCHEMA,
        "state": "VERIFIED",
        "action": "SET_BOOT_TARGET",
        "applied_value": current,
        "authority": "SYNTHETIC_ONLY",
        "device_mutation": False,
        "verified_utc": datetime.now(timezone.utc).isoformat(),
    }

    return (
        state,
        render_header(state),
        render_page(state),
        render_rail(state),
        render_bottom(state),
        gr.update(value=current),
        receipt,
    )



def _source_selection_status_html(root_state, pending_kernel=None, pending_root=None, prefix="SOURCE READY"):
    root_state = root_state or {}
    kernel = root_state.get("kernel_source") or {}
    root = root_state.get("root_source") or {}
    active_kernel = str(kernel.get("provider") or "UNRESOLVED")
    active_root = str(root.get("provider") or "UNRESOLVED")
    pending_kernel = str(pending_kernel or active_kernel)
    pending_root = str(pending_root or active_root)
    dirty = pending_kernel != active_kernel or pending_root != active_root
    dirty_text = "PENDING CHANGES" if dirty else "NO PENDING CHANGES"
    return f"""
    <div class="orf-loader-status">
      {prefix}<br>
      ACTIVE KERNEL • {active_kernel} • {kernel.get('selection_state') or 'UNKNOWN'}<br>
      ACTIVE ROOT • {active_root} • {root.get('selection_state') or 'UNKNOWN'}<br>
      PENDING KERNEL • {pending_kernel}<br>
      PENDING ROOT • {pending_root}<br>
      {dirty_text}
    </div>
    """


def _source_button_update(selected, provider):
    provider = str(provider).upper()
    label = "GOOGLE DRIVE" if provider == "DRIVE" else "GITHUB"
    return gr.update(value=(f"✓ {label}" if str(selected).upper() == provider else label))


def stage_source_selection(kind, provider, pending_kernel, pending_root, state):
    kind = str(kind).upper()
    provider = str(provider).upper()
    if provider not in SOURCE_PROVIDERS:
        raise RuntimeError(f"Unsupported source provider: {provider}")
    pending_kernel = str(pending_kernel or "GITHUB").upper()
    pending_root = str(pending_root or "GITHUB").upper()
    if kind == "KERNEL":
        pending_kernel = provider
    elif kind == "ROOT":
        pending_root = provider
    else:
        raise RuntimeError(f"Unsupported source-selection axis: {kind}")
    root_state = (state or {}).get("root_selection") or ROOT_INITIAL_STATE
    return (
        pending_kernel,
        pending_root,
        _source_button_update(pending_kernel, "DRIVE"),
        _source_button_update(pending_kernel, "GITHUB"),
        _source_button_update(pending_root, "DRIVE"),
        _source_button_update(pending_root, "GITHUB"),
        _source_selection_status_html(root_state, pending_kernel, pending_root, "SOURCE STAGED"),
    )


def apply_source_selection(state, pending_kernel, pending_root):
    state = copy.deepcopy(state)
    pending_kernel = str(pending_kernel or "GITHUB").upper()
    pending_root = str(pending_root or "GITHUB").upper()
    try:
        root_state = apply_bios_source_selection(pending_kernel, pending_root)
        state["root_selection"] = copy.deepcopy(root_state)
        status = _source_selection_status_html(
            root_state, pending_kernel, pending_root, "SOURCE SELECTION APPLIED"
        )
    except Exception as exc:
        root_state = state.get("root_selection") or ROOT_INITIAL_STATE
        status = f"""
        <div class="orf-loader-status">
          SOURCE APPLY REJECTED • {type(exc).__name__}: {str(exc)}<br>
          ACTIVE KERNEL • {(root_state.get('kernel_source') or {}).get('provider') or 'UNRESOLVED'}<br>
          ACTIVE ROOT • {(root_state.get('root_source') or {}).get('provider') or 'UNRESOLVED'}
        </div>
        """
    return (
        state,
        render_header(state),
        render_page(state),
        render_rail(state),
        render_bottom(state),
        pending_kernel,
        pending_root,
        _source_button_update(pending_kernel, "DRIVE"),
        _source_button_update(pending_kernel, "GITHUB"),
        _source_button_update(pending_root, "DRIVE"),
        _source_button_update(pending_root, "GITHUB"),
        status,
    )


BOOT_FRONT_TARGET_DESKTOP = "DESKTOP"
BOOT_FRONT_TARGET_BIOS = "BIOS"
BOOT_FRONT_DEFAULT_TARGET = str(
    globals().get("ORF_BIOS_BOOT_DEFAULT_TARGET") or BOOT_FRONT_TARGET_DESKTOP
).upper()
if BOOT_FRONT_DEFAULT_TARGET not in {BOOT_FRONT_TARGET_DESKTOP, BOOT_FRONT_TARGET_BIOS}:
    BOOT_FRONT_DEFAULT_TARGET = BOOT_FRONT_TARGET_DESKTOP
BOOT_FRONT_RUNTIME_CLASS = str(
    globals().get("ORF_BIOS_RUNTIME_BOOT_CLASS") or "WARM"
).upper()


def _boot_front_off_state():
    return {
        "schema": BOOT_STATE_SCHEMA,
        "boot_id": "ORF_BOOT_IDLE",
        "sequence": 0,
        "state": "OFF",
        "phase": "IDLE",
        "progress": 0,
        "message": "Press power to start ORFMOS",
        "node": "COLAB_KERNEL",
        "ready": False,
        "kernel_alive": False,
        "heartbeat_sequence": 0,
        "heartbeat_utc": None,
        "_bios_transport": "POWER_GATE",
        "_bios_power_started": False,
        "_bios_boot_target": BOOT_FRONT_DEFAULT_TARGET,
        "_bios_boot_default_target": BOOT_FRONT_DEFAULT_TARGET,
        "_bios_runtime_boot_class": BOOT_FRONT_RUNTIME_CLASS,
        "_bios_home_handoff_ready": False,
    }


def _orf_boot_power_start(current_boot_state):
    """Power edge: start/restart Kernel and arm the runtime-class default target."""
    request = globals().get("request_dev_kernel_power_start")
    if not callable(request):
        raise RuntimeError("Kernel power-start contract is unavailable")
    request("BOOT_POWER_BUTTON")
    baseline = current_boot_state or safe_read_boot_state()
    return (
        True,
        BOOT_FRONT_DEFAULT_TARGET,
        time.monotonic(),
        False,
        new_boot_freshness_state(baseline),
        {"manual_hold": False, "baseline": []},
        "AUTO",
    )


def _orf_boot_request_bios(power_started):
    """One-shot pre-READY override. POWER must have been accepted first."""
    return BOOT_FRONT_TARGET_BIOS if bool(power_started) else BOOT_FRONT_DEFAULT_TARGET


def _orf_bios_continue_to_home():
    """Resolve the separately loaded ORFMOS Home module and return its launch record."""
    launch = globals().get("orfmos_home_launch")
    if not callable(launch):
        return {
            "schema": "ORFMOS_HOME_HANDOFF_V0_1",
            "status": "UNAVAILABLE",
            "reason": "HOME_MODULE_NOT_LOADED",
            "url": "",
        }
    try:
        result = launch() or {}
        if not isinstance(result, dict):
            result = {"status": "FAILED", "reason": "INVALID_HOME_LAUNCH_RESULT"}
        result = dict(result)
        result.setdefault("schema", "ORFMOS_HOME_HANDOFF_V0_1")
        result.setdefault("url", result.get("share_url") or result.get("local_url") or "")
        return result
    except Exception as exc:
        return {
            "schema": "ORFMOS_HOME_HANDOFF_V0_1",
            "status": "FAILED",
            "reason": f"{type(exc).__name__}: {exc}",
            "url": "",
        }


def build_bios_demo(presentation_generation_id=None):
    presentation_generation_id = (
        str(presentation_generation_id or "").strip()
        or _new_presentation_generation_id()
    )
    initial_state = merge_live_boot_state(
        copy.deepcopy(ORF_BIOS_STATE_V0_1),
        BOOT_INITIAL_STATE,
    )
    initial_state["identity"]["firmware_version"] = BIOS_VERSION
    initial_state = _sync_maintenance_state(initial_state)
    initial_boot_presentation = _boot_front_off_state()

    with gr.Blocks(
        css=CSS,
        title="ORFMOS BIOS Development v0.1.61",
    ) as demo:

        state_store = gr.State(initial_state)
        boot_power_started_state = gr.State(False)
        boot_target_state = gr.State(BOOT_FRONT_DEFAULT_TARGET)
        boot_front_started_at = gr.State(time.monotonic())
        boot_transition_complete = gr.State(False)
        boot_freshness_state = gr.State(
            new_boot_freshness_state(BOOT_INITIAL_STATE)
        )
        boot_manual_view_state = gr.State(
            {"manual_hold": False, "baseline": []}
        )
        # Primary navigation owner.  AUTO delegates BOOT/BIOS ownership to the
        # Kernel heartbeat; ROOT_SELECTION temporarily owns the whole surface.
        primary_surface_owner_state = gr.State("AUTO")
        # Transient menus are not primary surfaces. The component visibility
        # itself is the local latch between RESET KERNEL and CANCEL/CONTINUE.
        # Heartbeat never reads or writes this state.
        reset_kernel_modal_open_state = gr.State(False)
        # This value is immutable for the lifetime of this browser/server
        # generation.  Rerunning the notebook creates a new value, allowing an
        # old Gradio surface to prove that it has been superseded.
        presentation_generation_state = gr.State(
            {"generation_id": presentation_generation_id}
        )
        # Per-browser session identity. A page/reconnect gets a new session ID;
        # the browser-persisted client_instance_id remains stable.
        device_client_session_id = gr.State(None)
        home_handoff_state = gr.JSON(
            value={
                "schema": "ORFMOS_HOME_HANDOFF_V0_1",
                "status": "IDLE",
                "url": "",
            },
            visible=False,
        )

        # Durable Kernel -> BIOS boot presentation telemetry.
        boot_state_store = gr.JSON(
            value=initial_boot_presentation,
            visible=False,
        )
        bios_heartbeat_timer = gr.Timer(
            value=BOOT_POLL_SECONDS,
            active=True,
        )
        # Backend-driven display owner.  The component itself has no visible
        # content; its <style> payload owns BOOT/BIOS display atomically.
        surface_owner_style = gr.HTML(
            render_surface_owner_style(show_boot=True, show_bios=False),
            show_label=False,
        )

        # ------------------------------------------------------------------
        # FRONT DOOR — exact pinned boot page from GitHub.
        # ------------------------------------------------------------------
        with gr.Group(visible=True, elem_id="orfBootFront") as boot_front:
            boot_html = gr.HTML(
                boot_iframe_markup(),
                show_label=False,
            )
            with gr.Row(elem_classes="orf-enter-row"):
                source_note = gr.HTML(
                    render_boot_gate_status(
                        initial_boot_presentation,
                        new_boot_freshness_state(initial_boot_presentation),
                        False,
                    )
                )

        # ------------------------------------------------------------------
        # BIOS SURFACE
        # Both primary surfaces stay mounted. Browser-side presentation ownership
        # switches display atomically; Gradio visibility is not part of the handoff.
        # ------------------------------------------------------------------
        with gr.Group(visible=True, elem_id="orfBiosSurface") as bios_surface:
            header = gr.HTML(render_header(initial_state))

            with gr.Row(equal_height=True):
                with gr.Column(
                    scale=15,
                    min_width=135,
                    elem_classes="orf-nav-wrap",
                ):
                    nav_system = gr.Button(
                        "SYSTEM",
                        elem_classes="orf-nav-btn",
                    )
                    nav_boot = gr.Button(
                        "BOOT",
                        elem_classes="orf-nav-btn",
                    )
                    nav_runtime = gr.Button(
                        "RUNTIME",
                        elem_classes="orf-nav-btn",
                    )
                    nav_recovery = gr.Button(
                        "RECOVERY",
                        elem_classes="orf-nav-btn",
                    )
                    nav_maintenance = gr.Button(
                        "MAINTENANCE",
                        elem_classes="orf-nav-btn",
                    )
                    open_file_loader = gr.Button(
                        "SOURCE SELECTION",
                        elem_id="orfSourceSelectionOpen",
                        elem_classes="orf-nav-btn",
                    )
                    continue_home = gr.Button(
                        "CONTINUE",
                        variant="primary",
                        elem_id="orfContinueHome",
                        elem_classes="orf-nav-btn",
                    )
                    reset_kernel = gr.Button(
                        "RESET KERNEL",
                        variant="stop",
                        elem_classes=["orf-nav-btn", "orf-reset-kernel"],
                    )

                with gr.Column(
                    scale=62,
                    min_width=360,
                    elem_classes="orf-workspace-wrap",
                ):
                    workspace = gr.HTML(render_page(initial_state))

                    with gr.Group(visible=False) as boot_controls:
                        target_dropdown = gr.Dropdown(
                            choices=[
                                (BOOT_TARGET_LABELS[k], k)
                                for k in initial_state["boot"]["available_targets"]
                            ],
                            value=initial_state["boot"]["selected_target"],
                            label="STAGE BOOT TARGET",
                            elem_classes="orf-boot-control",
                        )
                        with gr.Row():
                            discard_button = gr.Button(
                                "DISCARD",
                                elem_classes=["orf-action", "orf-discard"],
                            )
                            apply_button = gr.Button(
                                "APPLY SYNTHETIC",
                                elem_classes=["orf-action", "orf-apply"],
                            )

                    with gr.Group(
                        visible=False,
                        elem_id="orfMaintenanceControls",
                        elem_classes="orf-device-export-wrap",
                    ) as maintenance_controls:
                        maintenance_status = gr.HTML(_maintenance_status_html())
                        gr.HTML(
                            """
                            <div class="orf-loader-note">
                              Issue a one-time challenge, sign the exact challenge text on the trusted maintainer side
                              with the KORF Grandpa Boot signing key, then paste only the Base64 signature here.
                              The private keystore never enters ORFMOS BIOS.
                            </div>
                            """
                        )
                        issue_maintenance_challenge_button = gr.Button(
                            "ISSUE MAINTENANCE CHALLENGE",
                            elem_classes=["orf-action", "orf-apply"],
                        )
                        maintenance_challenge = gr.Textbox(
                            label="CHALLENGE — SIGN EXACT TEXT",
                            lines=7,
                            interactive=False,
                        )
                        maintenance_signature = gr.Textbox(
                            label="BASE64 SIGNATURE",
                            lines=3,
                            type="text",
                        )
                        with gr.Row():
                            verify_maintenance_signature_button = gr.Button(
                                "VERIFY + ARM",
                                elem_classes=["orf-action", "orf-apply"],
                            )
                            revoke_maintenance_button = gr.Button(
                                "REVOKE",
                                elem_classes=["orf-action", "orf-discard"],
                            )

                        gr.HTML("<div class='orf-loader-sub'>KERNEL MANIFEST UPDATE</div>")
                        maintenance_kernel_ref = gr.Textbox(
                            label="IMMUTABLE GITHUB COMMIT SHA",
                            value=str(globals().get("KERNEL_GITHUB_REF") or ""),
                        )
                        maintenance_kernel_prefix = gr.Textbox(
                            label="KERNEL PATH",
                            value=str(globals().get("KERNEL_GITHUB_PREFIX") or "kernel/v0.2.1"),
                        )
                        maintenance_kernel_manifest_sha = gr.Textbox(
                            label="EXPECTED ORF_KERNEL_BOOT_MANIFEST.json SHA256",
                            value=str(globals().get("KERNEL_GITHUB_MANIFEST_SHA256") or ""),
                        )
                        maintenance_kernel_status = gr.HTML(
                            '<div class="orf-loader-status">NO KERNEL CANDIDATE STAGED</div>'
                        )
                        with gr.Row():
                            maintenance_stage_kernel_button = gr.Button(
                                "STAGE + VERIFY MANIFEST",
                                elem_classes=["orf-action", "orf-apply"],
                            )
                            maintenance_apply_kernel_button = gr.Button(
                                "APPLY STAGED KERNEL",
                                elem_classes=["orf-action", "orf-apply"],
                            )
                            maintenance_rollback_kernel_button = gr.Button(
                                "ROLLBACK KERNEL",
                                elem_classes=["orf-action", "orf-discard"],
                            )

                        gr.HTML("<div class='orf-loader-sub'>TERMINAL RUNTIME CONTROL</div>")
                        maintenance_shutdown_status = gr.HTML(
                            '<div class="orf-loader-status">RUNTIME SHUTDOWN NOT ARMED</div>'
                        )
                        maintenance_arm_shutdown_button = gr.Button(
                            "ARM RUNTIME SHUTDOWN",
                            variant="stop",
                            elem_classes=["orf-action", "orf-reset-kernel"],
                        )
                        maintenance_confirm_shutdown_button = gr.Button(
                            "DISCONNECT + DELETE COLAB RUNTIME",
                            variant="stop",
                            visible=False,
                            elem_classes=["orf-action", "orf-reset-kernel"],
                        )

                    with gr.Group(
                        visible=True,
                        elem_id="orfDeviceExportGroup",
                        elem_classes="orf-device-export-wrap",
                    ) as device_export_group:
                        device_export_button = gr.Button(
                            "EXPORT DEVICE OBSERVATION",
                            elem_id="orfDeviceExportButton",
                        )
                        device_export_status = gr.HTML(
                            '<div class="orf-export-status">SESSION EXPORT READY</div>'
                        )

                    with gr.Accordion(
                        "BIOS COMMAND / RECEIPT",
                        open=False,
                    ):
                        command_json = gr.JSON(
                            value=render_command(initial_state),
                            label=None,
                        )

                with gr.Column(
                    scale=23,
                    min_width=170,
                    elem_classes="orf-rail-wrap",
                ):
                    rail = gr.HTML(render_rail(initial_state))

            bottom = gr.HTML(render_bottom(initial_state))

        # ------------------------------------------------------------------
        # BIOS SOURCE SELECTION — Kernel and ORFMOS root are independent axes.
        # ------------------------------------------------------------------
        kernel_source_pending = gr.State(
            str((ROOT_INITIAL_STATE.get("kernel_source") or {}).get("provider") or "GITHUB")
        )
        root_source_pending = gr.State(
            str((ROOT_INITIAL_STATE.get("root_source") or {}).get("provider") or "GITHUB")
        )

        with gr.Group(visible=True, elem_id="orfRootSelection", elem_classes="orf-loader-surface") as root_selector_surface:
            with gr.Group(elem_classes="orf-loader-shell"):
                gr.HTML(
                    """
                    <div class="orf-loader-head">
                      <div class="orf-loader-title">ORFMOS SOURCE SELECTION</div>
                      <div class="orf-loader-sub">INDEPENDENT KERNEL SOURCE • INDEPENDENT ORFMOS ROOT SOURCE • APPLY AS ONE BIOS CONFIGURATION</div>
                    </div>
                    """
                )
                with gr.Column(elem_classes="orf-loader-body"):
                    gr.HTML(
                        """
                        <div class="orf-loader-note">
                          Stage Kernel and ORFMOS root providers independently. Selecting a button does not alter
                          active boot authority; APPLY SELECTIONS verifies and commits both choices together.
                          RESET KERNEL then consumes the applied Kernel provider through the normal monitor path.
                        </div>
                        """
                    )
                    gr.HTML("<div class='orf-loader-sub'>KERNEL SOURCE</div>")
                    with gr.Row():
                        kernel_drive = gr.Button(
                            "✓ GOOGLE DRIVE" if str((ROOT_INITIAL_STATE.get("kernel_source") or {}).get("provider") or "GITHUB") == "DRIVE" else "GOOGLE DRIVE",
                            elem_id="orfKernelSourceDrive",
                            elem_classes=["orf-action", "orf-apply"],
                        )
                        kernel_github = gr.Button(
                            "✓ GITHUB" if str((ROOT_INITIAL_STATE.get("kernel_source") or {}).get("provider") or "GITHUB") == "GITHUB" else "GITHUB",
                            elem_id="orfKernelSourceGithub",
                            elem_classes=["orf-action", "orf-apply"],
                        )
                    gr.HTML("<div class='orf-loader-sub'>ORFMOS ROOT SOURCE</div>")
                    with gr.Row():
                        root_drive = gr.Button(
                            "✓ GOOGLE DRIVE" if str((ROOT_INITIAL_STATE.get("root_source") or {}).get("provider") or "GITHUB") == "DRIVE" else "GOOGLE DRIVE",
                            elem_id="orfRootSourceDrive",
                            elem_classes=["orf-action", "orf-apply"],
                        )
                        root_github = gr.Button(
                            "✓ GITHUB" if str((ROOT_INITIAL_STATE.get("root_source") or {}).get("provider") or "GITHUB") == "GITHUB" else "GITHUB",
                            elem_id="orfRootSourceGithub",
                            elem_classes=["orf-action", "orf-apply"],
                        )
                    with gr.Row():
                        apply_sources = gr.Button(
                            "APPLY SELECTIONS",
                            elem_id="orfApplySourceSelections",
                            elem_classes=["orf-action", "orf-apply"],
                        )
                        root_back = gr.Button(
                            "◀ BIOS",
                            elem_id="orfSourceSelectionBack",
                            elem_classes=["orf-action", "orf-discard"],
                        )
                    root_status = gr.HTML(
                        _source_selection_status_html(ROOT_INITIAL_STATE)
                    )

        # ------------------------------------------------------------------
        # BOOT FRONT-DOOR EVENT BRIDGES
        # Visual controls live inside the pinned boot iframe. These hidden
        # Gradio buttons transfer POWER / BIOS-request authority to Python.
        # ------------------------------------------------------------------
        boot_power_bridge = gr.Button(
            "BOOT POWER BRIDGE",
            elem_id="orfBootPowerBridge",
        )
        boot_bios_request_bridge = gr.Button(
            "BOOT BIOS REQUEST BRIDGE",
            elem_id="orfBootBiosRequestBridge",
        )
        boot_home_ready_bridge = gr.Button(
            "BOOT HOME READY BRIDGE",
            elem_id="orfBootHomeReadyBridge",
        )

        # ------------------------------------------------------------------
        # DEVICE SESSION CLIENT BRIDGES
        # Browser profile/telemetry stays browser-originated; Python receives
        # only the serialized observation payload through normal Gradio events.
        # ------------------------------------------------------------------
        device_client_payload = gr.Textbox(
            value="",
            elem_id="orfDeviceClientPayloadBridge",
            show_label=False,
        )
        device_client_probe_bridge = gr.Button(
            "DEVICE CLIENT PROBE BRIDGE",
            elem_id="orfDeviceClientProbeBridge",
        )

        # ------------------------------------------------------------------
        # TRANSIENT KERNEL RESTART BRIDGES
        # The visual popup is browser-native so Gradio layout wrappers cannot
        # distort its viewport position or separate its text/buttons. These two
        # off-screen Gradio buttons retain backend event authority and runtime
        # interaction accounting for CANCEL / CONTINUE.
        # ------------------------------------------------------------------
        reset_kernel_cancel = gr.Button(
            "RESET CANCEL BRIDGE",
            elem_id="orfResetKernelCancelBridge",
        )
        reset_kernel_confirm_button = gr.Button(
            "RESET CONTINUE BRIDGE",
            elem_id="orfResetKernelContinueBridge",
        )

        boot_power_event = boot_power_bridge.click(
            fn=_with_user_activity("BOOT_POWER", _orf_boot_power_start),
            inputs=boot_state_store,
            outputs=[
                boot_power_started_state,
                boot_target_state,
                boot_front_started_at,
                boot_transition_complete,
                boot_freshness_state,
                boot_manual_view_state,
                primary_surface_owner_state,
            ],
            show_progress="hidden",
            queue=False,
        )

        boot_bios_request_bridge.click(
            fn=_with_user_activity("BOOT_REQUEST_BIOS", _orf_boot_request_bios),
            inputs=boot_power_started_state,
            outputs=boot_target_state,
            show_progress="hidden",
            queue=False,
        )

        boot_home_ready_event = boot_home_ready_bridge.click(
            fn=_with_user_activity("BOOT_READY_HOME", _orf_bios_continue_to_home),
            inputs=None,
            outputs=home_handoff_state,
            show_progress="hidden",
            queue=False,
        )
        boot_home_ready_event.then(
            fn=None,
            inputs=home_handoff_state,
            outputs=None,
            js=r"""
            (handoff) => {
              try {
                const status = String((handoff && handoff.status) || "").toUpperCase();
                const url = String((handoff && handoff.url) || "").trim();
                if (status === "READY" && url) {
                  window.location.replace(url);
                  return [];
                }
                const reason = String((handoff && handoff.reason) || "HOME_NOT_READY");
                window.__orfBootHomeHandoffRequested = false;
                console.error("ORFMOS automatic Home handoff failed", handoff);
                window.alert(`ORFMOS Home handoff failed: ${reason}`);
              } catch (error) {
                window.__orfBootHomeHandoffRequested = false;
                console.error("ORFMOS automatic Home handoff exception", error);
              }
              return [];
            }
            """,
        )

        device_client_probe_bridge.click(
            fn=ingest_device_client_probe,
            inputs=[device_client_payload, device_client_session_id, state_store],
            outputs=[
                device_client_session_id,
                state_store,
                header,
                workspace,
                rail,
                bottom,
            ],
            show_progress="hidden",
            queue=False,
        )

        device_export_button.click(
            fn=_with_user_activity("EXPORT_DEVICE_OBSERVATION", export_current_device_observation),
            inputs=device_client_session_id,
            outputs=device_export_status,
            show_progress="hidden",
        )

        # ------------------------------------------------------------------
        # SINGLE LIVE HEARTBEAT
        # ------------------------------------------------------------------
        heartbeat = bios_heartbeat_timer.tick(
            fn=bios_heartbeat,
            inputs=[
                state_store,
                boot_front_started_at,
                boot_transition_complete,
                boot_freshness_state,
                boot_manual_view_state,
                presentation_generation_state,
                primary_surface_owner_state,
                boot_power_started_state,
                boot_target_state,
            ],
            outputs=[
                state_store,
                boot_state_store,
                header,
                workspace,
                rail,
                bottom,
                boot_transition_complete,
                boot_freshness_state,
                boot_manual_view_state,
                source_note,
                surface_owner_style,
                bios_heartbeat_timer,
            ],
            show_progress="hidden",
        )

        # Browser-side boot front-door wiring.  The pinned GitHub asset remains
        # presentation-only; this host supplies POWER, BIOS-request and READY->HOME
        # event bridges without granting the iframe backend authority directly.
        heartbeat.then(
            fn=None,
            inputs=[boot_state_store, boot_manual_view_state, boot_transition_complete],
            outputs=None,
            js=r"""
            (state, manualView, transitionComplete) => {
              try {
                const shutdownState = String((state && state._bios_shutdown_state) || "RUNNING").toUpperCase();
                const shutdownPending = Boolean(state && state._bios_shutdown_pending);
                const shutdownRemaining = Number((state && state._bios_shutdown_remaining_seconds) || 0);
                const shutdownActiveWrites = Number((state && state._bios_shutdown_active_writes) || 0);
                const shutdownDrainState = String((state && state._bios_shutdown_drain_state) || "IDLE").toUpperCase();
                const shutdownReturnBoot = Boolean(state && state._bios_shutdown_clients_return_to_boot);
                window.__ORF_EXPECTED_SERVER_DISCONNECT__ = shutdownPending;

                const ensureShutdownOverlay = () => {
                  let overlay = document.getElementById("orfShutdownOverlay");
                  if (!overlay) {
                    overlay = document.createElement("div");
                    overlay.id = "orfShutdownOverlay";
                    overlay.style.cssText = [
                      "position:fixed", "inset:0", "z-index:2147483000",
                      "display:grid", "place-items:center", "padding:24px",
                      "background:rgba(2,4,5,.94)", "color:#dcecff",
                      "font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace",
                      "text-align:center", "pointer-events:auto"
                    ].join(";");
                    document.body.appendChild(overlay);
                  }
                  return overlay;
                };

                if (shutdownPending && !shutdownReturnBoot) {
                  if (window.__ORF_DEVICE_SESSION_PROBE_TIMER_V0_1__) {
                    clearInterval(window.__ORF_DEVICE_SESSION_PROBE_TIMER_V0_1__);
                    window.__ORF_DEVICE_SESSION_PROBE_TIMER_V0_1__ = null;
                  }
                  const overlay = ensureShutdownOverlay();
                  const writeLine = shutdownActiveWrites > 0
                    ? `Finishing ${shutdownActiveWrites} pending write${shutdownActiveWrites === 1 ? "" : "s"}…`
                    : "Pending writes complete ✓";
                  overlay.innerHTML = `
                    <div style="max-width:720px;width:min(92vw,720px)">
                      <div style="font-size:clamp(18px,4vw,34px);font-weight:900;letter-spacing:.08em">SYSTEM SHUTDOWN</div>
                      <div style="margin-top:18px;color:#76ffae">New changes are locked ✓</div>
                      <div style="margin-top:8px;color:#a9c4d8">${writeLine}</div>
                      <div style="margin-top:26px;font-size:clamp(34px,10vw,78px);font-weight:900;color:#ffcc67">${shutdownRemaining}</div>
                      <div style="margin-top:4px;color:#a9c4d8">Runtime disconnect in ${shutdownRemaining} second${shutdownRemaining === 1 ? "" : "s"}</div>
                    </div>`;
                } else {
                  const overlay = document.getElementById("orfShutdownOverlay");
                  if (overlay) overlay.remove();
                }

                if (shutdownReturnBoot) {
                  // Latch terminal boot ownership before the backend disappears.
                  // In particular, prevent a READY warm-runtime state from immediately
                  // requesting Home again after BIOS has forced the client to BOOT.
                  window.__orfBootHomeHandoffRequested = true;
                  if (window.__ORF_DEVICE_SESSION_PROBE_TIMER_V0_1__) {
                    clearInterval(window.__ORF_DEVICE_SESSION_PROBE_TIMER_V0_1__);
                    window.__ORF_DEVICE_SESSION_PROBE_TIMER_V0_1__ = null;
                  }
                }

                const ready = String((state && state.state) || "").toUpperCase() === "READY";
                const kernelLive = Boolean(state && state._bios_kernel_live);
                const liveReady = ready && kernelLive;
                const powerStarted = Boolean(state && state._bios_power_started);
                const bootTarget = String((state && state._bios_boot_target) || "DESKTOP").toUpperCase();

                const ownGeneration = String((state && state._bios_presentation_generation) || "");
                const activeGeneration = String((state && state._bios_active_presentation_generation) || "");
                const activeUrl = String((state && state._bios_active_presentation_url) || "");
                const generationMatch = Boolean(
                  ownGeneration && activeGeneration && ownGeneration === activeGeneration
                );

                if (!generationMatch && activeUrl) {
                  try {
                    const target = new URL(activeUrl, window.location.href);
                    if (window.location.origin !== target.origin) {
                      window.location.replace(activeUrl);
                      return [];
                    }
                  } catch (redirectError) {
                    console.error("ORF BIOS presentation redirect failed", redirectError);
                  }
                }

                const findByIdDeep = (id, root = document) => {
                  try {
                    const direct = root.getElementById ? root.getElementById(id) : null;
                    if (direct) return direct;
                    const selected = root.querySelector ? root.querySelector(`#${id}`) : null;
                    if (selected) return selected;
                    const nodes = root.querySelectorAll ? root.querySelectorAll("*") : [];
                    for (const node of nodes) {
                      if (node && node.shadowRoot) {
                        const found = findByIdDeep(id, node.shadowRoot);
                        if (found) return found;
                      }
                    }
                  } catch (_) {}
                  return null;
                };
                const triggerBridge = (id) => {
                  const root = findByIdDeep(id);
                  const bridge = root && String(root.tagName || "").toUpperCase() === "BUTTON"
                    ? root
                    : (root && root.querySelector ? root.querySelector("button") : null);
                  if (!bridge) {
                    console.error("ORF boot bridge unavailable", id);
                    return false;
                  }
                  bridge.click();
                  return true;
                };

                const boot = document.getElementById("orfBootFront");
                const bios = document.getElementById("orfBiosSurface");
                const root = document.getElementById("orfRootSelection");
                const backendOwner = String((state && state._bios_surface_owner) || "BOOT");

                if (backendOwner === "ROOT_SELECTION") {
                  if (root) root.style.setProperty("display", "block", "important");
                  if (boot) boot.style.setProperty("display", "none", "important");
                  if (bios) bios.style.setProperty("display", "none", "important");
                } else if (backendOwner === "BIOS") {
                  if (root) root.style.setProperty("display", "none", "important");
                  if (bios) bios.style.setProperty("display", "block", "important");
                  if (boot) boot.style.setProperty("display", "none", "important");
                } else {
                  if (root) root.style.setProperty("display", "none", "important");
                  if (boot) boot.style.setProperty("display", "block", "important");
                  if (bios) bios.style.setProperty("display", "none", "important");
                }

                const frame = document.getElementById("orfBootFrame");
                if (frame && frame.contentWindow) {
                  if (
                    frame.contentWindow.ORF_BOOT &&
                    typeof frame.contentWindow.ORF_BOOT.update === "function"
                  ) {
                    frame.contentWindow.ORF_BOOT.update(state);
                  }

                  // Recovery failures may occur in the resident VM after the
                  // notebook cell has returned. On FAILED boot states the front door is
                  // intentionally verbose: keep the normal headline concise and expose
                  // the remaining bounded failure evidence in a selectable text block.
                  try {
                    const doc = frame.contentDocument || frame.contentWindow.document;
                    const messageText = doc && doc.getElementById("messageText");
                    const fullMessage = String((state && state.message) || "");
                    const failedState = String((state && state.state) || "").toUpperCase() === "FAILED";
                    const richFailure = failedState && fullMessage.includes("\n");
                    if (messageText) {
                      messageText.style.userSelect = "text";
                      messageText.style.webkitUserSelect = "text";
                      messageText.style.wordBreak = "break-word";
                      if (richFailure) {
                        messageText.textContent = fullMessage.split("\n")[0];
                      }
                    }
                    let detail = doc && doc.getElementById("orfBootFailureDetail");
                    if (doc) {
                      const shell = doc.getElementById("orfBootShell");
                      const decorativeSelectors = [
                        ".orf-logo",
                        ".orfmos-logo",
                        ".orf-subtitle",
                        ".orf-power-stage",
                        ".orf-progress-track",
                        ".orf-progress-text",
                        ".orf-telemetry",
                        ".orf-boot-id",
                      ];
                      if (richFailure) {
                        // Failure-console mode does not depend on document or iframe
                        // scrolling.  Collapse the decorative boot surface and use the
                        // existing viewport for selectable diagnostic evidence.
                        if (doc.documentElement) {
                          doc.documentElement.style.overflow = "hidden";
                          doc.documentElement.style.height = "100%";
                        }
                        if (doc.body) {
                          doc.body.style.overflow = "hidden";
                          doc.body.style.height = "100vh";
                          doc.body.style.touchAction = "manipulation";
                        }
                        if (shell) {
                          shell.style.overflow = "hidden";
                          shell.style.height = "100vh";
                          shell.style.minHeight = "100vh";
                          shell.style.justifyContent = "flex-start";
                          shell.style.paddingTop = "24px";
                          shell.style.paddingBottom = "18px";
                        }
                        decorativeSelectors.forEach((selector) => {
                          const el = doc.querySelector(selector);
                          if (el) {
                            if (!el.dataset.orfRichFailurePriorDisplay) {
                              el.dataset.orfRichFailurePriorDisplay = el.style.display || "__EMPTY__";
                            }
                            el.style.display = "none";
                          }
                        });
                        if (messageText) {
                          messageText.style.marginTop = "8px";
                          messageText.style.maxWidth = "92vw";
                        }
                      } else {
                        if (doc.documentElement) {
                          doc.documentElement.style.overflow = "";
                          doc.documentElement.style.height = "";
                        }
                        if (doc.body) {
                          doc.body.style.overflow = "hidden";
                          doc.body.style.height = "";
                          doc.body.style.touchAction = "";
                        }
                        if (shell) {
                          shell.style.overflow = "hidden";
                          shell.style.height = "";
                          shell.style.minHeight = "100vh";
                          shell.style.justifyContent = "center";
                          shell.style.paddingTop = "";
                          shell.style.paddingBottom = "";
                        }
                        decorativeSelectors.forEach((selector) => {
                          const el = doc.querySelector(selector);
                          if (el && el.dataset.orfRichFailurePriorDisplay) {
                            const prior = el.dataset.orfRichFailurePriorDisplay;
                            el.style.display = prior === "__EMPTY__" ? "" : prior;
                            delete el.dataset.orfRichFailurePriorDisplay;
                          }
                        });
                        if (messageText) {
                          messageText.style.marginTop = "";
                          messageText.style.maxWidth = "";
                        }
                      }
                    }
                    if (richFailure && doc) {
                      if (!detail) {
                        detail = doc.createElement("pre");
                        detail.id = "orfBootFailureDetail";
                        detail.setAttribute("aria-label", "Boot failure diagnostic details");
                        Object.assign(detail.style, {
                          display: "block",
                          width: "min(94%, 720px)",
                          maxHeight: "56vh",
                          overflow: "auto",
                          margin: "10px auto 0",
                          padding: "12px 13px",
                          boxSizing: "border-box",
                          border: "1px solid rgba(255,123,123,.34)",
                          borderRadius: "10px",
                          background: "rgba(12,5,7,.76)",
                          color: "#d8b4b7",
                          whiteSpace: "pre-wrap",
                          overflowWrap: "anywhere",
                          wordBreak: "break-word",
                          textAlign: "left",
                          font: "600 10px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace",
                          letterSpacing: ".025em",
                          userSelect: "text",
                          webkitUserSelect: "text",
                          cursor: "text",
                          touchAction: "pan-y",
                          webkitOverflowScrolling: "touch",
                        });
                        // Mount relative to the message itself.  The BIOS-request
                        // control may live under a different parent in the pinned boot
                        // artifact, so using it as insertBefore()'s reference node can
                        // raise NotFoundError and leave only the first-line headline.
                        if (messageText && messageText.parentNode) {
                          if (messageText.nextSibling) {
                            messageText.parentNode.insertBefore(detail, messageText.nextSibling);
                          } else {
                            messageText.parentNode.appendChild(detail);
                          }
                        } else if (doc.body) {
                          doc.body.appendChild(detail);
                        }
                      }
                      detail.textContent = "BOOT FAILURE DIAGNOSTICS\n\n" + fullMessage.split("\n").slice(1).join("\n");
                      detail.style.display = "block";
                    } else if (detail) {
                      detail.textContent = "";
                      detail.style.display = "none";
                    }
                  } catch (diagnosticRenderError) {
                    console.error("ORF boot failure diagnostic render failed", diagnosticRenderError);
                  }

                  if (shutdownReturnBoot) {
                    try {
                      const doc = frame.contentDocument || frame.contentWindow.document;
                      const stateText = doc && doc.getElementById("stateText");
                      const messageText = doc && doc.getElementById("messageText");
                      if (stateText) {
                        stateText.className = "orf-state";
                        stateText.textContent = shutdownState === "FAILED" ? "OFFLINE" : "SHUTDOWN";
                      }
                      if (messageText) {
                        messageText.textContent = shutdownDrainState === "TIMEOUT"
                          ? "Runtime disconnecting — write drain grace expired"
                          : "Final writes complete — runtime disconnecting";
                      }
                    } catch (_) {}
                  }

                  try {
                    const doc = frame.contentDocument || frame.contentWindow.document;
                    const ring = doc && doc.getElementById("powerRing");
                    const stage = doc && doc.getElementById("powerStage");
                    if (ring && !ring.dataset.orfPowerBound) {
                      ring.dataset.orfPowerBound = "1";
                      ring.setAttribute("role", "button");
                      ring.setAttribute("tabindex", "0");
                      ring.setAttribute("aria-label", "Start ORFMOS");
                      ring.style.cursor = "pointer";
                      const activatePower = () => {
                        if (frame.contentWindow.__orfPowerPressed) return;
                        frame.contentWindow.__orfPowerPressed = true;
                        if (stage) stage.className = "orf-power-stage active";
                        ring.className = "orf-power-ring active";
                        const stateText = doc.getElementById("stateText");
                        const messageText = doc.getElementById("messageText");
                        if (stateText) {
                          stateText.className = "orf-state active";
                          stateText.textContent = "STARTING";
                        }
                        if (messageText) messageText.textContent = "Power accepted — restarting ORFMOS Kernel";
                        const biosRequest = doc.getElementById("orfBootBiosRequest");
                        if (biosRequest) biosRequest.style.display = "block";
                        triggerBridge("orfBootPowerBridge");
                      };
                      ring.addEventListener("click", activatePower);
                      ring.addEventListener("keydown", (event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          activatePower();
                        }
                      });
                    }

                    if (doc && !doc.getElementById("orfBootBiosRequest")) {
                      const button = doc.createElement("button");
                      button.id = "orfBootBiosRequest";
                      button.type = "button";
                      button.textContent = "ENTER BIOS";
                      button.setAttribute("aria-label", "Enter BIOS when boot is ready");
                      Object.assign(button.style, {
                        display: powerStarted ? "block" : "none",
                        margin: "16px auto 0",
                        padding: "10px 18px",
                        borderRadius: "10px",
                        border: "1px solid rgba(77,163,255,.42)",
                        background: "rgba(4,12,18,.88)",
                        color: "#8fc7ff",
                        font: "700 10px ui-monospace,SFMono-Regular,Menlo,monospace",
                        letterSpacing: ".16em",
                        cursor: "pointer",
                        boxShadow: "0 0 18px rgba(77,163,255,.08)",
                      });
                      button.addEventListener("click", () => {
                        if (!frame.contentWindow.__orfPowerPressed && !powerStarted) return;
                        if (frame.contentWindow.__orfBiosRequested) return;
                        frame.contentWindow.__orfBiosRequested = true;
                        button.textContent = "BIOS REQUESTED ✓";
                        button.style.borderColor = "rgba(103,252,160,.48)";
                        button.style.color = "#67fca0";
                        triggerBridge("orfBootBiosRequestBridge");
                      });
                      const message = doc.getElementById("messageText");
                      if (message && message.parentNode) {
                        message.parentNode.insertBefore(button, message.nextSibling);
                      } else if (doc.body) {
                        doc.body.appendChild(button);
                      }
                    }

                    const biosRequest = doc && doc.getElementById("orfBootBiosRequest");
                    if (biosRequest) {
                      biosRequest.style.display = powerStarted ? "block" : "none";
                      if (bootTarget === "BIOS") {
                        frame.contentWindow.__orfBiosRequested = true;
                        biosRequest.textContent = "BIOS REQUESTED ✓";
                        biosRequest.style.borderColor = "rgba(103,252,160,.48)";
                        biosRequest.style.color = "#67fca0";
                      }
                    }
                    if (powerStarted) frame.contentWindow.__orfPowerPressed = true;
                  } catch (frameError) {
                    console.error("ORF boot control wiring failed", frameError);
                  }
                }

                if (
                  !shutdownPending &&
                  !shutdownReturnBoot &&
                  powerStarted &&
                  liveReady &&
                  bootTarget === "DESKTOP" &&
                  Boolean(state && state._bios_home_handoff_ready) &&
                  !window.__orfBootHomeHandoffRequested
                ) {
                  window.__orfBootHomeHandoffRequested = true;
                  if (!triggerBridge("orfBootHomeReadyBridge")) {
                    window.__orfBootHomeHandoffRequested = false;
                  }
                }
              } catch (error) {
                console.error("ORF BIOS boot-state bridge failed", error);
              }
              return [];
            }
            """,
        )

        # Front door transitions. Manual BOOT return was absorbed by RESET KERNEL.
        # Reset is intentionally two-step: opening/cancel/confirm are all real
        # runtime interactions, while only CONFIRM RESET posts the reboot request.
        reset_kernel_prompt_event = reset_kernel.click(
            fn=_with_user_activity("RESET_KERNEL_PROMPT", _show_reset_confirmation),
            inputs=None,
            outputs=reset_kernel_modal_open_state,
            show_progress="hidden",
        )
        reset_kernel_prompt_event.then(
            fn=None,
            inputs=None,
            outputs=None,
            js=r"""
            () => {
              try {
                const prior = document.getElementById("orfKernelRestartModal");
                if (prior) prior.remove();
                const card = document.createElement("div");
                card.id = "orfKernelRestartModal";
                card.setAttribute("role", "dialog");
                card.setAttribute("aria-modal", "false");
                card.setAttribute("aria-label", "Kernel restart confirmation");
                card.innerHTML = `
                  <div class="orf-reset-confirm-title">KERNEL RESTART STAGED</div>
                  <div class="orf-reset-confirm-copy">
                    Are you ready to restart the currently applied Kernel?
                    ORFMOS will return to the boot surface while the resident BIOS monitor
                    reruns the selected Kernel source. Continue or cancel.
                  </div>
                  <div class="orf-reset-confirm-actions">
                    <button type="button" class="orf-reset-native-button orf-reset-native-cancel" data-orf-reset="cancel">CANCEL</button>
                    <button type="button" class="orf-reset-native-button orf-reset-native-continue" data-orf-reset="continue">CONTINUE</button>
                  </div>`;
                document.body.appendChild(card);
                const findByIdDeep = (id, root = document) => {
                  try {
                    const direct = root.getElementById ? root.getElementById(id) : null;
                    if (direct) return direct;
                    const selected = root.querySelector ? root.querySelector(`#${id}`) : null;
                    if (selected) return selected;
                    const nodes = root.querySelectorAll ? root.querySelectorAll("*") : [];
                    for (const node of nodes) {
                      if (node && node.shadowRoot) {
                        const found = findByIdDeep(id, node.shadowRoot);
                        if (found) return found;
                      }
                    }
                  } catch (error) {
                    console.error("ORF BIOS reset bridge deep search failed", id, error);
                  }
                  return null;
                };
                const triggerBridge = (id) => {
                  const root = findByIdDeep(id);
                  const bridge = root && String(root.tagName || "").toUpperCase() === "BUTTON"
                    ? root
                    : (root && root.querySelector ? root.querySelector("button") : null);
                  if (!bridge) {
                    console.error("ORF BIOS reset bridge unavailable", id);
                    return false;
                  }
                  try {
                    bridge.focus({preventScroll:true});
                  } catch (_) {}
                  try {
                    bridge.click();
                    return true;
                  } catch (clickError) {
                    try {
                      for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]) {
                        bridge.dispatchEvent(new MouseEvent(type, {
                          bubbles: true,
                          cancelable: true,
                          composed: true,
                          view: window,
                        }));
                      }
                      return true;
                    } catch (dispatchError) {
                      console.error("ORF BIOS reset bridge dispatch failed", id, clickError, dispatchError);
                      return false;
                    }
                  }
                };
                card.querySelector('[data-orf-reset="cancel"]').addEventListener("click", () => {
                  triggerBridge("orfResetKernelCancelBridge");
                });
                card.querySelector('[data-orf-reset="continue"]').addEventListener("click", () => {
                  triggerBridge("orfResetKernelContinueBridge");
                });
              } catch (error) {
                console.error("ORF BIOS reset-modal open failed", error);
              }
              return [];
            }
            """,
        )
        reset_kernel_cancel_event = reset_kernel_cancel.click(
            fn=_with_user_activity("RESET_KERNEL_CANCEL", _hide_reset_confirmation),
            inputs=None,
            outputs=reset_kernel_modal_open_state,
            show_progress="hidden",
        )
        reset_kernel_cancel_event.then(
            fn=None,
            inputs=None,
            outputs=None,
            js=r"""
            () => {
              try {
                const modal = document.getElementById("orfKernelRestartModal");
                if (modal) modal.remove();
                const boot = document.getElementById("orfBootFront");
                const bios = document.getElementById("orfBiosSurface");
                const root = document.getElementById("orfRootSelection");
                if (root) root.style.setProperty("display", "none", "important");
                if (boot) boot.style.setProperty("display", "none", "important");
                if (bios) bios.style.setProperty("display", "block", "important");
              } catch (error) {
                console.error("ORF BIOS reset-modal cancel restore failed", error);
              }
              return [];
            }
            """,
        )
        reset_kernel_event = reset_kernel_confirm_button.click(
            fn=_with_user_activity(
                "RESET_KERNEL_CONFIRM",
                confirm_kernel_reboot_and_close_prompt,
            ),
            inputs=boot_state_store,
            outputs=[
                boot_front_started_at,
                boot_transition_complete,
                boot_freshness_state,
                boot_manual_view_state,
                primary_surface_owner_state,
                reset_kernel_modal_open_state,
            ],
            show_progress="hidden",
        )
        reset_kernel_event.then(
            fn=None,
            inputs=None,
            outputs=None,
            js=r"""
            () => {
              try {
                const modal = document.getElementById("orfKernelRestartModal");
                if (modal) modal.remove();
                const boot = document.getElementById("orfBootFront");
                const bios = document.getElementById("orfBiosSurface");
                const root = document.getElementById("orfRootSelection");
                if (root) root.style.setProperty("display", "none", "important");
                if (boot) boot.style.setProperty("display", "block", "important");
                if (bios) bios.style.setProperty("display", "none", "important");
              } catch (error) {
                console.error("ORF BIOS Kernel reset boot-view switch failed", error);
              }
              return [];
            }
            """,
        )

        # BIOS source selector. Kernel and ORFMOS root are staged independently;
        # Apply commits both. It does not replace the currently running Kernel.
        open_root_event = open_file_loader.click(
            fn=_with_user_activity("OPEN_SOURCE_SELECTION", lambda: "ROOT_SELECTION"),
            inputs=None,
            outputs=primary_surface_owner_state,
            show_progress="hidden",
        )
        open_root_event.then(
            fn=None,
            inputs=None,
            outputs=None,
            js=r"""
            () => {
              try {
                const boot = document.getElementById("orfBootFront");
                const bios = document.getElementById("orfBiosSurface");
                const root = document.getElementById("orfRootSelection");
                if (root) {
                  root.style.setProperty("display", "block", "important");
                  if (boot) boot.style.setProperty("display", "none", "important");
                  if (bios) bios.style.setProperty("display", "none", "important");
                } else {
                  if (bios) bios.style.setProperty("display", "block", "important");
                  else if (boot) boot.style.setProperty("display", "block", "important");
                  console.error("ORF BIOS source open blocked: SOURCE SELECTION surface is not mounted");
                }
              } catch (error) {
                console.error("ORF BIOS root-view switch failed", error);
              }
              return [];
            }
            """,
        )

        root_back_event = root_back.click(
            fn=_with_user_activity("RETURN_FROM_SOURCE_SELECTION", lambda: "AUTO"),
            inputs=None,
            outputs=primary_surface_owner_state,
            show_progress="hidden",
        )
        root_back_event.then(
            fn=None,
            inputs=None,
            outputs=None,
            js=r"""
            () => {
              try {
                const boot = document.getElementById("orfBootFront");
                const bios = document.getElementById("orfBiosSurface");
                const root = document.getElementById("orfRootSelection");
                // Explicit SOURCE SELECTION -> BIOS ownership transfer.  BIOS is
                // shown before ROOT is retired so zero visible primary surfaces
                // is impossible even if the DOM is momentarily slow.
                if (bios) {
                  bios.style.setProperty("display", "block", "important");
                  if (root) root.style.setProperty("display", "none", "important");
                  if (boot) boot.style.setProperty("display", "none", "important");
                } else if (root) {
                  root.style.setProperty("display", "block", "important");
                  console.error("ORF BIOS root return blocked: BIOS surface is not mounted");
                } else if (boot) {
                  boot.style.setProperty("display", "block", "important");
                  console.error("ORF BIOS root return fell back to BOOT");
                }
              } catch (error) {
                console.error("ORF BIOS root-to-BIOS switch failed", error);
              }
              return [];
            }
            """,
        )
        source_stage_outputs = [
            kernel_source_pending,
            root_source_pending,
            kernel_drive,
            kernel_github,
            root_drive,
            root_github,
            root_status,
        ]
        kernel_drive.click(
            fn=_with_user_activity(
                "STAGE_KERNEL_SOURCE_DRIVE",
                lambda pending_kernel, pending_root, state: stage_source_selection(
                    "KERNEL", "DRIVE", pending_kernel, pending_root, state
                ),
            ),
            inputs=[kernel_source_pending, root_source_pending, state_store],
            outputs=source_stage_outputs,
            show_progress="hidden",
        )
        kernel_github.click(
            fn=_with_user_activity(
                "STAGE_KERNEL_SOURCE_GITHUB",
                lambda pending_kernel, pending_root, state: stage_source_selection(
                    "KERNEL", "GITHUB", pending_kernel, pending_root, state
                ),
            ),
            inputs=[kernel_source_pending, root_source_pending, state_store],
            outputs=source_stage_outputs,
            show_progress="hidden",
        )
        root_drive.click(
            fn=_with_user_activity(
                "STAGE_ROOT_SOURCE_DRIVE",
                lambda pending_kernel, pending_root, state: stage_source_selection(
                    "ROOT", "DRIVE", pending_kernel, pending_root, state
                ),
            ),
            inputs=[kernel_source_pending, root_source_pending, state_store],
            outputs=source_stage_outputs,
            show_progress="hidden",
        )
        root_github.click(
            fn=_with_user_activity(
                "STAGE_ROOT_SOURCE_GITHUB",
                lambda pending_kernel, pending_root, state: stage_source_selection(
                    "ROOT", "GITHUB", pending_kernel, pending_root, state
                ),
            ),
            inputs=[kernel_source_pending, root_source_pending, state_store],
            outputs=source_stage_outputs,
            show_progress="hidden",
        )
        apply_sources.click(
            fn=_with_user_activity("APPLY_SOURCE_SELECTIONS", apply_source_selection),
            inputs=[state_store, kernel_source_pending, root_source_pending],
            outputs=[
                state_store,
                header,
                workspace,
                rail,
                bottom,
                kernel_source_pending,
                root_source_pending,
                kernel_drive,
                kernel_github,
                root_drive,
                root_github,
                root_status,
            ],
            show_progress="hidden",
        )

        # Navigation.
        nav_outputs = [
            state_store,
            header,
            workspace,
            rail,
            bottom,
            boot_controls,
            target_dropdown,
            command_json,
            device_export_group,
            maintenance_controls,
        ]

        nav_system.click(
            _with_user_activity("NAV_SYSTEM", lambda state: navigate("SYSTEM", state)),
            inputs=state_store,
            outputs=nav_outputs,
            show_progress="hidden",
        )
        nav_boot.click(
            _with_user_activity("NAV_BOOT", lambda state: navigate("BOOT", state)),
            inputs=state_store,
            outputs=nav_outputs,
            show_progress="hidden",
        )
        nav_runtime.click(
            _with_user_activity("NAV_RUNTIME", lambda state: navigate("RUNTIME", state)),
            inputs=state_store,
            outputs=nav_outputs,
            show_progress="hidden",
        )
        nav_recovery.click(
            _with_user_activity("NAV_RECOVERY", lambda state: navigate("RECOVERY", state)),
            inputs=state_store,
            outputs=nav_outputs,
            show_progress="hidden",
        )
        nav_maintenance.click(
            _with_user_activity("NAV_MAINTENANCE", lambda state: navigate("MAINTENANCE", state)),
            inputs=state_store,
            outputs=nav_outputs,
            show_progress="hidden",
        )

        continue_home_event = continue_home.click(
            _with_user_activity("CONTINUE_HOME", _orf_bios_continue_to_home),
            inputs=None,
            outputs=home_handoff_state,
            show_progress="minimal",
        )
        continue_home_event.then(
            fn=None,
            inputs=home_handoff_state,
            outputs=None,
            js=r"""
            (handoff) => {
              try {
                const status = String((handoff && handoff.status) || "").toUpperCase();
                const url = String((handoff && handoff.url) || "").trim();
                if (status === "READY" && url) {
                  window.location.replace(url);
                  return [];
                }
                const reason = String((handoff && handoff.reason) || "HOME_NOT_READY");
                console.error("ORFMOS Home handoff failed", handoff);
                window.alert(`ORFMOS Home handoff failed: ${reason}`);
              } catch (error) {
                console.error("ORFMOS Home handoff exception", error);
              }
              return [];
            }
            """,
        )

        # Trusted maintenance gate and maintenance-only mutation controls.
        maint_render_outputs = [state_store, header, workspace, rail, bottom]
        issue_maintenance_challenge_button.click(
            _with_user_activity("MAINT_ISSUE_CHALLENGE", _maintenance_issue_challenge),
            inputs=state_store,
            outputs=maint_render_outputs + [maintenance_challenge, maintenance_status],
            show_progress="minimal",
        )
        verify_maintenance_signature_button.click(
            _with_user_activity("MAINT_VERIFY_SIGNATURE", _maintenance_verify_signature),
            inputs=[maintenance_signature, state_store],
            outputs=maint_render_outputs + [maintenance_signature, maintenance_status],
            show_progress="minimal",
        )
        revoke_maintenance_button.click(
            _with_user_activity("MAINT_REVOKE", _maintenance_revoke),
            inputs=state_store,
            outputs=maint_render_outputs + [maintenance_challenge, maintenance_signature, maintenance_status, maintenance_confirm_shutdown_button],
            show_progress="hidden",
        )
        maintenance_stage_kernel_button.click(
            _with_user_activity("MAINT_STAGE_KERNEL_MANIFEST", _maintenance_stage_kernel),
            inputs=[maintenance_kernel_ref, maintenance_kernel_prefix, maintenance_kernel_manifest_sha, state_store],
            outputs=maint_render_outputs + [maintenance_kernel_status],
            show_progress="minimal",
        )
        maintenance_apply_kernel_button.click(
            _with_user_activity("MAINT_APPLY_KERNEL", _maintenance_apply_kernel),
            inputs=state_store,
            outputs=maint_render_outputs + [maintenance_kernel_status],
            show_progress="minimal",
        )
        maintenance_rollback_kernel_button.click(
            _with_user_activity("MAINT_ROLLBACK_KERNEL", _maintenance_rollback_kernel),
            inputs=state_store,
            outputs=maint_render_outputs + [maintenance_kernel_status],
            show_progress="minimal",
        )
        maintenance_arm_shutdown_button.click(
            _with_user_activity("MAINT_ARM_RUNTIME_SHUTDOWN", _maintenance_arm_shutdown),
            inputs=None,
            outputs=[maintenance_shutdown_status, maintenance_confirm_shutdown_button],
            show_progress="hidden",
        )
        maintenance_confirm_shutdown_button.click(
            _with_user_activity("MAINT_EXECUTE_RUNTIME_SHUTDOWN", _maintenance_execute_shutdown),
            inputs=None,
            outputs=maintenance_shutdown_status,
            show_progress="hidden",
        )

        # Synthetic staged boot mutation.
        target_dropdown.change(
            _with_user_activity("STAGE_BOOT_TARGET", stage_boot_target),
            inputs=[target_dropdown, state_store],
            outputs=[
                state_store,
                header,
                workspace,
                rail,
                bottom,
                command_json,
            ],
            show_progress="hidden",
        )

        discard_button.click(
            _with_user_activity("DISCARD_STAGED_BOOT", discard_staged),
            inputs=state_store,
            outputs=[
                state_store,
                header,
                workspace,
                rail,
                bottom,
                target_dropdown,
                command_json,
            ],
            show_progress="hidden",
        )

        apply_button.click(
            _with_user_activity("APPLY_STAGED_BOOT", apply_staged),
            inputs=state_store,
            outputs=[
                state_store,
                header,
                workspace,
                rail,
                bottom,
                target_dropdown,
                command_json,
            ],
            show_progress="hidden",
        )


        # Unified keyboard layer. It never calls BIOS mutation functions directly;
        # it activates the same Gradio controls used by touch/mouse.
        demo.load(
            fn=None,
            inputs=None,
            outputs=None,
            js=r"""
            () => {
              // Expected disconnects are a terminal state, not an invitation to stack
              // the same uncopyable transport toast indefinitely. Keep one notice.
              try {
                if (!window.__ORF_SERVER_NOTICE_GUARD_INSTALLED__) {
                  window.__ORF_SERVER_NOTICE_GUARD_INSTALLED__ = true;
                  window.__ORF_SERVER_NOTICE_SEEN__ = false;
                  const normalizeServerNotices = () => {
                    const nodes = Array.from(document.querySelectorAll('[role="alert"], .toast-wrap, .toast, [data-testid*="toast"]'));
                    const matching = nodes.filter(node => {
                      const text = String(node && node.textContent || "");
                      return /Could not parse server response|Unexpected token ['"]?<['"]?|server response/i.test(text);
                    });
                    if (!matching.length) return;
                    if (window.__ORF_EXPECTED_SERVER_DISCONNECT__) {
                      matching.forEach((node, index) => {
                        if (!window.__ORF_SERVER_NOTICE_SEEN__ && index === 0) {
                          window.__ORF_SERVER_NOTICE_SEEN__ = true;
                          try {
                            node.textContent = "COMMUNICATION WITH SERVER LOST — expected runtime shutdown";
                          } catch (_) {}
                        } else {
                          try { node.remove(); } catch (_) {}
                        }
                      });
                    } else if (matching.length > 1) {
                      matching.slice(1).forEach(node => { try { node.remove(); } catch (_) {} });
                    }
                  };
                  const observer = new MutationObserver(normalizeServerNotices);
                  observer.observe(document.documentElement || document.body, {childList:true, subtree:true, characterData:true});
                  window.__ORF_SERVER_NOTICE_OBSERVER__ = observer;
                }
              } catch (error) {
                console.error("ORF BIOS server-notice guard failed", error);
              }

              // DEVICE SESSION / PROFILE / TELEMETRY PROBE
              try {
                const STORAGE_KEY = "ORF_CLIENT_INSTANCE_ID_V0_1";
                let clientId = null;
                try { clientId = window.localStorage.getItem(STORAGE_KEY); } catch (_) {}
                if (!clientId) {
                  try { clientId = (crypto && crypto.randomUUID) ? crypto.randomUUID() : null; } catch (_) {}
                  if (!clientId) clientId = `orf-client-${Date.now()}-${Math.random().toString(16).slice(2)}`;
                  try { window.localStorage.setItem(STORAGE_KEY, clientId); } catch (_) {}
                }
                window.__ORF_CLIENT_INSTANCE_ID_V0_1__ = clientId;

                const findByIdDeep = (id, root = document) => {
                  try {
                    const direct = root.getElementById ? root.getElementById(id) : null;
                    if (direct) return direct;
                    const selected = root.querySelector ? root.querySelector(`#${id}`) : null;
                    if (selected) return selected;
                    const nodes = root.querySelectorAll ? root.querySelectorAll("*") : [];
                    for (const node of nodes) {
                      if (node && node.shadowRoot) {
                        const found = findByIdDeep(id, node.shadowRoot);
                        if (found) return found;
                      }
                    }
                  } catch (_) {}
                  return null;
                };
                const resolveInput = (id) => {
                  const root = findByIdDeep(id);
                  if (!root) return null;
                  if (["INPUT","TEXTAREA"].includes(String(root.tagName || "").toUpperCase())) return root;
                  return root.querySelector ? root.querySelector("textarea,input") : null;
                };
                const resolveButton = (id) => {
                  const root = findByIdDeep(id);
                  if (!root) return null;
                  if (String(root.tagName || "").toUpperCase() === "BUTTON") return root;
                  return root.querySelector ? root.querySelector("button") : null;
                };
                const setNativeValue = (el, value) => {
                  const proto = String(el.tagName || "").toUpperCase() === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
                  if (setter) setter.call(el, value); else el.value = value;
                  el.dispatchEvent(new Event("input", {bubbles:true, composed:true}));
                  el.dispatchEvent(new Event("change", {bubbles:true, composed:true}));
                };
                const connectionSnapshot = () => {
                  const c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
                  if (!c) return {};
                  return {
                    type: c.type ?? null,
                    effective_type: c.effectiveType ?? null,
                    downlink_mbps: c.downlink ?? null,
                    rtt_ms: c.rtt ?? null,
                    save_data: c.saveData ?? null,
                  };
                };
                window.__ORF_DEVICE_BATTERY_V0_1__ = window.__ORF_DEVICE_BATTERY_V0_1__ || null;
                if (navigator.getBattery && !window.__ORF_DEVICE_BATTERY_REQUESTED_V0_1__) {
                  window.__ORF_DEVICE_BATTERY_REQUESTED_V0_1__ = true;
                  navigator.getBattery().then(b => { window.__ORF_DEVICE_BATTERY_V0_1__ = b; }).catch(() => {});
                }
                const nativeHostSnapshot = (methodName) => {
                  try {
                    const host = window.ORFHost;
                    if (!host || typeof host[methodName] !== "function") return {};
                    const raw = host[methodName]();
                    if (!raw) return {};
                    const parsed = (typeof raw === "string") ? JSON.parse(raw) : raw;
                    if (!parsed || typeof parsed !== "object" || parsed.error) return {};
                    return parsed;
                  } catch (_) { return {}; }
                };
                const buildProfile = () => ({
                  schema: "ORF_DEVICE_PROFILE_V0_1",
                  user_agent: navigator.userAgent || null,
                  platform: navigator.platform || null,
                  language: navigator.language || null,
                  languages: Array.from(navigator.languages || []),
                  timezone: (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || null; } catch (_) { return null; } })(),
                  hardware_concurrency: navigator.hardwareConcurrency ?? null,
                  device_memory_gb: navigator.deviceMemory ?? null,
                  max_touch_points: navigator.maxTouchPoints ?? null,
                  cookies_enabled: navigator.cookieEnabled ?? null,
                  device_pixel_ratio: window.devicePixelRatio ?? null,
                  screen: {
                    width: window.screen?.width ?? null,
                    height: window.screen?.height ?? null,
                    avail_width: window.screen?.availWidth ?? null,
                    avail_height: window.screen?.availHeight ?? null,
                    color_depth: window.screen?.colorDepth ?? null,
                  },
                  viewport: {width: window.innerWidth ?? null, height: window.innerHeight ?? null},
                  orientation: window.screen?.orientation?.type || null,
                  connection: connectionSnapshot(),
                });
                const buildTelemetry = () => {
                  const b = window.__ORF_DEVICE_BATTERY_V0_1__;
                  return {
                    schema: "ORF_DEVICE_TELEMETRY_V0_1",
                    device_utc: new Date().toISOString(),
                    online: navigator.onLine,
                    visibility_state: document.visibilityState || null,
                    viewport: {width: window.innerWidth ?? null, height: window.innerHeight ?? null},
                    connection: connectionSnapshot(),
                    battery: b ? {level: b.level ?? null, charging: b.charging ?? null, charging_time: b.chargingTime ?? null, discharging_time: b.dischargingTime ?? null} : {},
                    performance_memory: performance.memory ? {
                      js_heap_size_limit: performance.memory.jsHeapSizeLimit ?? null,
                      total_js_heap_size: performance.memory.totalJSHeapSize ?? null,
                      used_js_heap_size: performance.memory.usedJSHeapSize ?? null,
                    } : {},
                  };
                };
                const sendProbe = (includeProfile) => {
                  const input = resolveInput("orfDeviceClientPayloadBridge");
                  const button = resolveButton("orfDeviceClientProbeBridge");
                  if (!input || !button) return false;
                  const payload = {
                    client_instance_id: clientId,
                    kind: includeProfile ? "PROFILE_TELEMETRY" : "TELEMETRY",
                    profile: includeProfile ? buildProfile() : {},
                    telemetry: buildTelemetry(),
                    device_profile: includeProfile ? nativeHostSnapshot("getDeviceProfile") : {},
                    device_telemetry: nativeHostSnapshot("getDeviceTelemetry"),
                  };
                  setNativeValue(input, JSON.stringify(payload));
                  button.click();
                  return true;
                };
                if (window.__ORF_DEVICE_SESSION_PROBE_TIMER_V0_1__) {
                  clearInterval(window.__ORF_DEVICE_SESSION_PROBE_TIMER_V0_1__);
                }
                setTimeout(() => sendProbe(true), 700);
                window.__ORF_DEVICE_SESSION_PROBE_TIMER_V0_1__ = setInterval(() => sendProbe(false), 5000);
              } catch (error) {
                console.error("ORF BIOS device session probe failed", error);
              }

              const bootRoot = document.getElementById("orfBootFront");
              const biosRoot = document.getElementById("orfBiosSurface");
              if (bootRoot) bootRoot.style.setProperty("display", "block", "important");
              if (biosRoot) biosRoot.style.setProperty("display", "none", "important");
              if (window.__ORF_BIOS_INPUT_V0_1_INSTALLED__) return [];
              window.__ORF_BIOS_INPUT_V0_1_INSTALLED__ = true;

              const orderedIds = [
                "orfNavSystem",
                "orfNavBoot",
                "orfNavRuntime",
                "orfNavRecovery",
                "orfNavBootScreen",
                "orfActionStage",
                "orfActionDiscard",
                "orfActionApply"
              ];

              let focusIndex = 0;

              function buttonFor(id) {
                const root = document.getElementById(id);
                if (!root) return null;
                if (root.tagName === "BUTTON") return root;
                return root.querySelector("button") || root;
              }

              function availableButtons() {
                return orderedIds
                  .map(buttonFor)
                  .filter(el => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return (
                      r.width > 0 &&
                      r.height > 0 &&
                      style.display !== "none" &&
                      style.visibility !== "hidden" &&
                      !el.disabled
                    );
                  });
              }

              function setFocus(index) {
                const items = availableButtons();
                if (!items.length) return;

                focusIndex = ((index % items.length) + items.length) % items.length;

                document
                  .querySelectorAll(".orf-kbd-focus")
                  .forEach(el => el.classList.remove("orf-kbd-focus"));

                const target = items[focusIndex];
                target.classList.add("orf-kbd-focus");
                target.focus({preventScroll:true});

                const r = target.getBoundingClientRect();
                if (r.top < 0 || r.bottom > window.innerHeight) {
                  target.scrollIntoView({block:"nearest", behavior:"smooth"});
                }
              }

              function activateFocused() {
                const items = availableButtons();
                if (!items.length) return;
                focusIndex = Math.min(focusIndex, items.length - 1);
                items[focusIndex].click();
              }

              function isEditable(target) {
                if (!target) return false;
                const tag = (target.tagName || "").toUpperCase();
                return (
                  tag === "INPUT" ||
                  tag === "TEXTAREA" ||
                  tag === "SELECT" ||
                  target.isContentEditable
                );
              }

              document.addEventListener("keydown", (event) => {
                if (isEditable(event.target)) return;

                switch (event.key) {
                  case "ArrowDown":
                  case "ArrowRight":
                    event.preventDefault();
                    setFocus(focusIndex + 1);
                    break;

                  case "ArrowUp":
                  case "ArrowLeft":
                    event.preventDefault();
                    setFocus(focusIndex - 1);
                    break;

                  case "Enter":
                  case " ":
                    event.preventDefault();
                    activateFocused();
                    break;

                  case "Escape":
                  case "Backspace": {
                    event.preventDefault();
                    const back = buttonFor("orfNavBootScreen");
                    if (back && back.getBoundingClientRect().height > 0) {
                      back.click();
                    }
                    break;
                  }

                  case "Home":
                    event.preventDefault();
                    setFocus(0);
                    break;

                  case "End": {
                    event.preventDefault();
                    const items = availableButtons();
                    if (items.length) setFocus(items.length - 1);
                    break;
                  }
                }
              }, true);

              // Clicking/tapping a firmware control also updates keyboard focus.
              document.addEventListener("pointerdown", (event) => {
                const items = availableButtons();
                const idx = items.findIndex(
                  el => el === event.target || el.contains(event.target)
                );
                if (idx >= 0) {
                  focusIndex = idx;
                  document
                    .querySelectorAll(".orf-kbd-focus")
                    .forEach(el => el.classList.remove("orf-kbd-focus"));
                  items[idx].classList.add("orf-kbd-focus");
                }
              }, true);

              // Prime navigation focus without forcing scroll.
              setTimeout(() => setFocus(0), 250);
              return [];
            }
            """,
        )

    return demo


ORF_BIOS_PRESENTATION_GENERATION_ID = _new_presentation_generation_id()
demo = build_bios_demo(ORF_BIOS_PRESENTATION_GENERATION_ID)

print("BIOS presentation : BUILT / RICH FAILURE CONSOLE + SHUTDOWN HANDOFF R5")
print("Presentation gen  :", ORF_BIOS_PRESENTATION_GENERATION_ID)
print("Boot front door   : PINNED GITHUB ARTIFACT")
print("Device mutation   : DISABLED")
