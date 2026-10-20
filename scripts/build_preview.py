"""Wrap mockup/index.html in the document skeleton the artifact host adds, for local preview.

Writes mockup/preview.html. Serve the mockup folder (see .claude/launch.json) and open
/preview.html at phone size.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKELETON = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>
:root { color-scheme: light; padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px); }
body { margin: 0; font: 14px system-ui, -apple-system, "Segoe UI", sans-serif; }
img { max-width: 100%; }
[hidden] { display: none !important; }
</style>
</head>
<body>
{content}
</body>
</html>
"""

page = (ROOT / "mockup" / "index.html").read_text(encoding="utf-8")
(ROOT / "mockup" / "preview.html").write_text(SKELETON.replace("{content}", page), encoding="utf-8")
print("wrote mockup/preview.html")
