# ORFMOS DURABLE BOOT ANCHOR v0.1
#
# Permanent front door:
#   https://raw.githubusercontent.com/hadrex83/ORFMOS/main/boot/ORFMOS_BOOTSTRAP_V0_1.py
#
# PROVIDER  GITHUB_RAW
# SERVICE   BOOTSTRAP
# INTENT    BOOT
# CONTRACT  LOCATE -> READ -> VALIDATE -> LOAD
#
# The bootstrap is immutable/versioned. The active selector is the only mutable pointer.
# Every selected BIOS manifest and every ordered module is SHA256/byte verified before
# any module is executed.
#
# No Drive mount. No subprocess. No filesystem WRITE. Standard library only.

import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ORFMOS_BOOTSTRAP_SCHEMA = "ORFMOS_DURABLE_BOOT_ANCHOR_V0_1"
ORFMOS_BOOTSTRAP_VERSION = "0.1"
ORFMOS_BOOTSTRAP_REVISION = "GITHUB_RAW_SELECTOR_MANIFEST_ORDERED_LOADER"
ORFMOS_BOOTSTRAP_SELECTOR_URL = "https://raw.githubusercontent.com/hadrex83/ORFMOS/main/boot/ORFMOS_ACTIVE_BOOT.json"
ORFMOS_BOOTSTRAP_ALLOWED_HOST = "raw.githubusercontent.com"
ORFMOS_BOOTSTRAP_ALLOWED_REPOSITORY = "hadrex83/ORFMOS"
ORFMOS_BOOTSTRAP_TIMEOUT_SECONDS = 30
ORFMOS_BOOTSTRAP_MAX_SELECTOR_BYTES = 65536
ORFMOS_BOOTSTRAP_MAX_MANIFEST_BYTES = 1048576
ORFMOS_BOOTSTRAP_MAX_MODULE_BYTES = 33554432

def _orfmos_boot_utc():
    return datetime.now(timezone.utc).isoformat()

def _orfmos_boot_sha(raw):
    return hashlib.sha256(raw).hexdigest()

def _orfmos_boot_validate_url(url):
    parsed = urllib.parse.urlsplit(str(url or "").strip())
    if parsed.scheme != "https":
        raise RuntimeError("BOOT_URL_HTTPS_REQUIRED")
    if parsed.hostname != ORFMOS_BOOTSTRAP_ALLOWED_HOST:
        raise RuntimeError("BOOT_URL_HOST_NOT_ALLOWED")
    prefix = "/" + ORFMOS_BOOTSTRAP_ALLOWED_REPOSITORY + "/"
    if not parsed.path.startswith(prefix):
        raise RuntimeError("BOOT_URL_REPOSITORY_NOT_ALLOWED")
    if parsed.username or parsed.password or parsed.port:
        raise RuntimeError("BOOT_URL_AUTHORITY_NOT_ALLOWED")
    return parsed

def _orfmos_boot_fetch(url, *, max_bytes):
    _orfmos_boot_validate_url(url)
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": "ORFMOS-Durable-Boot-Anchor/0.1",
            "Cache-Control": "no-cache",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=ORFMOS_BOOTSTRAP_TIMEOUT_SECONDS) as response:
        status = int(getattr(response, "status", 200) or 200)
        if status != 200:
            raise RuntimeError("BOOT_HTTP_STATUS_" + str(status))
        final_url = str(getattr(response, "geturl", lambda: url)() or url)
        _orfmos_boot_validate_url(final_url)
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise RuntimeError("BOOT_OBJECT_TOO_LARGE")
    return raw

def _orfmos_boot_json(raw, expected_schema):
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("BOOT_JSON_INVALID:" + type(exc).__name__) from exc
    if not isinstance(obj, dict):
        raise RuntimeError("BOOT_JSON_OBJECT_REQUIRED")
    if obj.get("schema") != expected_schema:
        raise RuntimeError("BOOT_SCHEMA_MISMATCH")
    return obj

