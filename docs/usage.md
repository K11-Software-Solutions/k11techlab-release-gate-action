# Usage guide

- [Quick start: JUnit only](#quick-start-junit-only)
- [Bringing evidence from other jobs](#bringing-evidence-from-other-jobs)
- [Full pipeline with the K11 tools](#full-pipeline-with-the-k11-tools)
- [Writing the release policy](#writing-the-release-policy)
- [Change-aware gating](#change-aware-gating)
- [Sign-off when a person is needed](#sign-off-when-a-person-is-needed)
- [Using the outputs](#using-the-outputs)
- [Monorepos](#monorepos)
- [Troubleshooting](#troubleshooting)
- [Upgrading](#upgrading)

## Quick start: JUnit only

You don't need any K11 tool to start: any test runner that writes JUnit XML is evidence.

**1. Add a policy** at `.qa-mcp/release-policy.yaml`. The built-in default requires API functional test evidence, so a JUnit-only
project must say what it requires:

```yaml
name: Release policy
required: [junit]            # evidence that must be present on every pull request
max_age_hours: 24            # older evidence is flagged as stale
approvers: ["@your-team-lead"]
```

**2. Add the workflow** `.github/workflows/release-gate.yml`:

```yaml
name: Release gate
on: pull_request

permissions:
  contents: read
  pull-requests: write                     # for the PR comment

jobs:
  test-and-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt pytest
      - name: Tests
        run: pytest --junitxml=test-results/junit.xml
        continue-on-error: true            # let the gate decide and explain
      - uses: K11-Software-Solutions/k11techlab-release-gate-action@v1
```

JUnit files are found at `test-results/**/*.xml`, `**/surefire-reports/TEST-*.xml` and `junit*.xml`. Maven, Gradle, Jest
(`jest-junit`), Playwright and most runners can write one of these.

**3. Open a pull request.** You get one comment on it, updated on every push:

- ✅ **ship**: required evidence present, nothing failing;
- 🟡 **ship with conditions**: e.g. stale evidence, healed locators awaiting approval;
- 🟠 **needs a person**: e.g. a contract change breaks a known consumer, a performance regression; the comment names the approvers;
- 🔴 **block**: e.g. failed tests, missing required evidence, critical security findings.

## Bringing evidence from other jobs

The gate reads files on its runner. When tests run in other jobs, upload each report and download it **to the path the policy
looks in**. A plain `actions/download-artifact` with no arguments puts every artifact in a folder named after it, which the
default policy won't find.

In the test job:

```yaml
      - run: k11-api-functional-qa-mcp run --env ci --fail-on never
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: api-test-report
          path: .qa-mcp/api-test-report/
          include-hidden-files: true       # .qa-mcp is a hidden folder
```

In the gate job:

```yaml
      - uses: actions/download-artifact@v4
        with:
          name: api-test-report
          path: .qa-mcp/api-test-report    # where the default policy looks
```

Alternatively, download everything anywhere (`merge-multiple: true`) and point the policy at it. Kinds are recognised by content,
so a broad pattern is safe:

```yaml
# .qa-mcp/release-policy.yaml: setting `evidence` replaces the defaults, so list every kind you use
evidence:
  api_tests: ["reports/**/api-test-report.json"]
  integration: ["reports/**/integration-report.json"]
  junit: ["reports/**/*.xml"]
required: [api_tests, junit]
```

## Full pipeline with the K11 tools

Each tool writes its report to a known place; the gate reads them all. Run the tools with `--fail-on never` so they report
instead of failing, and let the gate apply one policy.

```yaml
name: Release gate
on: pull_request

permissions:
  contents: read
  pull-requests: write

jobs:
  api:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install k11-api-functional-qa-mcp k11-api-security-qa-mcp
      - run: docker compose up -d && ./scripts/wait-for-api.sh       # your service, on a test environment
      - run: k11-api-functional-qa-mcp run --env ci --fail-on never
      - run: k11-api-security-qa-mcp run --env ci --fail-on never
        env: { ALICE_TOKEN: "${{ secrets.TEST_ALICE_TOKEN }}", BOB_TOKEN: "${{ secrets.TEST_BOB_TOKEN }}" }
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: api-reports, path: .qa-mcp/, include-hidden-files: true }

  integration:
    runs-on: ubuntu-latest
    services:
      kafka: { image: apache/kafka:3.9.1, ports: ["9092:9092"] }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install "k11-integration-qa-mcp[kafka]"
      - run: k11-integration-qa-mcp run --env ci --fail-on never
        env: { KAFKA_BOOTSTRAP: "localhost:9092" }
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: integration-reports, path: .qa-mcp/, include-hidden-files: true }

  gate:
    needs: [api, integration]
    if: always()                           # decide even when a test job failed
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with: { pattern: "*-reports", merge-multiple: true, path: .qa-mcp }
      - uses: K11-Software-Solutions/k11techlab-release-gate-action@v1
```

Uploading the whole `.qa-mcp/` folder keeps the report paths (`api-test-report/api-test-report.json`, …), so downloading every
artifact back into `.qa-mcp` restores the default locations.

| Tool | Report the gate reads | Typical CI command |
|---|---|---|
| [API Functional QA](https://github.com/K11-Software-Solutions/k11techlab-api-functional-qa-mcp) | `.qa-mcp/api-test-report/api-test-report.json` | `k11-api-functional-qa-mcp run --env ci` |
| [API Contract QA](https://github.com/K11-Software-Solutions/k11techlab-api-contract-qa-mcp) | `.qa-mcp/contract-report/contract-report.json` | `k11-api-contract-qa-mcp contract-ci` |
| [API Security QA](https://github.com/K11-Software-Solutions/k11techlab-api-security-qa-mcp) | `.qa-mcp/security-report/security-report.json` | `k11-api-security-qa-mcp run --env ci` |
| [Integration QA](https://github.com/K11-Software-Solutions/k11techlab-integration-qa-mcp) | `.qa-mcp/integration-report/integration-report.json` | `k11-integration-qa-mcp run --env ci` |
| [Performance QA](https://github.com/K11-Software-Solutions/k11techlab-performance-qa-mcp) | `.qa-mcp/perf-report/perf-report.json` | `k11-performance-qa-mcp run --env ci` |
| [Playwright QA](https://github.com/K11-Software-Solutions/k11techlab-playwright-qa-mcp) / [Selenium QA](https://github.com/K11-Software-Solutions/k11techlab-selenium-qa-mcp) | `.qa-mcp/heal-report/heal-report.json` | `heal-ci` |
| [LLM Assure](https://github.com/K11-Software-Solutions/k11techlab-llm-assurance-toolkit) | `llm-assure-report/assessment.json` | `llm-assure run` |
| Any test runner | JUnit XML | — |

Each tool's README has its full CI instructions.

## Writing the release policy

Create a starter policy with comments for every setting:

```bash
pipx run k11-release-gate-mcp init          # writes .qa-mcp/release-policy.yaml
```

| Key | What it does | Default |
|---|---|---|
| `name` | Shown in the report | `Default release policy` |
| `required` | Evidence kinds that must always be present | `[api_tests]` |
| `evidence` | Glob patterns per kind. **Replaces** the defaults: list every kind you use | see [reference](reference.md#evidence-kinds-and-default-locations) |
| `max_age_hours` | Evidence older than this triggers `evidence.stale` | `24` |
| `approvers` | Named in the comment when the verdict is `needs_human` | none |
| `critical_consumers` | Consumer criticalities whose breakage blocks (API contracts) | `[critical, high]` |
| `triggers` | File patterns that make a kind required for a change. **Merged** with the defaults per kind | built-in |
| `rules` | Change a rule's outcome (`block`, `needs_human`, `conditional`, `info`) or turn it `off` | each rule's default |

Example:

```yaml
name: Payments release policy
required: [api_tests, security, junit]
max_age_hours: 12
approvers: ["@payments-leads", "@qa-lead"]
triggers:
  integration: ["services/ledger/**", "**/consumers/**", "asyncapi.yaml"]
rules:
  security.medium: block              # stricter than the default (conditional)
  perf.no_baseline: off               # we don't keep performance baselines yet
  contract.breaks_consumer: block     # any broken consumer blocks, not just critical ones
```

Unknown keys, kinds or rule names are rejected with a clear error, so a typo can't silently weaken the gate. The policy file's
SHA-256 is recorded in every decision.

Every rule and its default outcome: [reference](reference.md#rules).

## Change-aware gating

On pull requests (`base: auto`), the gate diffs the branch against the PR's base and requires the evidence those files trigger,
on top of `required`. The decision lists which files triggered each kind.

| You change… | Evidence becomes required |
|---|---|
| `openapi.yaml`, `*.proto`, `*.graphql`, `asyncapi.yaml` | API contract (+ integration for AsyncAPI) |
| routes, controllers, handlers, services, migrations, SQL | API functional tests |
| auth, permissions, middleware, dependency manifests, Dockerfile | Security |
| consumers, producers, listeners, jobs, workers, schedulers | Integration |
| migrations, SQL, repositories, caches, DB code | Performance |
| `.tsx`, `.vue`, components, pages, templates | UI tests |
| prompts, `llm/`, `agents/`, `rag/` | LLM red-team |

The full built-in pattern list is in [k11 Release Gate's `plan.py`](https://github.com/K11-Software-Solutions/k11techlab-release-gate-mcp/blob/main/src/k11_release_gate/plan.py).

- Turn it off with `base: none`; on tag releases, pass `base: origin/main` to require everything triggered since main.
- A shallow checkout is fine: the action fetches what it needs. `fetch-depth: 0` skips that fetch.

## Sign-off when a person is needed

`needs_human` means "don't block, but a named person must look". Turn it into a real approval with a GitHub environment that has
required reviewers (Settings → Environments):

```yaml
jobs:
  gate:
    runs-on: ubuntu-latest
    outputs:
      verdict: ${{ steps.gate.outputs.verdict }}
    steps:
      - uses: actions/checkout@v4
      - id: gate
        uses: K11-Software-Solutions/k11techlab-release-gate-action@v1
        with: { fail-on: block }           # block stops here; needs_human continues

  sign-off:
    needs: gate
    if: needs.gate.outputs.verdict == 'needs_human'
    runs-on: ubuntu-latest
    environment: release-approval          # waits for a required reviewer
    steps:
      - run: echo "Approved"
```

Full example: [`examples/release-tag.yml`](../examples/release-tag.yml).

## Using the outputs

```yaml
- id: gate
  uses: K11-Software-Solutions/k11techlab-release-gate-action@v1
  with: { fail-on: never }

- name: Label the pull request
  if: steps.gate.outputs.verdict == 'ship'
  run: gh pr edit ${{ github.event.pull_request.number }} --add-label release-ready
  env: { GH_TOKEN: "${{ github.token }}" }

- name: Notify
  if: steps.gate.outputs.blockers != '0'
  run: echo "${{ steps.gate.outputs.blockers }} blocker(s); see ${{ steps.gate.outputs.decision-markdown }}"
```

## Monorepos

Run one gate per service with `working-directory`, each with its own `.qa-mcp/` policy and evidence. Use `comment: false`: each
pull request has one gate comment, so several gates would overwrite each other. Each job's summary shows its decision.
See [`examples/monorepo.yml`](../examples/monorepo.yml).

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| **Blocked: "No API functional tests evidence found"** | The default policy requires `api_tests`. Add a policy with your own `required:` list. |
| Evidence not found although the job produced it | The report isn't at the path the policy looks in on the gate's runner. See [Bringing evidence from other jobs](#bringing-evidence-from-other-jobs). |
| `.qa-mcp` artifact is empty | `upload-artifact` skips hidden folders: add `include-hidden-files: true`. |
| "evidence is N h old" (`evidence.stale`) | Reports from an earlier run or committed to the repo. Regenerate them in this run, or raise `max_age_hours`. |
| Warning: "Couldn't comment on the pull request: HTTP 403" | Add `permissions: pull-requests: write`. On fork PRs the token is read-only: see [Limitations](design.md#limitations). |
| Warning: "Can't find a common commit with origin/…" | The base branch couldn't be fetched. The gate still decides, without change-triggered evidence. Check the branch name, or set `base: none`. |
| Two gate comments on one PR | Two workflows or matrix jobs with `comment: true`. Keep one, or use `comment: false`. |
| Error: invalid policy | The error names the bad key, kind or rule. Run `k11-release-gate-mcp rules` locally to list rules. |

Run the same decision locally:

```bash
pipx run k11-release-gate-mcp evaluate --base origin/main
```

## Upgrading

- `@v1` gets fixes and new gate versions within v1; pin `@v1.0.0` (or a commit SHA) to stay fixed.
- The gate version is the `version` input. Upgrading it can add evidence kinds and rules, so review the gate's changelog first.
