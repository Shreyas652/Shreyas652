#!/usr/bin/env python3
"""Generate repository-owned SVG profile widgets from GitHub's public API.

The script has no third-party runtime dependencies. In Actions, GITHUB_TOKEN is
the automatically-provided repository token; no configured secret is needed.
"""
from __future__ import annotations

import argparse
import json
import os
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "generated"
API = "https://api.github.com"
PROJECTS = ["support-triage-agent", "FINVERSE", "AI-Drone-Mission-Copliot", "Veyra"]
COLORS = ["#58a6ff", "#a371f7", "#3fb950", "#d29922", "#f85149", "#39c5cf"]


def api_get(path: str, token: str) -> object:
    request = urllib.request.Request(
        API + path,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Shreyas652-profile-widgets",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def collect(username: str, token: str) -> dict:
    repos = api_get(f"/users/{urllib.parse.quote(username)}/repos?per_page=100&type=owner&sort=updated", token)
    owned = [repo for repo in repos if not repo.get("fork")]
    language_bytes: Counter[str] = Counter()
    for repo in owned[:30]:
        try:
            languages = api_get(f"/repos/{repo['full_name']}/languages", token)
            language_bytes.update(languages)
        except urllib.error.HTTPError:
            continue

    events = api_get(f"/users/{urllib.parse.quote(username)}/events/public?per_page=100", token)
    activity: Counter[str] = Counter()
    commits: list[dict] = []
    seen_commit_urls: set[str] = set()
    for event in events:
        stamp = event.get("created_at", "")[:10]
        if stamp:
            activity[stamp] += 1
        if event.get("type") != "PushEvent":
            continue
        repo_name = event.get("repo", {}).get("name", "").split("/")[-1]
        for commit in event.get("payload", {}).get("commits", []):
            sha = str(commit.get("sha", ""))[:7]
            url = f"https://github.com/{username}/{repo_name}/commit/{sha}"
            if not sha or url in seen_commit_urls:
                continue
            seen_commit_urls.add(url)
            commits.append(
                {
                    "repo": repo_name,
                    "message": str(commit.get("message", "")).splitlines()[0],
                    "url": url,
                    "date": stamp,
                }
            )

    by_name = {repo["name"].casefold(): repo for repo in owned}
    projects = []
    for name in PROJECTS:
        repo = by_name.get(name.casefold())
        projects.append(
            {
                "name": name,
                "url": repo.get("html_url") if repo else None,
                "description": repo.get("description") if repo else None,
                "language": repo.get("language") if repo else None,
                "pushed_at": repo.get("pushed_at") if repo else None,
            }
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "languages": dict(language_bytes),
        "activity": dict(activity),
        "projects": projects,
        "commits": commits[:5],
    }


def text(value: object, limit: int = 80) -> str:
    clean = " ".join(str(value or "").split())
    return escape(textwrap.shorten(clean, width=limit, placeholder="…"))


def svg_shell(title: str, subtitle: str, width: int, height: int, body: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">{escape(title)}</title>
  <desc id="desc">{escape(subtitle)}</desc>
  <style>
    .bg {{ fill:#0d1117 }} .panel {{ fill:#161b22; stroke:#30363d }}
    .title {{ fill:#f0f6fc; font:600 17px ui-monospace,SFMono-Regular,Consolas,monospace }}
    .text {{ fill:#c9d1d9; font:13px ui-monospace,SFMono-Regular,Consolas,monospace }}
    .muted {{ fill:#8b949e; font:12px ui-monospace,SFMono-Regular,Consolas,monospace }}
    @media (prefers-color-scheme:light) {{
      .bg {{ fill:#ffffff }} .panel {{ fill:#f6f8fa; stroke:#d0d7de }}
      .title {{ fill:#1f2328 }} .text {{ fill:#24292f }} .muted {{ fill:#57606a }}
    }}
  </style>
  <rect class="bg" width="{width}" height="{height}" rx="12"/>
  <rect class="panel" x="1" y="1" width="{width - 2}" height="{height - 2}" rx="11"/>
  <text class="title" x="20" y="30">{escape(title)}</text>
  <text class="muted" x="{width - 20}" y="29" text-anchor="end">{escape(subtitle)}</text>
{body}
</svg>\n'''


def languages_svg(data: dict) -> str:
    values = Counter(data.get("languages", {}))
    total = sum(values.values())
    rows = values.most_common(5)
    if not rows:
        body = '  <text class="muted" x="20" y="72">Refresh pending — run the widget workflow.</text>'
    else:
        body_parts = []
        x = 20.0
        usable = 720.0
        for index, (name, count) in enumerate(rows):
            width = usable * count / total
            body_parts.append(f'  <rect x="{x:.1f}" y="52" width="{width:.1f}" height="12" fill="{COLORS[index]}"/>')
            x += width
        for index, (name, count) in enumerate(rows):
            y = 92 + index * 24
            pct = count * 100 / total
            body_parts.append(f'  <circle cx="26" cy="{y - 4}" r="5" fill="{COLORS[index]}"/>')
            body_parts.append(f'  <text class="text" x="40" y="{y}">{text(name, 24)}</text>')
            body_parts.append(f'  <text class="muted" x="740" y="{y}" text-anchor="end">{pct:.1f}%</text>')
        body = "\n".join(body_parts)
    return svg_shell("Language footprint", "public, non-fork repositories", 760, 220, body)


def activity_svg(data: dict) -> str:
    counts = Counter(data.get("activity", {}))
    if data.get("pending"):
        body = '  <text class="muted" x="20" y="72">Refresh pending — run the widget workflow.</text>'
        return svg_shell("Recent activity", "generated from public GitHub events", 760, 228, body)
    today = datetime.now(UTC).date()
    values = []
    for days_ago in range(27, -1, -1):
        day = today.fromordinal(today.toordinal() - days_ago)
        values.append((day.isoformat(), counts[day.isoformat()]))
    high = max((value for _, value in values), default=1) or 1
    body = ['  <line x1="22" y1="155" x2="738" y2="155" stroke="#30363d"/>']
    for index, (day, count) in enumerate(values):
        bar_h = 78 * count / high
        x = 24 + index * 25.2
        body.append(f'  <rect x="{x:.1f}" y="{155 - bar_h:.1f}" width="14" height="{bar_h:.1f}" rx="3" fill="#58a6ff" opacity="{0.3 + 0.7 * count / high:.2f}"/>')
    body.append(f'  <text class="muted" x="22" y="181">{values[0][0]}</text>')
    body.append(f'  <text class="muted" x="738" y="181" text-anchor="end">{values[-1][0]}</text>')
    body.append(f'  <text class="text" x="20" y="208">{sum(value for _, value in values)} public events in this 28-day API window</text>')
    return svg_shell("Recent activity", "generated from public GitHub events", 760, 228, "\n".join(body))


def project_svg(data: dict) -> str:
    parts = []
    for index, project in enumerate(data.get("projects", [])):
        col, row = index % 2, index // 2
        x, y = 20 + col * 365, 52 + row * 116
        parts.append(f'  <rect class="bg" x="{x}" y="{y}" width="350" height="98" rx="9"/>')
        parts.append(f'  <text class="title" x="{x + 14}" y="{y + 26}">{text(project.get("name"), 34)}</text>')
        if project.get("pushed_at"):
            updated = project["pushed_at"][:10]
            meta = " · ".join(filter(None, [project.get("language"), f"last commit {updated}"]))
            description = project.get("description") or "Public repository"
        else:
            meta = "live metadata pending"
            description = "Refresh pending — run the widget workflow"
        parts.append(f'  <text class="text" x="{x + 14}" y="{y + 52}">{text(description, 45)}</text>')
        parts.append(f'  <text class="muted" x="{x + 14}" y="{y + 77}">{text(meta, 48)}</text>')
    return svg_shell("Project pulse", "last-commit dates from GitHub", 760, 296, "\n".join(parts))


def building_svg(data: dict) -> str:
    commits = data.get("commits", [])
    if not commits:
        message = "Refresh pending — run the widget workflow." if data.get("pending") else "No recent public push events were returned."
        body = f'  <text class="muted" x="20" y="72">{message}</text>'
    else:
        rows = []
        for index, commit in enumerate(commits[:5]):
            y = 65 + index * 33
            rows.append(f'  <text class="text" x="20" y="{y}">{text(commit["repo"], 25)}</text>')
            rows.append(f'  <text class="muted" x="185" y="{y}">{text(commit["message"], 62)}</text>')
            rows.append(f'  <text class="muted" x="740" y="{y}" text-anchor="end">{text(commit["date"], 10)}</text>')
        body = "\n".join(rows)
    return svg_shell("Now building", "recent public commits", 760, 240, body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default=os.environ.get("GITHUB_REPOSITORY_OWNER", "Shreyas652"))
    parser.add_argument("--fixture", type=Path, help="Use saved JSON instead of the network")
    args = parser.parse_args()
    if args.fixture:
        data = json.loads(args.fixture.read_text(encoding="utf-8"))
    else:
        data = collect(args.username, os.environ.get("GITHUB_TOKEN", ""))
    OUT.mkdir(parents=True, exist_ok=True)
    renderers = {
        "languages.svg": languages_svg,
        "activity.svg": activity_svg,
        "projects.svg": project_svg,
        "now-building.svg": building_svg,
    }
    for filename, renderer in renderers.items():
        (OUT / filename).write_text(renderer(data), encoding="utf-8")


if __name__ == "__main__":
    main()
