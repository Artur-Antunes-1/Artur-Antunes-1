"""Render a small animated skyline from the owner's real GitHub calendar."""
import calendar as months
import html
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys
from datetime import date

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date weekday contributionCount contributionLevel }
        }
      }
    }
  }
}
"""
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
ROOT = Path(__file__).resolve().parents[1]


def read_calendar(login):
    result = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={QUERY}", "-f", f"login={login}"],
        check=True, capture_output=True, text=True, encoding="utf-8"
    )
    payload = json.loads(result.stdout)
    if payload.get("errors"):
        raise ValueError("GitHub could not return the contribution calendar")
    return payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def validate(calendar):
    days = [day for week in calendar["weeks"] for day in week["contributionDays"]]
    dates = [date.fromisoformat(day["date"]) for day in days]
    if not dates or len(set(dates)) != len(dates):
        raise ValueError("Empty calendar or duplicate dates")
    if dates != sorted(dates) or (dates[-1] - dates[0]).days + 1 != len(dates):
        raise ValueError("The calendar must contain consecutive dates")
    for day, stamp in zip(days, dates):
        if day["contributionCount"] < 0 or day["contributionLevel"] not in LEVELS:
            raise ValueError("Invalid contribution count or level")
        if day["weekday"] != (stamp.weekday() + 1) % 7:
            raise ValueError("Weekday does not match its date")
    if sum(day["contributionCount"] for day in days) != calendar["totalContributions"]:
        raise ValueError("Contribution counts do not match GitHub's total")
    return days


def shade(color, factor):
    return "#" + "".join(f"{round(int(color[i:i + 2], 16) * factor):02x}" for i in (1, 3, 5))


def points(vertices):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in vertices)


def render(calendar, login, dark):
    days = validate(calendar)
    total = calendar["totalContributions"]
    active = sum(day["contributionCount"] > 0 for day in days)
    longest = streak = 0
    for day in days:
        streak = streak + 1 if day["contributionCount"] else 0
        longest = max(longest, streak)
    bg, ink, muted, border = (("#0d1117", "#e6edf3", "#8b949e", "#30363d") if dark
                               else ("#ffffff", "#1f2328", "#59636e", "#d1d9e0"))
    palette = (["#1b2530", "#155e59", "#0d9488", "#2dd4bf", "#a7f3d0"] if dark
               else ["#e8eef0", "#99d5c8", "#42b7a0", "#168c77", "#065f46"])
    period = f'{days[0]["date"]} to {days[-1]["date"]}'
    width, height = 820, 320
    output = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">',
        '<title id="title">Artur: contribution landscape</title>',
        f'<desc id="description">{html.escape(login)}. {total} GitHub contributions over {len(days)} days, {period}. {active} active days. Longest streak: {longest} days. Height and color represent GitHub contribution levels. A gentle light wave crosses the calendar.</desc>',
        '<style>.shine{opacity:0;animation:wave 14s linear infinite}@keyframes wave{0%,8%,100%{opacity:0}4%{opacity:.62}}@media(prefers-reduced-motion:reduce){.shine{animation:none!important}}</style>',
        f'<rect x=".5" y=".5" width="819" height="319" rx="16" fill="{bg}" stroke="{border}"/>',
        f'<g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" fill="{ink}">',
        f'<text x="32" y="33" font-size="11" letter-spacing="2" fill="{muted}">A YEAR IN BUILDING</text>',
        f'<text x="30" y="80" font-size="40" font-weight="650">{total:,}</text>',
        f'<text x="32" y="103" font-size="12" fill="{muted}">GitHub contributions</text>',
        f'<text x="586" y="56" font-size="24" font-weight="600">{active}</text>',
        f'<text x="586" y="78" font-size="11" fill="{muted}">ACTIVE DAYS</text>',
        f'<text x="703" y="56" font-size="24" font-weight="600">{longest}</text>',
        f'<text x="703" y="78" font-size="11" fill="{muted}">BEST STREAK</text>',
    ]
    columns = max(1, len(calendar["weeks"]) - 1)
    step = 650 / columns
    tiles, labels = [], []
    previous_month = None
    for week_index, week in enumerate(calendar["weeks"]):
        for day in week["contributionDays"]:
            dow = day["weekday"]
            x, y = 46 + week_index * step + dow * 7, 198 - week_index * .65 + dow * 5
            level = LEVELS[day["contributionLevel"]]
            altitude = [1.5, 9, 20, 33, 48][level]
            color = palette[level]
            a = (x, y - altitude)
            b = (x + step * .83, y - .55 - altitude)
            c = (b[0] + 5.6, b[1] + 4)
            d = (x + 5.6, y + 4 - altitude)
            lower = lambda point: (point[0], point[1] + altitude)
            tile = [
                f'<g data-date="{day["date"]}" data-count="{day["contributionCount"]}" data-level="{level}">',
                f'<title>{day["date"]}: {day["contributionCount"]} contributions</title>',
                f'<polygon points="{points([a, d, lower(d), lower(a)])}" fill="{shade(color, .56)}"/>',
                f'<polygon points="{points([d, c, lower(c), lower(d)])}" fill="{shade(color, .76)}"/>',
                f'<polygon points="{points([a, b, c, d])}" fill="{color}"/>',
            ]
            if level:
                delay = -14 + week_index * .18 + dow * .04
                tile.append(f'<polygon class="shine" style="animation-delay:{delay:.2f}s" points="{points([a, b, c, d])}" fill="#e2fff7"/>')
            tile.append("</g>")
            tiles.append((y, "".join(tile)))
        first = date.fromisoformat(week["contributionDays"][0]["date"])
        if first.month != previous_month:
            lx, ly = 89 + week_index * step, 251 - week_index * .65
            label = months.month_abbr[first.month]
            labels.append(f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="10" fill="{muted}">{label}</text>')
            previous_month = first.month
    output.extend(tile for _, tile in sorted(tiles))
    output.extend(labels)
    output.append(f'<path d="M32 271H788" stroke="{border}"/>')
    output.append(f'<text x="32" y="295" font-size="11" fill="{muted}">{period}</text>')
    output.append(f'<text x="599" y="296" font-size="10" fill="{muted}">Less</text>')
    for index, color in enumerate(palette):
        output.append(f'<rect x="{629 + index * 18}" y="286" width="12" height="12" rx="2" fill="{color}"/>')
    output.append(f'<text x="726" y="296" font-size="10" fill="{muted}">More</text>')
    output.extend(["</g>", "</svg>"])
    return "\n".join(output) + "\n"


def refresh_image_references(text, login, revision):
    for theme in ('dark', 'light'):
        url = f'https://raw.githubusercontent.com/{login}/{login}/main/assets/contributions-{theme}.svg'
        pattern = re.escape(url) + r'(?:\?v=[a-f0-9]+)?(?=["\s)])'
        text = re.sub(pattern, lambda _: f'{url}?v={revision}', text)
    return text


def main():
    login = sys.argv[1] if len(sys.argv) > 1 else "Artur-Antunes-1"
    calendar = read_calendar(login)
    days = validate(calendar)
    rendered = {theme: render(calendar, login, theme == "dark") for theme in ("dark", "light")}
    revision = hashlib.sha256(''.join(rendered.values()).encode('utf-8')).hexdigest()[:12]
    destination = ROOT / "assets"
    destination.mkdir(exist_ok=True)
    for theme, svg in rendered.items():
        target = destination / f"contributions-{theme}.svg"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(svg, encoding="utf-8")
        temporary.replace(target)
    readme_path = ROOT / 'README.md'
    if readme_path.is_file():
        original = readme_path.read_text(encoding='utf-8')
        updated = refresh_image_references(original, login, revision)
        if updated != original:
            readme_path.write_text(updated, encoding='utf-8')
    print(json.dumps({"user": login, "days": len(days),
                      "totalContributions": calendar["totalContributions"],
                      "firstDate": days[0]["date"], "lastDate": days[-1]["date"],
                      "imageRevision": revision}))


if __name__ == "__main__":
    main()
