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
        "commits": "202+",
        "followers": "1",
        "following": "2",
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


def wrap_text_into_chunks(text, max_len):
    """Splits comma-separated or space-separated items into lines of max_len."""
    if len(text) <= max_len:
        return [text]

    parts = [p.strip() for p in text.split(",")]
    lines = []
    current_line = []
    current_len = 0

    for part in parts:
        added_len = len(part) + (2 if current_line else 0)
        if current_line and (current_len + added_len > max_len):
            lines.append(", ".join(current_line))
            current_line = [part]
            current_len = len(part)
        else:
            current_line.append(part)
            current_len += added_len

    if current_line:
        lines.append(", ".join(current_line))

    return lines


def format_rows(sections, stats, colors, total_width=72):
    """Formats config sections into list of rendered SVG row strings with multiline support."""
    rendered_rows = []

    for sec in sections:
        stype = sec.get("type")

        if stype == "header":
            title = sec.get("title", "")
            prefix = "─ "
            title_str = f"{title} "
            remaining = total_width - len(prefix) - len(title_str)
            dashes = "─" * max(remaining, 0)
            row = (
                f'<tspan fill="{colors["header_line"]}">{html.escape(prefix)}</tspan>'
                f'<tspan fill="{colors["header_title"]}">{html.escape(title_str)}</tspan>'
                f'<tspan fill="{colors["header_line"]}">{html.escape(dashes)}</tspan>'
            )
            rendered_rows.append(row)

        elif stype in ("kv", "dynamic_uptime"):
            key = sec.get("key", "")
            if stype == "dynamic_uptime":
                raw_value = calculate_uptime(stats["created_at"])
            else:
                raw_value = sec.get("value", "")

            prefix = f". {key}: "
            # Minimum 4 dots for clean justification
            available_val_width = total_width - len(prefix) - 4

            if len(raw_value) > available_val_width and "," in raw_value:
                # Wrap value across multiple lines
                chunks = wrap_text_into_chunks(raw_value, available_val_width)
                for idx, chunk in enumerate(chunks):
                    if idx == 0:
                        val_str = f" {chunk}"
                        dots_count = max(
                            total_width - len(prefix) - len(val_str), 3
                        )
                        dots = "." * dots_count
                        row = (
                            f'<tspan fill="{colors["key"]}">{html.escape(prefix)}</tspan>'
                            f'<tspan fill="{colors["dots"]}">{html.escape(dots)}</tspan>'
                            f'<tspan fill="{colors["value"]}">{html.escape(val_str)}</tspan>'
                        )
                    else:
                        indent_prefix = f". {key}: "
                        dots_count = max(
                            total_width - len(indent_prefix) - len(f" {chunk}"),
                            3,
                        )
                        dots = "." * dots_count
                        spaces = " " * len(indent_prefix)
                        row = (
                            f'<tspan fill="{colors["key"]}">{html.escape(spaces)}</tspan>'
                            f'<tspan fill="{colors["dots"]}">{html.escape(dots)}</tspan>'
                            f'<tspan fill="{colors["value"]}"> {html.escape(chunk)}</tspan>'
                        )
                    rendered_rows.append(row)
            else:
                val_str = f" {raw_value}"
                dots_count = max(total_width - len(prefix) - len(val_str), 3)
                dots = "." * dots_count
                row = (
                    f'<tspan fill="{colors["key"]}">{html.escape(prefix)}</tspan>'
                    f'<tspan fill="{colors["dots"]}">{html.escape(dots)}</tspan>'
                    f'<tspan fill="{colors["value"]}">{html.escape(val_str)}</tspan>'
                )
                rendered_rows.append(row)

        elif stype == "dual_stat":
            left_key = sec["left"]["key"]
            left_stat_name = sec["left"]["stat"]
            left_val = stats.get(left_stat_name, "0")

            right_key = sec["right"]["key"]
            right_stat_name = sec["right"]["stat"]
            right_val = stats.get(right_stat_name, "0")

            # Total width = 72, separator = " | " (3 chars) -> 69 remaining -> left 34, right 35
            left_prefix = f". {left_key}: "
            left_val_str = f" {left_val}"
            left_dots_count = max(34 - len(left_prefix) - len(left_val_str), 2)
            left_dots = "." * left_dots_count

            right_prefix = f". {right_key}: "
            right_val_str = f" {right_val}"
            right_dots_count = max(
                35 - len(right_prefix) - len(right_val_str), 2
            )
            right_dots = "." * right_dots_count

            row = (
                f'<tspan fill="{colors["key"]}">{html.escape(left_prefix)}</tspan>'
                f'<tspan fill="{colors["dots"]}">{html.escape(left_dots)}</tspan>'
                f'<tspan fill="{colors["stat"]}">{html.escape(left_val_str)}</tspan>'
                f'<tspan fill="{colors["pipe"]}"> | </tspan>'
                f'<tspan fill="{colors["key"]}">{html.escape(right_prefix)}</tspan>'
                f'<tspan fill="{colors["dots"]}">{html.escape(right_dots)}</tspan>'
                f'<tspan fill="{colors["stat"]}">{html.escape(right_val_str)}</tspan>'
            )
            rendered_rows.append(row)

        elif stype == "blank":
            rendered_rows.append(f'<tspan fill="{colors["dots"]}">.</tspan>')

    return rendered_rows


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

    # Render Right Column: Pulled leftwards to x=580 with width=72 chars
    total_width_chars = 72
    start_x = 580
    line_height = 24

    sections = config.get("sections", [])
    rows = format_rows(sections, stats, colors, total_width=total_width_chars)

    total_height = len(rows) * line_height
    start_y = max(round((728 - total_height) / 2 + 14), 50)

    for i, row_content in enumerate(rows):
        y = start_y + i * line_height
        svg.append(
            f'  <text x="{start_x}" y="{y}" font-family="\'Consolas\', \'Menlo\', \'DejaVu Sans Mono\', monospace" xml:space="preserve" font-size="14.5">{row_content}</text>'
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
