"""Build the 이음온 logo: write SVG sources and render PNGs with headless Edge.

Run:  python design/logo/build_logo.py
Out:  design/logo/*.svg  and  design/logo/png/*.png
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PNG_DIR = HERE / "png"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SCALE = 3  # device pixels per SVG unit

# Palette taken from the prototype deck (cream paper, deep plum text, paper-cut leaves).
CREAM = "#FAF8F2"
INK = "#2F1F4F"        # deep plum used for headings
PLUM = "#96266B"       # flower magenta
TEAL = "#2B7A6F"       # teal leaf
OLIVE = "#8C8A2E"      # olive leaf / stem
GOLD = "#D9B452"       # flower stamen
MUTED = "#6E6480"      # tagline
LAVENDER = "#E3DBE6"   # card tint

FONT = "'Noto Sans KR','Malgun Gothic',sans-serif"
TAGLINE = "어르신의 이야기를 복지로 이어 드립니다"

# One leaf: base at the origin, tip straight up.
LEAF = "M0,0 C54,-40 54,-86 0,-118 C-54,-86 -54,-40 0,0 Z"
VEIN = "M0,-6 Q3,-60 0,-108"


def symbol(x: float, y: float, ink: str = INK, shadow: bool = True) -> str:
    """Two leaves growing from one stem; the overlap is the 'tie' (이음)."""
    filt = ' filter="url(#paper)"' if shadow else ""
    return f"""
  <g transform="translate({x},{y})"{filt}>
    <path d="M100,170 C99,180 99,188 100,196" fill="none" stroke="{OLIVE}" stroke-width="7" stroke-linecap="round"/>
    <g transform="translate(97,170) rotate(-23)">
      <path d="{LEAF}" fill="{PLUM}"/>
      <path d="{VEIN}" fill="none" stroke="{CREAM}" stroke-opacity="0.45" stroke-width="3" stroke-linecap="round"/>
    </g>
    <g transform="translate(103,170) rotate(23)">
      <path d="{LEAF}" fill="{TEAL}"/>
      <path d="{VEIN}" fill="none" stroke="{CREAM}" stroke-opacity="0.45" stroke-width="3" stroke-linecap="round"/>
    </g>
    <g clip-path="url(#leafA)">
      <path d="{LEAF}" transform="translate(103,170) rotate(23)" fill="{ink}"/>
    </g>
    <circle cx="100" cy="46" r="10" fill="{GOLD}"/>
  </g>"""


def defs() -> str:
    return f"""
  <defs>
    <clipPath id="leafA"><path d="{LEAF}" transform="translate(97,170) rotate(-23)"/></clipPath>
    <filter id="paper" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="3" stdDeviation="2.5" flood-color="{INK}" flood-opacity="0.18"/>
    </filter>
  </defs>"""


def svg(width: int, height: int, body: str, bg: str | None = None) -> str:
    rect = f'\n  <rect width="{width}" height="{height}" fill="{bg}"/>' if bg else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">{defs()}{rect}{body}\n</svg>\n'
    )


def wordmark(x: float, y: float, size: int, ink: str, accent: str, anchor: str = "start") -> str:
    return (
        f'\n  <text x="{x}" y="{y}" font-family="{FONT}" font-weight="800" font-size="{size}" '
        f'letter-spacing="-0.02em" fill="{ink}" text-anchor="{anchor}">이음<tspan fill="{accent}">온</tspan></text>'
    )


def tagline(x: float, y: float, size: int, color: str, anchor: str = "start") -> str:
    return (
        f'\n  <text x="{x}" y="{y}" font-family="{FONT}" font-weight="500" font-size="{size}" '
        f'letter-spacing="0.01em" fill="{color}" text-anchor="{anchor}">{TAGLINE}</text>'
    )


def build() -> dict[str, tuple[str, int, int]]:
    files: dict[str, tuple[str, int, int]] = {}

    # Symbol only (transparent).
    files["iumon-symbol"] = (svg(200, 200, symbol(0, 0)), 200, 200)

    # App-icon style badge: rounded square with the symbol centred.
    def badge(bg: str, overlap: str, border: str | None) -> str:
        stroke = f' stroke="{border}" stroke-width="2"' if border else ""
        body = f'\n  <rect x="1" y="1" width="238" height="238" rx="56" fill="{bg}"{stroke}/>' + symbol(20, 20, ink=overlap)
        return svg(240, 240, body)

    files["iumon-badge-cream"] = (badge(CREAM, INK, LAVENDER), 240, 240)
    files["iumon-badge-plum"] = (badge(INK, CREAM, None), 240, 240)

    # Horizontal lock-up: symbol + wordmark + tagline.
    def horizontal(bg: str | None, ink: str, accent: str, tag: str, overlap: str) -> str:
        body = symbol(10, 10, ink=overlap) + wordmark(232, 128, 112, ink, accent) + tagline(238, 186, 27, tag)
        return svg(740, 220, body, bg)

    files["iumon-logo-horizontal"] = (horizontal(None, INK, PLUM, MUTED, INK), 740, 220)
    files["iumon-logo-horizontal-cream"] = (horizontal(CREAM, INK, PLUM, MUTED, INK), 740, 220)
    files["iumon-logo-horizontal-reverse"] = (horizontal(INK, CREAM, GOLD, LAVENDER, CREAM), 740, 220)

    # Stacked lock-up: symbol above centred wordmark.
    def stacked(bg: str | None, ink: str, accent: str, tag: str, overlap: str) -> str:
        body = (
            symbol(150, 14, ink=overlap)
            + wordmark(250, 334, 104, ink, accent, anchor="middle")
            + tagline(250, 386, 25, tag, anchor="middle")
        )
        return svg(500, 420, body, bg)

    files["iumon-logo-stacked"] = (stacked(None, INK, PLUM, MUTED, INK), 500, 420)
    files["iumon-logo-stacked-cream"] = (stacked(CREAM, INK, PLUM, MUTED, INK), 500, 420)
    files["iumon-logo-stacked-reverse"] = (stacked(INK, CREAM, GOLD, LAVENDER, CREAM), 500, 420)

    # Wordmark only, for slide footers.
    files["iumon-wordmark"] = (svg(360, 130, wordmark(180, 104, 112, INK, PLUM, anchor="middle")), 360, 130)
    return files


def browser() -> str:
    for exe in (EDGE, CHROME):
        if Path(exe).exists():
            return exe
    sys.exit("No Edge or Chrome found for rendering.")


def render(name: str, svg_text: str, w: int, h: int, exe: str, profile: Path) -> Path:
    html = HERE / "_render.html"
    html.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;padding:0;background:transparent;overflow:hidden}svg{display:block}</style>"
        f"</head><body>{svg_text}</body></html>",
        encoding="utf-8",
    )
    out = PNG_DIR / f"{name}.png"
    cmd = [
        exe,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={profile}",
        "--default-background-color=00000000",
        f"--force-device-scale-factor={SCALE}",
        f"--window-size={w},{h}",
        f"--screenshot={out}",
        html.resolve().as_uri(),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    html.unlink(missing_ok=True)
    return out


def main() -> None:
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    exe = browser()
    profile = Path(tempfile.mkdtemp(prefix="iumon-logo-"))
    try:
        for name, (text, w, h) in build().items():
            (HERE / f"{name}.svg").write_text(text, encoding="utf-8")
            out = render(name, text, w, h, exe, profile)
            print(f"{out.relative_to(HERE.parent.parent)}  {w * SCALE}x{h * SCALE}")
    finally:
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    os.chdir(HERE)
    main()
