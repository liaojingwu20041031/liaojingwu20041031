#!/usr/bin/env python3
"""生成仓库自托管的 GitHub 主页数据 SVG 面板。"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date contributionCount contributionLevel }
        }
      }
    }
    repositories(
      first: 100
      ownerAffiliations: OWNER
      privacy: PUBLIC
      isFork: false
    ) {
      totalCount
      nodes {
        stargazerCount
        primaryLanguage { name color }
      }
    }
  }
}
"""


THEMES = {
    "light": {
        "background": "#fbfdff",
        "surface": "#eef6ff",
        "border": "#cfe3f6",
        "text": "#172033",
        "muted": "#64748b",
        "accent": "#2563eb",
        "empty": "#edf4fb",
        "levels": ["#dbeafe", "#93c5fd", "#60a5fa", "#2563eb"],
    },
}

LEVEL_INDEX = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}


def fetch_profile(login: str, token: str) -> dict:
    payload = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-metrics-renderer",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"GitHub GraphQL 请求失败：{exc}") from exc

    if result.get("errors"):
        raise RuntimeError(f"GitHub GraphQL 返回错误：{result['errors']}")
    user = result.get("data", {}).get("user")
    if not user:
        raise RuntimeError(f"未找到 GitHub 用户“{login}”")
    return user


def svg_text(x: int, y: int, text: str, size: int, color: str, weight: int = 400) -> str:
    return (
        f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
        f'font-weight="{weight}">{text}</text>'
    )


def render_panel(user: dict, login: str, theme_name: str) -> str:
    theme = THEMES[theme_name]
    repositories = user["repositories"]
    calendar = user["contributionsCollection"]["contributionCalendar"]
    weeks = calendar["weeks"][-52:]
    stars = sum(repo["stargazerCount"] for repo in repositories["nodes"])
    followers = user["followers"]["totalCount"]
    languages = Counter(
        repo["primaryLanguage"]["name"]
        for repo in repositories["nodes"]
        if repo.get("primaryLanguage")
    )
    top_languages = languages.most_common(4)
    language_total = sum(languages.values()) or 1
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    width, height = 960, 330
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" style="font-family:\'Microsoft YaHei\',\'PingFang SC\',\'Noto Sans CJK SC\',\'Segoe UI\',sans-serif;font-variant-numeric:tabular-nums">',
        f"<title>{login} 的 GitHub 工程数据</title>",
        "<desc>公开仓库、项目获星、关注者、年度贡献和主要开发语言分布。</desc>",
        "<defs>",
        f'<linearGradient id="accent" x1="0" x2="1"><stop stop-color="{theme["accent"]}"/><stop offset="1" stop-color="#2da44e"/></linearGradient>',
        "</defs>",
        f'<rect x="0.5" y="0.5" width="959" height="329" rx="18" fill="{theme["background"]}" stroke="{theme["border"]}"/>',
        '<rect x="24" y="22" width="6" height="36" rx="3" fill="url(#accent)"/>',
        svg_text(46, 39, "GITHUB / 工程数据", 12, theme["accent"], 700),
        svg_text(46, 58, f"@{login} · 更新于 {updated} UTC", 12, theme["muted"]),
    ]

    stats = [
        ("年度贡献", calendar["totalContributions"]),
        ("公开仓库", repositories["totalCount"]),
        ("项目获星", stars),
        ("关注者", followers),
    ]
    stat_x = [46, 250, 454, 658]
    for x, (label, value) in zip(stat_x, stats):
        parts.append(svg_text(x, 104, str(value), 30, theme["text"], 700))
        parts.append(svg_text(x, 124, label, 11, theme["muted"], 600))

    parts.extend(
        [
            f'<line x1="46" y1="146" x2="914" y2="146" stroke="{theme["border"]}"/>',
            svg_text(46, 171, "52 周贡献节奏", 10, theme["muted"], 600),
        ]
    )

    cell, gap = 9, 3
    grid_x, grid_y = 46, 191
    month_labels: list[tuple[int, str]] = []
    previous_month = None
    for week_index, week in enumerate(weeks):
        first_date = datetime.strptime(week["contributionDays"][0]["date"], "%Y-%m-%d")
        if first_date.month != previous_month:
            month_labels.append((grid_x + week_index * (cell + gap), f"{first_date.month}月"))
            previous_month = first_date.month
        for day_index, day in enumerate(week["contributionDays"]):
            level = LEVEL_INDEX[day["contributionLevel"]]
            color = theme["empty"] if level == 0 else theme["levels"][level - 1]
            x = grid_x + week_index * (cell + gap)
            y = grid_y + day_index * (cell + gap)
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{color}">'
                f'<title>{day["date"]}: {day["contributionCount"]} contributions</title></rect>'
            )

    last_label_x = -100
    for x, label in month_labels:
        if x < 652 and x - last_label_x >= 30:
            parts.append(svg_text(x, 187, label, 9, theme["muted"], 500))
            last_label_x = x

    language_x = 708
    parts.append(svg_text(language_x, 171, "仓库语言分布", 10, theme["muted"], 600))
    bar_colors = [theme["accent"], "#0891b2", "#4f46e5", "#64748b"]
    for index, (language, count) in enumerate(top_languages):
        y = 198 + index * 29
        ratio = count / language_total
        parts.append(svg_text(language_x, y, language, 11, theme["text"], 600))
        parts.append(svg_text(895, y, f"{round(ratio * 100)}%", 10, theme["muted"], 600))
        parts.append(f'<rect x="{language_x}" y="{y + 7}" width="204" height="5" rx="2.5" fill="{theme["surface"]}"/>')
        parts.append(
            f'<rect x="{language_x}" y="{y + 7}" width="{round(204 * ratio)}" height="5" '
            f'rx="2.5" fill="{bar_colors[index]}"/>'
        )

    parts.append("</svg>")
    return "".join(parts)


def main() -> int:
    login = os.environ.get("PROFILE_USERNAME", "liaojingwu20041031")
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("缺少 GITHUB_TOKEN", file=sys.stderr)
        return 2

    try:
        user = fetch_profile(login, token)
        output_dir = Path("assets")
        output_dir.mkdir(parents=True, exist_ok=True)
        for theme_name in THEMES:
            output = output_dir / f"github-signal-{theme_name}.svg"
            output.write_text(render_panel(user, login, theme_name), encoding="utf-8")
            print(f"已生成 {output}")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
