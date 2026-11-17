#!/usr/bin/env python3
"""Build the standalone theme files in styles/ from igs-themes.user.css.

igs-themes.user.css is the only file to edit. Run this script after
changing it, so the copy-and-paste files in styles/ stay in sync:

    python3 tools/build.py

Each styles/goschool_<theme>.css is the UserCSS file with that theme's
palette filled in and the day/night switching removed.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "igs-themes.user.css"

DESCRIPTIONS = {
    "green": "Sage green and teal over moss-green contour lines with Go calligraphy (the original theme, refreshed).",
    "kaya": "Pale kaya wood-tone background, cream paper cards, ink text, deep red accents.",
    "momiji": "Autumn maple: sand page, cream cards, dark bark menu, burnt orange and moss green.",
    "seigaiha": "Calm ocean blues, white cards, deep sea-teal menu, coral accents.",
    "kaki": "Persimmon: warm sand page, cream cards, coral menu and headings, leaf green and sky blue touches.",
    "fuji": "Mount Fuji at dawn: peach-to-indigo sky, Prussian-blue menu, washi-white cards, vermilion accents.",
    "sakura": "Cherry blossom: blush page with an asanoha pattern and a blossoming branch, plum menu, sakura pink and matcha green.",
    "karesansui": "Dry rock garden: raked gravel with stones, stone-grey menu, moss-green accents.",
    "dark": "Charcoal background, slate cards, soft teal accents.",
    "chochin": "Paper lanterns at night: sumi-black page, glowing red and amber lanterns, vermilion and amber accents.",
}


def parse(text):
    """Return (metadata, body, {var: {option: (label, value)}})."""
    meta, body = text.split("==/UserStyle== */\n", 1)
    options = {}
    for block in re.finditer(r'@advanced dropdown (\w+) "[^"]*" \{\n(.*?)\n\}', meta, re.S):
        var, inner = block.groups()
        options[var] = {
            key: (label.rstrip("*"), value)
            for key, label, value in re.findall(r'    (\w+) "([^"]*)" <<<EOT\n(.*?)\n    EOT;', inner, re.S)
        }
    return meta, body, options


def render(body, options, day, night=None, mode="auto"):
    """Fill in the placeholders, like Stylus does. night=None drops the night block."""
    out = body.replace("/*[[dayTheme]]*/", options["dayTheme"][day][1])
    if night is None:
        out, n = re.subn(r"\n    /\* night theme:.*?\n    @media /\*\[\[mode\]\]\*/ \{.*?\n    \}\n", "\n", out, flags=re.S)
        assert n == 1, "night block not found"
    else:
        out = out.replace("/*[[nightTheme]]*/", options["nightTheme"][night][1])
        out = out.replace("/*[[mode]]*/", options["mode"][mode][1])
    assert "/*[[" not in out
    return out


def main():
    meta, body, options = parse(SOURCE.read_text())
    for key, (label, _) in options["dayTheme"].items():
        css = render(body, options, key)
        css = re.sub(
            r"       INTERNET GO SCHOOL THEMES\n.*?\n\n",
            f"       INTERNET GO SCHOOL - {label.upper()}\n       {DESCRIPTIONS[key]}\n"
            "       Generated from igs-themes.user.css by tools/build.py - edit that file instead.\n\n",
            css, count=1, flags=re.S,
        )
        css = css.replace("- filled in from the theme you pick", "- edit these to customize the theme")
        (ROOT / "styles" / f"goschool_{key}.css").write_text(css)
        print(f"styles/goschool_{key}.css")


if __name__ == "__main__":
    if len(sys.argv) == 4:  # preview: build.py <day> <night> <mode>  -> stdout
        _, body, options = parse(SOURCE.read_text())
        sys.stdout.write(render(body, options, *sys.argv[1:]))
    else:
        main()
