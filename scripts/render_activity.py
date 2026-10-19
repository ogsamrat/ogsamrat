#!/usr/bin/env python3
"""Render a cached GitHub contribution card from GitHub's GraphQL API."""

from __future__ import annotations

import datetime as dt
import html
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request


LOGIN = "ogsamrat"
OUTPUT = Path("assets/activity.svg")
README = Path("README.md")
ACTIVITY_SOURCE = re.compile(
    r'(?<=src=")\./assets/activity(?:-\d{8})?\.svg(?:\?rev=[^"]+)?'
    r'(?=" alt="Samrat\'s GitHub contribution graph")'
)
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    createdAt
    email
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


def fetch_user(token: str, query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
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
        raise ValueError("GitHub returned no usable contribution data")
    return payload["data"]["user"]


def get_user(token: str, today: dt.date) -> dict:
    start = today - dt.timedelta(days=364)
    user = fetch_user(token, QUERY, {
        "login": LOGIN,
        "from": f"{start.isoformat()}T00:00:00Z",
        "to": f"{(today + dt.timedelta(days=1)).isoformat()}T00:00:00Z",
    })
    joined = dt.date.fromisoformat(user["createdAt"][:10])
    if joined > today:
        raise ValueError("Invalid GitHub join date")
    years = range(joined.year, today.year + 1)
    yearly_fields = "\n".join(
        f'y{year}: contributionsCollection(from: "{year}-01-01T00:00:00Z", '
        f'to: "{year}-12-31T23:59:59Z") '
        '{ contributionCalendar { totalContributions } }'
        for year in years
    )
    totals = fetch_user(
        token,
        f"query($login: String!) {{ user(login: $login) {{ {yearly_fields} }} }}",
        {"login": LOGIN},
    )
    try:
        user["allTimeContributions"] = sum(
            int(totals[f"y{year}"]["contributionCalendar"]["totalContributions"])
            for year in years
        )
    except (KeyError, TypeError) as exc:
        raise ValueError("Incomplete all-time contribution totals") from exc
    return user


def render(user: dict, today: dt.date) -> str:
    start = today - dt.timedelta(days=364)
    calendar = user["contributionsCollection"]["contributionCalendar"]
    days = [day for week in calendar["weeks"] for day in week["contributionDays"]]
    months = []
    year, month = start.year, start.month
    while (year, month) <= (today.year, today.month):
        months.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    buckets = [0] * len(months)
    seen = 0
    for day in days:
        date = dt.date.fromisoformat(day["date"])
        if start <= date <= today:
            count = int(day["contributionCount"])
            if count < 0:
                raise ValueError("Negative contribution count")
            buckets[months.index((date.year, date.month))] += count
            seen += 1
    if seen < 350 or sum(buckets) == 0:
        raise ValueError("Incomplete or empty contribution calendar; keep the old image")

    total = int(user["allTimeContributions"])
    if total <= 0:
        raise ValueError("Invalid all-time contribution total; keep the old image")
    repos = int(user["repositories"]["totalCount"])
    joined = dt.date.fromisoformat(user["createdAt"][:10])
    years = today.year - joined.year - ((today.month, today.day) < (joined.month, joined.day))
    email = html.escape(user.get("email") or "me@drick.in")
    left, right, top, bottom = 448, 1104, 53, 270
    ceiling = max(200, ((max(buckets) + 199) // 200) * 200)
    points = [
        (left + i * (right - left) / (len(buckets) - 1), bottom - count * (bottom - top) / ceiling)
        for i, count in enumerate(buckets)
    ]
    line = f"M {points[0][0]:.1f} {points[0][1]:.1f}"
    for i in range(1, len(points)):
        px, py = points[i - 1]
        x, y = points[i]
        midpoint = (px + x) / 2
        line += f" C {midpoint:.1f} {py:.1f}, {midpoint:.1f} {y:.1f}, {x:.1f} {y:.1f}"
    area = f"{line} L {right} {bottom} L {left} {bottom} Z"
    ticks = "".join(
        f'<line x1="{x:.1f}" y1="270" x2="{x:.1f}" y2="280" stroke="#43828c"/>'
        f'<text x="{x:.1f}" y="302" text-anchor="middle" class="axis">'
        f'{year % 100:02d}/{month:02d}</text>'
        for i, ((year, month), (x, _)) in enumerate(zip(months, points)) if i % 2 == 0
    )
    y_ticks = "".join(
        f'<line x1="1104" y1="{bottom - value * (bottom - top) / ceiling:.1f}" '
        f'x2="1116" y2="{bottom - value * (bottom - top) / ceiling:.1f}" stroke="#43828c"/>'
        f'<text x="1124" y="{bottom - value * (bottom - top) / ceiling + 7:.1f}" class="axis">{value:,}</text>'
        for value in range(0, ceiling + 1, 200)
    )
    compact_total = f"{total / 1000:.2f}k" if total >= 1000 else str(total)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="338" viewBox="0 0 1200 338" role="img" aria-label="GitHub contribution activity for the past year">
<style>
  .meta {{ font: 400 25px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #43828c; }}
  .axis {{ font: 400 19px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #43828c; }}
  .small {{ font: 400 18px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #43828c; }}
</style>
<g fill="none" stroke="#0969da" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="41" cy="83" r="17"/><path d="M32 94v-5c-4-2-5-6-3-9l3-2 2-5 5 3 5-3 2 5 3 2c2 3 1 7-3 9v5"/>
  <path d="M27 137h27v28H27z M27 160h27 M33 137v23"/>
  <circle cx="41" cy="220" r="16"/><path d="M41 209v12l8 5"/>
  <path d="M25 271h32v23H25z M26 272l15 12 15-12"/>
</g>
<text x="73" y="91" class="meta">{compact_total} Contributions on GitHub</text>
<text x="73" y="160" class="meta">{repos} Public Repos</text>
<text x="73" y="228" class="meta">Joined GitHub {years} years ago</text>
<text x="73" y="290" class="meta">{email}</text>
<text x="1104" y="29" text-anchor="end" class="small">contributions in the last year</text>
<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#43828c"/>
<line x1="{right}" y1="{top}" x2="{right}" y2="{bottom}" stroke="#43828c"/>
<path d="{area}" fill="#0969ff"/>
{ticks}
{y_ticks}
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
    dated_output = OUTPUT.with_name(f"activity-{today:%Y%m%d}.svg")
    readme = README.read_text(encoding="utf-8")
    updated_readme, replacements = ACTIVITY_SOURCE.subn(f"./assets/{dated_output.name}", readme)
    if replacements != 1:
        raise ValueError("Expected exactly one activity image in README; old image remains")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".svg.tmp")
    temporary.write_text(svg, encoding="utf-8")
    temporary.replace(OUTPUT)
    dated_temporary = dated_output.with_suffix(".svg.tmp")
    dated_temporary.write_text(svg, encoding="utf-8")
    dated_temporary.replace(dated_output)
    readme_temporary = README.with_suffix(".md.tmp")
    readme_temporary.write_text(updated_readme, encoding="utf-8")
    readme_temporary.replace(README)


if __name__ == "__main__":
    main()
