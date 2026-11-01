# MCP Migrations: Replication Package

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Code: MIT](https://img.shields.io/badge/code-MIT-green)
![Data: CC BY 4.0](https://img.shields.io/badge/data-CC%20BY%204.0-lightgrey)
![Reproduction: offline](https://img.shields.io/badge/reproduction-offline%2C%20no%20token-brightgreen)
![Tests: pytest](https://img.shields.io/badge/tests-pytest-informational)

Data, pipeline and scripts for a study of how GitHub projects that use the
Model Context Protocol (MCP) responded to the `2026-07-28` protocol revision,
which shipped with major version 2 (v2) of the official Python and TypeScript
SDKs. Every statistic and figure reported in the study is regenerated from the
released data by one script, and checked against the expected outputs.

| | |
|---|---|
| Repositories mined | 32,939 |
| Commits with an SDK, constraint or protocol signal | 292,203 |
| v2 repositories re-scanned at the application level | 4,577 |
| Labeled episodes (LLM pre-labels, verified by two coders) | 520 in round 1; 176 in round 2 + 60 blind episodes (Human only labeling) |
| Snapshot | mined 15–29 September 2026; re-scanned 14 October 2026 |

## Contents

- [MCP Migrations: Replication Package](#mcp-migrations-replication-package)
  - [Contents](#contents)
  - [Quick start for reviewers](#quick-start-for-reviewers)
  - [What the package contains](#what-the-package-contains)
  - [Where each result comes from](#where-each-result-comes-from)
  - [How the labels were produced](#how-the-labels-were-produced)
  - [Running the pipeline from scratch](#running-the-pipeline-from-scratch)
  - [Tests and checks](#tests-and-checks)
  - [Notes and limitations](#notes-and-limitations)
  - [Citing and license](#citing-and-license)

## Quick start for reviewers

Requires Python 3.11 or later. No GitHub access or token is needed: the
collection and mining stages are already done, and their outputs are in
`data/*.tar.gz`.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,paper]"
scripts/reproduce.sh
```

With [uv](https://docs.astral.sh/uv/), `uv sync --extra dev --extra paper`
followed by `uv run scripts/reproduce.sh` does the same.

The script unpacks the data, rebuilds the episodes from the mined commits,
recomputes every statistic and figure, and compares them with
`results/expected/`. It takes about 20 minutes on a laptop, most of it the
1,000-resample bootstraps of the time-to-event analyses, and ends with:

```
reproduced: every statistic and every number matches results/expected/
```

Outputs go to `results/`:

| File | What it holds |
|---|---|
| `results/summary.json` | Every statistic, as JSON |
| `results/numbers.tex` | The same statistics as LaTeX macros, one per reported number |
| `results/figures/*.pdf` | Every data figure |

## What the package contains

| Path | What it is |
|---|---|
| `src/mcp_migration/` | The pipeline: collection, mining, episode extraction, statistics, figures, and the labeling app |
| `tests/` | Unit tests, including a synthetic Git repository |
| `scripts/reproduce.sh` | Regenerates everything and checks it against `results/expected/` |
| `scripts/verify.py` | The comparison step that `reproduce.sh` runs last |
| `config/queries.toml` | The 12 GitHub search queries |
| `data/mined.tar.gz` (45 MB) | Everything mined: metadata, signal commits, HEAD states, harvest outcomes |
| `data/search-hits.tar.gz` (7 MB) | Raw GitHub search hits, per query |
| `data/ts-scans.tar.gz` (5 MB) | Application-level scans of the v2 repositories, the TypeScript mining pass, and the manual audits of protocol support; unpacks to `data/ts/` |
| `data/external/mcpcorpus_repos.txt` | Repository list derived from MCPCorpus, the subset selected independently of the outcome |
| `data/labeling/round<N>/` | Each labeling round: the draw, LLM pre-labels, both coders' sheets, the adjudicated sheet ([layout](data/labeling/README.md)) |
| `data/processed/qualitative.json` | Coded developer text: ceiling commits and breakage issues, with evidence |
| `docs/codebook.md` | The labeling codebook, including adjudication rules R1–R9 |
| `docs/llm-labeling/` | The LLM-assisted labeling protocol, the prompt for each round and the prompt changelog |
| `results/expected/` | The expected outputs that `reproduce.sh` checks against |

[`data/README.md`](data/README.md) documents every data file and its fields.

## Where each result comes from

Keys refer to `results/summary.json`; figures are in `results/figures/`. The
code for each analysis is in `src/mcp_migration/report/`: `measurement.py` for
responses, deferral and protocol support, `labels.py` for precision and
agreement, `stats.py` for the summary and the LaTeX macros.

| Result | Keys | Figure |
|---|---|---|
| Corpus construction | `n_search_queries`, `n_seed_repos`, `n_resolved_repos`, `n_clone_candidates`, `exclusion`, `harvest`, `n_mined_repos`, `n_signal_commits` | |
| Responses to the revision (v2 adoption, version ceilings) | `measurement.responses`, `measurement.responses_corpus` | |
| What developers wrote | `measurement.pin_wording`, `measurement.issue_themes`, `coded_pins`, `coded_pins_post` | |
| Time to v2 adoption after a ceiling, primary comparison | `measurement.deferral` | `deferral.pdf` |
| Design variants of that comparison | `measurement.deferral_*` (one block per variant) | `deferral-forest.pdf` (selection), `deferral-forest-full.pdf` (all variants) |
| Copies of one codebase | `measurement.copies` | |
| Protocol support and feature markers | `measurement.protocol_app*`, `measurement.legacy_audit`, `measurement.audit`, `measurement.holdout`, `measurement.feature_check`, `measurement.upgrade_claims_manual` | `protocol-support.pdf` |
| History reconstruction check | `measurement.history_validation` | |
| Detector precision and coder agreement | `labels` | |
| Episodes by kind, end state and authorship | `episode_kinds`, `head_eras`, `migration_end_states`, `revisions_added` | `episodes-by-kind.pdf`, `kind-by-era.pdf`, `migration-end-states.pdf`, `revision-adoption.pdf`, `author-kind-share.pdf` |
| Technical lag | `technical_lag`, `technical_lag_repos`, `technical_lag_all` | `technical-lag.pdf` |
| Episode-boundary sensitivity, size cap | `gap_sensitivity`, `repo_size` | |

Each design variant of the time-to-adoption comparison changes one choice
(timing, event definition, sample or control selection). The variants are
defined in the docstring of `deferral_from_commits` in `measurement.py` and
listed in `FOREST_ROWS` in `figures.py`.

## How the labels were produced

Labeling is LLM-assisted and human-verified:

1. **Draw.** `mcp-migration sample` draws up to 15 episodes per stratum, where a
   stratum is an episode kind and the repository's SDK state at HEAD.
2. **Pre-label.** Claude Opus 5.5, run in Claude Code, pre-labels each episode
   under the codebook. The prompts are in `docs/llm-labeling/`.
3. **Verify.** Two coders verify every label independently in a local web app
   that hides the detector's output until the coder has judged the episode.
   From round 2, a blind subset of 60 episodes is coded without pre-labels.
4. **Adjudicate.** Disagreements are resolved under the written rules R1–R9 in
   the codebook, into `round<N>/adjudicated.csv`.

The first round shaped how episodes are built, so detector precision is
measured on a second round drawn after those changes, excluding round 1's
episodes. To compute agreement and precision for a round:

```bash
mcp-migration labels data/labeling/round1/coderA.csv data/labeling/round1/coderB.csv \
  --prelabels data/labeling/round1/llm/coderLLM.csv \
  --adjudicated data/labeling/round1/adjudicated.csv
```

`--prelabels` reports the share of pre-labels each coder kept, and `--blind`
reports kappa on the blind subset. Precision is weighted by each stratum's
share of the episodes, with a Wilson interval at the matching effective sample
size (`src/mcp_migration/report/labels.py`). Before adjudication, an episode
counts as genuine only when both coders said `yes`, and split episodes are
listed under `split_episodes`.

To open the labeling app, install `pip install -e ".[label]"` and run
`mcp-migration label --coder A --round 2`.

## Running the pipeline from scratch

The released data is a snapshot. Re-running collection queries GitHub as it is
today, so counts will differ: repositories are deleted and histories grow. Each
stage reads the previous one's output:

```bash
export GITHUB_TOKENS=...                    # one or more tokens, comma-separated
mcp-migration search                        # GitHub search      -> data/raw/search/
mcp-migration seed data/external/* --include-search-hits   #     -> data/interim/repos.txt
mcp-migration metadata                      # GraphQL metadata   -> data/interim/repo_meta.jsonl
mcp-migration filter                        # inclusion criteria -> data/interim/repos_to_clone.txt
mcp-migration harvest --budget 1800         # clone, mine, delete -> data/interim/{commits,heads}/
mcp-migration episodes                      # -> data/processed/episodes.jsonl
mcp-migration stats --out results/summary.json --tex results/numbers.tex
mcp-migration figures --out-dir results/figures --summary results/summary.json
```

`harvest` keeps one clone on disk per worker, so a full run needs about as much
disk as the largest repositories being mined at once, not the 1.5 TB of the
whole corpus. `--prefilter` lets `git log -G` choose the commits worth diffing;
it yields the same records and is faster on long histories.

## Tests and checks

```bash
pytest              # unit tests, including a synthetic Git repository
ruff check src tests
mypy src/mcp_migration
python scripts/verify.py   # compare results/ with results/expected/
```

## Notes and limitations

- **Snapshot.** Most repositories were mined on 15–16 September 2026 and the
  rest by 29 September. The application-level re-scan ran on 14 October 2026.
- **Mining budget.** A 30-minute budget per repository was introduced part way
  through the harvest. Repositories that exceeded it are listed, with reasons,
  in `data/interim/harvest_outcomes.jsonl` (inside `mined.tar.gz`).
- **Signals are lexical.** Version constraints are matched on the package name
  `mcp` with optional extras; the ceiling pattern allows other text before the
  `<2` bound. Exact pins, compatible-release ranges on 1.x and lockfiles are
  not read. The mined records store signal counts, not lines, so changing a
  pattern requires mining again.
- **Personal data.** No author names or e-mail addresses are stored, only
  whether an author is a bot, an AI agent (by commit trailer) or neither.
- **MCPCorpus.** Only the repository names derived from it are redistributed,
  not the corpus itself.

## Citing and license

`CITATION.cff` has the citation metadata. The code (everything outside `data/`
and `results/`) is released under the MIT License (`LICENSE`); the data
(`data/` and `results/`) under Creative Commons Attribution 4.0 International
(`data/LICENSE`). Commit messages, issue excerpts and repository names remain
the work of their authors.
