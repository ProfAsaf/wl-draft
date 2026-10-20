"""Draw the site's home-screen icon (the split ball) and render it at every size phones ask for.

Writes site/icons/: icon.svg (browser tab), apple-touch-icon.png (iPhone home screen,
full-bleed because iOS rounds the corners itself), icon-192.png and icon-512.png
(rounded, for Android), and icon-maskable-512.png (padded so Android's circle or
squircle crop never cuts into the ball). PNGs are rendered with a headless Chromium
browser so they match the SVG exactly.

Usage: python scripts/make_icons.py [path-to-chrome-or-edge]
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "icons"
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
]

BG = "#0c0e12"
BALL = """<circle cx="90" cy="90" r="74" fill="#EE7429"/>
<path d="M26 50 Q40 90 26 130" fill="none" stroke="#0c0e12" stroke-width="5" stroke-linecap="round"/>
<path d="M154 50 Q140 90 154 130" fill="none" stroke="#0c0e12" stroke-width="5" stroke-linecap="round"/>
<path d="M44 66 L56 114 L67 82 L78 114 L90 66" fill="none" stroke="#ffffff" stroke-width="10" stroke-linejoin="miter"/>
<path d="M97 118 L112 62" fill="none" stroke="#0c0e12" stroke-width="8" stroke-linecap="round"/>
<path d="M120 66 L120 114 L142 114" fill="none" stroke="#ffffff" stroke-width="10" stroke-linejoin="miter"/>"""


def icon_svg(rounded=True, inset=1.0, size=None):
    """The icon on a 180-unit canvas; inset < 1 shrinks the ball toward the center."""
    corner = ' rx="40"' if rounded else ""
    shift = 90 * (1 - inset)
    dims = f' width="{size}" height="{size}"' if size else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 180"{dims}>'
            f'<rect width="180" height="180"{corner} fill="{BG}"/>'
            f'<g transform="translate({shift:g} {shift:g}) scale({inset:g})">{BALL}</g></svg>')


def render(browser, svg, size, out):
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "icon.html"
        page.write_text(f"<!doctype html><style>html,body{{margin:0;background:transparent}}"
                        f"svg{{display:block}}</style>{svg}", encoding="utf-8")
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1", f"--window-size={size},{size}",
                        "--default-background-color=00000000", f"--user-data-dir={tmp}",
                        f"--screenshot={out}", page.as_uri()],
                       check=True, capture_output=True, timeout=60)
    with Image.open(out) as img:
        if img.size != (size, size):
            raise RuntimeError(f"{out.name} came out {img.size}, expected {size}x{size}")


def main():
    browser = sys.argv[1] if len(sys.argv) > 1 else next((b for b in BROWSERS if Path(b).exists()), None)
    if not browser:
        raise SystemExit("No Chrome or Edge found; pass its path as the first argument.")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "icon.svg").write_text(icon_svg() + "\n", encoding="utf-8")
    for name, size, rounded, inset in [
        ("apple-touch-icon.png", 180, False, 1.0),
        ("icon-192.png", 192, True, 1.0),
        ("icon-512.png", 512, True, 1.0),
        ("icon-maskable-512.png", 512, False, 0.8),
    ]:
        render(browser, icon_svg(rounded, inset, size), size, OUT / name)
        print(f"wrote site/icons/{name} ({size}x{size}, {(OUT / name).stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
