#!/usr/bin/env python3
"""
Generate a Markdown profile snapshot for a GitHub user.

Usage:
  python generate_github_user_info.py <github_username> [--out GITHUB_USER_INFO.md]

Optionally set GH_TOKEN env var for higher rate limits and better stability.
"""
import argparse
import datetime
import os
import sys
import textwrap
from typing import List, Dict, Any, Optional

import requests

API_BASE = "https://api.github.com"


def gh_get(url: str, params: Optional[dict] = None) -> requests.Response:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.get(url, headers=headers, params=params, timeout=30)
    if r.status_code == 404:
        raise SystemExit(f"❌ Not found: {url}")
    if r.status_code == 403 and "rate limit" in r.text.lower():
        rl = r.headers.get("X-RateLimit-Remaining", "?")
        rst = r.headers.get("X-RateLimit-Reset", "?")
        raise SystemExit(f"❌ Rate limited (remaining={rl}, reset={rst}). Provide GH_TOKEN.")
    r.raise_for_status()
    return r


def fetch_user(username: str) -> Dict[str, Any]:
    return gh_get(f"{API_BASE}/users/{username}").json()


def fetch_repos(username: str) -> List[Dict[str, Any]]:
    repos = []
    page = 1
    # Public repos only; if you need orgs too, you can expand this.
    while True:
        r = gh_get(f"{API_BASE}/users/{username}/repos", params={"per_page": 100, "page": page, "type": "owner", "sort": "updated"})
        batch = r.json()
        if not batch:
            break
        repos.extend(batch)
        page += 1
        if page > 10:  # Safety stop for extremely large accounts
            break
    return repos


def md_link(text: str, url: Optional[str]) -> str:
    if not url:
        return text
    return f"[{text}]({url})"


def truncate(s: Optional[str], n: int = 120) -> str:
    if not s:
        return ""
    s = " ".join(s.split())
    return (s[: n - 1] + "…") if len(s) > n else s


def top_repos_by_stars(repos: List[Dict[str, Any]], n: int = 6) -> List[Dict[str, Any]]:
    # Filter out forks by default; change if you want to include them
    own = [r for r in repos if not r.get("fork")]
    own.sort(key=lambda r: (r.get("stargazers_count", 0), r.get("forks_count", 0)), reverse=True)
    return own[:n]


def repos_table_rows(repos: List[Dict[str, Any]], n: int = 8) -> List[str]:
    # Show a quick overview table by stars
    rows = []
    for r in top_repos_by_stars(repos, n):
        name = r.get("name", "")
        html_url = r.get("html_url")
        stars = r.get("stargazers_count", 0)
        forks = r.get("forks_count", 0)
        desc = truncate(r.get("description") or "", 80)
        rows.append(f"| {md_link(name, html_url)} | {stars} | {forks} | {desc} |")
    if not rows:
        rows.append("| – | – | – | No repositories found |")
    return rows


def recent_activity_hint(repos: List[Dict[str, Any]]) -> str:
    # Heuristic: repo with most recent push
    if not repos:
        return "No public activity found."
    latest = sorted(repos, key=lambda r: r.get("pushed_at") or r.get("updated_at") or "", reverse=True)[0]
    pushed = latest.get("pushed_at") or latest.get("updated_at") or ""
    name = latest.get("name", "")
    url = latest.get("html_url", "")
    return f"Latest push: **{pushed[:10]}** to {md_link(name, url)}"


def build_markdown(user: Dict[str, Any], repos: List[Dict[str, Any]]) -> str:
    username = user.get("login", "")
    name = user.get("name") or ""
    location = user.get("location") or ""
    blog = user.get("blog") or ""
    email = user.get("email") or ""
    created_at = (user.get("created_at") or "")[:10]
    public_repos = user.get("public_repos", 0)
    followers = user.get("followers", 0)
    following = user.get("following", 0)
    public_gists = user.get("public_gists", 0)
    profile_url = user.get("html_url", f"https://github.com/{username}")

    pinned_rows = repos_table_rows(repos, n=6)
    activity = recent_activity_hint(repos)

    today = datetime.date.today().isoformat()

    md = f"""# GitHub User Information

## 👤 Profile
- **Username:** `{username}` ({md_link("view profile", profile_url)})
- **Full Name:** {name or "–"}
- **Location:** {location or "–"}
- **Website/Portfolio:** {md_link(blog, blog) if blog else "–"}
- **Email:** {email or "–"}
- **Joined GitHub:** {created_at or "–"}

## 📊 Stats
- **Public Repositories:** {public_repos}
- **Followers:** {followers}
- **Following:** {following}
- **Gists:** {public_gists}

## 📈 Activity
- {activity}

## 📂 Top Repositories (by ⭐)
| Repository | Stars ⭐ | Forks 🍴 | Description |
|------------|---------:|---------:|-------------|
{chr(10).join(pinned_rows)}

---
*Generated: {today}*
"""
    return textwrap.dedent(md).strip() + "\n"


def main():
    parser = argparse.ArgumentParser(description="Generate a GitHub user info markdown.")
    parser.add_argument("username", help="GitHub username (e.g., torvalds)")
    parser.add_argument("--out", default="GITHUB_USER_INFO.md", help="Output markdown file path")
    args = parser.parse_args()

    try:
        user = fetch_user(args.username)
        repos = fetch_repos(args.username)
        md = build_markdown(user, repos)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"✅ Wrote {args.out} for user '{args.username}'")
    except requests.HTTPError as e:
        print(f"❌ HTTP error: {e} - {getattr(e.response, 'text', '')[:200]}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
