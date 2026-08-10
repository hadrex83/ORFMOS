#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUEST_NAME = "ORF_RUNTIME_REQUEST.json"
RESULT_NAME = "ORF_RUNTIME_RESULT.json"
DEFAULT_PACKAGE_NAME = "ORF_NODE_PACKAGE.zip"
LOADER_VERSION = "0.1.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_request_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("request_id is required")
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
    if any(c not in allowed for c in text):
        raise ValueError("request_id contains unsupported characters")
    return text[:160]


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return obj


def validate_zip_members(zf: zipfile.ZipFile) -> None:
    for info in zf.infolist():
        name = info.filename
        p = Path(name)
        if name.startswith(("/", "\\")) or ".." in p.parts:
            raise ValueError(f"unsafe ZIP member: {name}")
        # refuse symlinks from Unix ZIP metadata
        mode = (info.external_attr >> 16) & 0xFFFF
        if mode and (mode & 0o170000) == 0o120000:
            raise ValueError(f"symlink ZIP member not permitted: {name}")


def read_manifest(zf: zipfile.ZipFile) -> dict:
    try:
        raw = zf.read("manifest.json")
    except KeyError as exc:
        raise ValueError("node package has no root manifest.json") from exc
    manifest = json.loads(raw.decode("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest.json must contain an object")
    if manifest.get("schema") != "ORF_NODE_PACKAGE_MANIFEST_V0_1":
        raise ValueError(f"unsupported manifest schema: {manifest.get('schema')!r}")
    if not manifest.get("node_id"):
        raise ValueError("manifest node_id is required")
    if not isinstance(manifest.get("capabilities"), dict):
        raise ValueError("manifest capabilities must be an object")
    return manifest


def verify_declared_resources(zf: zipfile.ZipFile, manifest: dict, required_ids: list[str] | None = None) -> list[dict]:
    resources = manifest.get("resources", [])
    by_id = {r.get("resource_id"): r for r in resources if isinstance(r, dict) and r.get("resource_id")}
    selected = []
    if required_ids is None:
        selected = list(by_id.values())
    else:
        for rid in required_ids:
            if rid not in by_id:
                raise ValueError(f"required resource not declared: {rid}")
            selected.append(by_id[rid])

    verified = []
    for res in selected:
        path = res.get("path")
        expected = str(res.get("sha256") or "").lower()
        if not path or not expected:
            raise ValueError(f"resource declaration incomplete: {res.get('resource_id')}")
        try:
            data = zf.read(path)
        except KeyError as exc:
            raise ValueError(f"declared resource missing from ZIP: {path}") from exc
        actual = sha256_bytes(data)
        if actual != expected:
            raise ValueError(f"resource SHA256 mismatch for {res.get('resource_id')}: {actual} != {expected}")
        declared_size = res.get("size_bytes")
        if declared_size is not None and int(declared_size) != len(data):
            raise ValueError(f"resource size mismatch for {res.get('resource_id')}")
        verified.append({"resource_id": res.get("resource_id"), "path": path, "sha256": actual, "size_bytes": len(data)})
    return verified


def extract_package(zf: zipfile.ZipFile, root: Path) -> None:
    validate_zip_members(zf)
    zf.extractall(root)


def load_entrypoint(module_path: Path, function_name: str):
    if not module_path.is_file():
        raise FileNotFoundError(f"entrypoint module missing: {module_path}")
    spec = importlib.util.spec_from_file_location("orf_node_entrypoint", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load entrypoint module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, function_name, None)
    if not callable(fn):
        raise RuntimeError(f"entrypoint function not callable: {function_name}")
    return fn


def resolve_package_path(request: dict, request_path: Path) -> Path:
    locator = request.get("package_locator")
    if locator:
        p = Path(str(locator)).expanduser()
        if not p.is_absolute():
            p = (request_path.parent / p).resolve()
        return p
    return request_path.parent / DEFAULT_PACKAGE_NAME


def write_result(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def execute_request(request_path: Path, result_path: Path | None = None) -> dict:
    started = utc_now()
    request = load_json(request_path)
    request_id = safe_request_id(request.get("request_id"))
    capability = str(request.get("capability") or "").strip()
    if not capability:
        raise ValueError("capability is required")

    package_path = resolve_package_path(request, request_path)
    if not package_path.is_file():
        raise FileNotFoundError(f"node package not found: {package_path}")

    package_sha = sha256_path(package_path)
    expected_package_sha = str(request.get("expected_package_sha256") or "").lower().strip()
    if expected_package_sha and expected_package_sha != package_sha:
        raise ValueError(f"package SHA256 mismatch: {package_sha} != {expected_package_sha}")

    runtime_root = request_path.parent / ".orf_runtime" / request_id
    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    runtime_root.mkdir(parents=True)

    with zipfile.ZipFile(package_path, "r") as zf:
        validate_zip_members(zf)
        manifest = read_manifest(zf)
        cap = manifest["capabilities"].get(capability)
        if not isinstance(cap, dict):
            raise ValueError(f"capability not provided by node {manifest.get('node_id')}: {capability}")

        required_resources = list(cap.get("required_resources") or [])
        verified = verify_declared_resources(zf, manifest, required_resources)
        extract_package(zf, runtime_root)

    entry = cap.get("entrypoint") or {}
    module_rel = entry.get("module")
    function_name = entry.get("function", "run")
    if not module_rel:
        raise ValueError(f"capability {capability} has no entrypoint module")

    fn = load_entrypoint(runtime_root / module_rel, function_name)
    context = {
        "loader_version": LOADER_VERSION,
        "request": request,
        "request_path": str(request_path),
        "package_path": str(package_path),
        "package_sha256": package_sha,
        "package_root": str(runtime_root),
        "manifest": manifest,
        "verified_resources": verified,
    }
    payload = fn(context)

    result = {
        "schema": "ORF_RUNTIME_RESULT_V0_1",
        "status": "COMPLETE",
        "request_id": request_id,
        "capability": capability,
        "node_id": manifest.get("node_id"),
        "node_version": manifest.get("version"),
        "package_sha256": package_sha,
        "loader_version": LOADER_VERSION,
        "started_utc": started,
        "completed_utc": utc_now(),
        "verified_resource_count": len(verified),
        "payload": payload,
    }
    write_result(result_path or (request_path.parent / RESULT_NAME), result)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="ORF manifest node-package loader v0.1")
    ap.add_argument("--request", default=REQUEST_NAME)
    ap.add_argument("--result", default=None)
    args = ap.parse_args()
    request_path = Path(args.request).expanduser().resolve()
    result_path = Path(args.result).expanduser().resolve() if args.result else request_path.parent / RESULT_NAME

    try:
        result = execute_request(request_path, result_path)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except BaseException as exc:
        failure = {
            "schema": "ORF_RUNTIME_RESULT_V0_1",
            "status": "FAILED",
            "loader_version": LOADER_VERSION,
            "timestamp_utc": utc_now(),
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "traceback": traceback.format_exc(),
        }
        try:
            write_result(result_path, failure)
        except Exception:
            pass
        print(json.dumps(failure, indent=2, sort_keys=True), file=sys.stderr)
        return 1
