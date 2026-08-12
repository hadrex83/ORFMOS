# ORFMOS Cloud BIOS v0.1.61-R6

Immutable provider publication of the certified ORFMOS Cloud BIOS R6 source set.

## Authority contract

BIOS authority is the verified artifact path + SHA-256 chain, not the hosting provider. This GitHub tree was derived from the live Drive authority without modifying the R6 module sources.

- BIOS version: `0.1.61-R6`
- Revision: `R6_SHUTDOWN_CLIENT_HANDOFF_ACK`
- Execution model: `ORDERED_SHARED_GLOBALS`
- Ordered modules: `5`
- Publication manifest SHA-256: `18c74294439d84de07893fb029bdf154e38b8e9cd931e2a25965645ea8cc8895`
- Source Drive manifest SHA-256: `c1d5b5a2f4819d2d136695171008c01ee4ad3ad1b07de3c7aa3ff48bb8e2090f`
- Source Drive manifest file ID: `1izhdO9SjuSk4BuJNnyCMGqGgNeOPEZSY`

## Verification semantics

A provider copy is selectable only after every object is read back from that provider and its SHA-256 matches the publication manifest. GitHub publication alone does **not** certify GitHub BIOS boot authority. Certification requires an observed BIOS boot using the GitHub source selection path.

Historical/versioned artifacts are immutable. Presentation or boot-front-door fixes advance lineage rather than modifying this R6 tree in place.
