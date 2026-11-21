# k11 Release Gate Action

**Can this pull request ship?** One deterministic answer from your QA evidence, posted on the pull request:
**ship**, **ship with conditions**, **needs a named person**, or **block**, with every reason and the evidence file it came from.

The action runs [k11 Release Gate](https://github.com/K11-Software-Solutions/k11techlab-release-gate-mcp) after your tests.
It reads the reports they wrote, applies your written release policy, and works out from the diff which evidence
this change needs: change a Kafka consumer and integration tests become required; change auth code and security tests do.

```yaml
- uses: K11-Software-Solutions/k11techlab-release-gate-action@v1
```

## What you get on every pull request

```text
## Release gate: 🔴 Block — PR #42

2 blocker(s), 0 needing a person, 0 condition(s). Policy Default release policy. Commit c3169e665356.

### Blockers
- No API functional tests evidence found (evidence.missing)
- 4 integration flows failed (integration.failed, .qa-mcp/integration-report/integration-report.json)
  - An order reserves stock through the inventory consumer: the inventory consumer reserves all 3 (expect_message):
    message on orders.events: 0 of 1 matching message(s) within 10s; closest: $.qty: expected 3, got 1
  - The sku_totals batch job is safe to run twice: the total is still 2 (db): qty 2: expected 2, got 4

### Evidence
| Area | File | Result | Age | SHA-256 |
| Integration (messaging, jobs, databases) | .qa-mcp/integration-report/integration-report.json | 0/4 flows passed | 0.2 h | 9c781091cc8d |
```

- One comment per pull request, updated in place on every push
- The same report in the job summary, and `release-decision.json` (the audit record, with each evidence file's SHA-256) as an artifact
- The job fails at the verdict you choose (`fail-on`)

## Evidence it reads

Recognised by content, wherever your policy says to look:

| Evidence | Produced by |
|---|---|
| UI tests with self-healing | [Playwright QA](https://github.com/K11-Software-Solutions/k11techlab-playwright-qa-mcp), [Selenium QA](https://github.com/K11-Software-Solutions/k11techlab-selenium-qa-mcp) |
| API contract: which consumers a change breaks | [API Contract QA](https://github.com/K11-Software-Solutions/k11techlab-api-contract-qa-mcp) |
| API functional tests with database checks | [API Functional QA](https://github.com/K11-Software-Solutions/k11techlab-api-functional-qa-mcp) |
| Load tests against SLOs and a baseline | [Performance QA](https://github.com/K11-Software-Solutions/k11techlab-performance-qa-mcp) |
| OWASP API Top 10 tests and scanner SARIF | [API Security QA](https://github.com/K11-Software-Solutions/k11techlab-api-security-qa-mcp) |
| API, Kafka, batch job and database flows | [Integration QA](https://github.com/K11-Software-Solutions/k11techlab-integration-qa-mcp) |
| LLM red-team | [LLM Assure](https://github.com/K11-Software-Solutions/k11techlab-llm-assurance-toolkit) |
| Any JUnit XML | pytest, Maven Surefire, Gradle, Jest, Playwright, … |

You don't need all of them. With only JUnit files, it is already a policy-driven gate.

## Usage

```yaml
name: Release gate
on: pull_request

permissions:
  contents: read
  pull-requests: write          # for the comment

jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # ... your tests, writing their reports (JUnit, or the K11 tools' reports) ...

  gate:
    needs: tests
    if: always()                # decide even when tests failed: that's evidence too
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0        # optional: the action fetches what it needs from a shallow checkout
      - uses: actions/download-artifact@v4   # the reports your test jobs uploaded
      - uses: K11-Software-Solutions/k11techlab-release-gate-action@v1
        with:
          fail-on: block
```

More: [`examples/`](examples) (single job, tag releases with sign-off, monorepo).

## Inputs

| Input | Default | |
|---|---|---|
| `base` | `auto` | Diff against this ref so the evidence the change triggers is required. `auto` = the PR's base branch (none on push); `none` turns it off |
| `fail-on` | `block` | Fail the job at this verdict or worse: `block`, `needs-human`, `conditions`, `never` |
| `policy` | | Policy file; default `.qa-mcp/release-policy.yaml`, or built-in defaults |
| `label` | | Release name in the report; default `PR #n`, the tag, or the short commit |
| `working-directory` | `.` | Project folder (monorepos) |
| `comment` | `true` | Post and update the pull request comment |
| `upload` | `true` | Upload the decision as an artifact |
| `version` | `0.4.0` | k11-release-gate-mcp version from PyPI |
| `python-version` | `3.12` | |
| `github-token` | `github.token` | |

## Outputs

`verdict` (`ship`, `ship_with_conditions`, `needs_human`, `block`), `blockers`, `needs-human`, `conditions`,
`decision-json`, `decision-markdown`.

```yaml
- id: gate
  uses: K11-Software-Solutions/k11techlab-release-gate-action@v1
  with: { fail-on: never }
- if: steps.gate.outputs.verdict == 'needs_human'
  run: echo "Ask the approvers named in the policy to sign off"
```

## The release policy

`.qa-mcp/release-policy.yaml` says which evidence is required, how fresh it must be, who signs off, and what each
finding means. Start with `pipx run k11-release-gate-mcp init`. The same evidence and policy always give the same
verdict, so the decision holds up in an audit.

## Safety

- Reads reports; never calls your services, never changes code.
- Your evidence stays in your runner; the only network calls are to PyPI (install) and the GitHub API (the comment).
- Refs are validated before they reach git.

## Part of the K11 QA suite

Ten free MCP servers and a [Release Readiness Agent](https://github.com/K11-Software-Solutions/k11techlab-release-readiness-agent) for Claude Code,
by [K11 Software Solutions](https://k11softwaresolutions.com). MIT licensed.
