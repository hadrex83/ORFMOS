# ORF KERNEL — COLD RUNTIME RECOVERY HYDRATION
# Provider-neutral. BIOS/root source stages logical recovery resources; the Kernel
# verifies hashes and rebuilds prerequisite stages locally.

from pathlib import Path
import hashlib
import json

ORF_RUNTIME_TARGET_RESOURCE_REF = "recovery/ORF_RUNTIME_TARGET.json"
ORF_RUNTIME_REQUEST_PATH = Path("/content/ORF_RUNTIME_REQUEST.json")
ORF_NODE_PACKAGE_PATH = Path("/content/ORF_NODE_PACKAGE.zip")
ORF_RUNTIME_RESULT_PATH = Path("/content/ORF_RUNTIME_RESULT.json")

def _recovery_sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _resource_bytes(resource_ref: str) -> bytes:
    reader = globals().get("orf_kernel_resource_bytes")
    if not callable(reader):
        raise RuntimeError("BIOS/local Kernel resource resolver is not available")
    data = reader(str(resource_ref))
    if not isinstance(data, (bytes, bytearray)):
        raise RuntimeError(f"resource resolver returned non-bytes for {resource_ref}")
    return bytes(data)

def _recovery_json_bytes(data: bytes, label: str) -> dict:
    try:
        value = json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"invalid recovery JSON: {label}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"recovery JSON must be an object: {label}")
    return value

def _recovery_fetch_verified(resource_ref: str, expected_sha256: str, label: str) -> bytes:
    data = _resource_bytes(resource_ref)
    actual = _recovery_sha256_bytes(data)
    if actual != expected_sha256:
        raise RuntimeError(
            f"recovery SHA mismatch for {label}: expected {expected_sha256}, got {actual}"
        )
    return data

def _recovery_stage_dependencies(manifest: dict, stage: str) -> list[dict]:
    deps = [d for d in manifest.get("dependencies", []) if d.get("stage") == stage]
    if not deps:
        raise RuntimeError(f"no recovery dependencies declared for stage: {stage}")
    return deps

def _recovery_stage_ready(manifest: dict, stage: str) -> bool:
    spec = (manifest.get("stage_readiness") or {}).get(stage) or {}
    required = [Path(p) for p in spec.get("required_paths") or []]
    return bool(required) and all(p.exists() for p in required)

def _recovery_hydrate_stage_inputs(manifest: dict, stage: str) -> dict:
    written = []
    request_obj = None
    for dep in _recovery_stage_dependencies(manifest, stage):
        role = str(dep.get("role") or "")
        runtime_name = str(dep.get("runtime_name") or "").strip()
        if role == "NONSECRET_SIGNING_AUTHORITY_DESCRIPTOR":
            continue
        if runtime_name not in {"ORF_RUNTIME_REQUEST.json", "ORF_NODE_PACKAGE.zip"}:
            continue
        resource_ref = str(dep.get("resource_ref") or "").strip()
        if not resource_ref:
            raise RuntimeError(f"recovery dependency lacks resource_ref: {stage}:{runtime_name}")
        data = _recovery_fetch_verified(
            resource_ref,
            str(dep["sha256"]),
            f"{stage}:{runtime_name}",
        )
        target = Path("/content") / runtime_name
        target.write_bytes(data)
        written.append({
            "stage": stage,
            "runtime_path": str(target),
            "resource_ref": resource_ref,
            "sha256": str(dep["sha256"]),
            "role": role,
        })
        if runtime_name == "ORF_RUNTIME_REQUEST.json":
            request_obj = _recovery_json_bytes(data, f"{stage}:request")
    if not ORF_RUNTIME_REQUEST_PATH.is_file() or not ORF_NODE_PACKAGE_PATH.is_file():
        raise RuntimeError(f"recovery failed to hydrate runtime handoff for {stage}")
    return {"stage": stage, "request": request_obj or {}, "written": written}

def _recovery_prerequisite_order(manifest: dict, target_stage: str) -> list[str]:
    graph = manifest.get("stage_dependencies") or {}
    ordered = []
    visiting = set()
    visited = set()
    def visit(stage: str):
        if stage in visited:
            return
        if stage in visiting:
            raise RuntimeError(f"recovery dependency cycle at {stage}")
        visiting.add(stage)
        for dep_stage in graph.get(stage, []) or []:
            visit(str(dep_stage))
        visiting.remove(stage)
        visited.add(stage)
        if stage != target_stage:
            ordered.append(stage)
    visit(target_stage)
    return ordered

