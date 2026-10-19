#!/usr/bin/env python3
"""Emit the shared toolchain manifest as GitHub Actions outputs.

`toolchain-versions.json` is the single source of truth for pinned tool
versions (see docs/development-environment.md). This script validates that
every dependent location in the repository agrees with the manifest and
fails on drift, then emits the manifest values as GitHub Actions outputs.

Reference: issue #1461.
"""

import json
from pathlib import Path
import re
import sys
import tomllib


REPO_ROOT = Path(__file__).resolve().parent.parent


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def _fail(message: str) -> None:
    raise SystemExit(f"toolchain drift: {message}")


def _expect_contains(rel_path: str, needle: str, label: str) -> None:
    contents = _read(rel_path)
    if needle not in contents:
        _fail(f"{rel_path} does not reference {label} ({needle!r})")


def _expect_regex(rel_path: str, pattern: str, expected: str, label: str) -> None:
    contents = _read(rel_path)
    matches = re.findall(pattern, contents, re.MULTILINE)
    if not matches:
        _fail(f"{rel_path} is missing a {label} pin")
    for match in matches:
        value = match if isinstance(match, str) else match[0]
        if value != expected:
            _fail(
                f"{rel_path} pins {label} {value}, expected {expected} "
                f"from toolchain-versions.json"
            )


