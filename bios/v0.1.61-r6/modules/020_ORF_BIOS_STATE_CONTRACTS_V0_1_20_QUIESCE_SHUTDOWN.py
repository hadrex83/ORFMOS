# ======================================================================================
# CELL 2 — BIOS STATE + COMMAND CONTRACTS
# ======================================================================================

from __future__ import annotations

import copy
import html
import json
from datetime import datetime, timezone

BIOS_VERSION = "0.1.20"
BIOS_SCHEMA = "ORF_BIOS_STATE_V0_1"
COMMAND_SCHEMA = "ORF_BIOS_COMMAND_V0_1"
DEVICE_LINK_SCHEMA = "ORF_DEVICE_LINK_V0_1"
DEVICE_STATE_SCHEMA = "ORF_DEVICE_STATE_V0_1"

PAGE_ORDER = ["SYSTEM", "BOOT", "RUNTIME", "RECOVERY", "MAINTENANCE"]

BOOT_TARGET_LABELS = {
    "ORFMOS_NORMAL": "ORFMOS Normal",
    "ORFMOS_SAFE": "ORFMOS Safe Boot",
    "RECOVERY": "Recovery Environment",
    "ANDROID_COMPATIBILITY_HOST": "Android Compatibility Host",
}

ORF_BIOS_STATE_V0_1 = {
    "schema": BIOS_SCHEMA,

    "identity": {
        "device": "UNRESOLVED",
        "architecture": "UNRESOLVED",
        "platform_role": "LOCAL_ORFMOS",
        "compatibility_host": "UNRESOLVED",
        "firmware_version": BIOS_VERSION,
        "authority": "LOCAL_ORFMOS_DEVICE_STATE",
    },

    "device_link": {
        "schema": DEVICE_LINK_SCHEMA,
        "pairing_state": "UNPAIRED",
        "connection_state": "NOT_CONNECTED",
        "device_id": None,
        "client_instance_id": None,
        "peer_address": None,
        "profile_state": "NOT_COLLECTED",
        "telemetry_state": "INACTIVE",
        "telemetry_sequence": 0,
        "device_profile_state": "NOT_REPORTED",
        "device_telemetry_state": "INACTIVE",
        "device_telemetry_sequence": 0,
        "device_key_id": None,
        "cloud_key_id": None,
        "session_id": None,
        "session_state": "INACTIVE",
        "probe_stream": "INACTIVE",
        "sequence": None,
        "last_seen_utc": None,
        "device_state_schema": DEVICE_STATE_SCHEMA,
        "authority": "LOCAL_ORFMOS",
    },

    "system": {
        "cpu": {
            "model": "PROBE PENDING",
            "cores": None,
            "utilization": None,
            "thermal_state": "OK",
        },
        "memory": {
            "total": "PROBE PENDING",
            "available": "PROBE PENDING",
            "utilization": None,
        },
        "storage": {
            "total": "PROBE PENDING",
            "available": "PROBE PENDING",
            "utilization": None,
        },
        "display": {
            "width": None,
            "height": None,
            "orientation": "UNRESOLVED",
            "profile": "UNRESOLVED",
        },
        "power": {
            "source": "PROBE PENDING",
            "battery_percent": None,
            "charging": None,
        },
    },

    "session_observations": {
        "network": {},
        "client_profile": {},
        "telemetry": {},
        "device_profile": {},
        "device_telemetry": {},
        "profile_received_utc": None,
        "telemetry_received_utc": None,
        "device_profile_received_utc": None,
        "device_telemetry_received_utc": None,
    },

    "ownership": {
        "home_role": "AWAITING LOCAL ORFMOS",
        "package_manager": "AWAITING LOCAL ORFMOS",
        "file_surface": "AWAITING LOCAL ORFMOS",
        "runtime_provider": "COLAB",
        "execution_authority": "ORF",
    },

    "root_selection": copy.deepcopy(ROOT_INITIAL_STATE),

    "boot": {
        "selected_target": "ORFMOS_NORMAL",
        "available_targets": [
            "ORFMOS_NORMAL",
            "ORFMOS_SAFE",
            "RECOVERY",
            "ANDROID_COMPATIBILITY_HOST",
        ],
        "runtime_provider": "COLAB_KERNEL",
        "presentation": "GITHUB_BOOT_SURFACE",
        "last_boot": {
            "state": "READY",
            "recovery_used": False,
            "sequence": 11,
            "boot_id": "ORF_BOOT_DEVELOPMENT_STATE",
        },
    },

    "runtime": {
        "kernel": {
            "state": "READY",
            "authority": "EXECUTION",
        },
        "drive_api": {
            "state": "READY",
            "authority": "DURABLE_STATE",
        },
        "github": {
            "state": "READY",
            "authority": "PUBLICATION",
        },
        "recovery": {
            "state": "READY",
            "authority": "RECONSTRUCTION",
        },
        "presentation_bridge": {
            "state": "ACTIVE",
            "authority": "PRESENTATION",
        },
        "shutdown": {
            "schema": "ORF_SYSTEM_QUIESCE_V0_1",
            "state": "RUNNING",
            "writes_enabled": True,
            "active_writes": 0,
            "countdown_seconds": 0,
            "drain_state": "IDLE",
            "clients_return_to_boot": False,
        },
    },

    "recovery": {
        "last_known_good": "AVAILABLE",
        "dependency_package": "VERIFIED",
        "runtime_snapshot": "VERIFIED",
        "signing_authority": "PROTECTED",
    },

    "security": {
        "maintainer_gate": "LOCKED",
        "maintainer_authority": "KORF_SIGNER_CHALLENGE",
        "maintainer_session": "INACTIVE",
        "package_authority": "VERIFIED",
        "integrity": "VERIFIED",
    },

    "maintenance": {
        "state": "LOCKED",
        "authority": "KORF_SIGNER_CHALLENGE",
        "session_id": None,
        "session_expires_in_seconds": 0,
        "kernel_update": {
            "state": "IDLE",
            "candidate_version": None,
            "candidate_manifest_sha256": None,
        },
        "runtime_shutdown": {
            "state": "LOCKED",
        },
    },

    "telemetry": {
        "source": "ORF_BOOT_STATE_V0_1",
        "source_mode": "DRIVE_API_LIVE",
        "boot_state": "UNKNOWN",
        "phase": "UNKNOWN",
        "progress": 0,
        "message": "Awaiting Kernel telemetry",
        "boot_id": None,
        "sequence": None,
        "updated_utc": None,
        "kernel_id": None,
        "kernel_version": None,
        "services": {},
        "runtime_environment": {},
    },

    "ui": {
        "active_page": "SYSTEM",
        "selected_item": None,
        "staged_changes": [],
        "mutation_state": "VIEWING",
    },
}



