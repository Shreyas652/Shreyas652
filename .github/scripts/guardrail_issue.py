#!/usr/bin/env python3
"""Score a guardrail issue and prepare safe repository/comment output."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from guardrail import Assessment, assess

README = ROOT / "README.md"
PAGE = ROOT / "docs" / "index.html"
DATA = ROOT / ".github" / "guardrail" / "bypasses.json"
COMMENT = ROOT / "guardrail-comment.md"
RESULT = ROOT / "guardrail-result.json"
START = "<!--GUARDRAIL-START-->"
END = "<!--GUARDRAIL-END-->"
PAGE_START = "<!--GUARDRAIL-PAGE-START-->"
PAGE_END = "<!--GUARDRAIL-PAGE-END-->"
ATTACK_RE = re.compile(r"<!--\s*attack:start\s*-->(.*?)<!--\s*attack:end\s*-->", re.I | re.S)
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


def api_get(path: str, token: str) -> object:
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "Shreyas652-guardrail",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def extract_attack(body: str) -> str:
    match = ATTACK_RE.search(body or "")
    return match.group(1).strip() if match else (body or "").strip()


def attempts_today(repo: str, login: str, token: str) -> int:
    if not token:
        return 1
    since = datetime.now(UTC).strftime("%Y-%m-%dT00:00:00Z")
    query = urllib.parse.urlencode({"state": "all", "creator": login, "since": since, "per_page": 100})
    issues = api_get(f"/repos/{repo}/issues?{query}", token)
    today = datetime.now(UTC).date().isoformat()
    return sum(
        1
        for issue in issues
        if str(issue.get("title", "")).startswith("[guardrail]")
        and str(issue.get("created_at", "")).startswith(today)
    )


def render_comment(result: Assessment) -> str:
    icon = "🛑" if result.verdict == "blocked" else "🟢"
    lines = [
        f"## {icon} Verdict: {result.verdict.upper()}",
        "",
        f"**Risk score:** {result.risk_score}/100",
        "",
    ]
    if result.findings:
        lines.extend(["| Rule | Why it fired | Weight |", "|---|---|---:|"])
        for finding in result.findings:
            lines.append(f"| `{finding.rule_id}` | {finding.description} | +{finding.weight} |")
    else:
        lines.append("No current rule fired. This attempt is recorded as a bypass so the policy can improve.")
    if result.truncated:
        lines.extend(["", "Input exceeded 8,000 characters and was truncated before evaluation."])
    lines.extend(
        [
            "",
            "This is a deterministic demonstration: no model was called, no input was executed, and no URL from the issue was fetched.",
        ]
    )
    return "\n".join(lines) + "\n"


def replace_block(path: Path, start: str, end: str, replacement: str) -> None:
    source = path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pattern.search(source):
        raise SystemExit(f"Missing leaderboard markers in {path}")
    path.write_text(pattern.sub(lambda _: f"{start}\n{replacement}\n{end}", source), encoding="utf-8")


def render_leaderboards(records: list[dict], repo: str) -> None:
    if records:
        rows = []
        items = []
        for record in records[-10:][::-1]:
            number = int(record["issue"])
            login = record["author"]
            url = f"https://github.com/{repo}/issues/{number}"
            signals = ", ".join(f"`{rule}`" for rule in record["rules"]) or "none"
            rows.append(f"| [#{number}]({url}) | [@{login}](https://github.com/{login}) | {record['score']} | {signals} | {record['date']} |")
            items.append(f'<li><a href="{url}">Attempt #{number}</a> by <a href="https://github.com/{login}">@{login}</a> — score {record["score"]}; signals: {", ".join(record["rules"]) or "none"}</li>')
        readme = "| Attempt | Author | Score | Signals | Date (UTC) |\n|---|---|---:|---|---|\n" + "\n".join(rows)
        page = "<ol>\n" + "\n".join(items) + "\n</ol>"
    else:
        readme = "_No bypasses recorded yet._"
        page = "<p>No bypasses recorded yet.</p>"
    replace_block(README, START, END, readme)
    replace_block(PAGE, PAGE_START, PAGE_END, page)


def main() -> None:
    body = os.environ.get("ISSUE_BODY", "")
    login = os.environ.get("USER_LOGIN", "")
    repo = os.environ.get("REPOSITORY", "Shreyas652/Shreyas652")
    token = os.environ.get("GITHUB_TOKEN", "")
    issue = int(os.environ.get("ISSUE_NUMBER", "0"))
    if not LOGIN_RE.fullmatch(login):
        raise SystemExit("Invalid GitHub login")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise SystemExit("Invalid repository name")

    count = attempts_today(repo, login, token)
    if count > 3:
        COMMENT.write_text(
            "## Rate limit reached\n\nThe challenge accepts three attempts per GitHub account per UTC day. Please try again tomorrow.\n",
            encoding="utf-8",
        )
        RESULT.write_text(json.dumps({"rate_limited": True}) + "\n", encoding="utf-8")
        return

    result = assess(extract_attack(body))
    COMMENT.write_text(render_comment(result), encoding="utf-8")
    payload = {
        "rate_limited": False,
        "verdict": result.verdict,
        "score": result.risk_score,
        "rules": [finding.rule_id for finding in result.findings],
    }
    RESULT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if result.verdict != "allowed":
        return

    records = json.loads(DATA.read_text(encoding="utf-8"))
    if not any(record["issue"] == issue for record in records):
        records.append(
            {
                "issue": issue,
                "author": login,
                "score": result.risk_score,
                "rules": payload["rules"],
                "date": datetime.now(UTC).date().isoformat(),
            }
        )
    records = records[-100:]
    DATA.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    render_leaderboards(records, repo)


if __name__ == "__main__":
    main()
