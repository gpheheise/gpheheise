import html
import json
import os
import pathlib
import re
import urllib.request
from datetime import datetime
from typing import Any, Iterable

HTB_USER_ID = "378794"
PROFILE_URL = f"https://app.hackthebox.com/public/users/{HTB_USER_ID}"

# Correct HTB v4 Labs API base (per community docs)
API_CANDIDATES = [
    f"https://labs.hackthebox.com/api/v4/user/profile/basic/{HTB_USER_ID}",
]

OUT_SVG = pathlib.Path("assets/htb-card.svg")
OUT_DEBUG = pathlib.Path("assets/htb-debug.json")


def fetch_json(url: str, token: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (GitHub Actions)",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def walk(obj: Any) -> Iterable[Any]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def fmt_num(x: Any) -> str:
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "—"
    if isinstance(x, (int, float)):
        if isinstance(x, float) and x.is_integer():
            x = int(x)
        return str(x)
    s = str(x).strip()
    m = re.search(r"[\d][\d,\.]*", s)
    return m.group(0) if m else (s if s else "—")


def svg_card(p: dict[str, Any]) -> str:
    W, H = 980, 260
    pad = 28

    username = p.get("name") or p.get("username") or "Hack The Box"
    rank = p.get("rank") or "—"
    points = fmt_num(p.get("points"))
    ranking = fmt_num(p.get("ranking"))  # global ranking in this response
    user_owns = fmt_num(p.get("user_owns"))
    system_owns = fmt_num(p.get("system_owns"))
    respects = fmt_num(p.get("respects"))

    updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    def esc(x: Any) -> str:
        return html.escape(str(x))

    scanlines = "\n".join(
        f'<rect x="0" y="{y}" width="{W}" height="1" fill="#00ff41" opacity="0.05"/>'
        for y in range(0, H, 4)
    )

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

  <text class="t h" x="{pad}" y="55" filter="url(#glow)">{esc(username)}</text>
  <text class="t s muted" x="{pad}" y="78">{esc(rank)} · {esc(PROFILE_URL)}</text>

  <text class="t k" x="{pad}" y="120">POINTS</text>
  <text class="t v" x="{pad}" y="145">{esc(points)}</text>

  <text class="t k" x="{pad+160}" y="120">GLOBAL</text>
  <text class="t v" x="{pad+160}" y="145">#{esc(ranking)}</text>

  <text class="t k" x="{pad+320}" y="120">USER OWNS</text>
  <text class="t v" x="{pad+320}" y="145">{esc(user_owns)}</text>

  <text class="t k" x="{pad+480}" y="120">SYSTEM OWNS</text>
  <text class="t v" x="{pad+480}" y="145">{esc(system_owns)}</text>

  <text class="t k" x="{pad+660}" y="120">RESPECTS</text>
  <text class="t v" x="{pad+660}" y="145">{esc(respects)}</text>

  <text class="t k muted" x="{pad}" y="{H-28}">updated {updated}</text>
</svg>
'''


def main() -> None:
    token = os.environ.get("HTB_TOKEN", "").strip()
    if not token:
        raise SystemExit("Missing HTB_TOKEN env var (set it via GitHub Actions secret).")

    pathlib.Path("assets").mkdir(parents=True, exist_ok=True)

    payload = None
    used_api = None
    errors: list[str] = []

    for api in API_CANDIDATES:
        try:
            payload = fetch_json(api, token)
            used_api = api
            break
        except Exception as e:
            errors.append(f"{api} -> {type(e).__name__}: {e}")

    profile = {}
    if isinstance(payload, dict):
        if isinstance(payload.get("profile"), dict):
            profile = payload["profile"]
        else:
            profile = payload

    # Debug (safe: no token)
    OUT_DEBUG.write_text(
        json.dumps(
            {
                "used_api": used_api,
                "errors": errors,
                "payload_type": type(payload).__name__ if payload is not None else None,
                "top_level_keys": list(payload.keys()) if isinstance(payload, dict) else None,
                "profile_keys": list(profile.keys()) if isinstance(profile, dict) else None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    OUT_SVG.write_text(svg_card(profile), encoding="utf-8")
    print(f"Wrote {OUT_SVG}")
    print(f"Wrote {OUT_DEBUG}")


if __name__ == "__main__":
    main()
