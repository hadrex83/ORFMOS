# ORFMOS COLAB BOOT AUTHORIZATION GATE v0.1
#
# Host adapter only. This module belongs in the Colab boot/control notebook,
# immediately before the permanent provider-neutral ORFMOS bootstrap.
#
# PROVIDER  COLAB_HOST
# SERVICE   AUTHORIZATION_GATE
# INTENT    AUTHORIZE
# TARGET    HOST_CREDENTIAL_ACCESS
#
# Security contract:
# - requests notebook-local access to declared Colab Secrets
# - never prints, returns, persists, hashes, or stores secret values
# - records only sanitized authorization states
# - optional provider credentials do not demote core ORFMOS boot readiness
#
# Permanent ORFMOS bootstrap remains provider-neutral and must not import google.colab.

from datetime import datetime, timezone

ORFMOS_COLAB_BOOT_AUTH_SCHEMA = "ORFMOS_COLAB_BOOT_AUTHORIZATION_GATE_V0_1"
ORFMOS_COLAB_BOOT_AUTH_VERSION = "0.1"
ORFMOS_COLAB_BOOT_AUTH_REVISION = "INITIAL_SECRET_ACCESS_GATE"
ORFMOS_COLAB_BOOT_AUTH_STATE_GLOBAL = "__ORFMOS_COLAB_BOOT_AUTHORIZATION_STATE__"

# Add future notebook-host secrets here. Secret values are never retained.
ORFMOS_COLAB_BOOT_SECRET_REQUESTS = (
    {
        "secret_name": "ORF_GITHUB_TOKEN",
        "service": "GITHUB_PUBLISHER",
        "required_for_core_boot": False,
        "purpose": "GITHUB_PROVIDER_PUBLICATION",
    },
)

def _orfmos_colab_boot_auth_utc():
    return datetime.now(timezone.utc).isoformat()

def _orfmos_colab_boot_auth_request_secret(userdata, request):
    name = str(request["secret_name"])
    base = {
        "secret_name": name,
        "service": str(request["service"]),
        "purpose": str(request["purpose"]),
        "required_for_core_boot": bool(request["required_for_core_boot"]),
        "credential_output": "SUPPRESSED",
    }

    try:
        value = userdata.get(name)
        present = bool(str(value or "").strip())
        # Deliberately discard the returned credential immediately.
        value = None
        if present:
            return {
                **base,
                "state": "AUTHORIZED",
                "notebook_interaction_required": False,
                "message": "Notebook secret access granted and credential is present.",
            }
        return {
            **base,
            "state": "EMPTY",
            "notebook_interaction_required": True,
            "message": "Secret access resolved but no credential value is present.",
        }
    except Exception as exc:
        etype = type(exc).__name__
        text = str(exc or "")

        if etype == "NotebookAccessError":
            state = "ACCESS_DENIED"
            message = "Notebook access to this secret was not granted."
            interaction = True
        elif etype == "SecretNotFoundError":
            state = "MISSING"
            message = "Declared Colab Secret does not exist."
            interaction = True
        else:
            state = "ERROR"
            message = f"{etype}: {text}"
            interaction = True

        return {
            **base,
            "state": state,
            "notebook_interaction_required": interaction,
            "message": message,
        }

def orfmos_colab_boot_authorization_gate():
    started = _orfmos_colab_boot_auth_utc()

    try:
        from google.colab import userdata
    except Exception as exc:
        record = {
            "schema": ORFMOS_COLAB_BOOT_AUTH_SCHEMA,
            "version": ORFMOS_COLAB_BOOT_AUTH_VERSION,
            "revision": ORFMOS_COLAB_BOOT_AUTH_REVISION,
            "state": "HOST_AUTH_PROVIDER_UNAVAILABLE",
            "provider": "COLAB_HOST",
            "service": "AUTHORIZATION_GATE",
            "intent": "AUTHORIZE",
            "core_boot_allowed": True,
            "started_utc": started,
            "completed_utc": _orfmos_colab_boot_auth_utc(),
            "requests": [],
            "message": f"{type(exc).__name__}: {exc}",
            "credential_output": "SUPPRESSED",
        }
        globals()[ORFMOS_COLAB_BOOT_AUTH_STATE_GLOBAL] = record
        return record

    results = [
        _orfmos_colab_boot_auth_request_secret(userdata, request)
        for request in ORFMOS_COLAB_BOOT_SECRET_REQUESTS
    ]

    required_failures = [
        row for row in results
        if row["required_for_core_boot"] and row["state"] != "AUTHORIZED"
    ]
    optional_unavailable = [
        row for row in results
        if not row["required_for_core_boot"] and row["state"] != "AUTHORIZED"
    ]

    if required_failures:
        state = "REQUIRED_AUTHORIZATION_UNAVAILABLE"
        core_boot_allowed = False
    elif optional_unavailable:
        state = "READY_WITH_OPTIONAL_AUTHORIZATION_RESIDUALS"
        core_boot_allowed = True
    else:
        state = "READY"
        core_boot_allowed = True

    record = {
        "schema": ORFMOS_COLAB_BOOT_AUTH_SCHEMA,
        "version": ORFMOS_COLAB_BOOT_AUTH_VERSION,
        "revision": ORFMOS_COLAB_BOOT_AUTH_REVISION,
        "state": state,
        "provider": "COLAB_HOST",
        "service": "AUTHORIZATION_GATE",
        "intent": "AUTHORIZE",
        "core_boot_allowed": core_boot_allowed,
        "request_count": len(results),
        "authorized_count": sum(row["state"] == "AUTHORIZED" for row in results),
        "optional_residual_count": len(optional_unavailable),
        "required_failure_count": len(required_failures),
        "started_utc": started,
        "completed_utc": _orfmos_colab_boot_auth_utc(),
        "requests": results,
        "credential_output": "SUPPRESSED",
    }

    globals()[ORFMOS_COLAB_BOOT_AUTH_STATE_GLOBAL] = record
    return record

ORFMOS_COLAB_BOOT_AUTHORIZATION_STATE = orfmos_colab_boot_authorization_gate()

print("=" * 108)
print("ORFMOS COLAB BOOT AUTHORIZATION GATE v0.1")
print("=" * 108)
print("State             :", ORFMOS_COLAB_BOOT_AUTHORIZATION_STATE["state"])
print("Core boot allowed :", ORFMOS_COLAB_BOOT_AUTHORIZATION_STATE["core_boot_allowed"])
print("Requests          :", ORFMOS_COLAB_BOOT_AUTHORIZATION_STATE["request_count"])
print("Authorized        :", ORFMOS_COLAB_BOOT_AUTHORIZATION_STATE["authorized_count"])
print("Credential output : SUPPRESSED")
for row in ORFMOS_COLAB_BOOT_AUTHORIZATION_STATE["requests"]:
    print(
        f"  {row['service']:<24} {row['secret_name']:<24} "
        f"{row['state']:<18} core_required={row['required_for_core_boot']}"
    )
print("=" * 108)
