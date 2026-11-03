"""
Fails when an emoji appears in the project's own files: code, settings, styles, pages and documents.

    python scripts/check_no_emoji.py              check the whole project
    python scripts/check_no_emoji.py PATH ...     check these files or folders

Typographic characters are not emoji and stay allowed: the rupee sign, the minus and multiplication signs, dashes and
arrows in comments and formulas. Generated or third-party folders (node_modules, dist, data, caches) are skipped.
Exit code 0 when clean, 1 when an emoji was found (each one is listed with its file, line and code point).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "coverage",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "data",
}
SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".mjs", ".css", ".html", ".json", ".md", ".txt", ".toml", ".ini", ".cfg",
    ".yml", ".yaml", ".bat", ".cmd", ".ps1", ".sh", ".mako", ".svg",
}  # fmt: skip
EMOJI = re.compile(
    "["
    "\U0001f000-\U0001faff"  # pictographs, emoticons, transport, flags, playing cards, chess and more
    "\u2600-\u27bf"  # miscellaneous symbols and dingbats (sun, telephone, check marks, stars)
    "\u2b00-\u2bff"  # symbols and arrows drawn as emoji (stars, circles, squares)
    "\u2300-\u23ff"  # technical symbols drawn as emoji (watch, hourglass, keyboard)
    "\ufe0f"  # emoji presentation selector
    "\u200d"  # zero-width joiner (joins emoji into one)
    "\u20e3"  # keycap
    "]"
)
ALLOWED = {"\u2318", "\u2325", "\u2303", "\u23ce"}  # keyboard keys shown in shortcut hints


def files(paths: list[Path]):
    for path in paths:
        if path.is_file():
            yield path
            continue
        for p in sorted(path.rglob("*")):
            parts = set(p.relative_to(path).parts)
            if p.is_file() and p.suffix.lower() in SUFFIXES and not SKIP_DIRS & parts and p.name != "package-lock.json":
                yield p


def scan(paths: list[Path]) -> list[str]:
    problems = []
    for path in files(paths):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for match in EMOJI.finditer(line):
                if match.group() in ALLOWED:
                    continue
                shown = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
                problems.append(f"{shown}:{number}: U+{ord(match.group()):04X}")
    return problems


def main(argv: list[str]) -> int:
    targets = [Path(a).resolve() for a in argv] or [ROOT]
    problems = scan(targets)
    for p in problems:
        print(p)
    if problems:
        print(f"{len(problems)} emoji found. Use words instead.")
        return 1
    print("No emoji found.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
