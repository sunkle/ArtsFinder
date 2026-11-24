#!/usr/bin/env python3
"""Build dist/ : index.html with lot data, rules and schema embedded, plus manifest, sw, icons, robots.txt.

Usage: python3 app/build.py [path/to/lots.json] [--out DIR]
  lots.json  default data/lots.json
  --out      default app/dist (tests build into a temp folder so they never touch the real dist/)

The service worker's cache name gets a hash of everything that was built, so every new build replaces
the old cached copy on the phone."""
import argparse, hashlib, json, re, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent / "shared"
ASSETS = ["manifest.webmanifest", "icon.svg", "icon-180.png", "icon-512.png"]
ROBOTS = "User-agent: *\nDisallow: /\n"  # asks search engines to stay away (the site is public but unlisted)
# <script type="application/json" id="..."> blocks in index.html that build.py fills in.
BLOCKS = ("embedded-data", "embedded-rules", "embedded-schema")


def embed(html, block_id, value):
    """Put `value` (as JSON) into the <script id=block_id> block. '<' is escaped so it can never end the script."""
    rx = re.compile(r'(<script type="application/json" id="%s">)(.*?)(</script>)' % block_id, re.S)
    if not rx.search(html):
        sys.exit(f"{block_id} block not found in index.html")
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return rx.sub(lambda m: m.group(1) + payload + m.group(3), html, 1)


def build(src, dist):
    data = json.loads(Path(src).read_text(encoding="utf-8"))  # validates JSON
    dist = Path(dist)
    dist.mkdir(parents=True, exist_ok=True)
    html = (HERE / "index.html").read_text(encoding="utf-8")
    values = {"embedded-data": data,
              "embedded-rules": json.loads((SHARED / "rules.json").read_text(encoding="utf-8")),
              "embedded-schema": json.loads((SHARED / "schema.json").read_text(encoding="utf-8"))}
    for block_id in BLOCKS:
        html = embed(html, block_id, values[block_id])
    (dist / "index.html").write_text(html, encoding="utf-8")
    (dist / "lots.json").write_text(Path(src).read_text(encoding="utf-8"), encoding="utf-8")
    (dist / "robots.txt").write_text(ROBOTS, encoding="utf-8")
    for name in ASSETS:
        if (HERE / name).exists():
            shutil.copy(HERE / name, dist / name)
    version = hashlib.sha256((html + Path(src).read_text(encoding="utf-8")).encode()).hexdigest()[:12]
    sw = (HERE / "sw.js").read_text(encoding="utf-8")
    if "__BUILD__" not in sw:
        sys.exit("__BUILD__ placeholder not found in sw.js")
    (dist / "sw.js").write_text(sw.replace("__BUILD__", version), encoding="utf-8")
    return len(data.get("lots", [])), version


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("lots", nargs="?", default=str(HERE.parent / "data" / "lots.json"))
    ap.add_argument("--out", default=str(HERE / "dist"))
    args = ap.parse_args(argv)
    n, version = build(args.lots, args.out)
    print(f"Built {Path(args.out) / 'index.html'} with {n} lots (cache version {version})")


if __name__ == "__main__":
    main()
