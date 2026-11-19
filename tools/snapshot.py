#!/usr/bin/env python3
"""Check igs-themes.user.css against snapshots of the site's pages.

The style only works while internetgoschool.com keeps the classes and
structure it targets. snapshots/pages/ holds the structure of each page
(captured by tools/capture.js, no text or personal data), taken when the
style was known to look right. When the site changes, capture the pages
again and compare:

    python3 tools/snapshot.py check                 # files in ~/Downloads
    python3 tools/snapshot.py check path/to/dir     # or another folder
    python3 tools/snapshot.py import                # make them the new baseline
    python3 tools/snapshot.py coverage              # selectors no page matches

`check` lists, per page, the selectors that matched the baseline page but
match nothing now (with their line in igs-themes.user.css), the classes
that disappeared or appeared (often the rename you are looking for), and
site color variables the style sets that the site no longer uses.

Needs: pip install beautifulsoup4 (soupsieve comes with it).
"""
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

try:
    from bs4 import BeautifulSoup
    import soupsieve
except ImportError:
    sys.exit("Needs BeautifulSoup: pip install beautifulsoup4")

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "igs-themes.user.css"
PAGES = ROOT / "snapshots" / "pages"
DOWNLOADS = Path.home() / "Downloads"

# states the snapshot cannot be in: dropped before matching
DYNAMIC = r"hover|focus|focus-visible|focus-within|active|visited|link|target"
PSEUDO_ELEMENT = re.compile(
    r"::?(?:before|after|first-line|first-letter|marker|placeholder|selection|backdrop)\b"
    r"|::-?[\w-]+(?:\([^)]*\))?"
)


# ---------- selectors in the style ----------

def strip_comments(text):
    """Blank out comments, keeping line numbers and strings intact."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r"[^\n]", " ", text[i:j]))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def split_top(prelude):
    """Split a selector list on commas outside parentheses."""
    parts, depth, cur = [], 0, ""
    for c in prelude:
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        if c == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += c
    parts.append(cur)
    return [" ".join(p.split()) for p in parts if p.strip()]


def style_selectors():
    """[(selector, line)] for every rule in the style's body."""
    text = SOURCE.read_text()
    head, body = text.split("==/UserStyle== */\n", 1)
    offset = head.count("\n") + 2
    body = strip_comments(body)
    found, stack, start, i = [], [], 0, 0
    while i < len(body):
        c = body[i]
        if c in "\"'":
            j = i + 1
            while j < len(body) and body[j] != c:
                j += 2 if body[j] == "\\" else 1
            i = j + 1
            continue
        if c == "{":
            prelude = body[start:i].strip()
            kind = "at" if prelude.startswith("@") else "rule"
            if kind == "at" and re.match(r"@(font-face|keyframes|page)", prelude):
                kind = "skip"
            if kind == "rule" and (not stack or stack[-1] == "at"):
                line = offset + body.count("\n", 0, start + len(body[start:i]) - len(body[start:i].lstrip()))
                found += [(s, line) for s in split_top(prelude)]
            stack.append(kind if not stack or stack[-1] == "at" else "skip")
            start = i + 1
        elif c == "}":
            if stack:
                stack.pop()
            start = i + 1
        elif c == ";" and (not stack or stack[-1] == "at"):
            start = i + 1
        i += 1
    return found


def for_matching(sel):
    """The selector without hover/focus states and pseudo-elements, or None."""
    s = PSEUDO_ELEMENT.sub("", sel)
    s = re.sub(rf":(?:{DYNAMIC})\b(?!-)", "", s)
    s = re.sub(r":not\(\s*\)", "", s)
    s = s.strip()
    if not s or s.endswith((">", "+", "~")):
        s = (s + " *").strip() if s else "*"
    return s


def remove_not(sel):
    """The selector with every :not(...) argument removed (it adds no requirement)."""
    out, i = "", 0
    while i < len(sel):
        if sel.startswith(":not(", i):
            depth, j = 1, i + 5
            while j < len(sel) and depth:
                depth += {"(": 1, ")": -1}.get(sel[j], 0)
                j += 1
            i = j
        else:
            out += sel[i]
            i += 1
    return out


def group_key(sel):
    """Selectors that differ only in a number (streak 1..999, bar widths) form one group."""
    return re.sub(r'(\[(?:src|style)[\^*$]?=")([^"]*)"', lambda m: m.group(1) + re.sub(r"\d+", "N", m.group(2)) + '"', sel)


def selector_groups():
    """{group: {"lines": [..], "selectors": [normalized, ..], "example": sel}}"""
    groups = {}
    for sel, line in style_selectors():
        g = groups.setdefault(group_key(sel), {"lines": [], "selectors": set(), "example": sel})
        g["lines"].append(line)
        m = for_matching(sel)
        if m:
            g["selectors"].add(m)
    return groups


# ---------- pages ----------

