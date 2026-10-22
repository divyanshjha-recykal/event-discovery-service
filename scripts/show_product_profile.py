"""Load a product profile workbook and show what the component pipeline will see.

    uv run python scripts/show_product_profile.py ace

No network, no model. Fails with the sheet, column or row at fault if the
workbook cannot be used.
"""

from __future__ import annotations

import argparse
import io
import sys
from collections import Counter

from opportunity_radar.product_profile import ProductProfileError, load_product_profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product", help="product folder name, e.g. ace")
    args = parser.parse_args()
    try:
        profile = load_product_profile(args.product)
    except ProductProfileError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    parts = profile.parts
    print(f"{profile.product}: {len(parts)} parts from {profile.path}")
    print("  by subsystem:", dict(Counter(p.subsystem for p in parts)))
    print("  priced:", sum(1 for p in parts if p.rate is not None),
          "| with a part number:", sum(1 for p in parts if p.part_number),
          "| with a vendor:", sum(1 for p in parts if p.vendor),
          "| with a reason:", sum(1 for p in parts if p.why_chosen))
    for part in parts:
        print(f"\n[{part.part_id}] {part.subsystem}\n  " + part.brief().replace("\n", "\n  "))
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.exit(main())
