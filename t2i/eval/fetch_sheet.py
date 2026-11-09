"""Fetch the blind-eval sheet as CSV through the Apps Script web app (needs doGet).

Usage:
  python fetch_sheet.py --url "https://script.google.com/macros/s/<ID>/exec" \
      --out ..\\results\\blind\\sheet_votes.csv
"""
import argparse
import urllib.request


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="Apps Script web app URL (doGet CSV dump)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    req = urllib.request.Request(args.url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read().decode("utf-8", errors="replace")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(data)
    print(f"{len(data)} bytes -> {args.out}")
    lines = data.strip().splitlines()
    print(f"{len(lines)} lines")
    for line in lines[:4]:
        print("  " + line[:160])


if __name__ == "__main__":
    main()
