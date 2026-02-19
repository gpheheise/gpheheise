import html
import pathlib
import re
import urllib.request
from datetime import datetime


HTB_URL = "https://app.hackthebox.com/public/users/378794"
OUT_FILE = pathlib.Path("assets/htb-card.svg")


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (GitHub Actions; +https://github.com/gpheheise/gpheheise)"
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def pick(patterns: list[str], text: str) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            val = m.group(1)
            val = re.sub(r"\s+", " ", val).strip()
            val = html.unescape(val)
            return val
    return None


def numify(s: str | None) -> str | None:
    if not s:
        return None
    # keep digits and separators
    m = re.search(r"[\d][\d,\.]*", s)
    return m.group(0) if m else s


def matrix_svg(data: dict) -> str:
    # Matrix-ish styling (black bg, green text)
    W, H = 900, 220
    pad = 28

    username = data.get("username") or "Hack The Box"
    rank = data.get("rank") or "Profile"
    tier = data.get("tier") or ""
    points = data.get("points") or "—"
    global_rank = data.get("global_rank") or "—"
    flags = data.get("flags") or "—"
    machines = data.get("machines") or "—"
    challenges = data.get("challenges") or "—"

    updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Simple “scanline” effect using repeated semi-transparent lines
    scanlines = "\n".join(
        f'<rect x="0" y="{y}" width="{W}" height="1" fill="#00ff41" opacity="0.05"/>'
        for y in range(0, H, 4)
    )

    def esc(x: str) -> str:
        return html.escape(x)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <style>
      .bg {{ fill: #000; }}
      .card {{ fill: #050a05; stroke: #00ff41; stroke-width: 1.2; }}
      .t {{ font-family: Consolas, Monaco, "Courier New", monospace; fill: #00ff41; }}
      .h {{ font-size: 22px; font-weight: 700; }}
      .s {{ font-size: 14px; opacity: 0.95; }}
      .k {{ font-size: 12px; opacity: 0.80; }}
      .v {{ font-size: 16px; font-weight: 700; }}
      .muted {{ opacity: 0.65; }}
      .red {{ fill: #ff0033; }}
      .blue {{ fill: #0099ff; }}
    </style>
    <filter id="glow">
      <feGaussianBlur stdDeviation="1.2" result="coloredBlur"/>
      <feMerge>
        <feMergeNode in="coloredBlur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>

  <rect class="bg" x="0" y="0" width="{W}" height="{H}"/>
  <rect class="card" x="14" y="14" rx="14" ry="14" width="{W-28}" height="{H-28}"/>
  {scanlines}

  <!-- Header -->
  <text class="t h" x="{pad}" y="55" filter="url(#glow)">{esc(username)}</text>
  <text class="t s muted" x="{pad}" y="78">{esc(rank)}{(" · " + esc(tier)) if tier else ""}</text>

  <!-- Stats grid -->
  <text class="t k" x="{pad}" y="120">POINTS</text>
  <text class="t v" x="{pad}" y="145">{esc(points)}</text>

  <text class="t k" x="{pad+190}" y="120">GLOBAL RANK</text>
  <text class="t v" x="{pad+190}" y="145">#{esc(global_rank)}</text>

  <text class="t k" x="{pad+420}" y="120">FLAGS</text>
  <text class="t v" x="{pad+420}" y="145">{esc(flags)}</text>

  <text class="t k" x="{pad+560}" y="120">MACHINES</text>
  <text class="t v" x="{pad+560}" y="145">{esc(machines)}</text>

  <text class="t k" x="{pad+720}" y="120">CHALLENGES</text>
  <text class="t v" x="{pad+720}" y="145">{esc(challenges)}</text>

  <!-- Footer -->
  <text class="t k muted" x="{pad}" y="{H-28}">HTB public profile snapshot · updated {updated}</text>
  <text class="t k" x="{W-pad}" y="{H-28}" text-anchor="end">{esc(HTB_URL)}</text>
</svg>
'''


def main() -> None:
    pathlib.Path("assets").mkdir(parents=True, exist_ok=True)

    page = fetch(HTB_URL)

    # Best-effort parsing (HTML can change)
    username = pick([
        r'<h1[^>]*>\s*([^<]+)\s*</h1>',
        r'"name"\s*:\s*"([^"]+)"',
        r'"username"\s*:\s*"([^"]+)"',
    ], page)

    rank = pick([
        r'Hack The Box Rank</[^>]*>\s*<[^>]*>\s*([^<]+)\s*<',   # “Pro Hacker”
        r'>\s*Hack The Box Rank\s*<.*?>\s*([^<]+)\s*<',
    ], page)

    tier = pick([
        r'SILVER TIER</[^>]*>\s*<[^>]*>\s*([^<]+)\s*<',
        r'(["\']tier["\']\s*:\s*["\'])([^"\']+)',
    ], page)

    points = numify(pick([
        r'>\s*Points\s*<.*?>\s*([\d][\d,\.]*)\s*<',
        r'"points"\s*:\s*([\d][\d,\.]*)',
    ], page))

    global_rank = numify(pick([
        r'>\s*Global Ranking\s*<.*?>\s*#?\s*([\d][\d,\.]*)\s*<',
        r'"globalRanking"\s*:\s*#?\s*([\d][\d,\.]*)',
    ], page))

    flags = numify(pick([
        r'>\s*Flags\s*<.*?>\s*([\d][\d,\.]*)\s*<',
    ], page))

    machines = numify(pick([
        r'>\s*Machines\s*<.*?>\s*([\d][\d,\.]*)\s*/\s*([\d][\d,\.]*)\s*<',
    ], page))
    if machines and "/" in machines:
        machines = machines.split("/")[0].strip()

    challenges = numify(pick([
        r'>\s*Challenges\s*<.*?>\s*([\d][\d,\.]*)\s*/\s*([\d][\d,\.]*)\s*<',
    ], page))
    if challenges and "/" in challenges:
        challenges = challenges.split("/")[0].strip()

    data = {
        "username": username,
        "rank": rank,
        "tier": tier,
        "points": points,
        "global_rank": global_rank,
        "flags": flags,
        "machines": machines,
        "challenges": challenges,
    }

    OUT_FILE.write_text(matrix_svg(data), encoding="utf-8")
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
