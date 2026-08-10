# ORF KERNEL — PORTABLE LOCAL-TREE BOOTSTRAP
# BIOS owns distribution transport and stages the selected source locally.
# Kernel executes only a local verified tree and provider-neutral resource hooks.

from pathlib import Path
import hashlib
import json

ORF_KERNEL_SOURCE_ROOT = Path(
    globals().get("ORF_KERNEL_SOURCE_ROOT")
    or "/content/.orf_kernel_source"
)
ORF_KERNEL_MANIFEST_PATH = ORF_KERNEL_SOURCE_ROOT / "ORF_KERNEL_BOOT_MANIFEST.json"
ORF_KERNEL_MODULE_ROOT = ORF_KERNEL_SOURCE_ROOT / "modules"
ORF_KERNEL_RUNTIME_ROOT = Path("/content/.orf_kernel")
ORF_KERNEL_RUNTIME_MODULE_ROOT = ORF_KERNEL_RUNTIME_ROOT / "modules"

ORF_KERNEL_RESOURCE_ROOT = Path(
    globals().get("ORF_KERNEL_RESOURCE_ROOT")
    or "/content/.orf_runtime/resources"
)
ORF_KERNEL_PERSIST_ROOT = Path(
    globals().get("ORF_KERNEL_PERSIST_ROOT")
    or "/content/.orf_runtime/persist"
)

def _orf_kernel_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def orf_kernel_resource_bytes(resource_ref: str) -> bytes:
    external = globals().get("ORF_BIOS_RESOURCE_READ")
    if callable(external):
        data = external(str(resource_ref))
        if not isinstance(data, (bytes, bytearray)):
            raise RuntimeError(f"BIOS resource reader returned non-bytes for {resource_ref}")
        return bytes(data)

    rel = Path(str(resource_ref))
    if rel.is_absolute() or ".." in rel.parts:
        raise RuntimeError(f"unsafe ORF resource ref: {resource_ref}")
    path = ORF_KERNEL_RESOURCE_ROOT / rel
    if not path.is_file():
        raise RuntimeError(f"ORF resource not staged: {resource_ref}")
    return path.read_bytes()

def orf_kernel_persist_bytes(resource_ref: str, data: bytes) -> dict:
    external = globals().get("ORF_BIOS_PERSIST_WRITE")
    if callable(external):
        value = external(str(resource_ref), bytes(data))
        if isinstance(value, dict):
            return dict(value)
        return {"resource_ref": str(resource_ref), "transport": "BIOS_PERSIST_WRITE"}

    rel = Path(str(resource_ref))
    if rel.is_absolute() or ".." in rel.parts:
        raise RuntimeError(f"unsafe ORF persistence ref: {resource_ref}")
    path = ORF_KERNEL_PERSIST_ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(data))
    return {
        "resource_ref": str(resource_ref),
        "transport": "LOCAL_RUNTIME",
        "runtime_path": str(path),
        "size_bytes": len(data),
        "sha256": _orf_kernel_sha256(data),
    }

manifest_bytes = ORF_KERNEL_MANIFEST_PATH.read_bytes()
manifest_sha256 = _orf_kernel_sha256(manifest_bytes)
expected_manifest_sha = str(
    globals().get("ORF_KERNEL_EXPECTED_MANIFEST_SHA256") or ""
).strip().lower()
if expected_manifest_sha and manifest_sha256 != expected_manifest_sha:
    raise RuntimeError(
        f"ORF Kernel manifest SHA256 mismatch: {manifest_sha256} != {expected_manifest_sha}"
    )

manifest = json.loads(manifest_bytes.decode("utf-8"))
if manifest.get("schema") != "ORF_KERNEL_BOOT_MANIFEST_V0_2":
    raise RuntimeError(f"Unsupported ORF Kernel manifest schema: {manifest.get('schema')!r}")

ORF_KERNEL_RUNTIME_MODULE_ROOT.mkdir(parents=True, exist_ok=True)

print("=" * 88)
print("ORF KERNEL — PORTABLE MODULAR BOOT")
print("=" * 88)
print("Kernel ID       :", manifest.get("kernel_id"))
print("Kernel version  :", manifest.get("version"))
print("Manifest SHA256 :", manifest_sha256)
print("Source root     :", ORF_KERNEL_SOURCE_ROOT)
print("Transport       : BIOS-RESOLVED LOCAL TREE")

loaded = []
for module in sorted(manifest.get("modules") or [], key=lambda item: int(item.get("order", 0))):
    module_id = str(module["module_id"])
    file_name = str(module["file_name"])
    expected_sha = str(module["sha256"]).lower()
    source_path = ORF_KERNEL_MODULE_ROOT / file_name
    source_bytes = source_path.read_bytes()
    actual_sha = _orf_kernel_sha256(source_bytes)
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"ORF Kernel module SHA256 mismatch for {module_id}: {actual_sha} != {expected_sha}"
        )

    runtime_path = ORF_KERNEL_RUNTIME_MODULE_ROOT / file_name
    runtime_path.write_bytes(source_bytes)
    source = source_bytes.decode("utf-8")
    exec(compile(source, f"<ORF_KERNEL:{module_id}>", "exec"), globals(), globals())

    loaded.append({
        "module_id": module_id,
        "file_name": file_name,
        "sha256": actual_sha,
        "size_bytes": len(source_bytes),
    })
    print(f"LOADED [{module['order']:>2}] {module_id}  {actual_sha[:16]}…")

ORF_KERNEL_BOOT_STATE = {
    "schema": "ORF_KERNEL_BOOT_STATE_V0_2",
    "kernel_id": manifest.get("kernel_id"),
    "kernel_version": manifest.get("version"),
    "manifest_sha256": manifest_sha256,
    "source_transport": "BIOS_RESOLVED_LOCAL_TREE",
    "source_root": str(ORF_KERNEL_SOURCE_ROOT),
    "loaded_modules": loaded,
}

print("=" * 88)
print("ORF KERNEL PORTABLE MODULAR BOOT COMPLETE")
print("=" * 88)
