# ORF Kernel v0.2.1

Portable ORF Kernel publication boundary.

- Kernel source transport is not embedded.
- BIOS resolves the selected source into `ORF_KERNEL_SOURCE_ROOT`.
- Manifest verifies every ordered module by SHA-256.
- Live heartbeat is local shared runtime state.
- Resource hydration uses logical ORF resource refs.
- Persistence uses an optional BIOS persistence hook with local fallback.
- No provider authentication, provider APIs, provider-specific file IDs, or publication APIs exist inside the Kernel package.

Manifest SHA256: `30f39ba016d0f5d0f3f0cc7903d1474611896808d9af29ca15e0f6cb0a454a54`

Patch v0.2.1: protected signing descriptor remains V0_1-compatible while transport source fields are provider-neutral.
