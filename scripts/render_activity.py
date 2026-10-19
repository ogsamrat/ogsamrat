#!/usr/bin/env python3
"""Render a cached GitHub contribution card from GitHub's GraphQL API."""

from __future__ import annotations

import datetime as dt
import html
import json
import os
from pathlib import Path
import urllib.error
import urllib.request


LOGIN = "ogsamrat"
OUTPUT = Path("assets/activity.svg")
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    createdAt
    publicEmail
    repositories(first: 1, privacy: PUBLIC, ownerAffiliations: OWNER) {
      totalCount
    }
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date contributionCount }
        }
      }
    }
  }
}
"""


def get_user(token: str, today: dt.date) -> dict:
    start = today - dt.timedelta(days=364)
    body = json.dumps({
        "query": QUERY,
        "variables": {
            "login": LOGIN,
            "from": f"{start.isoformat()}T00:00:00Z",
            "to": f"{(today + dt.timedelta(days=1)).isoformat()}T00:00:00Z",
        },
    }).encode()
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "ogsamrat-profile-activity",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors") or not payload.get("data", {}).get("user"):
        raise ValueError(str(payload.get("errors", "GitHub returned no usable contribution data"))[:400])
    return payload["data"]["user"]


def render(user: dict, today: dt.date) -> str:
    start = today - dt.timedelta(days=364)
    calendar = user["contributionsCollection"]["contributionCalendar"]
    days = [day for week in calendar["weeks"] for day in week["contributionDays"]]
    buckets = [0] * 12
    seen = 0
    for day in days:
        date = dt.date.fromisoformat(day["date"])
        if start <= date <= today:
            count = int(day["contributionCount"])
            if count < 0:
                raise ValueError("Negative contribution count")
            buckets[min(11, ((date - start).days * 12) // 365)] += count
            seen += 1
    if seen < 350 or sum(buckets) == 0:
        raise ValueError("Incomplete or empty contribution calendar; keep the old image")

    total = int(calendar["totalContributions"])
    if total <= 0:
        raise ValueError("Invalid contribution total; keep the old image")
    repos = int(user["repositories"]["totalCount"])
    joined = dt.date.fromisoformat(user["createdAt"][:10]).year
    email = html.escape(user.get("publicEmail") or "me@drick.in")
    left, right, top, bottom = 572, 1132, 86, 257
    ceiling = max(buckets) * 1.12
    points = [
        (left + i * (right - left) / 11, bottom - count * (bottom - top) / ceiling)
        for i, count in enumerate(buckets)
    ]
    line = " ".join(f"{'M' if i == 0 else 'L'} {x:.1f} {y:.1f}" for i, (x, y) in enumerate(points))
    area = f"{line} L {right} {bottom} L {left} {bottom} Z"
    ticks = "".join(
        f'<text x="{x:.1f}" y="289" text-anchor="middle" class="axis">'
        f'{(start + dt.timedelta(days=round((i + .5) * 365 / 12))).strftime("%b %y")}</text>'
        for i, (x, _) in enumerate(points) if i % 2 == 0
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="320" viewBox="0 0 1200 320" role="img" aria-label="GitHub contribution activity for the past year">
<style>
  .main {{ font: 600 31px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #f0f6fc; }}
  .meta {{ font: 400 18px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #9ba9ba; }}
  .axis {{ font: 400 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #9ba9ba; }}
  .small {{ font: 500 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #9ba9ba; letter-spacing: 1.2px; }}
</style>
<rect x="0.5" y="0.5" width="1199" height="319" rx="18" fill="#0d1117" stroke="#30363d"/>
<text x="40" y="48" class="small">GITHUB ACTIVITY · LAST 365 DAYS</text>
<text x="40" y="111" class="main">{total:,} contributions</text>
<text x="40" y="158" class="meta">{repos} public repositories</text>
<text x="40" y="195" class="meta">On GitHub since {joined}</text>
<text x="40" y="232" class="meta">{email}</text>
<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#30363d"/>
<path d="{area}" fill="#2f81f7" fill-opacity=".23"/>
<path d="{line}" fill="none" stroke="#58a6ff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
{ticks}
<text x="1132" y="48" text-anchor="end" class="small">UPDATED {today.isoformat()}</text>
</svg>
'''


def main() -> None:
    today = dt.datetime.now(dt.timezone.utc).date()
    candidates = [os.getenv("METRICS_TOKEN"), os.getenv("GITHUB_TOKEN")]
    error = None
    for token in (value for value in candidates if value):
        try:
            svg = render(get_user(token, today), today)
            break
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError, KeyError) as exc:
            error = exc
    else:
        raise RuntimeError("Could not refresh GitHub activity; old image remains") from error
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".svg.tmp")
    temporary.write_text(svg, encoding="utf-8")
    temporary.replace(OUTPUT)


if __name__ == "__main__":
    main()
