# ORFMOS Durable Boot Anchor v0.1

Upload this `boot/` folder into the root of `hadrex83/ORFMOS`.

Permanent bootstrap URL:

https://raw.githubusercontent.com/hadrex83/ORFMOS/main/boot/ORFMOS_BOOTSTRAP_V0_1.py

Mutable selector URL:

https://raw.githubusercontent.com/hadrex83/ORFMOS/main/boot/ORFMOS_ACTIVE_BOOT.json

Initial immutable BIOS target:

bios/v0.1.61-r6/ORF_BIOS_MODULE_MANIFEST.json

Manifest SHA256:

18c74294439d84de07893fb029bdf154e38b8e9cd931e2a25965645ea8cc8895

Bootstrap SHA256:

bd96b01a06545633a98ccd68290db919d399a424ef32b0f9c4c57a1ddb98deb9

Selector SHA256 at generation 1:

6aa31d60e0105bd7bfa0b82c26fb46ec8cc3f9d0e1bdb3ac33e02429429761b4

Verifier R1.1 SHA256:

98d8a282a664ca0933c65f1023347790371ea43f731b60d013d1f9e200f058bd

Verifier result before publication:

PASS — 23/23 checks
Mock cold boot: COMPLETE
Execution model: ORDERED_SHARED_GLOBALS
Write authority: NONE

Cold-start cell after publication:

```python
import urllib.request
url = "https://raw.githubusercontent.com/hadrex83/ORFMOS/main/boot/ORFMOS_BOOTSTRAP_V0_1.py"
raw = urllib.request.urlopen(url, timeout=30).read()
exec(compile(raw, url, "exec"), globals(), globals())
```

Publication is not certified until the GitHub files are read back and a real cold boot succeeds.
