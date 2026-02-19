name: Build CVE timeline
on:
  schedule:
    - cron: "0 7 * * 1" # Mondays
  workflow_dispatch:

permissions:
  contents: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python scripts/build_cve_timeline.py
      - run: |
          if git diff --quiet; then
            echo "No changes."
          else
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git add assets/cve-timeline.svg
            git commit -m "Update CVE timeline"
            git push
          fi
