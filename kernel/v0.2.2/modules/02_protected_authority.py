# ORF RELEASE SIGNING — PROTECTED AUTHORITY HYDRATION
# Provider-neutral. BIOS/root resolver supplies protected bytes by logical resource ref.
# Secret values remain memory-only and are never recorded in descriptors.

from pathlib import Path
import ast
import hashlib
import json
import os
import subprocess
import shutil

SIGNING_AUTHORITY_ID = "ORF_RELEASE_SIGNING"
SIGNING_KEYSTORE_RESOURCE_REF = "signing/ORF_RELEASE_SIGNING.jks"
SIGNING_RESOLVER_RESOURCE_REF = "signing/ORF_SIGNING_RESOLVER.py"
SIGNING_KEYSTORE_SHA256 = "424f99088522160ef0556b5a3cfc6acb7c0c95b26250532e5dd162014bcb681c"
SIGNING_RESOLVER_SHA256 = "8133d8e8a2cc842ed1f6c2f5a58701fbf9e773fa26916f07d218838be0a126f3"
KEYSTORE = Path("/content/ORF_RELEASE_SIGNING.jks")
DESCRIPTOR = Path("/content/ORF_SIGNING_AUTHORITY.json")

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _resource_bytes(resource_ref: str) -> bytes:
    reader = globals().get("orf_kernel_resource_bytes")
    if not callable(reader):
        raise RuntimeError("BIOS/local Kernel resource resolver is not available")
    data = reader(str(resource_ref))
    if not isinstance(data, (bytes, bytearray)):
        raise RuntimeError(f"resource resolver returned non-bytes for {resource_ref}")
    return bytes(data)

def _resolver_default(tree: ast.AST, assignment_name: str, env_name: str) -> str:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != assignment_name:
            continue
        value = node.value
        if not isinstance(value, ast.Call) or len(value.args) < 2:
            break
        func = value.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "get"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "environ"
        ):
            break
        env_arg, default_arg = value.args[0], value.args[1]
        if not (isinstance(env_arg, ast.Constant) and env_arg.value == env_name):
            break
        if not (isinstance(default_arg, ast.Constant) and isinstance(default_arg.value, str)):
            break
        return default_arg.value
    raise RuntimeError(f"Protected signing resolver does not expose expected {assignment_name} contract")

def hydrate_release_signing_authority() -> dict:
    actual_keystore_sha = _sha256_path(KEYSTORE) if KEYSTORE.is_file() else None
    if actual_keystore_sha != SIGNING_KEYSTORE_SHA256:
        if KEYSTORE.exists():
            KEYSTORE.unlink()
        key_bytes = _resource_bytes(SIGNING_KEYSTORE_RESOURCE_REF)
        actual_keystore_sha = _sha256_bytes(key_bytes)
        if actual_keystore_sha != SIGNING_KEYSTORE_SHA256:
            raise RuntimeError(
                f"ORF signing keystore SHA256 mismatch: {actual_keystore_sha} != {SIGNING_KEYSTORE_SHA256}"
            )
        KEYSTORE.write_bytes(key_bytes)

    resolver_bytes = _resource_bytes(SIGNING_RESOLVER_RESOURCE_REF)
    actual_resolver_sha = _sha256_bytes(resolver_bytes)
    if actual_resolver_sha != SIGNING_RESOLVER_SHA256:
        raise RuntimeError(
            f"ORF signing resolver SHA256 mismatch: {actual_resolver_sha} != {SIGNING_RESOLVER_SHA256}"
        )

    resolver_tree = ast.parse(resolver_bytes.decode("utf-8"), filename="<ORF_SIGNING_RESOLVER>")
    resolved_values = {
        "ORF_SIGNING_ALIAS": _resolver_default(resolver_tree, "SIGNING_ALIAS", "ORF_SIGNING_ALIAS"),
        "ORF_SIGNING_STORE_PASSWORD": _resolver_default(
            resolver_tree, "SIGNING_STORE_PASSWORD", "ORF_SIGNING_STORE_PASSWORD"
        ),
        "ORF_SIGNING_KEY_PASSWORD": _resolver_default(
            resolver_tree, "SIGNING_KEY_PASSWORD", "ORF_SIGNING_KEY_PASSWORD"
        ),
    }
    for env_name, value in resolved_values.items():
        os.environ.setdefault(env_name, value)

    keytool = shutil.which("keytool")
    if keytool:
        check = subprocess.run(
            [
                keytool,
                "-list",
                "-keystore", str(KEYSTORE),
                "-storepass", os.environ["ORF_SIGNING_STORE_PASSWORD"],
                "-alias", os.environ["ORF_SIGNING_ALIAS"],
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if check.returncode != 0:
            raise RuntimeError("Resolved ORF signing authority failed protected keytool validation")

    descriptor = {
        "schema": "ORF_PROTECTED_AUTHORITY_DESCRIPTOR_V0_1",
        "authority_id": SIGNING_AUTHORITY_ID,
        "keystore_path": str(KEYSTORE),
        "expected_keystore_sha256": SIGNING_KEYSTORE_SHA256,
        "source": {
            "type": "ORF_RESOURCE_REF",
            "keystore_ref": SIGNING_KEYSTORE_RESOURCE_REF,
            "resolver_ref": SIGNING_RESOLVER_RESOURCE_REF,
            "resolver_sha256": SIGNING_RESOLVER_SHA256,
        },
        "environment": {
            "alias": "ORF_SIGNING_ALIAS",
            "store_password": "ORF_SIGNING_STORE_PASSWORD",
            "key_password": "ORF_SIGNING_KEY_PASSWORD",
        },
        "policy": {
            "credentials_embedded": False,
            "secret_values_recorded": False,
            "manifest_policy": "REFERENCE_ONLY",
            "resolver_values_memory_only": True,
        },
    }
    DESCRIPTOR.write_text(json.dumps(descriptor, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    del resolver_bytes, resolver_tree, resolved_values

    print("ORF_RELEASE_SIGNING hydrated for this runtime process.")
    print("Authority resolver: ORF_RESOURCE_REF")
    print("Keystore SHA256:", actual_keystore_sha)
    print("Resolver SHA256:", actual_resolver_sha)
    print("Manual signing prompts: NO")
    print("Secret values written to disk: NO")
    return descriptor
