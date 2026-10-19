# Reproducible Development Environment

The development container and Nix shell read pinned tool versions from
[`toolchain-versions.json`](../toolchain-versions.json). CI loads the same
manifest through `.github/actions/tool-versions`; it also fails if the native
`rust-toolchain.toml` or Stellar CLI deployment manifest pins have drifted.
The Nix inputs still require a committed `flake.lock` to freeze nixpkgs and
rust-overlay revisions; generate and review that lockfile when Nix is available
before treating shell package versions as immutable.

## Pinned tool versions: single source of truth

Every pinned toolchain or tool version (Rust, Stellar CLI, `cargo-audit`,
`cargo-deny`, and any future pinned tool) has exactly one authoritative
location. All other references must either read from that location or be
validated against it; they must never restate a version independently.

| Tool | Source of truth | Dependent locations |
| --- | --- | --- |
| Rust channel | `rust-toolchain.toml` | `toolchain-versions.json` (`rust`), devcontainer, Nix shell, workflows |
| Stellar CLI | `toolchain-versions.json` (`stellar_cli`) | devcontainer, Nix shell, workflows, deployment manifests |
| `cargo-audit` | `toolchain-versions.json` (`cargo_audit`) | devcontainer, Nix shell, workflows |
| `cargo-deny` | `toolchain-versions.json` (`cargo_deny`) | devcontainer, Nix shell, workflows |

`toolchain-versions.json` is the shared manifest consumed by
`.github/actions/tool-versions`, the devcontainer, and the Nix shell;
`rust-toolchain.toml` remains authoritative for the Rust channel itself and is
mirrored into the manifest. `scripts/export-tool-versions.py` emits the
manifest for consumers that cannot read JSON directly.

### Adding a new pinned-version reference

1. Add or update the version in its source of truth (`toolchain-versions.json`,
   or `rust-toolchain.toml` for the Rust channel).
2. Make every consumer read from that source (via the
   `.github/actions/tool-versions` action, the devcontainer, or the Nix shell)
   instead of hardcoding a version string.
3. If a location genuinely cannot read the source, add it to the drift check
   so it is validated against the source of truth.
4. Run the toolchain drift check locally before opening a PR.

### CI drift check

The toolchain drift check (see the toolchain-drift-alert documentation and
`.github/actions/tool-versions`) fails when any dependent location diverges
from its source of truth, including a seeded drift introduced in a workflow,
script, or documentation reference. This enforces the convention above for
future contributors (see issue #1461).

## Start

- VS Code Dev Containers: open the repository in WSL2 or Docker Desktop and run
  **Dev Containers: Reopen in Container**.
- Nix: run `nix develop` from the repository root.
- Full local verification: run `scripts/verify-local.sh` in the container or a
  POSIX shell after installing the pinned tools.

The verification script runs formatting, Clippy, workspace tests, contract
build lints, the release WASM build and size budget, and the TLA+ simulation. It
expects `TLA_TOOLS_JAR` to point to the pinned `tla2tools.jar` when the default
`.cache/tla2tools.jar` path is not used.

## Windows and macOS

Windows contributors are supported through WSL2 with Docker Desktop's WSL
integration. Keep the checkout inside the WSL2 filesystem (for example,
`~/src/Ledgerlens-contract`) for reliable file watching and build performance.
Native Windows is not supported for the shell-based verification, deployment,
and operational scripts; they depend on POSIX shell behavior and Unix command
line tools. Run those scripts inside WSL2 or the devcontainer. macOS users can
use the Nix shell or the Linux devcontainer through Docker Desktop.