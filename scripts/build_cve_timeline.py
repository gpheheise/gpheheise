import collections
import datetime
import pathlib
import re
import urllib.request


def main() -> None:
    out_dir = pathlib.Path("assets")
    out_dir.mkdir(parents=True, exist_ok=True)

    url = "https://raw.githubusercontent.com/gpheheise/All-Awareded-CVE-List/main/README.md"
    md = urllib.request.urlopen(url, timeout=30).read().decode("utf-8", errors="replace")

    awarded = re.findall(r"\bCVE-(\d{4})-\d{4,}\b", md)
    pending = re.findall(r"CVE-PENDING", md)

    awarded_years = [int(y) for y in awarded]
    current_year = datetime.date.today().year

    awarded_by_year = collections.Counter(awarded_years)
    pending_by_year = collections.Counter({current_year: len(pending)})

    all_years = sorted(set(awarded_by_year.keys()) | set(pending_by_year.keys()))

    if all_years:
        min_y, max_y = min(all_years), max(all_years)
    else:
        min_y = max_y = current_year

    W, H = 1000, 220
    pad = 60
    bar_h = 90
    base_y = 170

    years_list = list(range(min_y, max_y + 1))

    max_val = max(
        [awarded_by_year.get(y, 0) for y in years_list] +
        [pending_by_year.get(y, 0) for y in years_list] +
        [1]
    )

    bar_w = (W - 2 * pad) / max(1, len(years_list))

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')

    svg.append("<defs><style>")
    svg.append("""
text {
    font-family: Consolas, Monaco, 'Courier New', monospace;
    fill: #00ff41;
}
.small { font-size: 12px; }
.big { font-size: 18px; font-weight: 700; }
.awarded { fill: #ff0033; }
.pending { fill: #0099ff; }
.bg { fill: #000000; }
.axis { stroke: #00ff41; stroke-width: 1; }
.legend { font-size: 12px; fill: #00ff41; }
""")
    svg.append("</style></defs>")

    # Background
    svg.append(f'<rect class="bg" x="0" y="0" width="{W}" height="{H}" />')

    total_awarded = sum(awarded_by_year.values())
    total_pending = len(pending)

    svg.append(f'<text class="big" x="{pad}" y="40">CVE TIMELINE :: SECURITY RESEARCH</text>')
    svg.append(
        f'<text class="small" x="{pad}" y="65">'
        f'> Awarded: {total_awarded}  |  Pending: {total_pending}'
        f'</text>'
    )

    svg.append(f'<line class="axis" x1="{pad}" y1="{base_y}" x2="{W-pad}" y2="{base_y}" />')

    for i, y in enumerate(years_list):
        awarded_val = awarded_by_year.get(y, 0)
        pending_val = pending_by_year.get(y, 0)

        awarded_height = (awarded_val / max_val) * bar_h
        pending_height = (pending_val / max_val) * bar_h

        x = pad + i * bar_w
        half = bar_w / 2

        # Awarded (red)
        svg.append(
            f'<rect class="awarded" x="{x + 4:.2f}" '
            f'y="{base_y - awarded_height:.2f}" '
            f'width="{half - 8:.2f}" height="{awarded_height:.2f}" />'
        )

        # Pending (blue)
        svg.append(
            f'<rect class="pending" x="{x + half + 4:.2f}" '
            f'y="{base_y - pending_height:.2f}" '
            f'width="{half - 8:.2f}" height="{pending_height:.2f}" />'
        )

        svg.append(
            f'<text class="small" x="{x + bar_w/2:.2f}" '
            f'y="{base_y + 18}" text-anchor="middle">{y}</text>'
        )

    # Legend
    svg.append(f'<rect class="awarded" x="{W-260}" y="35" width="14" height="14" />')
    svg.append(f'<text class="legend" x="{W-235}" y="47">AWARDED</text>')

    svg.append(f'<rect class="pending" x="{W-150}" y="35" width="14" height="14" />')
    svg.append(f'<text class="legend" x="{W-125}" y="47">PENDING</text>')

    svg.append("</svg>")

    out_file = out_dir / "cve-timeline.svg"
    out_file.write_text("\n".join(svg), encoding="utf-8")
    print(f"Wrote {out_file}")


if __name__ == "__main__":
    main()