def merge_local_device_state(state, link_payload=None, device_payload=None):
    """
    Presentation-side merge boundary for Local ORFMOS -> Cloud ORFMOS.

    This function deliberately does not authenticate or transport anything.
    The local ORF Console will eventually establish the device link, verify the
    pairing/session, and supply already-validated ORF_DEVICE_LINK_V0_1 and
    ORF_DEVICE_STATE_V0_1 payloads.

    Until that path exists, unresolved fields remain unresolved.
    """
    state = copy.deepcopy(state)
    link_payload = link_payload or {}
    device_payload = device_payload or {}

    if link_payload:
        if link_payload.get("schema") != DEVICE_LINK_SCHEMA:
            raise ValueError(
                f"Unexpected device-link schema: {link_payload.get('schema')!r}"
            )

        link = state["device_link"]
        for key in (
            "pairing_state",
            "connection_state",
            "device_id",
            "client_instance_id",
            "peer_address",
            "profile_state",
            "telemetry_state",
            "telemetry_sequence",
            "device_profile_state",
            "device_telemetry_state",
            "device_telemetry_sequence",
            "device_key_id",
            "cloud_key_id",
            "session_id",
            "session_state",
            "probe_stream",
            "sequence",
            "last_seen_utc",
        ):
            if key in link_payload:
                link[key] = link_payload[key]

    if device_payload:
        if device_payload.get("schema") != DEVICE_STATE_SCHEMA:
            raise ValueError(
                f"Unexpected device-state schema: {device_payload.get('schema')!r}"
            )

        identity = device_payload.get("identity") or {}
        hardware = device_payload.get("hardware") or {}
        display = device_payload.get("display") or {}
        power = device_payload.get("power") or {}
        ownership = device_payload.get("orf_roles") or {}

        ident = state["identity"]
        ident["device"] = (
            identity.get("profile")
            or identity.get("model")
            or state["device_link"].get("device_id")
            or "UNRESOLVED"
        )
        ident["architecture"] = identity.get("architecture", "UNRESOLVED")
        ident["platform_role"] = identity.get("platform_role", "LOCAL_ORFMOS")
        ident["compatibility_host"] = identity.get("platform", "UNRESOLVED")

        sys = state["system"]
        sys["cpu"]["model"] = hardware.get("soc", "PROBE PENDING")
        sys["cpu"]["cores"] = hardware.get("cpu_cores")
        sys["memory"]["total"] = hardware.get("memory_total", "PROBE PENDING")
        sys["memory"]["available"] = hardware.get("memory_available", "PROBE PENDING")
        sys["storage"]["total"] = hardware.get("storage_total", "PROBE PENDING")
        sys["storage"]["available"] = hardware.get("storage_available", "PROBE PENDING")
        sys["display"]["width"] = display.get("width")
        sys["display"]["height"] = display.get("height")
        sys["display"]["orientation"] = display.get("orientation", "UNRESOLVED")
        sys["display"]["profile"] = display.get("profile", "UNRESOLVED")
        sys["power"]["source"] = power.get("source", "PROBE PENDING")
        sys["power"]["battery_percent"] = power.get("battery_percent")
        sys["power"]["charging"] = power.get("charging")

        own = state["ownership"]
        own["home_role"] = ownership.get("home", "AWAITING LOCAL ORFMOS")
        own["package_manager"] = ownership.get("package_manager", "AWAITING LOCAL ORFMOS")
        own["file_surface"] = ownership.get("file_surface", "AWAITING LOCAL ORFMOS")

    return state


def new_bios_command(action, target, requested_value, requires_maintainer=False):
    now = datetime.now(timezone.utc)
    command_id = "ORF_BIOS_CMD_" + now.strftime("%Y%m%dT%H%M%S%fZ")
    return {
        "schema": COMMAND_SCHEMA,
        "command_id": command_id,
        "action": action,
        "target": target,
        "requested_value": requested_value,
        "requires_maintainer": bool(requires_maintainer),
        "state": "STAGED",
        "created_utc": now.isoformat(),
    }


BIOS_STATE = copy.deepcopy(ORF_BIOS_STATE_V0_1)

print("BIOS state schema   :", BIOS_STATE["schema"])
print("BIOS command schema :", COMMAND_SCHEMA)
print("Mutation authority  : SYNTHETIC ONLY")
