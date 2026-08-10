# ORF KERNEL — /content RECOVERY SNAPSHOT
# Creates a non-secret runtime recovery snapshot locally and optionally hands
# persistence to a BIOS/root-provider hook. No cloud/auth provider is embedded.

from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone

ORF_RECOVERY_ALLOWLIST = [
    Path("/content/ORF_RUNTIME_REQUEST.json"),
    Path("/content/ORF_NODE_PACKAGE.zip"),
    Path("/content/ORF_RUNTIME_RESULT.json"),
    Path("/content/ORF_SIGNING_AUTHORITY.json"),
    Path("/content/ORF_NODE_OUTPUT/apk_build_unsigned/APK_UNSIGNED_BUILD_RECEIPT.json"),
    Path("/content/ORF_NODE_OUTPUT/apk_signing/APK_SIGNING_RECEIPT.json"),
]

def _orf_recovery_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _persist_bytes(resource_ref: str, data: bytes) -> dict:
    writer = globals().get("orf_kernel_persist_bytes")
    if not callable(writer):
        raise RuntimeError("Kernel persistence contract unavailable")
    value = writer(str(resource_ref), bytes(data))
    return dict(value) if isinstance(value, dict) else {"resource_ref": str(resource_ref)}

def persist_orf_content_recovery_snapshot():
    orf_service_transition("recovery_snapshot", "STARTING", message="Persisting certified recovery state")
    orf_publish_boot_state("STARTING", "RECOVERY_SNAPSHOT", 0.96, "Persisting certified recovery state")

    result = globals().get("ORF_KERNEL_LAST_RESULT") or {}
    request_id = str(result.get("request_id") or "UNRESOLVED_REQUEST").strip() or "UNRESOLVED_REQUEST"
    prefix = f"recovery/snapshots/{request_id}"

    captured = []
    missing = []
    for path in ORF_RECOVERY_ALLOWLIST:
        if not path.is_file():
            missing.append(str(path))
            continue
        data = path.read_bytes()
        record = _persist_bytes(f"{prefix}/{path.name}", data)
        captured.append({
            "runtime_path": str(path),
            "file_name": path.name,
            "resource_ref": record.get("resource_ref") or f"{prefix}/{path.name}",
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
        })

    snapshot = {
        "schema": "ORF_CONTENT_RECOVERY_SNAPSHOT_V0_2",
        "request_id": request_id,
        "captured_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_root": "/content",
        "status": result.get("status"),
        "capability": result.get("capability"),
        "captured": captured,
        "missing_optional": missing,
        "secret_material_persisted": False,
        "persistence_transport": "ORF_PERSISTENCE_CONTRACT",
        "excluded": [
            "/content/ORF_RELEASE_SIGNING.jks",
            "ORF_SIGNING_ALIAS environment value",
            "ORF_SIGNING_STORE_PASSWORD environment value",
            "ORF_SIGNING_KEY_PASSWORD environment value",
        ],
    }

    snapshot_path = Path("/content/ORF_RECOVERY_SNAPSHOT.json")
    snapshot_bytes = (json.dumps(snapshot, indent=2, sort_keys=True) + "\n").encode("utf-8")
    snapshot_path.write_bytes(snapshot_bytes)
    record = _persist_bytes(f"{prefix}/ORF_RECOVERY_SNAPSHOT.json", snapshot_bytes)
    snapshot["snapshot_resource_ref"] = record.get("resource_ref") or f"{prefix}/ORF_RECOVERY_SNAPSHOT.json"

    print("=" * 88)
    print("ORF KERNEL — RECOVERY SNAPSHOT")
    print("=" * 88)
    print("Request ID       :", request_id)
    print("Captured files   :", len(captured))
    print("Persistence      : ORF_PERSISTENCE_CONTRACT")
    print("Secret persisted : NO")
    orf_service_transition("recovery_snapshot", "READY", message="Certified recovery state persisted")
    orf_publish_boot_state("READY", "COMPLETE", 1.0, "ORFMOS execution node ready", ready=True)
    return snapshot

try:
    ORF_KERNEL_LAST_RECOVERY_SNAPSHOT = persist_orf_content_recovery_snapshot()
except Exception as exc:
    orf_service_transition("recovery_snapshot", "FAILED", message=f"Recovery snapshot failed: {type(exc).__name__}")
    orf_publish_boot_state("FAILED", "RECOVERY_SNAPSHOT", 1.0, f"Recovery snapshot failed: {type(exc).__name__}")
    raise