def _orfmos_boot_validate_selector(selector_obj):
    if selector_obj.get("state") != "ACTIVE":
        raise RuntimeError("BOOT_SELECTOR_NOT_ACTIVE")
    if selector_obj.get("provider") != "GITHUB_RAW":
        raise RuntimeError("BOOT_SELECTOR_PROVIDER_UNSUPPORTED")
    if selector_obj.get("repository") != ORFMOS_BOOTSTRAP_ALLOWED_REPOSITORY:
        raise RuntimeError("BOOT_SELECTOR_REPOSITORY_MISMATCH")
    manifest = selector_obj.get("manifest")
    if not isinstance(manifest, dict):
        raise RuntimeError("BOOT_SELECTOR_MANIFEST_REQUIRED")
    url = str(manifest.get("url") or "")
    _orfmos_boot_validate_url(url)
    expected_sha = str(manifest.get("sha256") or "").lower()
    if len(expected_sha) != 64 or any(ch not in "0123456789abcdef" for ch in expected_sha):
        raise RuntimeError("BOOT_SELECTOR_MANIFEST_SHA_INVALID")
    expected_bytes = manifest.get("bytes")
    if not isinstance(expected_bytes, int) or expected_bytes <= 0:
        raise RuntimeError("BOOT_SELECTOR_MANIFEST_BYTES_INVALID")
    if manifest.get("publication_state") != "IMMUTABLE":
        raise RuntimeError("BOOT_SELECTOR_TARGET_NOT_IMMUTABLE")
    return manifest

def _orfmos_boot_validate_manifest(manifest_obj, manifest_url):
    if manifest_obj.get("schema") != "ORF_BIOS_MODULE_MANIFEST_V0_1":
        raise RuntimeError("BOOT_MANIFEST_SCHEMA_MISMATCH")
    if manifest_obj.get("execution_model") != "ORDERED_SHARED_GLOBALS":
        raise RuntimeError("BOOT_EXECUTION_MODEL_UNSUPPORTED")
    modules = manifest_obj.get("modules")
    if not isinstance(modules, list) or not modules:
        raise RuntimeError("BOOT_MODULES_REQUIRED")
    if manifest_obj.get("module_count") != len(modules):
        raise RuntimeError("BOOT_MODULE_COUNT_MISMATCH")

    base_url = manifest_url.rsplit("/", 1)[0] + "/"
    seen_orders = set()
    seen_ids = set()
    verified_plan = []

    for row in sorted(modules, key=lambda x: int(x.get("order", -1)) if isinstance(x, dict) else -1):
        if not isinstance(row, dict):
            raise RuntimeError("BOOT_MODULE_RECORD_INVALID")
        order = row.get("order")
        module_id = str(row.get("module_id") or "")
        path = str(row.get("path") or "")
        expected_sha = str(row.get("sha256") or "").lower()
        expected_bytes = row.get("bytes")

        if not isinstance(order, int) or order < 0 or order in seen_orders:
            raise RuntimeError("BOOT_MODULE_ORDER_INVALID")
        if not module_id or module_id in seen_ids:
            raise RuntimeError("BOOT_MODULE_ID_INVALID")
        if not path or path.startswith("/") or ".." in path.split("/") or not path.endswith(".py"):
            raise RuntimeError("BOOT_MODULE_PATH_INVALID")
        if len(expected_sha) != 64 or any(ch not in "0123456789abcdef" for ch in expected_sha):
            raise RuntimeError("BOOT_MODULE_SHA_INVALID")
        if not isinstance(expected_bytes, int) or expected_bytes <= 0:
            raise RuntimeError("BOOT_MODULE_BYTES_INVALID")

        module_url = urllib.parse.urljoin(base_url, path)
        _orfmos_boot_validate_url(module_url)
        seen_orders.add(order)
        seen_ids.add(module_id)
        verified_plan.append({
            "order": order,
            "module_id": module_id,
            "path": path,
            "url": module_url,
            "bytes": expected_bytes,
            "sha256": expected_sha,
        })

    return verified_plan

