#!/usr/bin/env python3
import collections
import datetime
import pathlib
import re
import urllib.request


CVE_LIST_URL = "https://raw.githubusercontent.com/gpheheise/All-Awareded-CVE-List/main/README.md"


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def main() -> None:
    out_dir = pathlib.Path("assets")
    out_dir.mkdir(parents=True, exist_ok=True)

    md = urllib.request.urlopen(CVE_LIST_URL, timeout=30).read().decode("utf-8", errors="replace")

    # Awarded CVEs: capture year
    awarded_years = [int(y) for y in re.findall(r"\bCVE-(\d{4})-\d{4,}\b", md)]

    # Pending CVEs: your list uses "CVE-PENDING"
    pending_count = len(re.findall(r"\bCVE-PENDING\b", md))
    current_year = datetime.date.today().year

    awarded_by_year = collections.Counter(awarded_years)
    # If you later encode pending years, change this. For now, assign all pending to current year.
    pending_by_year = collections.Counter({current_year: pending_count})

    all_years = sorted(set(awarded_by_year.keys()) | set(pending_by_year.keys()) | {current_year})
    min_y, max_y = min(all_years), max(all_years)
    years_list = list(range(min_y, max_y + 1))

    # Canvas
    W, H = 1200, 260
    pad_l, pad_r = 70, 70
    pad_t = 22

    base_y = 190          # baseline for bars (x-axis)
    bar_area_h = 110      # max bar height

    # Slot geometry
    n = max(1, len(years_list))
    slot_w = (W - pad_l - pad_r) / n

    # Bar geometry inside a slot:
    # Two bars (pending + awarded) placed side-by-side, centered in slot.
    bar_w = slot_w * 0.26
    gap = slot_w * 0.10
    total_pair_w = 2 * bar_w + gap

    # Scale
    max_val = max(
        [awarded_by_year.get(y, 0) for y in years_list]
        + [pending_by_year.get(y, 0) for y in years_list]
        + [1]
    )

    total_awarded = sum(awarded_by_year.values())
    total_pending = pending_count

    svg: list[str] = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
    svg.append("<defs>")
    svg.append("""
<style>
  .bg { fill: #000; }
  .title { font-family: Consolas, Monaco, "Courier New", monospace; fill: #00ff41; font-size: 20px; font-weight: 700; }
  .sub { font-family: Consolas, Monaco, "Courier New", monospace; fill: #00ff41; font-size: 14px; opacity: 0.85; }
  .axis { stroke: #00ff41; stroke-width: 1; opacity: 0.35; }
  .year { font-family: Consolas, Monaco, "Courier New", monospace; fill: #00ff41; font-size: 12px; opacity: 0.85; }
  .awarded { fill: #ff0033; opacity: 0.92; }
  .pending { fill: #1e90ff; opacity: 0.92; }
  .legend { font-family: Consolas, Monaco, "Courier New", monospace; fill: #00ff41; font-size: 12px; opacity: 0.9; }
</style>
""".strip())
    svg.append("</defs>")

    # Background
    svg.append(f'<rect class="bg" x="0" y="0" width="{W}" height="{H}"/>')

    # Header
    svg.append(f'<text class="title" x="{pad_l}" y="{pad_t + 22}">CVE TIMELINE :: SECURITY RESEARCH</text>')
    svg.append(
        f'<text class="sub" x="{pad_l}" y="{pad_t + 46}">&gt; Awarded: {total_awarded} | Pending: {total_pending}</text>'
    )

    # X axis
    svg.append(f'<line class="axis" x1="{pad_l}" y1="{base_y}" x2="{W - pad_r}" y2="{base_y}"/>')

    # Bars + Years
    for i, year in enumerate(years_list):
        awarded_val = awarded_by_year.get(year, 0)
        pending_val = pending_by_year.get(year, 0)

        # Slot center
        slot_x0 = pad_l + i * slot_w
        x_center = slot_x0 + slot_w / 2

        # Left bar (pending), right bar (awarded)
        pair_left = x_center - total_pair_w / 2
        x_pending = pair_left
        x_awarded = pair_left + bar_w + gap

        # Heights
        h_awarded = (awarded_val / max_val) * bar_area_h
        h_pending = (pending_val / max_val) * bar_area_h

        y_awarded = base_y - h_awarded
        y_pending = base_y - h_pending

        # Draw bars (only if > 0, but safe to draw zero-height too)
        svg.append(
            f'<rect class="pending" x="{x_pending:.2f}" y="{y_pending:.2f}" '
            f'width="{bar_w:.2f}" height="{h_pending:.2f}"/>'
        )
        svg.append(
            f'<rect class="awarded" x="{x_awarded:.2f}" y="{y_awarded:.2f}" '
            f'width="{bar_w:.2f}" height="{h_awarded:.2f}"/>'
        )

        # Year label centered under slot
        svg.append(
            f'<text class="year" x="{x_center:.2f}" y="{base_y + 22}" text-anchor="middle">{year}</text>'
        )

    # Legend (bottom-right)
    lx = W - pad_r - 240
    ly = pad_t + 24
    svg.append(f'<rect class="awarded" x="{lx}" y="{ly}" width="14" height="14"/>')
    svg.append(f'<text class="legend" x="{lx + 22}" y="{ly + 12}">AWARDED</text>')
    svg.append(f'<rect class="pending" x="{lx}" y="{ly + 22}" width="14" height="14"/>')
    svg.append(f'<text class="legend" x="{lx + 22}" y="{ly + 34}">PENDING</text>')

    svg.append("</svg>")

    out_file = out_dir / "cve-timeline.svg"
    out_file.write_text("\n".join(svg), encoding="utf-8")
    print(f"Wrote {out_file}")


if __name__ == "__main__":
    main()
