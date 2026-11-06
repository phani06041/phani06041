"""Render profile stat cards as SVGs from the GitHub GraphQL API.

Usage: python cards.py <username> <out_dir>   (needs GITHUB_TOKEN in env)
Standard library only.
"""
import json
import os
import sys
import urllib.request
from datetime import date, timedelta
from html import escape

USER, OUT = sys.argv[1], sys.argv[2]
TOKEN = os.environ["GITHUB_TOKEN"]

BG, BORDER, TITLE, TEXT, MUTED = "#0D1117", "#30363d", "#00C6FF", "#c9d1d9", "#8b949e"
ACCENT, ACCENT2 = "#8A2BE2", "#302b63"
FONT = "font-family:'Segoe UI',Ubuntu,'Helvetica Neue',Sans-Serif"


def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if body.get("errors"):
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]


Q_PROFILE = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    name
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def fetch():
    repos, cursor, first = [], None, None
    while True:
        d = gql(Q_PROFILE, {"login": USER, "cursor": cursor})["user"]
        first = first or d
        repos += d["repositories"]["nodes"]
        page = d["repositories"]["pageInfo"]
        if not page["hasNextPage"]:
            break
        cursor = page["endCursor"]
    return first, repos


def frame(w, h, title, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f"<style>.t{{{FONT};font-weight:600;font-size:18px;fill:{TITLE}}}"
        f".l{{{FONT};font-size:14px;fill:{TEXT}}}.m{{{FONT};font-size:12px;fill:{MUTED}}}"
        f".v{{{FONT};font-weight:700;font-size:14px;fill:#fff}}"
        f".f{{animation:in .6s ease-out backwards}}@keyframes in{{from{{opacity:0}}}}</style>"
        f'<rect x="0.5" y="0.5" rx="10" width="{w-1}" height="{h-1}" fill="{BG}" stroke="{BORDER}"/>'
        f'<text x="25" y="38" class="t">{escape(title)}</text>{body}</svg>'
    )


def stats_card(u, repos):
    cc = u["contributionsCollection"]
    rows = [
        ("⭐", "Total stars earned", sum(r["stargazerCount"] for r in repos)),
        ("📦", "Public repositories", u["repositories"]["totalCount"]),
        ("🔥", "Contributions (last year)", cc["contributionCalendar"]["totalContributions"]),
        ("💾", "Commits (last year)", cc["totalCommitContributions"] + cc["restrictedContributionsCount"]),
        ("🔀", "Pull requests", u["pullRequests"]["totalCount"]),
        ("👥", "Followers", u["followers"]["totalCount"]),
    ]
    body = ""
    for i, (icon, label, val) in enumerate(rows):
        y = 72 + i * 26
        body += (
            f'<g class="f" style="animation-delay:{i*120}ms">'
            f'<text x="25" y="{y}" class="l">{icon}  {label}</text>'
            f'<text x="330" y="{y}" class="v" text-anchor="end">{val:,}</text></g>'
        )
    return frame(360, 230, f"{u['name'] or USER}'s GitHub stats", body)


def langs_card(repos, top=6):
    totals, colors = {}, {}
    for r in repos:
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            totals[n] = totals.get(n, 0) + e["size"]
            colors[n] = e["node"]["color"] or MUTED
    items = sorted(totals.items(), key=lambda kv: -kv[1])[:top]
    total = sum(v for _, v in items) or 1
    bar, x, w = "", 25.0, 310.0
    for n, v in items:
        seg = w * v / total
        bar += f'<rect x="{x:.2f}" y="56" width="{seg:.2f}" height="8" fill="{colors[n]}"/>'
        x += seg
    bar = f'<clipPath id="c"><rect x="25" y="56" width="{w}" height="8" rx="4"/></clipPath><g clip-path="url(#c)">{bar}</g>'
    legend = ""
    for i, (n, v) in enumerate(items):
        col, row = i % 2, i // 2
        lx, ly = 25 + col * 160, 98 + row * 30
        legend += (
            f'<g class="f" style="animation-delay:{i*120}ms">'
            f'<circle cx="{lx+5}" cy="{ly-4}" r="5" fill="{colors[n]}"/>'
            f'<text x="{lx+16}" y="{ly}" class="l">{escape(n)} <tspan class="m">{100*v/total:.1f}%</tspan></text></g>'
        )
    return frame(360, 230, "Most used languages", bar + legend)


def activity_card(u, days=31):
    cal = [d for w in u["contributionsCollection"]["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    cal = cal[-days:]
    counts = [d["contributionCount"] for d in cal]
    W, H, L, R, T, B = 900, 300, 50, 25, 60, 50
    pw, ph = W - L - R, H - T - B
    mx = max(4, -(-max(counts) // 4) * 4)
    step = pw / (len(counts) - 1)
    pts = [(L + i * step, T + ph - ph * c / mx) for i, c in enumerate(counts)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{L},{T+ph} {line} {L+pw},{T+ph}"
    grid = ""
    for k in range(5):
        v = mx * k / 4
        y = T + ph - ph * k / 4
        grid += (f'<line x1="{L}" x2="{L+pw}" y1="{y:.1f}" y2="{y:.1f}" stroke="{BORDER}" stroke-dasharray="3 4"/>'
                 f'<text x="{L-10}" y="{y+4:.1f}" class="m" text-anchor="end">{v:.0f}</text>')
    labels = ""
    for i, d in enumerate(cal):
        if i % 5 == 0 or i == len(cal) - 1:
            dt = date.fromisoformat(d["date"])
            labels += f'<text x="{pts[i][0]:.1f}" y="{H-22}" class="m" text-anchor="middle">{dt.strftime("%d %b")}</text>'
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#fff" stroke="{TITLE}" stroke-width="2"/>'
                   for x, y in pts)
    body = (
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{ACCENT}" stop-opacity=".55"/><stop offset="1" stop-color="{ACCENT2}" stop-opacity="0"/>'
        f'</linearGradient></defs>{grid}'
        f'<polygon points="{area}" fill="url(#g)"/>'
        f'<polyline points="{line}" fill="none" stroke="{TITLE}" stroke-width="2.5" stroke-linejoin="round" '
        f'stroke-dasharray="3000" style="animation:draw 2s ease-out"/>'
        f'<style>@keyframes draw{{from{{stroke-dashoffset:3000}}}}</style>{dots}{labels}'
        f'<text x="{W-25}" y="38" class="m" text-anchor="end">last {days} days · updated {date.today():%d %b %Y}</text>'
    )
    return frame(W, H, "Contribution pulse", body)


def main():
    u, repos = fetch()
    os.makedirs(OUT, exist_ok=True)
    for name, svg in (("stats.svg", stats_card(u, repos)),
                      ("top-langs.svg", langs_card(repos)),
                      ("activity.svg", activity_card(u))):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(svg)
    print("wrote cards to", OUT)


if __name__ == "__main__":
    main()
