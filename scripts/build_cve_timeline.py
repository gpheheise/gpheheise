#!/usr/bin/env python3
import collections
import datetime
import pathlib
import re
import urllib.request

CVE_LIST_URL = "https://raw.githubusercontent.com/gpheheise/All-Awareded-CVE-List/main/README.md"


def main() -> None:
    out_dir = pathlib.Path("assets")
    out_dir.mkdir(parents=True, exist_ok=True)

    md = urllib.request.urlopen(CVE_LIST_URL, timeout=30).read().decode("utf-8", errors="replace")

    # Awarded CVEs (with year)
    awarded_years = [int(y) for y in re.findall(r"\bCVE-(\d{4})-\d{4,}\b", md)]
    awarded_by_year = collections.Counter(awarded_years)

    # Pending CVEs (no year info in list -> attribute to current year)
    pending_count = len(re.findall(r"\bCVE-PENDING\b", md))
    current_year = datetime.date.today().year
    pending_by_year = collections.Counter({current_year: pending_count})

    # Years range
    all_years = sorted(set(awarded_by_year.keys()) | set(pending_by_year.keys()) | {current_year})
    min_y, max_y = min(all_years), max(all_years)
    years = list(range(min_y, max_y + 1))

    # Make it BIG
    W, H = 1600, 420
    pad_l, pad_r = 90, 90
    pad_t = 32

    base_y = 320              # baseline for bars
    bar_area_h = 190          # max stack height

    # Slot sizing
    n = max(1, len(years))
    slot_w = (W - pad_l - pad_r) / n
    bar_w = slot_w * 0.62     # fat bars (key for readability)

    # Scale by per-year TOTAL (awarded + pending)
    max_total = max((awarded_by_year.get(y, 0) + pending_by_year.get(y, 0)) for y in years) or 1

    total_awarded = sum(awarded_by_year.values())
    total_pending = pending_count

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
    svg.append("<defs>")
    svg.append("""
<style>
  .bg { fill:#000; }
  .title { font-family:Consolas, Monaco, "Courier New", monospace; fill:#00ff41; font-size:26px; font-weight:800; }
  .sub { font-family:Consolas, Monaco, "Courier New", monospace; fill:#00ff41; font-size:16px; opacity:0.90; }
  .axis { stroke:#00ff41; stroke-width:2; opacity:0.35; }
  .grid { stroke:#00ff41; stroke-width:1; opacity:0.12; }
  .year { font-family:Consolas, Monaco, "Courier New", monospace; fill:#00ff41; font-size:16px; opacity:0.92; }
  .awarded { fill:#ff0033; opacity:0.92; }
  .pending { fill:#1e90ff; opacity:0.92; }
  .legend { font-family:Consolas, Monaco, "Courier New", monospace; fill:#00ff41; font-size:14px; opacity:0.92; }
</style>
""".strip())
    svg.append("</defs>")

    # Background
    svg.append(f'<rect class="bg" x="0" y="0" width="{W}" height="{H}"/>')

    # Header
    svg.append(f'<text class="title" x="{pad_l}" y="{pad_t + 28}">CVE TIMELINE :: SECURITY RESEARCH</text>')
    svg.append(f'<text class="sub" x="{pad_l}" y="{pad_t + 56}">&gt; Awarded: {total_awarded} | Pending: {total_pending}</text>')

    # Grid + axis
    for k in range(1, 4):
        y = base_y - (bar_area_h * k / 4)
        svg.append(f'<line class="grid" x1="{pad_l}" y1="{y:.2f}" x2="{W-pad_r}" y2="{y:.2f}"/>')
    svg.append(f'<line class="axis" x1="{pad_l}" y1="{base_y}" x2="{W-pad_r}" y2="{base_y}"/>')

    # Bars
    for i, year in enumerate(years):
        awarded = awarded_by_year.get(year, 0)
        pending = pending_by_year.get(year, 0)
        total = awarded + pending

        # Slot center
        x_center = pad_l + i * slot_w + slot_w / 2
        x = x_center - bar_w / 2

        # Heights (stacked)
        h_total = (total / max_total) * bar_area_h
        h_awarded = (awarded / max_total) * bar_area_h
        h_pending = (pending / max_total) * bar_area_h

        # Draw awarded at bottom, pending on top (both above baseline)
        y_awarded = base_y - h_awarded
        y_pending = y_awarded - h_pending

        if h_awarded > 0:
            svg.append(f'<rect class="awarded" x="{x:.2f}" y="{y_awarded:.2f}" width="{bar_w:.2f}" height="{h_awarded:.2f}"/>')
        if h_pending > 0:
            svg.append(f'<rect class="pending" x="{x:.2f}" y="{y_pending:.2f}" width="{bar_w:.2f}" height="{h_pending:.2f}"/>')

        # YEAR: directly under the BAR (centered on bar)
        svg.append(f'<text class="year" x="{x_center:.2f}" y="{base_y + 38}" text-anchor="middle">{year}</text>')

    # Legend (top right)
    lx = W - pad_r - 270
    ly = pad_t + 18
    svg.append(f'<rect class="awarded" x="{lx}" y="{ly}" width="16" height="16"/>')
    svg.append(f'<text class="legend" x="{lx + 26}" y="{ly + 13}">AWARDED</text>')
    svg.append(f'<rect class="pending" x="{lx + 140}" y="{ly}" width="16" height="16"/>')
    svg.append(f'<text class="legend" x="{lx + 166}" y="{ly + 13}">PENDING</text>')

    svg.append("</svg>")

    out_file = out_dir / "cve-timeline.svg"
    out_file.write_text("\n".join(svg), encoding="utf-8")
    print(f"Wrote {out_file}")


if __name__ == "__main__":
    main()