def prepare_orf_runtime_recovery():
    orf_service_transition("recovery", "STARTING", message="Resolving durable recovery target")
    orf_publish_boot_state("RECOVERING", "RECOVERY_RESOLUTION", 0.24, "Resolving durable recovery target")

    target_bytes = _resource_bytes(ORF_RUNTIME_TARGET_RESOURCE_REF)
    target = _recovery_json_bytes(target_bytes, "ORF_RUNTIME_TARGET")
    if target.get("schema") not in {"ORF_RUNTIME_TARGET_V0_1", "ORF_RUNTIME_TARGET_V0_2"}:
        raise RuntimeError("unsupported ORF runtime target schema")

    manifest_ref = str(target.get("dependency_manifest_ref") or "").strip()
    manifest_sha = str(target.get("dependency_manifest_sha256") or "").strip()
    if not manifest_ref or not manifest_sha:
        raise RuntimeError("runtime target requires dependency_manifest_ref + dependency_manifest_sha256")

    manifest_bytes = _recovery_fetch_verified(
        manifest_ref,
        manifest_sha,
        "recovery dependency manifest",
    )
    manifest = _recovery_json_bytes(manifest_bytes, "recovery dependency manifest")
    if manifest.get("schema") not in {
        "ORF_RECOVERY_DEPENDENCY_MANIFEST_V0_1",
        "ORF_RECOVERY_DEPENDENCY_MANIFEST_V0_2",
    }:
        raise RuntimeError("unsupported recovery dependency manifest schema")

    target_stage = str(target.get("target_stage") or "").strip()
    if not target_stage:
        raise RuntimeError("ORF runtime target has no target_stage")

    rebuilt = []
    prerequisite_order = _recovery_prerequisite_order(manifest, target_stage)
    if prerequisite_order:
        orf_publish_boot_state(
            "RECOVERING", "DEPENDENCY_RESOLUTION", 0.32,
            f"Resolving {len(prerequisite_order)} prerequisite stage(s)"
        )
    for stage_index, stage in enumerate(prerequisite_order):
        if _recovery_stage_ready(manifest, stage):
            print(f"RECOVERY READY  [{stage}] prerequisite already hydrated")
            continue
        stage_hydration = _recovery_hydrate_stage_inputs(manifest, stage)
        request = stage_hydration["request"]
        stage_progress = 0.38 + (0.20 * (stage_index / max(1, len(prerequisite_order))))
        orf_publish_boot_state(
            "RECOVERING", "PREREQUISITE_REBUILD", stage_progress,
            f"Rebuilding {stage}: {request.get('capability') or 'UNKNOWN_CAPABILITY'}"
        )
        print(f"RECOVERY REBUILD [{stage}] {request.get('capability') or 'UNKNOWN_CAPABILITY'}")
        result = execute_request(ORF_RUNTIME_REQUEST_PATH, ORF_RUNTIME_RESULT_PATH)
        if result.get("status") != "COMPLETE":
            raise RuntimeError(f"recovery prerequisite failed: {stage}")
        if not _recovery_stage_ready(manifest, stage):
            raise RuntimeError(f"recovery prerequisite did not satisfy readiness: {stage}")
        rebuilt.append({
            "stage": stage,
            "request_id": result.get("request_id"),
            "capability": result.get("capability"),
            "package_sha256": result.get("package_sha256"),
        })

    orf_publish_boot_state("RECOVERING", "RUNTIME_HANDOFF", 0.66, f"Hydrating target stage {target_stage}")
    target_hydration = _recovery_hydrate_stage_inputs(manifest, target_stage)
    target_request = target_hydration["request"]
    expected_request_id = str(target.get("request_id") or "").strip()
    actual_request_id = str(target_request.get("request_id") or "").strip()
    if expected_request_id and actual_request_id != expected_request_id:
        raise RuntimeError(
            f"runtime target request mismatch: expected {expected_request_id}, got {actual_request_id}"
        )

    state = {
        "schema": "ORF_RUNTIME_RECOVERY_HYDRATION_V0_2",
        "target_stage": target_stage,
        "request_id": actual_request_id,
        "capability": target_request.get("capability"),
        "rebuilt_prerequisites": rebuilt,
        "handoff_ready": True,
        "resource_transport": "ORF_RESOURCE_REF",
        "secret_material_persisted": False,
    }

    print("=" * 88)
    print("ORF KERNEL — COLD RECOVERY HYDRATED")
    print("=" * 88)
    print("Target stage     :", target_stage)
    print("Request ID       :", actual_request_id)
    print("Capability       :", target_request.get("capability"))
    print("Prereqs rebuilt  :", len(rebuilt))
    print("Runtime handoff  : READY")
    orf_service_transition("recovery", "READY", message="Runtime recovery handoff ready")
    orf_publish_boot_state("STARTING", "RUNTIME_HANDOFF", 0.72, "Runtime handoff restored; starting execution")
    return state

try:
    ORF_KERNEL_LAST_RECOVERY_HYDRATION = prepare_orf_runtime_recovery()
except Exception as exc:
    orf_service_transition("recovery", "FAILED", message=f"Recovery failed: {type(exc).__name__}")
    orf_publish_boot_state("FAILED", "RECOVERY", 1.0, f"Recovery failed: {type(exc).__name__}")
    raise
