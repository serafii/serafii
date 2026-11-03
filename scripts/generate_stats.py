#!/usr/bin/env python3
"""Generate assets/stats.svg and assets/langs.svg for the profile README.

Uses a personal access token (env GH_STATS_TOKEN) so private repositories
are included. Standard library only — no installs needed.
"""
import html
import json
import os
import sys
import urllib.request

TOKEN = os.environ.get("GH_STATS_TOKEN")
OUT = os.path.join(os.path.dirname(__file__), "..", "assets")
TOP_N = 6
# Languages to leave out of the chart (e.g. generated or markup-heavy ones).
EXCLUDE = {"HTML", "Jupyter Notebook", "Dockerfile", "Makefile", "Batchfile"}

W, H = 440, 200
FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
C = dict(bg="#0d1117", border="#30363d", title="#8b949e", blue="#58a6ff",
         orange="#f0883e", dots="#484f58", val="#c9d1d9", muted="#8b949e")


def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req) as r:
        body = json.load(r)
    if "errors" in body:
        sys.exit(f"GraphQL error: {body['errors']}")
    return body["data"]


QUERY = """
query($cursor: String) {
  viewer {
    login
    followers { totalCount }
    pullRequests { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar { totalContributions }
    }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def fetch():
    cursor, stars, langs, first = None, 0, {}, None
    while True:
        v = gql(QUERY, {"cursor": cursor})["viewer"]
        first = first or v
        repos = v["repositories"]
        for n in repos["nodes"]:
            stars += n["stargazerCount"]
            for e in n["languages"]["edges"]:
                name = e["node"]["name"]
                if name in EXCLUDE:
                    continue
                size, color = langs.get(name, (0, None))
                langs[name] = (size + e["size"], e["node"]["color"] or "#8b949e")
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]
    cc = first["contributionsCollection"]
    stats = {
        "Repos": first["repositories"]["totalCount"],
        "Stars": stars,
        "Commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "PRs": first["pullRequests"]["totalCount"],
        "Contribs": cc["contributionCalendar"]["totalContributions"],
        "Followers": first["followers"]["totalCount"],
    }
    return stats, langs


def frame(title, body):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}">
<style>text{{font-family:{FONT};font-size:13px}} .t{{font-size:12px;letter-spacing:2px}}</style>
<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="8" fill="{C['bg']}" stroke="{C['border']}"/>
<text class="t" x="26" y="38" fill="{C['title']}">[ {html.escape(title.upper())} ]</text>
{body}
</svg>
'''


def fmt(n):
    return f"{n/1000:.1f}k" if n >= 10000 else f"{n:,}"


def render_stats(stats):
    cw = 7.8  # monospace char width at 13px, enforced with textLength
    items = list(stats.items())
    body, cols = [], 2
    colw = (W - 52) / cols
    for i, (k, v) in enumerate(items):
        col, row = i % cols, i // cols
        x = 26 + col * colw
        y = 80 + row * 34
        key, val = f"{k}:", fmt(v)
        ncols = int((colw - 30) / cw)
        ndots = max(2, ncols - len(key) - len(val) - 2)
        segs = [(key, C["orange"]), (" " + "." * ndots + " ", C["dots"]), (val, C["blue"])]
        cx = x
        for s, color in segs:
            body.append(f'<text x="{cx:.1f}" y="{y}" fill="{color}" textLength="{len(s)*cw:.1f}" '
                        f'lengthAdjust="spacingAndGlyphs" xml:space="preserve">{html.escape(s)}</text>')
            cx += len(s) * cw
    body.append(f'<text x="26" y="{H-18}" fill="{C["dots"]}" style="font-size:11px">'
                'incl. private repos · commits &amp; contribs: last 12 months</text>')
    return frame("GitHub stats", "\n".join(body))


def render_langs(langs):
    top = sorted(langs.items(), key=lambda kv: kv[1][0], reverse=True)[:TOP_N]
    total = sum(s for _, (s, _) in top) or 1
    x0, x1, by, bh, gap = 26, W - 26, 62, 10, 3
    body = [f'<clipPath id="bar"><rect x="{x0}" y="{by}" width="{x1-x0}" height="{bh}" rx="5"/></clipPath>',
            '<g clip-path="url(#bar)">']
    span = x1 - x0 - gap * (len(top) - 1)
    x = x0
    for _, (size, color) in top:
        w = max(span * size / total, 2)
        body.append(f'<rect x="{x:.1f}" y="{by}" width="{w:.1f}" height="{bh}" fill="{color}"/>')
        x += w + gap
    body.append("</g>")
    for i, (name, (size, color)) in enumerate(top):
        col, row = i % 2, i // 2
        lx = x0 + col * ((x1 - x0) / 2)
        ly = 106 + row * 30
        pct = 100 * size / total
        body.append(f'<circle cx="{lx+5}" cy="{ly-4}" r="5" fill="{color}"/>')
        body.append(f'<text x="{lx+18}" y="{ly}" fill="{C["val"]}">{html.escape(name)} '
                    f'<tspan fill="{C["muted"]}">{pct:.1f}%</tspan></text>')
    return frame("Top languages", "\n".join(body))


def main():
    if not TOKEN:
        sys.exit("GH_STATS_TOKEN is not set")
    stats, langs = fetch()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "stats.svg"), "w") as f:
        f.write(render_stats(stats))
    with open(os.path.join(OUT, "langs.svg"), "w") as f:
        f.write(render_langs(langs))
    print("stats:", stats)
    print("langs:", {k: v[0] for k, v in langs.items()})


if __name__ == "__main__":
    main()