def orfmos_durable_boot():
    print("=" * 112)
    print("ORFMOS DURABLE BOOT ANCHOR v0.1 — GITHUB RAW SELECTOR / VERIFIED ORDERED LOADER")
    print("=" * 112)
    print("Selector :", ORFMOS_BOOTSTRAP_SELECTOR_URL)
    print("Authority: MUTABLE SELECTOR -> IMMUTABLE MANIFEST -> SHA-VERIFIED MODULES")
    print("Write    : NONE")
    print("-" * 112)

    selector_raw = _orfmos_boot_fetch(
        ORFMOS_BOOTSTRAP_SELECTOR_URL,
        max_bytes=ORFMOS_BOOTSTRAP_MAX_SELECTOR_BYTES,
    )
    selector_sha = _orfmos_boot_sha(selector_raw)
    selector_obj = _orfmos_boot_json(selector_raw, "ORFMOS_ACTIVE_BOOT_SELECTOR_V0_1")
    manifest_record = _orfmos_boot_validate_selector(selector_obj)

    manifest_url = str(manifest_record["url"])
    manifest_raw = _orfmos_boot_fetch(
        manifest_url,
        max_bytes=ORFMOS_BOOTSTRAP_MAX_MANIFEST_BYTES,
    )
    manifest_sha = _orfmos_boot_sha(manifest_raw)
    if len(manifest_raw) != int(manifest_record["bytes"]):
        raise RuntimeError("BOOT_MANIFEST_BYTES_MISMATCH")
    if manifest_sha != str(manifest_record["sha256"]).lower():
        raise RuntimeError("BOOT_MANIFEST_SHA_MISMATCH")

    manifest_obj = _orfmos_boot_json(manifest_raw, "ORF_BIOS_MODULE_MANIFEST_V0_1")
    plan = _orfmos_boot_validate_manifest(manifest_obj, manifest_url)

    # Phase 1 — read and verify every selected module before executing any module.
    staged = []
    for item in plan:
        raw = _orfmos_boot_fetch(item["url"], max_bytes=ORFMOS_BOOTSTRAP_MAX_MODULE_BYTES)
        observed_sha = _orfmos_boot_sha(raw)
        if len(raw) != item["bytes"]:
            raise RuntimeError("BOOT_MODULE_BYTES_MISMATCH:" + item["module_id"])
        if observed_sha != item["sha256"]:
            raise RuntimeError("BOOT_MODULE_SHA_MISMATCH:" + item["module_id"])
        staged.append((item, raw))
        print(f"VALIDATED {item['order']:03d} {item['module_id']} · {len(raw)} bytes · {observed_sha[:16]}…")

    globals()["__ORFMOS_DURABLE_BOOT_ANCHOR__"] = {
        "schema": ORFMOS_BOOTSTRAP_SCHEMA,
        "state": "VALIDATED",
        "bootstrap_version": ORFMOS_BOOTSTRAP_VERSION,
        "bootstrap_revision": ORFMOS_BOOTSTRAP_REVISION,
        "selector_url": ORFMOS_BOOTSTRAP_SELECTOR_URL,
        "selector_bytes": len(selector_raw),
        "selector_sha256": selector_sha,
        "selector_generation": selector_obj.get("selector_generation"),
        "manifest_url": manifest_url,
        "manifest_bytes": len(manifest_raw),
        "manifest_sha256": manifest_sha,
        "bios_version": manifest_obj.get("bios_version"),
        "bios_revision": manifest_obj.get("revision"),
        "module_count": len(staged),
        "execution_model": "ORDERED_SHARED_GLOBALS",
        "loader_semantics": "exec(compile(...), globals(), globals())",
        "write_authority": "NONE",
        "validated_utc": _orfmos_boot_utc(),
    }

    # Phase 2 — exact ordered shared-global execution.
    for item, raw in staged:
        print(f"LOAD      {item['order']:03d} {item['module_id']}")
        exec(compile(raw, item["url"], "exec"), globals(), globals())

    record = globals().get("__ORFMOS_DURABLE_BOOT_ANCHOR__")
    if isinstance(record, dict):
        record["state"] = "COMPLETE"
        record["completed_utc"] = _orfmos_boot_utc()

    print("-" * 112)
    print("BOOT STATE: COMPLETE")
    print("BIOS      :", manifest_obj.get("bios_version"), "/", manifest_obj.get("revision"))
    print("MANIFEST  :", manifest_sha)
    print("MODULES   :", len(staged), "VERIFIED BEFORE EXECUTION")
    print("=" * 112)
    return globals().get("__ORFMOS_DURABLE_BOOT_ANCHOR__")

if __name__ == "__main__":
    orfmos_durable_boot()
