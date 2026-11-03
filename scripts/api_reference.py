"""
Writes docs/API.md (every route, grouped as in the interactive documentation) and docs/openapi.json from the
backend's own OpenAPI description, so the reference always matches the code.

    backend/.venv/bin/python scripts/api_reference.py          (Windows: backend\\.venv\\Scripts\\python ...)
    ... scripts/api_reference.py --check                       fail if docs/ is out of date (used by CI)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

INTRO = """# API reference

Generated from the backend's OpenAPI description by `scripts/api_reference.py`; do not edit by hand. The running
backend serves the same reference interactively at http://127.0.0.1:8000/api/docs (try any request there) and the
machine-readable description at `/api/openapi.json` (also saved as [openapi.json](openapi.json)).

## Conventions

- Two APIs share one server. `/api/v1/...` is the learner website's API, `/api/v1/crm/...` the CRM team's API.
- Sign-in returns a JSON Web Token; send it as `Authorization: Bearer <token>`. Learner and team tokens have
  different audiences, so neither opens the other API. A token stops working when its account's password changes.
- Team roles are checked on every request: **admin** (everything), **marketing** (campaigns, A/B tests, coupons,
  exports, the learning loop) and **counsellor** (leads, today's actions, callbacks, pipeline, questions; changes
  only their own leads and unassigned ones). Reading campaigns and tests is open to the whole team.
- Errors are JSON: `{"detail": "a sentence a person can act on"}` with the usual status codes (400 invalid input,
  401 not signed in, 403 not allowed for this role, 404 not found, 409 conflict, 422 malformed request,
  429 too many attempts, 503 a dependency such as email is unavailable).
- Every response carries `X-Request-ID` (sent back when the caller supplies one) and the security headers
  `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and `Cache-Control: no-store`.
- Times are the server's local time as `YYYY-MM-DD HH:MM:SS`; money is in Indian rupees.
"""


def build() -> tuple[str, str]:
    from app.main import app

    spec = app.openapi()
    groups: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    order: list[str] = []
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            tag = (op.get("tags") or ["Other"])[0]
            if tag not in order:
                order.append(tag)
            groups[tag].append((method.upper(), path, op.get("summary", "")))
    lines = [INTRO.rstrip(), ""]
    total = sum(len(v) for v in groups.values())
    lines += [f"{total} routes in {len(order)} groups.", ""]
    for tag in order:
        lines += [f"## {tag}", "", "| Method | Path | What it does |", "|---|---|---|"]
        for method, path, summary in groups[tag]:
            lines.append(f"| {method} | `{path}` | {summary} |")
        lines.append("")
    return "\n".join(lines), json.dumps(spec, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail when docs/API.md or docs/openapi.json is out of date")
    args = ap.parse_args()
    md, spec = build()
    targets = {ROOT / "docs" / "API.md": md, ROOT / "docs" / "openapi.json": spec}
    if args.check:
        stale = [p.name for p, text in targets.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        if stale:
            print(f"Out of date: {', '.join(stale)}. Run python scripts/api_reference.py")
            return 1
        print("The API reference is up to date.")
        return 0
    for path, text in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"Wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
