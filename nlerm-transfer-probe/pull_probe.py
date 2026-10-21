#!/usr/bin/env python3
"""Read-only fetch of a pinned, harmless NLERM transport probe.

Does not execute downloaded bytes. Fails closed on SHA mismatch.
"""
import hashlib
import os
from pathlib import Path
from urllib.request import urlopen

URL = "https://raw.githubusercontent.com/hadrex83/ORFMOS/5205f26e4d3223fbf5b4a427526873a2e6af78f4/nlerm-transfer-probe/PROBE.txt"
EXPECTED_SHA256 = "c5390063b09999636f3ef6d5b00f42d40de405046401b4976ef40d425fc22525"
DEST = Path.home() / "Projects" / "NLERM" / "artifact_intake" / "probe_v01"


def main():
    with urlopen(URL, timeout=20) as response:
        payload = response.read(4097)
    if len(payload) > 4096:
        raise RuntimeError("SIZE_LIMIT_EXCEEDED")
    observed = hashlib.sha256(payload).hexdigest()
    if observed != EXPECTED_SHA256:
        raise RuntimeError(f"SHA256_MISMATCH expected={EXPECTED_SHA256} observed={observed}")
    DEST.mkdir(parents=True, exist_ok=True)
    temp = DEST / (".PROBE.txt." + str(os.getpid()))
    final = DEST / "PROBE.txt"
    if final.is_symlink() or temp.is_symlink():
        raise RuntimeError("SYMLINK_REFUSED")
    with temp.open("xb") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, final)
    print(f"TRANSFER_VERIFIED sha256={observed} bytes={len(payload)} staged={final}")
    print("EXECUTION_AUTHORIZED=false")


if __name__ == "__main__":
    main()
