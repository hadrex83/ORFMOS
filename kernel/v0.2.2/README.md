# ORF Kernel v0.2.2

Provider-neutral ORF Kernel realization successor to v0.2.1.

## Realization change

v0.2.2 removes the duplicate physical copy from
`/content/.orf_kernel_source/modules/*` to `/content/.orf_kernel/modules/*`.

Manifest-pinned module bytes are SHA-256 verified at the source tree and executed
directly using the realization policy:

- `module_realization = VERIFIED_SOURCE_REFERENCE`
- `runtime_module_copy = false`

The six Kernel module payloads and the notebook entrypoint are byte-identical to
v0.2.1. The bootstrap and manifest encode the realization-policy change.

## Physical acceptance

Observed in Colab through ORFMOS BIOS v1.29:

- Kernel version: `0.2.2`
- Manifest SHA-256: `027c91e87f2bedd186837a811bb3a5ea8fabf5338131099897541a4a5978a496`
- 6/6 source modules verified
- 6/6 loaded modules verified
- 6/6 source-reference realizations verified
- `/content/.orf_kernel/modules` absent
- Kernel alive + READY
- Home READY
- Runtime monitor alive
- Durable selector/source/provider manifest unchanged during proof

Publication verification is not durable selector promotion. The v0.2.2 GitHub
commit must be cold-booted from GitHub before the durable Kernel selector is advanced.
