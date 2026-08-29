import html
import json
import os
import urllib.request
from datetime import datetime

# ─── Layout (matches original gh-ascii geometry exactly) ──────────────────────
# SVG canvas : 1317 × 728
# ASCII col  : x=28, font-size=8, ≈4.8px/char, 140 chars → right edge ≈700 px
# Info panel : x=732, font-size=16, ≈9.6px/char
#              available width = 1317 − 732 − 28 = 557 px → ~58 chars max
#              right edge at 732 + 58×9.6 = 1289 px  ✓ (safe margin to 1317)
PANEL_X    = 732
FONT_SIZE  = 16
COLS       = 58          # characters per line — ALL values are pre-fitted to this
LINE_H     = 20          # px between rows


def calculate_uptime(created_at_str: str) -> str:
    created = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
    now     = datetime.now(created.tzinfo)
    y, m, d = now.year - created.year, now.month - created.month, now.day - created.day
    if d < 0: m -= 1; d += 30
    if m < 0: y -= 1; m += 12
    parts = []
    if y: parts.append(f"{y} year{'s' if y!=1 else ''}")
    if m: parts.append(f"{m} month{'s' if m!=1 else ''}")
    if d or not parts: parts.append(f"{d} day{'s' if d!=1 else ''}")
    return ", ".join(parts)


