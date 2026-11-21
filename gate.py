"""Runs k11 Release Gate for the GitHub Action: evaluate, set outputs, write the job summary, comment on the PR.

`gate.py`            evaluate (never fails the step on the verdict; enforcement is a separate step,
                     so the artifact and the comment are always written first)
`gate.py --enforce`  exit 1 when VERDICT is at or worse than FAIL_ON
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ORDER = ["ship", "ship_with_conditions", "needs_human", "block"]
FAIL_AT = {"block": "block", "needs-human": "needs_human", "conditions": "ship_with_conditions", "never": None}
MARKER = "<!-- k11-release-gate -->"
REPORT_DIR = ".qa-mcp/release-gate"
REF = re.compile(r"^[\w./-]+$")


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")


def output(name: str, value: str) -> None:
    path = env("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")
    else:
        print(f"[output] {name}={value}")


def resolve_base() -> str | None:
    """'auto' -> origin/<PR base branch>, fetched (and history deepened) so `base...HEAD` works."""
    base = env("INPUT_BASE", "auto")
    if base.lower() == "none":
        return None
    if base.lower() == "auto":
        if not env("GH_BASE_REF"):
            return None  # a push: no base to compare with
        base = f"origin/{env('GH_BASE_REF')}"
    if not REF.match(base) or base.startswith("-"):
        sys.exit(f"::error::Invalid base ref: {base!r}")
    if base.startswith("origin/") and git("rev-parse", "--verify", "--quiet", base).returncode != 0:
        branch = base[len("origin/"):]
        git("fetch", "--no-tags", "--quiet", "origin", f"+refs/heads/{branch}:refs/remotes/{base}")
    if git("merge-base", base, "HEAD").returncode != 0 and git("rev-parse", "--is-shallow-repository").stdout.strip() == "true":
        print("Shallow checkout: fetching history to find where the branch started (use fetch-depth: 0 to skip this)")
        git("fetch", "--no-tags", "--quiet", "--unshallow", "origin")
        git("fetch", "--no-tags", "--quiet", "origin", f"+refs/heads/{base.split('/', 1)[-1]}:refs/remotes/{base}")
    if git("merge-base", base, "HEAD").returncode != 0:
        print(f"::warning::Can't find a common commit with {base}; evaluating without change-triggered evidence")
        return None
    return base


def default_label() -> str:
    if env("PR_NUMBER"):
        return f"PR #{env('PR_NUMBER')}"
    if env("GITHUB_REF_TYPE") == "tag":
        return env("GITHUB_REF_NAME")
    return env("GITHUB_SHA")[:7] or "local"


def comment(markdown: str) -> None:
    repo, pr, token = env("GITHUB_REPOSITORY"), env("PR_NUMBER"), env("GITHUB_TOKEN")
    if env("INPUT_COMMENT", "true").lower() != "true" or not (repo and pr and token):
        return
    api = env("GITHUB_API_URL", "https://api.github.com")
    head = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

    def call(method: str, url: str, body: dict | None = None):
        req = urllib.request.Request(url, method=method, headers=head,
                                     data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"null")

    body = {"body": f"{MARKER}\n{markdown}"}
    try:
        existing = None
        for page in range(1, 11):
            items = call("GET", f"{api}/repos/{repo}/issues/{pr}/comments?per_page=100&page={page}")
            existing = next((c for c in items if MARKER in (c.get("body") or "")), None)
            if existing or len(items) < 100:
                break
        if existing:
            call("PATCH", f"{api}/repos/{repo}/issues/comments/{existing['id']}", body)
        else:
            call("POST", f"{api}/repos/{repo}/issues/{pr}/comments", body)
    except urllib.error.HTTPError as e:
        hint = " (give the job `permissions: pull-requests: write`)" if e.code in (403, 404) else ""
        print(f"::warning::Couldn't comment on the pull request: HTTP {e.code}{hint}")
    except urllib.error.URLError as e:
        print(f"::warning::Couldn't comment on the pull request: {e.reason}")


def evaluate() -> None:
    cmd = ["k11-release-gate-mcp", "evaluate", "--fail-on", "never", "--report-dir", REPORT_DIR,
           "--label", env("INPUT_LABEL") or default_label()]
    if env("INPUT_POLICY"):
        cmd += ["--policy", env("INPUT_POLICY")]
    base = resolve_base()
    if base:
        cmd += ["--base", base]
    print("$ " + " ".join(cmd), flush=True)
    r = subprocess.run(cmd)
    out = Path(REPORT_DIR).resolve()
    js, md = out / "release-decision.json", out / "release-decision.md"
    if r.returncode != 0 or not js.is_file():
        sys.exit("::error::k11 Release Gate didn't produce a decision (see the log above)")
    d = json.loads(js.read_text("utf-8"))
    c = d.get("counts", {})
    output("verdict", d["verdict"])
    output("blockers", str(c.get("block", 0)))
    output("needs-human", str(c.get("needs_human", 0)))
    output("conditions", str(c.get("conditional", 0)))
    output("decision-json", str(js))
    output("decision-markdown", str(md))
    # the job summary is written by k11-release-gate-mcp itself
    text = md.read_text("utf-8") if md.is_file() else f"Release gate verdict: **{d['verdict']}**\n"
    comment(text)
    print(f"Verdict: {d['verdict']} ({c.get('block', 0)} blocker(s), {c.get('needs_human', 0)} needing a person, "
          f"{c.get('conditional', 0)} condition(s))")


def enforce() -> int:
    verdict, fail_on = env("VERDICT"), env("FAIL_ON", "block").lower()
    if fail_on not in FAIL_AT:
        print(f"::error::fail-on must be one of {', '.join(FAIL_AT)}; got {fail_on!r}")
        return 1
    if verdict not in ORDER:
        print("::error::No verdict: the evaluation step failed")
        return 1
    threshold = FAIL_AT[fail_on]
    if threshold and ORDER.index(verdict) >= ORDER.index(threshold):
        print(f"::error title=Release gate::Verdict '{verdict}' (fail-on: {fail_on}). See the job summary for each reason.")
        return 1
    print(f"Release gate: {verdict} (fail-on: {fail_on})")
    return 0


if __name__ == "__main__":
    if "--enforce" in sys.argv:
        raise SystemExit(enforce())
    evaluate()
