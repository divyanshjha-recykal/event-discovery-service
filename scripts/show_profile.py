"""Stage 0 acceptance check: load the business profile from disk and print it.

    uv run python scripts/show_profile.py [--summary]
"""

from __future__ import annotations

import argparse
import sys

from opportunity_radar.profile import ProfileNotFound, load_business_profile


def _force_utf8_stdout() -> None:
    """The profile contains characters (e.g. Rs sign) that cp1252 cannot encode.

    On a Windows console, printing it raises UnicodeEncodeError unless the
    stream is switched to UTF-8 first.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _force_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", help="Override the profile path.")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print the path, size and section headings instead of the full text.",
    )
    args = parser.parse_args()

    try:
        profile = load_business_profile(args.path)
    except ProfileNotFound as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if args.summary:
        print(f"path:     {profile.path}")
        print(f"chars:    {len(profile.text):,}")
        print(f"words:    {len(profile.text.split()):,}")
        print(f"sections: {len(profile.sections)}")
        for section in profile.sections:
            print(f"  - {section}")
    else:
        print(profile.text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
