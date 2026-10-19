# Running Tests with cargo-nextest

CI runs the unit-test stage with [cargo-nextest](https://nexte.st) (issue #1223).
Nextest runs every test in its own process, in parallel across binaries, and
produces JUnit output that CI uses for partitioning and flaky-test reporting.

## Install

```bash
cargo install cargo-nextest --version 0.9.87 --locked
# or a prebuilt binary:
curl -LsSf https://get.nexte.st/0.9.87/linux | tar zxf - -C ~/.cargo/bin
```

`cargo test` keeps working; nextest is faster for the full suite and gives
better subset selection.

## Running subsets locally

```bash
# Whole workspace (local `default` profile: fail fast, no retries)
cargo nextest run --workspace

# One crate
cargo nextest run -p ledgerlens-score

# Tests whose name contains a substring
cargo nextest run -p ledgerlens-score heartbeat

# One test module, using a filterset expression
cargo nextest run -p ledgerlens-score -E 'test(/^test_governance_chain::/)'

# Everything except slow adversarial suites
cargo nextest run --workspace -E 'not test(/adversarial/)'

# Reproduce one CI partition exactly (see "Partitioning" below)
cargo nextest list --workspace --message-format json > target/list.json
python3 tools/ci/partition_tests.py --list target/list.json --shards 4 --index 2 > target/filter.txt
cargo nextest run --workspace -E "$(cat target/filter.txt)"

# Use the CI or nightly profile
cargo nextest run --workspace --profile ci
```

Filterset syntax is documented at <https://nexte.st/docs/filtersets/>.

## Profiles (`.config/nextest.toml`)

| Profile | Used by | Timeouts | Retries | Output |
|---|---|---|---|---|
| `default` | local runs | slow after 30s, killed after 2 min | none | failures only, fail fast |
| `ci` | PR / main CI | slow after 60s, killed after 5 min | none | JUnit at `target/nextest/ci/junit.xml`, no fail fast |
| `nightly` | `nightly-tests.yml` | slow after 120s, killed after 20 min | none | JUnit with full output |

**Retries are allowed only for network-dependent tests**, identified by a test
name segment starting with `network_` (for example `mod::network_fetch_snapshot`).
No other test is ever retried. If you add a test that genuinely needs the
network, name it accordingly; deterministic tests must not use that prefix.

## Flaky and slow test reporting

A test that fails and then passes on retry is recorded by nextest as a
`<flakyFailure>` in the JUnit report. The `Flaky and slow test report` CI job
(`tools/ci/nextest_report.py --fail-on-flaky`) lists every such test, emits a
warning annotation and **fails**, so a retry-pass is reported as flaky, never
as green. The job also lists the slowest tests and uploads `test-report.json`
(retained 90 days) for trend tracking; the nightly workflow does the same for
the full suite.

## Partitioning

The `Unit tests` job runs as four parallel partitions. Each partition:

1. downloads the JUnit reports of the latest successful run on `main`;
2. runs `tools/ci/partition_tests.py`, which assigns every current test to a
   shard with a longest-processing-time-first greedy algorithm using those
   historical durations (tests with no history are weighted with the median);
3. runs only its shard via a nextest filterset.

Every listed test lands in exactly one shard, so new tests are never skipped.
When no history is available (first run, expired artifacts) the split degrades
to an even count-based split.

## Doctests and benches

Nextest does not run doctests. The `Doctests and benches` CI job runs
`cargo test --workspace --doc` and `cargo test --workspace --benches`, which
executes each Criterion benchmark once in test mode so benches keep compiling
and running. Full benchmark measurements run nightly in `nightly-tests.yml`.

## Workspace member → CI job coverage

Every member listed in the workspace `Cargo.toml` must have its tests executed
by at least one required CI job (issue #1459). The table below is the
authoritative mapping; it is verified by the structural check described in the
next section, which fails CI when a member is added without a verified
execution path.

| Workspace member | Kind | CI job(s) that run its tests |
|---|---|---|
| `ledgerlens-score` | contract | `Unit tests` (partitioned nextest), `Doctests and benches` |
| `ledgerlens-registry` | contract | `Unit tests` (partitioned nextest), `Doctests and benches` |
| `ledgerlens-governance` | contract | `Unit tests` (partitioned nextest), `Doctests and benches` |
| `reference-provider` | example contract | `Unit tests` (partitioned nextest), `Doctests and benches` |
| `mock-amm` | mock contract | `Unit tests` (partitioned nextest), `Doctests and benches` |
| `mock-lending` | mock contract | `Unit tests` (partitioned nextest), `Doctests and benches` |
| `examples/*` (each example crate) | example | `Unit tests` (partitioned nextest), `Doctests and benches` |
| `tools/*` (each tool crate) | tool | `Unit tests` (partitioned nextest), `Doctests and benches` |
| `tests/*` (integration test crates) | test | `Unit tests` (partitioned nextest), `Doctests and benches` |

Notes:

- The `Unit tests` job runs `cargo nextest run --workspace`, so every member
  with at least one test binary is covered by the partitioned run. The
  partitioning step assigns every listed test to exactly one shard, so no
  member's tests are dropped.
- The `Doctests and benches` job runs `cargo test --workspace --doc` and
  `cargo test --workspace --benches`, covering doctests and bench-mode tests
  that nextest does not execute.
- When you add a member, add a row here **and** ensure it is picked up by the
  workspace-wide jobs above (or add an explicit job and register it in the
  check's allow-list).

## Structural check: workspace members must have a CI execution path

`tools/ci/check_workspace_ci_coverage.py` (run by the `Workspace CI coverage`
job in `.github/workflows/ci.yml`) enforces the invariant:

1. It reads the workspace members from `Cargo.toml` (including globs such as
   `examples/*` and `tools/*`, expanded on disk).
2. It parses `.github/workflows/ci.yml` and collects the set of members whose
   tests are actually executed — either via a workspace-wide command
   (`--workspace`) or an explicit `-p <member>` / `--package <member>` in a
   required job.
3. It cross-references the committed table above (`docs/testing.md`) to ensure
   every member has a documented job mapping.
4. It **fails** if any workspace member has no verified execution path, or if a
   row in the table references a member that no longer exists.

This makes the gap impossible to reintroduce silently: adding a crate to the
workspace without wiring its tests into a required CI job (and documenting it
here) turns the `Workspace CI coverage` job red.

## Measured impact

Baseline (`cargo test --workspace` single job on `main`, last three runs
before this change): 12.2 min, 10.9 min, 13.2 min, median **12.2 min**. The
partitioned stage's wall clock is recorded in the PR that introduced it and
tracked afterwards by the `CI metrics` workflow ([ci-performance.md](ci-performance.md)).