def fetch_github_stats(username: str, token: str | None = None) -> dict:
    defaults = {
        "created_at": "2024-05-24T21:40:25Z",
        "repos": "22", "stars": "0",
        "commits": "202+", "followers": "1",
    }
    headers = {"User-Agent": "GitHub-Profile-Card"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # ── GraphQL (token required for commit count) ──────────────────────────────
    if token:
        query = """query($login:String!){user(login:$login){
          createdAt followers{totalCount} following{totalCount}
          repositories(first:100,ownerAffiliations:OWNER){
            totalCount nodes{stargazerCount}
          }
          contributionsCollection{
            totalCommitContributions restrictedContributionsCount
            contributionCalendar{totalContributions}
          }
        }}"""
        try:
            req = urllib.request.Request(
                "https://api.github.com/graphql",
                data=json.dumps({"query": query, "variables": {"login": username}}).encode(),
                headers={**headers, "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                d = json.loads(r.read().decode())
            if u := (d.get("data") or {}).get("user"):
                defaults["created_at"] = u.get("createdAt", defaults["created_at"])
                defaults["followers"]  = str(u["followers"]["totalCount"])
                repos = u.get("repositories", {})
                defaults["repos"]  = str(repos.get("totalCount", 0))
                defaults["stars"]  = str(sum(n.get("stargazerCount", 0) for n in repos.get("nodes", [])))
                cc = u.get("contributionsCollection", {})
                commits = max(
                    cc.get("totalCommitContributions", 0) + cc.get("restrictedContributionsCount", 0),
                    cc.get("contributionCalendar", {}).get("totalContributions", 0),
                )
                defaults["commits"] = f"{commits:,}"
                return defaults
        except Exception as e:
            print(f"GraphQL failed ({e}), trying REST…")

    # ── REST fallback ──────────────────────────────────────────────────────────
    try:
        req = urllib.request.Request(f"https://api.github.com/users/{username}", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            u = json.loads(r.read().decode())
        defaults["created_at"] = u.get("created_at", defaults["created_at"])
        defaults["repos"]      = str(u.get("public_repos", 0))
        defaults["followers"]  = str(u.get("followers", 0))

        req = urllib.request.Request(f"https://api.github.com/users/{username}/repos?per_page=100", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            defaults["stars"] = str(sum(x.get("stargazers_count", 0) for x in json.loads(r.read().decode())))
    except Exception as e:
        print(f"REST failed ({e})")

    return defaults


def tspan(fill: str, text: str) -> str:
    return f'<tspan fill="{fill}">{html.escape(text)}</tspan>'


def build_rows(sections: list, stats: dict, c: dict) -> list[str]:
    """Return one SVG inner-text string per rendered row (no wrapping; values are pre-fitted)."""
    rows = []
    for sec in sections:
        t = sec.get("type")

        if t == "header":
            title  = sec["title"]
            prefix = "\u2500 "          # ─
            body   = f"{title} "
            dashes = "\u2500" * max(0, COLS - len(prefix) - len(body))
            rows.append(tspan(c["hl"], prefix) + tspan(c["ht"], body) + tspan(c["hl"], dashes))

        elif t in ("kv", "dynamic_uptime"):
            key = sec.get("key", "")
            val = calculate_uptime(stats["created_at"]) if t == "dynamic_uptime" else sec.get("value", "")
            pfx = f". {key}: "
            vs  = f" {val}"
            # Clamp dots to at least 3 even if value is slightly long
            dots = max(3, COLS - len(pfx) - len(vs))
            rows.append(tspan(c["key"], pfx) + tspan(c["dot"], "." * dots) + tspan(c["val"], vs))

        elif t == "dual_stat":
            lk, ls = sec["left"]["key"],  sec["left"]["stat"]
            rk, rs = sec["right"]["key"], sec["right"]["stat"]
            lv, rv = stats.get(ls, "0"),  stats.get(rs, "0")

            half = (COLS - 3) // 2          # 3 = " | "
            lp, lv_s = f". {lk}: ", f" {lv}"
            rp, rv_s = f". {rk}: ", f" {rv}"
            ld = "." * max(2, half - len(lp) - len(lv_s))
            rd = "." * max(2, (COLS - 3 - half) - len(rp) - len(rv_s))

            rows.append(
                tspan(c["key"], lp) + tspan(c["dot"], ld) + tspan(c["sta"], lv_s)
                + tspan(c["pip"], " | ")
                + tspan(c["key"], rp) + tspan(c["dot"], rd) + tspan(c["sta"], rv_s)
            )

        elif t == "blank":
            rows.append(tspan(c["dot"], " "))

    return rows


def build_svg(theme: str, config: dict, stats: dict, ascii_lines: list[str]) -> str:
    dark = theme == "dark"
    c = {
        "bg":  "#0d1117" if dark else "#ffffff",
        "brd": "#30363d" if dark else "#d0d7de",
        "asc": "#c9d1d9" if dark else "#24292f",
        "hl":  "#3d444d" if dark else "#d0d7de",   # header line dashes
        "ht":  "#58a6ff" if dark else "#0969da",   # header title
        "key": "#ffa657" if dark else "#953800",   # key label
        "dot": "#484f58" if dark else "#8c959f",   # dots
        "val": "#c9d1d9" if dark else "#24292f",   # value text
        "sta": "#79c0ff" if dark else "#0550ae",   # stat numbers
        "pip": "#3d444d" if dark else "#d0d7de",   # " | " separator
    }
    FONT = "'Consolas','Menlo','DejaVu Sans Mono',monospace"

    username_safe = html.escape(config["username"])
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1317" height="728" viewBox="0 0 1317 728" '
        f'role="img" aria-label="GitHub profile card for {username_safe}">',
        f'  <rect x="0.5" y="0.5" width="1316" height="727" rx="8" fill="{c["bg"]}" stroke="{c["brd"]}"/>',
    ]

    # ── Left: ASCII portrait (70 lines, font-size 8) ──────────────────────────
    for i, line in enumerate(ascii_lines):
        y = round(34.6 + i * 9.6, 2)
        svg.append(
            f'  <text x="28" y="{y}" fill="{c["asc"]}" font-family="{FONT}" '
            f'xml:space="preserve" font-size="8">{html.escape(line)}</text>'
        )

    # ── Right: terminal info panel ─────────────────────────────────────────────
    rows     = build_rows(config.get("sections", []), stats, c)
    total_h  = len(rows) * LINE_H
    start_y  = max(round((728 - total_h) / 2 + 10), 50)

    for i, row_html in enumerate(rows):
        y = start_y + i * LINE_H
        svg.append(
            f'  <text x="{PANEL_X}" y="{y}" font-family="{FONT}" '
            f'xml:space="preserve" font-size="{FONT_SIZE}">{row_html}</text>'
        )

    svg.append("</svg>")
    return "\n".join(svg)


def main():
    with open("profile_config.json", encoding="utf-8") as f:
        config = json.load(f)

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    print(f"Panel: x={PANEL_X}, font={FONT_SIZE}px, cols={COLS}, token={bool(token)}")
    stats = fetch_github_stats(config["username"], token=token)
    print(f"Stats: repos={stats['repos']} stars={stats['stars']} "
          f"commits={stats['commits']} followers={stats['followers']}")

    with open("assets/ascii_dark.txt",  encoding="utf-8") as f:
        dark_ascii  = [l.rstrip("\r\n") for l in f]
    with open("assets/ascii_light.txt", encoding="utf-8") as f:
        light_ascii = [l.rstrip("\r\n") for l in f]

    for theme, lines, fname in [
        ("dark",  dark_ascii,  "dark_mode.svg"),
        ("light", light_ascii, "light_mode.svg"),
    ]:
        with open(fname, "w", encoding="utf-8") as f:
            f.write(build_svg(theme, config, stats, lines))
        print(f"  [OK] {fname}")


if __name__ == "__main__":
    main()
