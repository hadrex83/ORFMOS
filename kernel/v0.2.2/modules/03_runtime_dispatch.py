# ORF KERNEL — RUNTIME DISPATCH
# Request-aware final stage. Provider-neutral; BIOS/runtime input provider owns handoff staging.

from pathlib import Path
import json

REQUEST_PATH = Path("/content/ORF_RUNTIME_REQUEST.json")
PACKAGE_PATH = Path("/content/ORF_NODE_PACKAGE.zip")
RESULT_PATH = Path("/content/ORF_RUNTIME_RESULT.json")


def run_orf_kernel_request():
    orf_service_transition("runtime_dispatch", "STARTING", message="Resolving runtime request")
    orf_publish_boot_state("STARTING", "RUNTIME_DISPATCH", 0.76, "Resolving runtime request")
    missing = [p.name for p in (REQUEST_PATH, PACKAGE_PATH) if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            "Missing ORF runtime handoff files staged by BIOS/runtime input provider: "
            + ", ".join(missing)
        )

    request = load_json(REQUEST_PATH)
    capability = str(request.get("capability") or "").strip()

    if capability == "APK_SIGN_AND_VERIFY":
        orf_service_transition("protected_authority", "STARTING", message="Hydrating protected signing authority")
        orf_publish_boot_state("STARTING", "PROTECTED_AUTHORITY", 0.81, "Hydrating protected signing authority")
        hydrate_release_signing_authority()
        orf_service_transition("protected_authority", "READY", message="Protected signing authority ready")

    orf_publish_boot_state("STARTING", "CAPABILITY_EXECUTION", 0.86, f"Executing {capability or 'runtime capability'}")
    result = execute_request(REQUEST_PATH, RESULT_PATH)
    print(json.dumps(result, indent=2, sort_keys=True))
    print("\nRESULT:", RESULT_PATH)
    orf_service_transition("runtime_dispatch", "READY", message=f"{capability or 'runtime capability'} complete")
    orf_publish_boot_state("STARTING", "RESULT_VERIFIED", 0.93, "Runtime result complete and verified")
    return result


try:
    ORF_KERNEL_LAST_RESULT = run_orf_kernel_request()
except Exception as exc:
    orf_service_transition("runtime_dispatch", "FAILED", message=f"Runtime dispatch failed: {type(exc).__name__}")
    orf_publish_boot_state("FAILED", "RUNTIME_DISPATCH", 1.0, f"Runtime dispatch failed: {type(exc).__name__}")
    raise
