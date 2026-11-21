# Reference

Applies to **v1.0.0**, which runs `k11-release-gate-mcp` **0.4.0**.

- [Inputs](#inputs)
- [Outputs](#outputs)
- [Verdicts and `fail-on`](#verdicts-and-fail-on)
- [Evidence kinds and default locations](#evidence-kinds-and-default-locations)
- [Rules](#rules)
- [Files written](#files-written)
- [Permissions, network and environment](#permissions-network-and-environment)

## Inputs

| Input | Default | Description |
|---|---|---|
| `base` | `auto` | Ref to diff against, so the evidence the change triggers is required. `auto`: `origin/<PR base branch>` on pull requests, nothing on other events. `none`: off. Anything else is used as is (letters, digits, `.`, `/`, `_`, `-`; can't start with `-`). |
| `label` | | Release name in the report. Default: `PR #<number>`, else the tag on a tag push, else the 7-character commit SHA. |
| `policy` | | Path to the policy, relative to `working-directory`. Default `.qa-mcp/release-policy.yaml`, or the built-in policy if that file doesn't exist. A path that is given but missing is an error. |
| `fail-on` | `block` | `block`, `needs-human`, `conditions` or `never`. See [below](#verdicts-and-fail-on). |
| `working-directory` | `.` | Folder that holds `.qa-mcp/` and the evidence. Evidence globs are relative to it; the diff is always for the whole repository. |
| `comment` | `true` | Post the decision as a PR comment, updated in place. Ignored outside pull requests. |
| `upload` | `true` | Upload the decision files as the artifact `release-decision`. |
| `version` | `0.4.0` | `k11-release-gate-mcp` version installed from PyPI (exact). |
| `python-version` | `3.12` | Python for `actions/setup-python`. 3.10 or newer. |
| `github-token` | `${{ github.token }}` | Used only for the PR comment. |

## Outputs

| Output | Example | Description |
|---|---|---|
| `verdict` | `needs_human` | `ship`, `ship_with_conditions`, `needs_human` or `block` |
| `blockers` | `2` | Findings with outcome `block` |
| `needs-human` | `1` | Findings with outcome `needs_human` |
| `conditions` | `0` | Findings with outcome `conditional` |
| `decision-json` | `/home/runner/work/app/app/.qa-mcp/release-gate/release-decision.json` | Absolute path to the audit record |
| `decision-markdown` | `…/release-decision.md` | Absolute path to the report used for the comment and the job summary |

The gate CLI also writes its own outputs to the same step (`needs_human`, `report`, `report_json`, with underscores). They still
work, but the hyphenated names above are the documented interface.

## Verdicts and `fail-on`

The verdict is the most severe outcome among all findings:

| Worst finding outcome | Verdict | Meaning |
|---|---|---|
| `block` | `block` | Don't release |
| `needs_human` | `needs_human` | A named person must look before release |
| `conditional` | `ship_with_conditions` | Release, and deal with the listed conditions |
| `info` or none | `ship` | Release |

| `fail-on` | The enforce step fails on |
|---|---|
| `block` | `block` |
| `needs-human` | `block`, `needs_human` |
| `conditions` | `block`, `needs_human`, `ship_with_conditions` |
| `never` | never (read the `verdict` output instead) |

An invalid `fail-on` value fails the enforce step with a message listing the valid ones.

## Evidence kinds and default locations

Kinds are recognised from each file's content. These are the default glob patterns (relative to `working-directory`);
a policy's `evidence:` key replaces them.

| Kind | Name in reports | Default patterns | Produced by |
|---|---|---|---|
| `api_tests` | API functional tests | `.qa-mcp/api-test-report/api-test-report.json` | k11 API Functional QA |
| `contract` | API contract | `.qa-mcp/contract-report/contract-report.json` | k11 API Contract QA |
| `ui_heal` | UI tests (self-healing) | `.qa-mcp/heal-report/heal-report.json` | k11 Playwright QA, k11 Selenium QA |
| `perf` | Performance (load tests) | `.qa-mcp/perf-report/perf-report.json` | k11 Performance QA |
| `security` | Security (API tests and scanners) | `.qa-mcp/security-report/security-report.json` | k11 API Security QA |
| `integration` | Integration (messaging, jobs, databases) | `.qa-mcp/integration-report/integration-report.json` | k11 Integration QA |
| `llm` | LLM red-team | `llm-assure-report/assessment.json`, `.qa-mcp/llm-assure/assessment.json` | LLM Assure |
| `junit` | Test suites (JUnit) | `test-results/**/*.xml`, `**/surefire-reports/TEST-*.xml`, `junit*.xml` | any test runner |

The built-in policy requires `api_tests` only, with `max_age_hours: 24`.

## Rules

37 rules, each with a default outcome that a policy can change (`rules: { <id>: block | needs_human | conditional | info | off }`).

| Rule | Default | Fires when |
|---|---|---|
| `evidence.missing` | block | Required (or change-triggered) evidence isn't found |
| `evidence.stale` | conditional | Evidence is older than `max_age_hours` |
| `evidence.unreadable` | needs_human | An evidence file can't be parsed |
| `api.server_error` | block | A 5xx response in an API test step |
| `api.flow_failed` | block | An API test flow failed |
| `api.flow_not_run` | needs_human | API flows were refused (writes not allowed) or errored |
| `contract.breaks_critical_consumer` | block | A breaking change affects a consumer of `critical_consumers` criticality |
| `contract.breaks_consumer` | needs_human | A breaking change affects another known consumer |
| `contract.escalation` | needs_human | The contract tool asked for a person (e.g. a consumer it couldn't assess) |
| `contract.breaking_unused` | conditional | Breaking changes with no known consumer |
| `ui.real_failures` | block | UI tests failed for reasons other than locators |
| `ui.unresolved_locators` | block | Broken locators that weren't safely healed |
| `ui.healed` | conditional | Locators were healed and verified; the heal PR needs approval |
| `ui.suggested` | conditional | Heals were suggested in a dry run but not applied |
| `llm.critical` | block | Critical LLM security finding |
| `llm.high` | block | High-severity LLM security finding |
| `llm.medium` | conditional | Medium-severity LLM security finding |
| `llm.low` | info | Low-severity LLM security finding |
| `llm.inconclusive` | needs_human | LLM probes that need review or errored |
| `perf.not_run` | needs_human | The load test was refused by guardrails or didn't start |
| `perf.aborted` | block | The load test stopped because too many requests failed |
| `perf.server_errors` | block | Server errors (5xx) under load |
| `perf.slo_breached` | block | An endpoint missed a latency, error-rate or throughput SLO |
| `perf.regression` | needs_human | Significantly slower (or more errors) than the baseline |
| `perf.no_baseline` | info | No baseline, so regressions can't be detected |
| `perf.insufficient_samples` | info | Too few requests to compare some endpoints with the baseline |
| `security.not_run` | needs_human | The security run was refused or failed |
| `security.critical` | block | Critical finding: API test, or new scanner finding |
| `security.high` | block | High-severity finding: API test, or new scanner finding |
| `security.acceptance_expired` | needs_human | An accepted security risk passed its expiry date |
| `security.medium` | conditional | Medium-severity security finding |
| `security.inconclusive` | info | Security tests that were inconclusive or not run |
| `integration.not_run` | needs_human | No integration flows ran |
| `integration.failed` | block | An integration flow failed (event, consumer, dead-letter queue, job or database) |
| `integration.flows_not_run` | needs_human | Integration flows were refused (writes not allowed, protected topic) or errored |
| `junit.failures` | block | Failures or errors in a JUnit report |
| `junit.skipped` | info | Skipped tests |

List them with the outcomes your policy gives: `k11-release-gate-mcp rules`.

## Files written

In `<working-directory>/.qa-mcp/release-gate/`:

| File | Content |
|---|---|
| `release-decision.md` | The report: verdict, findings grouped by outcome with their evidence, the evidence table (kind, file, result, age, SHA-256 prefix), what wasn't tested, the plan when `base` is set. Used for the comment and the job summary. |
| `release-decision.json` | The audit record: verdict, counts, every finding (rule, outcome, message, details, evidence path), every evidence file with its full SHA-256, age and facts, the policy's name, source and SHA-256, the plan (changed files, needed kinds and why), commit, label and time. |

Add `.qa-mcp/release-gate/` to `.gitignore`; the artifact keeps the decision.

## Permissions, network and environment

| | |
|---|---|
| **Token permissions** | `contents: read`; `pull-requests: write` for the comment |
| **Network** | `pypi.org` / `files.pythonhosted.org` (install), the GitHub API (`GITHUB_API_URL`, for the comment), and GitHub's artifact service |
| **Runners** | GitHub-hosted Linux, Windows and macOS (tested); self-hosted with git, bash and network access to PyPI |
| **Git** | Fetches the base branch, and unshallows a shallow clone when needed to find the common commit |
| **Comment identity** | The account that owns the token: `github-actions[bot]` with the default token |
| **Marker** | The comment body starts with `<!-- k11-release-gate -->`; don't remove it, or the next run posts a new comment |
