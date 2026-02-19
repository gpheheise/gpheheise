import re, collections, datetime, pathlib, urllib.request

OUT = pathlib.Path("assets")
OUT.mkdir(parents=True, exist_ok=True)

# Pull README from your CVE list repo (raw)
url = "https://raw.githubusercontent.com/gpheheise/All-Awareded-CVE-List/main/README.md"
md = urllib.request.urlopen(url, timeout=30).read().decode("utf-8", errors="replace")

cves = sorted(set(re.findall(r"\bCVE-\d{4}-\d{4,}\b", md)))
count = len(cves)

years = [int(c.split("-")[1]) for c in cves]
by_year = collections.Counter(years)

if years:
    min_y, max_y = min(years), max(years)
else:
    min_y = max_y = datetime.date.today().year

# Build a simple SVG bar timeline
W, H = 900, 140
pad = 30
bar_h = 70
years_list = list(range(min_y, max_y + 1))
max_val = max(by_year.values()) if by_year else 1
bar_w = (W - 2*pad) / max(1, len(years_list))

def rect(x, y, w, h):
    return f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="6" />'

svg = []
svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
svg.append('<defs><style>')
svg.append("""
text { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; fill: #111; }
.small { font-size: 12px; fill: #333; }
.big { font-size: 18px; font-weight: 700; }
.bar { fill: #2f81f7; opacity: 0.85; }
.bg { fill: #f6f8fa; }
""".strip())
svg.append('</style></defs>')

svg.append(rect(10, 10, W-20, H-20))
svg[-1] = svg[-1].replace("<rect ", '<rect class="bg" ')

svg.append(f'<text class="big" x="{pad}" y="40">CVE timeline (total: {count})</text>')

base_y = 110
svg.append(f'<line x1="{pad}" y1="{base_y}" x2="{W-pad}" y2="{base_y}" stroke="#d0d7de" stroke-width="2"/>')

for i, y in enumerate(years_list):
    v = by_year.get(y, 0)
    h = 0 if max_val == 0 else (v / max_val) * bar_h
    x = pad + i * bar_w + 2
    w = max(2, bar_w - 4)
    y_top = base_y - h
    svg.append(f'<rect class="bar" x="{x:.2f}" y="{y_top:.2f}" width="{w:.2f}" height="{h:.2f}" rx="6"/>')
    svg.append(f'<text class="small" x="{x + w/2:.2f}" y="{base_y + 18}" text-anchor="middle">{y}</text>')
    if v:
        svg.append(f'<text class="small" x="{x + w/2:.2f}" y="{y_top - 6:.2f}" text-anchor="middle">{v}</text>')

svg.append('</svg>')

(OUT / "cve-timeline.svg").write_text("\n".join(svg), encoding="utf-8")
print("Wrote assets/cve-timeline.svg")
