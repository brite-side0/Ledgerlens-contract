#![forbid(unsafe_code)]

use anyhow::{bail, Context, Result};
use invocation_fuzzer::{
    audit_corpus, load_campaign, load_corpus, replay_campaign, run_fuzz_with_abi, DEFAULT_CASES,
    MAX_CASES,
};
use std::env;
use std::path::{Path, PathBuf};

fn usage() -> &'static str {
    "Usage:
    cargo run -p invocation-fuzzer --locked -- smoke [--seed N] [--cases N] [--corpus-dir PATH] [--abi-schema PATH]
  cargo run -p invocation-fuzzer --locked -- replay PATH
  cargo run -p invocation-fuzzer --locked -- corpus-audit [--corpus-dir PATH] [--require-provenance]

smoke replays every regression fixture before running a bounded deterministic
corpus-guided campaign. replay executes the selected fixture twice and rejects
any observable mismatch. corpus-audit prints each committed seed's provenance
note and, with --require-provenance, fails when a seed lacks one (see issue
#1460)."
}

fn parse_number<T>(value: Option<String>, flag: &str) -> Result<T>
where
    T: std::str::FromStr,
    T::Err: std::fmt::Display,
{
    value
        .with_context(|| format!("missing value for {flag}"))?
        .parse()
        .map_err(|error| anyhow::anyhow!("invalid {flag}: {error}"))
}

fn smoke(mut args: impl Iterator<Item = String>) -> Result<()> {
    let mut seed = 0x6390_c0de_u64;
    let mut cases = DEFAULT_CASES;
    let mut corpus_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("corpus");
    let mut abi_schema_path = None;

    while let Some(flag) = args.next() {
        match flag.as_str() {
            "--seed" => seed = parse_number(args.next(), "--seed")?,
            "--cases" => cases = parse_number(args.next(), "--cases")?,
            "--corpus-dir" => {
                corpus_dir = PathBuf::from(args.next().context("missing value for --corpus-dir")?)
            }
            "--abi-schema" => {
                abi_schema_path = Some(PathBuf::from(
                    args.next().context("missing value for --abi-schema")?,
                ))
            }
            _ => bail!("unknown smoke option {flag}\n\n{}", usage()),
        }
    }
    if cases > MAX_CASES {
        bail!("--cases cannot exceed {MAX_CASES}");
    }

    let corpus = load_corpus(&corpus_dir)?;
    let summary = run_fuzz_with_abi(corpus, seed, cases, abi_schema_path.as_deref())?;
    println!(
        "PASS seed={} regression_cases={} generated_cases={} retained_cases={} behavior_signatures={}",
        summary.seed,
        summary.regression_cases,
        summary.generated_cases,
        summary.retained_cases,
        summary.behavior_signatures
    );
    println!(
        "MAX cpu_instructions={} memory_bytes={} encoded_input_bytes={} operations={} raw_arguments={} logical_score_reads={} logical_score_writes={} contract_events={}",
        summary.max_resources.cpu_instructions,
        summary.max_resources.memory_bytes,
        summary.max_resources.encoded_input_bytes,
        summary.max_resources.operations,
        summary.max_resources.raw_arguments,
        summary.max_resources.logical_score_reads,
        summary.max_resources.logical_score_writes,
        summary.max_resources.contract_events,
    );
    Ok(())
}

fn corpus_audit(mut args: impl Iterator<Item = String>) -> Result<()> {
    let mut corpus_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("corpus");
    let mut require_provenance = false;

    while let Some(flag) = args.next() {
        match flag.as_str() {
            "--corpus-dir" => {
                corpus_dir = PathBuf::from(args.next().context("missing value for --corpus-dir")?)
            }
            "--require-provenance" => require_provenance = true,
            _ => bail!("unknown corpus-audit option {flag}\n\n{}", usage()),
        }
    }

    let report = audit_corpus(&corpus_dir)?;
    for entry in &report.entries {
        match &entry.provenance {
            Some(note) => println!("OK   {}: {}", entry.name, note),
            None => println!("MISS {}: <no provenance note>", entry.name),
        }
    }
    println!(
        "corpus-audit seeds={} documented={} undocumented={}",
        report.entries.len(),
        report.documented,
        report.undocumented
    );

    if require_provenance && report.undocumented > 0 {
        bail!(
            "{} corpus seed(s) lack a provenance note; every new seed must carry a \
             co-located note explaining why it was added (issue #1460)",
            report.undocumented
        );
    }
    Ok(())
}

fn replay(path: &Path) -> Result<()> {
    let campaign = load_campaign(path)?;
    let report = replay_campaign(&campaign)?;
    println!("{}", serde_json::to_string_pretty(&report)?);
    println!("PASS deterministic replay: {}", path.display());
    Ok(())
}

fn main() -> Result<()> {
    let mut args = env::args().skip(1);
    match args.next().as_deref() {
        Some("smoke") => smoke(args),
        Some("replay") => {
            let path = args.next().context("replay requires a fixture path")?;
            if args.next().is_some() {
                bail!("replay accepts exactly one fixture path");
            }
            replay(Path::new(&path))
        }
        Some("corpus-audit") => corpus_audit(args),
        Some("-h" | "--help") => {
            println!("{}", usage());
            Ok(())
        }
        Some(command) => bail!("unknown command {command}\n\n{}", usage()),
        None => bail!("{}", usage()),
    }
}
