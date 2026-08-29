import html
import json
import os
import urllib.request
from datetime import datetime


def calculate_uptime(created_at_str):
    """Calculates human-readable uptime from ISO date string."""
    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
    now = datetime.now(created_at.tzinfo)

    years = now.year - created_at.year
    months = now.month - created_at.month
    days = now.day - created_at.day

    if days < 0:
        months -= 1
        days += 30
    if months < 0:
        years -= 1
        months += 12

    parts = []
    if years > 0:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months > 0:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if days > 0 or not parts:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    return ", ".join(parts)


def fetch_github_stats(username, token=None):
    """Fetches user and repository stats from GitHub GraphQL / REST API."""
    stats = {
        "created_at": "2024-05-24T21:40:25Z",
        "location": "Bengaluru",
        "repos": "22",
        "contributed_repos": "0",
        "stars": "0",
        "commits": "150+",
        "followers": "1",
        "following": "0",
    }

    # Try GraphQL first if token is available
    if token:
        graphql_query = """
        query($login: String!) {
          user(login: $login) {
            createdAt
            location
            followers { totalCount }
            following { totalCount }
            repositories(first: 100, ownerAffiliations: OWNER) {
              totalCount
              nodes {
                stargazerCount
                forkCount
              }
            }
            repositoriesContributedTo(first: 100) {
              totalCount
            }
            contributionsCollection {
              totalCommitContributions
              restrictedContributionsCount
              totalPullRequestContributions
              totalIssueContributions
              contributionCalendar {
                totalContributions
              }
            }
          }
        }
        """
        try:
            req = urllib.request.Request(
                "https://api.github.com/graphql",
                data=json.dumps(
                    {"query": graphql_query, "variables": {"login": username}}
                ).encode(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "User-Agent": "GitHub-Profile-Card-Generator",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                if "data" in data and data["data"].get("user"):
                    u = data["data"]["user"]
                    stats["created_at"] = u.get(
                        "createdAt", stats["created_at"]
                    )
                    stats["location"] = u.get("location") or stats["location"]
                    stats["followers"] = str(
                        u.get("followers", {}).get("totalCount", 0)
                    )
                    stats["following"] = str(
                        u.get("following", {}).get("totalCount", 0)
                    )

                    repos_data = u.get("repositories", {})
                    stats["repos"] = str(repos_data.get("totalCount", 0))
                    total_stars = sum(
                        node.get("stargazerCount", 0)
                        for node in repos_data.get("nodes", [])
                    )
                    stats["stars"] = str(total_stars)

                    stats["contributed_repos"] = str(
                        u.get("repositoriesContributedTo", {}).get(
                            "totalCount", 0
                        )
                    )

                    cc = u.get("contributionsCollection", {})
                    total_commits = cc.get("totalCommitContributions", 0)
                    restricted = cc.get("restrictedContributionsCount", 0)
                    calendar_total = cc.get("contributionCalendar", {}).get(
                        "totalContributions", 0
                    )
                    commit_count = max(
                        total_commits + restricted, calendar_total
                    )
                    stats["commits"] = f"{commit_count:,}"
                    return stats
        except Exception as e:
            print(f"GraphQL fetch failed ({e}), falling back to REST API...")

    # Fallback to public REST API
    try:
        user_url = f"https://api.github.com/users/{username}"
        headers = {"User-Agent": "GitHub-Profile-Card-Generator"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        req = urllib.request.Request(user_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            u = json.loads(resp.read().decode())
            stats["created_at"] = u.get("created_at", stats["created_at"])
            stats["location"] = u.get("location") or stats["location"]
            stats["repos"] = str(u.get("public_repos", 0))
            stats["followers"] = str(u.get("followers", 0))
            stats["following"] = str(u.get("following", 0))

        repos_url = f"https://api.github.com/users/{username}/repos?per_page=100"
        req = urllib.request.Request(repos_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            repos = json.loads(resp.read().decode())
            stats["stars"] = str(
                sum(r.get("stargazers_count", 0) for r in repos)
            )
    except Exception as e:
        print(f"REST API fetch error ({e}), using default/cached stats...")

    return stats


def format_row(section, stats, colors, total_width=58):
    """Formats a single config row into SVG tspan elements."""
    stype = section.get("type")

    if stype == "header":
        title = section.get("title", "")
        # Format: ─ title ─────────────────────────
        prefix = "─ "
        title_str = f"{title} "
        remaining = total_width - len(prefix) - len(title_str)
        dashes = "─" * max(remaining, 0)
        return (
            f'<tspan fill="{colors["header_line"]}">{html.escape(prefix)}</tspan>'
            f'<tspan fill="{colors["header_title"]}">{html.escape(title_str)}</tspan>'
            f'<tspan fill="{colors["header_line"]}">{html.escape(dashes)}</tspan>'
        )

    elif stype in ("kv", "dynamic_uptime"):
        key = section.get("key", "")
        if stype == "dynamic_uptime":
            value = calculate_uptime(stats["created_at"])
        else:
            value = section.get("value", "")

        prefix = f". {key}: "
        val_str = f" {value}"
        dots_count = total_width - len(prefix) - len(val_str)
        if dots_count < 2:
            dots_count = 2
        dots = "." * dots_count

        return (
            f'<tspan fill="{colors["key"]}">{html.escape(prefix)}</tspan>'
            f'<tspan fill="{colors["dots"]}">{html.escape(dots)}</tspan>'
            f'<tspan fill="{colors["value"]}">{html.escape(val_str)}</tspan>'
        )

    elif stype == "dual_stat":
        left_key = section["left"]["key"]
        left_stat_name = section["left"]["stat"]
        left_val = stats.get(left_stat_name, "0")

        right_key = section["right"]["key"]
        right_stat_name = section["right"]["stat"]
        right_val = stats.get(right_stat_name, "0")

        # Total width = 58, separator = " | " (3 chars) -> 55 remaining -> left 27, right 28
        left_prefix = f". {left_key}: "
        left_val_str = f" {left_val}"
        left_dots_count = max(27 - len(left_prefix) - len(left_val_str), 2)
        left_dots = "." * left_dots_count

        right_prefix = f". {right_key}: "
        right_val_str = f" {right_val}"
        right_dots_count = max(28 - len(right_prefix) - len(right_val_str), 2)
        right_dots = "." * right_dots_count

        return (
            f'<tspan fill="{colors["key"]}">{html.escape(left_prefix)}</tspan>'
            f'<tspan fill="{colors["dots"]}">{html.escape(left_dots)}</tspan>'
            f'<tspan fill="{colors["stat"]}">{html.escape(left_val_str)}</tspan>'
            f'<tspan fill="{colors["pipe"]}"> | </tspan>'
            f'<tspan fill="{colors["key"]}">{html.escape(right_prefix)}</tspan>'
            f'<tspan fill="{colors["dots"]}">{html.escape(right_dots)}</tspan>'
            f'<tspan fill="{colors["stat"]}">{html.escape(right_val_str)}</tspan>'
        )

    elif stype == "blank":
        return f'<tspan fill="{colors["dots"]}">.</tspan>'

    return ""


def build_svg(theme, config, stats, ascii_lines):
    """Constructs the complete SVG card for dark or light theme."""
    is_dark = theme == "dark"

    colors = {
        "bg": "#0d1117" if is_dark else "#ffffff",
        "border": "#30363d" if is_dark else "#d0d7de",
        "ascii": "#c9d1d9" if is_dark else "#24292f",
        "header_line": "#3d444d" if is_dark else "#d0d7de",
        "header_title": "#58a6ff" if is_dark else "#0969da",
        "key": "#ffa657" if is_dark else "#953800",
        "dots": "#484f58" if is_dark else "#8c959f",
        "value": "#c9d1d9" if is_dark else "#24292f",
        "stat": "#79c0ff" if is_dark else "#0550ae",
        "pipe": "#3d444d" if is_dark else "#d0d7de",
    }

    svg = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1317" height="728" viewBox="0 0 1317 728" role="img" aria-label="ASCII GitHub profile card for {html.escape(config["username"])}">'
    )
    svg.append(
        f'  <rect x="0.5" y="0.5" width="1316" height="727" rx="8" fill="{colors["bg"]}" stroke="{colors["border"]}"/>'
    )

    # Render Left Column: ASCII Portrait (70 lines)
    for i, line in enumerate(ascii_lines):
        y = round(34.6 + i * 9.6, 2)
        svg.append(
            f'  <text x="28" y="{y}" fill="{colors["ascii"]}" font-family="\'Consolas\', \'Menlo\', \'DejaVu Sans Mono\', monospace" xml:space="preserve" font-size="8">{html.escape(line)}</text>'
        )

    # Render Right Column: Terminal Info Rows
    sections = config.get("sections", [])
    line_height = 24
    total_height = len(sections) * line_height
    start_y = max(round((728 - total_height) / 2 + 14), 60)

    for i, sec in enumerate(sections):
        y = start_y + i * line_height
        row_content = format_row(sec, stats, colors)
        if row_content:
            svg.append(
                f'  <text x="732" y="{y}" font-family="\'Consolas\', \'Menlo\', \'DejaVu Sans Mono\', monospace" xml:space="preserve" font-size="16">{row_content}</text>'
            )

    svg.append("</svg>")
    return "\n".join(svg)


def main():
    config_path = "profile_config.json"
    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found!")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    print(
        f"Fetching dynamic stats for {config['username']} (Token present: {bool(token)})..."
    )
    stats = fetch_github_stats(config["username"], token=token)
    print("Stats fetched:", json.dumps(stats, indent=2))

    # Load ASCII assets
    dark_asset = "assets/ascii_dark.txt"
    light_asset = "assets/ascii_light.txt"

    with open(dark_asset, "r", encoding="utf-8") as f:
        dark_ascii = [line.rstrip("\r\n") for line in f]

    with open(light_asset, "r", encoding="utf-8") as f:
        light_ascii = [line.rstrip("\r\n") for line in f]

    # Generate SVGs
    dark_svg = build_svg("dark", config, stats, dark_ascii)
    light_svg = build_svg("light", config, stats, light_ascii)

    with open("dark_mode.svg", "w", encoding="utf-8") as f:
        f.write(dark_svg)

    with open("light_mode.svg", "w", encoding="utf-8") as f:
        f.write(light_svg)

    print("Successfully generated dark_mode.svg and light_mode.svg!")


if __name__ == "__main__":
    main()