def main() -> None:
    versions = json.loads(_read("toolchain-versions.json"))

    required_keys = ("contract_rust", "stellar_cli", "cargo_audit", "cargo_deny")
    for key in required_keys:
        if key not in versions:
            _fail(f"toolchain-versions.json is missing required key {key!r}")

    rust_channel = tomllib.loads(_read("rust-toolchain.toml"))["toolchain"]["channel"].strip()
    if rust_channel != versions["contract_rust"]:
        _fail(
            f"rust-toolchain.toml pins {rust_channel}, but toolchain-versions.json "
            f"pins {versions['contract_rust']}"
        )

    for manifest in sorted((REPO_ROOT / "deploy/manifests").glob("*.env")):
        rel = manifest.relative_to(REPO_ROOT).as_posix()
        contents = manifest.read_text(encoding="utf-8")
        match = re.search(r'^EXPECTED_STELLAR_CLI_VERSION="([^"]+)"$', contents, re.MULTILINE)
        if not match:
            _fail(f"{rel} is missing EXPECTED_STELLAR_CLI_VERSION")
        if match.group(1) != versions["stellar_cli"]:
            _fail(
                f"{rel} pins Stellar CLI {match.group(1)}, expected "
                f"{versions['stellar_cli']} from toolchain-versions.json"
            )

    # Workflows: Rust toolchain channel.
    for workflow in sorted((REPO_ROOT / ".github/workflows").glob("*.yml")):
        rel = workflow.relative_to(REPO_ROOT).as_posix()
        contents = workflow.read_text(encoding="utf-8")
        for match in re.finditer(r"toolchain:\s*['\"]?([^'\"\s]+)['\"]?", contents):
            value = match.group(1)
            if value != versions["contract_rust"]:
                _fail(
                    f"{rel} pins Rust toolchain {value}, expected "
                    f"{versions['contract_rust']} from toolchain-versions.json"
                )

    # Workflows: Stellar CLI version pins.
    for workflow in sorted((REPO_ROOT / ".github/workflows").glob("*.yml")):
        rel = workflow.relative_to(REPO_ROOT).as_posix()
        contents = workflow.read_text(encoding="utf-8")
        for match in re.finditer(r"STELLAR_CLI_VERSION:\s*['\"]?([^'\"\s]+)['\"]?", contents):
            value = match.group(1)
            if value != versions["stellar_cli"]:
                _fail(
                    f"{rel} pins Stellar CLI {value}, expected "
                    f"{versions['stellar_cli']} from toolchain-versions.json"
                )

    # Workflows: cargo-audit / cargo-deny version pins.
    for workflow in sorted((REPO_ROOT / ".github/workflows").glob("*.yml")):
        rel = workflow.relative_to(REPO_ROOT).as_posix()
        contents = workflow.read_text(encoding="utf-8")
        for match in re.finditer(r"cargo-audit@v?([0-9][^'\"\s]*)", contents):
            value = match.group(1)
            if value != versions["cargo_audit"]:
                _fail(
                    f"{rel} pins cargo-audit {value}, expected "
                    f"{versions['cargo_audit']} from toolchain-versions.json"
                )
        for match in re.finditer(r"cargo-deny@v?([0-9][^'\"\s]*)", contents):
            value = match.group(1)
            if value != versions["cargo_deny"]:
                _fail(
                    f"{rel} pins cargo-deny {value}, expected "
                    f"{versions['cargo_deny']} from toolchain-versions.json"
                )

    # Devcontainer pins.
    devcontainer = REPO_ROOT / ".devcontainer/devcontainer.json"
    if devcontainer.exists():
        rel = devcontainer.relative_to(REPO_ROOT).as_posix()
        contents = devcontainer.read_text(encoding="utf-8")
        for match in re.finditer(r"rust:([0-9][^'\"\s]*)", contents):
            value = match.group(1)
            if value != versions["contract_rust"]:
                _fail(
                    f"{rel} pins Rust {value}, expected "
                    f"{versions['contract_rust']} from toolchain-versions.json"
                )

    # Nix flake pins.
    flake = REPO_ROOT / "flake.nix"
    if flake.exists():
        rel = flake.relative_to(REPO_ROOT).as_posix()
        contents = flake.read_text(encoding="utf-8")
        for match in re.finditer(r'rustVersion\s*=\s*"([^"]+)"', contents):
            value = match.group(1)
            if value != versions["contract_rust"]:
                _fail(
                    f"{rel} pins Rust {value}, expected "
                    f"{versions['contract_rust']} from toolchain-versions.json"
                )

    # Scripts that invoke a pinned tool version directly.
    scripts_dir = REPO_ROOT / "scripts"
    if scripts_dir.exists():
        for script in sorted(scripts_dir.glob("*")):
            if not script.is_file() or script.name == Path(__file__).name:
                continue
            if script.suffix not in (".sh", ".py", ".bash"):
                continue
            rel = script.relative_to(REPO_ROOT).as_posix()
            contents = script.read_text(encoding="utf-8")
            for match in re.finditer(r"stellar-cli@v?([0-9][^'\"\s]*)", contents):
                value = match.group(1)
                if value != versions["stellar_cli"]:
                    _fail(
                        f"{rel} pins Stellar CLI {value}, expected "
                        f"{versions['stellar_cli']} from toolchain-versions.json"
                    )
            for match in re.finditer(r"cargo-audit@v?([0-9][^'\"\s]*)", contents):
                value = match.group(1)
                if value != versions["cargo_audit"]:
                    _fail(
                        f"{rel} pins cargo-audit {value}, expected "
                        f"{versions['cargo_audit']} from toolchain-versions.json"
                    )
            for match in re.finditer(r"cargo-deny@v?([0-9][^'\"\s]*)", contents):
                value = match.group(1)
                if value != versions["cargo_deny"]:
                    _fail(
                        f"{rel} pins cargo-deny {value}, expected "
                        f"{versions['cargo_deny']} from toolchain-versions.json"
                    )

    # Development-environment documentation must reference the manifest.
    docs = REPO_ROOT / "docs/development-environment.md"
    if docs.exists():
        rel = docs.relative_to(REPO_ROOT).as_posix()
        contents = docs.read_text(encoding="utf-8")
        if "toolchain-versions.json" not in contents:
            _fail(
                f"{rel} must reference toolchain-versions.json as the single "
                f"source of truth for pinned tool versions"
            )
        for key in required_keys:
            if versions[key] not in contents:
                _fail(
                    f"{rel} does not mention the pinned {key} value "
                    f"{versions[key]!r} from toolchain-versions.json"
                )

    for key, value in versions.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        print(f"toolchain drift check failed: {exc}", file=sys.stderr)
        raise SystemExit(1)