class Page:
    def __init__(self, path):
        self.path = path
        text = path.read_text()
        meta = dict(re.findall(r"<!-- igs-(\w+): (.*?) -->", text[:200000]))
        self.name = meta.get("page", path.stem.removeprefix("igs-"))
        self.route = meta.get("route", "?")
        self.date = meta.get("captured", "?")
        self.vars = set(meta.get("vars", "").split())
        self.text = text
        self.soup = BeautifulSoup(text, "html.parser")
        self.class_set = self.classes()
        self.id_set = {el["id"] for el in self.soup.find_all(id=True)}
        self._cache = {}

    def could_match(self, selector):
        """Cheap test: every class, id and quoted value the selector needs is on the page."""
        need = remove_not(selector)
        values = re.findall(r'[*^$|~]?="([^"]+)"', need)
        bare = re.sub(r'"[^"]*"', '""', need)
        if any(c not in self.class_set for c in re.findall(r"\.(-?[_a-zA-Z][\w-]*)", bare)):
            return False
        if any(i not in self.id_set for i in re.findall(r"#(-?[_a-zA-Z][\w-]*)", bare)):
            return False
        return all(v in self.text for v in values)

    def matches(self, selector):
        if selector not in self._cache:
            try:
                self._cache[selector] = self.could_match(selector) and self.soup.select_one(selector) is not None
            except Exception:
                self._cache[selector] = None  # selector the matcher cannot run
        return self._cache[selector]

    def matches_group(self, group):
        results = [self.matches(s) for s in group["selectors"]]
        if any(results):
            return True
        return None if results and all(r is None for r in results) else False

    def classes(self):
        out = set()
        for el in self.soup.find_all(class_=True):
            out.update(el.get("class"))
        return out


def load(folder):
    files = sorted(Path(folder).glob("igs-*.html"))
    return {p.name: p for p in map(Page, files)}


def site_tokens():
    """The site's own variables the style sets (everything but --igs-*)."""
    body = SOURCE.read_text().split("==/UserStyle== */\n", 1)[1]
    return sorted(set(re.findall(r"^\s*(--(?!igs-)[\w-]+)\s*:", body, re.M)))


def lines(nums, limit=6):
    nums = sorted(set(nums))
    s = ", ".join(map(str, nums[:limit]))
    return s + (f" (+{len(nums) - limit})" if len(nums) > limit else "")


# ---------- commands ----------

def check(folder):
    new = load(folder)
    if not new:
        sys.exit(f"No igs-*.html files in {folder}. Run tools/capture.js on the site first.")
    base = load(PAGES)
    groups = selector_groups()
    problems = 0

    for name, page in new.items():
        old = base.get(name)
        print(f"\n== {name}  ({page.route}, captured {page.date})")
        if not old:
            print("   no baseline for this page: `import` it to start tracking it")
            continue
        lost = [g for g in groups.values() if old.matches_group(g) and page.matches_group(g) is False]
        gone = sorted(old.classes() - page.classes())
        added = sorted(page.classes() - old.classes())
        if not (lost or gone or added):
            print("   OK, same structure as the baseline of", old.date)
            continue
        if lost:
            problems += len(lost)
            print(f"   {len(lost)} selector(s) matched on {old.date} and match nothing now:")
            for g in sorted(lost, key=lambda g: g["lines"][0]):
                print(f"     line {lines(g['lines'])}: {g['example']}")
        if gone:
            print(f"   classes gone:  {' '.join(gone)}")
        if added:
            print(f"   classes new:   {' '.join(added)}")

    site_vars = set().union(*(p.vars for p in new.values()))
    if site_vars:
        unused = [t for t in site_tokens() if t not in site_vars]
        old_vars = set().union(*(p.vars for p in base.values())) if base else set()
        newly = [t for t in unused if t in old_vars]
        if newly:
            problems += len(newly)
            print(f"\n== site variables the style sets but the site no longer uses:\n   {' '.join(newly)}")

    print(f"\n{problems} problem(s) found." if problems else "\nNo broken selectors found.")
    return 1 if problems else 0


def import_(folder):
    files = sorted(Path(folder).glob("igs-*.html"))
    if not files:
        sys.exit(f"No igs-*.html files in {folder}.")
    PAGES.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.move(str(f), PAGES / f.name)
        print("baseline:", (PAGES / f.name).relative_to(ROOT))


def coverage():
    pages = list(load(PAGES).values())
    if not pages:
        sys.exit("No baseline yet: capture pages and `import` them.")
    groups = selector_groups()
    never, unsupported = [], []
    per_page = defaultdict(int)
    for g in groups.values():
        results = [p.matches_group(g) for p in pages]
        for p, r in zip(pages, results):
            if r:
                per_page[p.name] += 1
        if any(results):
            continue
        (unsupported if all(r is None for r in results) else never).append(g)
    print(f"{len(groups)} selector groups, {len(pages)} pages in the baseline\n")
    for p in pages:
        print(f"  {per_page[p.name]:5}  {p.name}")
    print(f"\n{len(never)} match no baseline page (pages not captured yet, states like")
    print("open menus or popups, or rules the site no longer needs):")
    for g in sorted(never, key=lambda g: g["lines"][0]):
        print(f"  line {lines(g['lines'])}: {g['example']}")
    if unsupported:
        print(f"\n{len(unsupported)} the checker cannot test:")
        for g in unsupported:
            print(f"  line {lines(g['lines'])}: {g['example']}")


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "check"
    folder = Path(args[1]).expanduser() if len(args) > 1 else DOWNLOADS
    if cmd == "check":
        sys.exit(check(folder))
    elif cmd == "import":
        import_(folder)
    elif cmd == "coverage":
        coverage()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
