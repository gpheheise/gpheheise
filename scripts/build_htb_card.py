import pathlib
import re
import urllib.request

URL = "https://app.hackthebox.com/public/users/378794?profile-top-tab=machines&ownership-period=1M&profile-bottom-tab=prolabs"

def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")

def main():
    pathlib.Path("assets").mkdir(parents=True, exist_ok=True)
    html = fetch(URL)
    pathlib.Path("assets/htb-page.html").write_text(html, encoding="utf-8")

    # Extract API-like URLs from HTML/JS
    urls = set()

    # absolute URLs
    for m in re.finditer(r"https?://[a-zA-Z0-9\.\-_/:%\?\=&]+", html):
        u = m.group(0)
        if "api" in u.lower() or "graphql" in u.lower():
            urls.add(u)

    # relative api paths
    for m in re.finditer(r'["\'](/api/[^"\']+)["\']', html, flags=re.IGNORECASE):
        urls.add("https://app.hackthebox.com" + m.group(1))

    # write results
    out = "\n".join(sorted(urls)) if urls else "(no api urls found in html)"
    pathlib.Path("assets/htb-api-urls.txt").write_text(out + "\n", encoding="utf-8")

    print("Wrote assets/htb-page.html")
    print("Wrote assets/htb-api-urls.txt")

if __name__ == "__main__":
    main()
