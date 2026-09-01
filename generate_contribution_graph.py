import html
import json
import os
import sys
import urllib.request
from collections import Counter


GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
GRAPHQL_QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    login
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""

WIDTH = 820
HEIGHT = 154
CELL_SIZE = 11
CELL_GAP = 3
STEP = CELL_SIZE + CELL_GAP
GRAPH_X = 56
GRAPH_Y = 30
COLORS = ["#050505", "#262626", "#666666", "#adadad", "#ffffff"]


def fetch_contributions(username: str, token: str) -> dict:
    request = urllib.request.Request(
        GRAPHQL_ENDPOINT,
        data=json.dumps({"query": GRAPHQL_QUERY, "variables": {"login": username}}).encode(),
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "ankit18193-contribution-graph",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode())

    if payload.get("errors"):
        messages = "; ".join(error.get("message", "GraphQL request failed") for error in payload["errors"])
        raise RuntimeError(messages)
    user = (payload.get("data") or {}).get("user")
    if not user:
        raise RuntimeError(f"GitHub user not found: {username}")
    return user


def intensity(count: int, nonzero_counts: list[int]) -> int:
    if count == 0:
        return 0
    if not nonzero_counts:
        return 1
    rank = sum(value <= count for value in nonzero_counts) / len(nonzero_counts)
    return min(4, 1 + int(rank * 4))


def build_svg(username: str, user: dict) -> str:
    calendar = user["contributionsCollection"]["contributionCalendar"]
    days = [day for week in calendar["weeks"] for day in week["contributionDays"]]
    days = days[-371:]
    nonzero_counts = [day["contributionCount"] for day in days if day["contributionCount"] > 0]
    weeks = [days[index:index + 7] for index in range(0, len(days), 7)]
    display_name = user.get("name") or username

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="100%" role="img" aria-labelledby="title description">',
        f"  <title id=\"title\">{html.escape(display_name)}'s GitHub contribution activity</title>",
        f'  <desc id="description">{calendar["totalContributions"]} contributions in the last year, shown by day.</desc>',
        '  <rect width="100%" height="100%" rx="8" fill="#0d1117"/>',
        '  <text x="56" y="17" fill="#f0f0f0" font-family="ui-sans-serif,system-ui,sans-serif" font-size="11" font-weight="600">Last year</text>',
        f'  <text x="764" y="17" text-anchor="end" fill="#8b8b8b" font-family="ui-sans-serif,system-ui,sans-serif" font-size="10">{calendar["totalContributions"]} contributions</text>',
    ]

    for week_index, week in enumerate(weeks):
        for day_index, day in enumerate(week):
            count = day["contributionCount"]
            color = COLORS[intensity(count, nonzero_counts)]
            x = GRAPH_X + week_index * STEP
            y = GRAPH_Y + day_index * STEP
            label = f'{day["date"]}: {count} contribution' + ("s" if count != 1 else "")
            parts.append(
                f'  <rect x="{x}" y="{y}" width="{CELL_SIZE}" height="{CELL_SIZE}" rx="2" fill="{color}">'
                f"<title>{html.escape(label)}</title></rect>"
            )

    legend_x = 610
    parts.append('  <text x="56" y="137" fill="#777777" font-family="ui-sans-serif,system-ui,sans-serif" font-size="10">Less</text>')
    for index, color in enumerate(COLORS):
        parts.append(f'  <rect x="{legend_x + index * 16}" y="129" width="11" height="11" rx="2" fill="{color}"/>')
    parts.append(f'  <text x="{legend_x + 5 * 16 + 4}" y="137" fill="#777777" font-family="ui-sans-serif,system-ui,sans-serif" font-size="10">More</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    username = os.environ.get("GITHUB_USERNAME", "ankit18193")
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required to fetch the real contribution calendar")

    user = fetch_contributions(username, token)
    svg = build_svg(username, user)
    output_path = os.environ.get("OUTPUT_PATH", "assets/contribution-graph.svg")
    with open(output_path, "w", encoding="utf-8") as output:
        output.write(svg)
    print(f"Wrote {output_path} for {username}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, urllib.error.URLError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)