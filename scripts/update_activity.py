import os
import json
import math
import urllib.request
from datetime import datetime
from pathlib import Path

QUERY = """
query {
  user(login: "sudosz") {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            color
          }
        }
      }
    }
  }
}
"""

def fetch_contributions(token: str) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "sudosz-activity-updater",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def generate_activity_svg(cal_data: dict, output_svg_path: str):
    cal = cal_data["totalContributions"] if "totalContributions" in cal_data else cal_data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    if isinstance(cal, dict) and "totalContributions" in cal:
        total_contributions = cal["totalContributions"]
        weeks = cal["weeks"]
    else:
        # nested
        root = cal_data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        total_contributions = root["totalContributions"]
        weeks = root["weeks"]

    weekly_data = []
    for w in weeks:
        count = sum(d["contributionCount"] for d in w["contributionDays"])
        start_date = w["contributionDays"][0]["date"]
        weekly_data.append({"date": start_date, "count": count})

    counts = [w["count"] for w in weekly_data]
    max_count = max(counts) if counts else 1
    grid_max = math.ceil(max_count / 50.0) * 50
    if grid_max < 100:
        grid_max = 100

    active_weeks = sum(1 for c in counts if c > 0)
    avg_active = (total_contributions / active_weeks) if active_weeks > 0 else 0

    W, H = 850, 340
    chart_x1, chart_x2 = 65, 805
    chart_y1, chart_y2 = 90, 270
    chart_w = chart_x2 - chart_x1
    chart_h = chart_y2 - chart_y1

    n = len(weekly_data)
    points = []
    for i, w in enumerate(weekly_data):
        x = chart_x1 + (i / (n - 1)) * chart_w
        val = w["count"]
        y = chart_y2 - (val / grid_max) * chart_h
        points.append((x, y))

    def get_spline_path(pts):
        if not pts:
            return ""
        if len(pts) == 1:
            return f"M {pts[0][0]} {pts[0][1]}"

        d = [f"M {pts[0][0]:.2f} {pts[0][1]:.2f}"]
        for i in range(len(pts) - 1):
            p0 = pts[i - 1] if i > 0 else pts[i]
            p1 = pts[i]
            p2 = pts[i + 1]
            p3 = pts[i + 2] if i + 2 < len(pts) else p2

            cp1x = p1[0] + (p2[0] - p0[0]) / 6.0
            cp1y = p1[1] + (p2[1] - p0[1]) / 6.0
            cp2x = p2[0] - (p3[0] - p1[0]) / 6.0
            cp2y = p2[1] - (p3[1] - p1[1]) / 6.0

            cp1y = min(chart_y2, max(chart_y1 - 10, cp1y))
            cp2y = min(chart_y2, max(chart_y1 - 10, cp2y))

            d.append(f"C {cp1x:.2f} {cp1y:.2f}, {cp2x:.2f} {cp2y:.2f}, {p2[0]:.2f} {p2[1]:.2f}")
        return " ".join(d)

    line_d = get_spline_path(points)
    area_d = f"{line_d} L {points[-1][0]:.2f} {chart_y2:.2f} L {points[0][0]:.2f} {chart_y2:.2f} Z"

    grid_steps = 4
    grid_lines = []
    for step in range(grid_steps + 1):
        frac = step / grid_steps
        y = chart_y2 - frac * chart_h
        val = int(frac * grid_max)
        grid_lines.append((y, val))

    month_labels = []
    seen_months = set()
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for i, w in enumerate(weekly_data):
        dt = datetime.strptime(w["date"], "%Y-%m-%d")
        m_key = (dt.year, dt.month)
        if m_key not in seen_months:
            seen_months.add(m_key)
            x = chart_x1 + (i / (n - 1)) * chart_w
            month_labels.append((x, month_names[dt.month - 1]))

    max_idx = counts.index(max_count)
    peak_x, peak_y = points[max_idx]

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <defs>
    <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#4ade80" stop-opacity="0.32" />
      <stop offset="70%" stop-color="#4ade80" stop-opacity="0.06" />
      <stop offset="100%" stop-color="#4ade80" stop-opacity="0.0" />
    </linearGradient>
  </defs>

  <style>
    .bg {{ fill: #0a0a0a; }}
    .border {{ stroke: #222222; stroke-width: 1; fill: none; }}
    .header-title {{ fill: #f4f4f5; font-family: ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, monospace; font-size: 13px; font-weight: 600; letter-spacing: 0.5px; }}
    .header-sub {{ fill: #a1a1aa; font-family: ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, monospace; font-size: 12px; }}
    .grid-line {{ stroke: #191919; stroke-width: 1; stroke-dasharray: 3 3; }}
    .axis-label {{ fill: #52525b; font-family: ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, monospace; font-size: 10px; text-anchor: end; }}
    .month-label {{ fill: #71717a; font-family: ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, monospace; font-size: 11px; text-anchor: middle; }}
    .chart-line {{ fill: none; stroke: #4ade80; stroke-width: 2.25; stroke-linecap: round; stroke-linejoin: round; }}
    .chart-area {{ fill: url(#areaGradient); }}
    .footer-text {{ fill: #52525b; font-family: ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, monospace; font-size: 11px; }}
    .peak-text {{ fill: #4ade80; font-family: ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, monospace; font-size: 10px; font-weight: 600; }}
  </style>

  <rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="8" class="bg border" />

  <circle cx="28" cy="38" r="4" fill="#4ade80" />
  <text x="42" y="42" class="header-title">ACTIVITY GRAPH  <tspan fill="#52525b">//</tspan>  sudosz</text>
  <text x="{W - 28}" y="42" class="header-sub" text-anchor="end">{total_contributions:,} CONTRIBUTIONS IN PAST YEAR</text>

  <line x1="20" y1="64" x2="{W - 20}" y2="64" stroke="#1c1c1c" stroke-width="1" />
"""

    for y, val in grid_lines:
        svg += f"""  <line x1="{chart_x1}" y1="{y:.1f}" x2="{chart_x2}" y2="{y:.1f}" class="grid-line" />
  <text x="{chart_x1 - 10}" y="{y + 3.5:.1f}" class="axis-label">{val}</text>
"""

    svg += f"""
  <path d="{area_d}" class="chart-area" />
  <path d="{line_d}" class="chart-line" />

  <circle cx="{peak_x:.2f}" cy="{peak_y:.2f}" r="4" fill="#4ade80" stroke="#0a0a0a" stroke-width="2" />
  <text x="{peak_x:.2f}" y="{peak_y - 10:.2f}" class="peak-text" text-anchor="middle">PEAK: {max_count}/wk</text>
"""

    for x, mname in month_labels:
        svg += f"""  <text x="{x:.1f}" y="296" class="month-label">{mname}</text>
"""

    svg += f"""
  <line x1="20" y1="310" x2="{W - 20}" y2="310" stroke="#181818" stroke-width="1" />
  <text x="28" y="327" class="footer-text">ACTIVE WEEKS: {active_weeks}/{n} ({int(active_weeks/n*100)}%)   ·   PEAK: {max_count} COMMITS/WK   ·   AVG/ACTIVE: {avg_active:.1f} COMMITS</text>
  <text x="{W - 28}" y="327" class="footer-text" text-anchor="end">SOURCE: GITHUB GRAPHQL API</text>
</svg>
"""

    Path(output_svg_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_svg_path, "w") as f:
        f.write(svg)
    print(f"Updated {output_svg_path}")

def main():
    token = os.environ.get("GITHUB_TOKEN")
    root_dir = Path(__file__).resolve().parent.parent
    svg_path = root_dir / "activity-graph.svg"
    cached_json = root_dir / ".cache" / "contributions.json"

    if token:
        print("Fetching fresh contributions via GitHub GraphQL API...")
        data = fetch_contributions(token)
        cached_json.parent.mkdir(parents=True, exist_ok=True)
        with open(cached_json, "w") as f:
            json.dump(data, f, indent=2)
    elif cached_json.exists():
        print(f"Using cached JSON: {cached_json}")
        with open(cached_json) as f:
            data = json.load(f)
    else:
        # Fallback to scratch data if available
        scratch = Path("/home/sina/.gemini/antigravity/brain/6eb2f4f4-ad9b-4ced-ae9b-7a9cb948dae4/scratch/contributions.json")
        if scratch.exists():
            with open(scratch) as f:
                data = json.load(f)
        else:
            raise RuntimeError("No GITHUB_TOKEN or cached contributions JSON found.")

    generate_activity_svg(data, str(svg_path))

if __name__ == "__main__":
    main()
