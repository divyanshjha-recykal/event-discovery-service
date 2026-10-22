"""Loads a product profile workbook (docs/products/<product>/ProductProfile.<PRODUCT>.xlsx).

One 'Parts' sheet, one row per BOM part. The teams keep it in Excel, so the
loader stops with the column or row at fault when something it needs is wrong.
The rate is read for code-side arithmetic only; `Part.brief()` is what a prompt
receives, and it has no cost.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import openpyxl

from .paths import PRODUCTS_DIR

#: The columns the team fills in; Why chosen and Must Have may be left blank.
COLUMNS = ("Part ID", "Subsystem", "Item", "What it does", "Manufacturer", "Part number",
           "Qty per machine", "Rate (₹, before GST)", "Vendor", "Why chosen", "Must Have")
SUBSYSTEMS = {"Embedded", "Electrical", "Mechanical"}


class ProductProfileError(ValueError):
    """The workbook is missing, or a sheet, column or value the pipeline needs is wrong."""


@dataclass(frozen=True)
class Part:
    part_id: str
    subsystem: str
    item: str
    what_it_does: str
    manufacturer: str
    part_number: str
    qty: float | None
    rate: float | None
    vendor: str
    why_chosen: str
    must_have: tuple[str, ...] = ()

    def brief(self) -> str:
        """What a prompt may see about this part: never its rate."""
        model = " ".join(v for v in (self.manufacturer, self.part_number) if v)
        qty = f"{self.qty:g}" if self.qty is not None else "not stated"
        return "\n".join([
            f"Part: {self.item}",
            f"What it does: {self.what_it_does or 'not stated'}",
            f"Qty per machine: {qty} (our rate is for one of these)",
            f"Current model: {model or 'not stated'}",
            f"Current vendor: {self.vendor or 'not stated'}",
            f"Why chosen: {self.why_chosen or 'not stated'}",
            f"Must have: {'; '.join(self.must_have) or 'not stated'}",
        ])


@dataclass(frozen=True)
class ProductProfile:
    product: str
    path: Path
    parts: tuple[Part, ...]


def _number(value, where: str) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        raise ProductProfileError(f"{where}: expected a number, found {value!r}") from None


def profile_path(product: str) -> Path:
    return PRODUCTS_DIR / product.lower() / f"ProductProfile.{product.upper()}.xlsx"


MACHINES_FILE = PRODUCTS_DIR / "machines.json"


def machines() -> list[dict]:
    """The product line from docs/products/machines.json; a machine is available once its workbook exists."""
    if not MACHINES_FILE.exists():
        raise ProductProfileError(f"no machine list at {MACHINES_FILE}")
    listed = json.loads(MACHINES_FILE.read_text(encoding="utf-8"))
    return [{"name": m["name"], "key": m["key"], "available": profile_path(m["key"]).exists(),
             "workbook": str(profile_path(m["key"]).relative_to(PRODUCTS_DIR.parent.parent))} for m in listed]


def load_product_profile(product: str, path: Path | None = None) -> ProductProfile:
    """Read and validate one product's Parts sheet; raises ProductProfileError on anything it cannot use."""
    path = path or profile_path(product)
    if not path.exists():
        raise ProductProfileError(f"no product profile at {path}")
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if "Parts" not in book.sheetnames:
        raise ProductProfileError(f"{path.name} has no 'Parts' sheet")
    rows = book["Parts"].iter_rows(values_only=True)
    header = [str(c or "").strip() for c in next(rows, ())]
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        raise ProductProfileError(f"{path.name} Parts sheet is missing column(s): {', '.join(missing)}")

    parts, ids = [], set()
    for n, row in enumerate(rows, 2):
        v = {h: ("" if c is None else str(c).strip()) for h, c in zip(header, row) if h}
        if not v.get("Item"):
            continue
        where = f"{path.name} Parts row {n} ({v['Item'][:40]})"
        if v["Subsystem"] not in SUBSYSTEMS:
            raise ProductProfileError(f"{where}: Subsystem must be one of {sorted(SUBSYSTEMS)}, found {v['Subsystem']!r}")
        part_id = v["Part ID"] or f"row-{n}"
        if part_id in ids:
            raise ProductProfileError(f"{where}: Part ID {part_id} is used twice")
        ids.add(part_id)
        parts.append(Part(
            part_id=part_id, subsystem=v["Subsystem"], item=v["Item"], what_it_does=v["What it does"],
            manufacturer=v["Manufacturer"], part_number=v["Part number"],
            qty=_number(v["Qty per machine"], f"{where} quantity"),
            rate=_number(v["Rate (₹, before GST)"], f"{where} rate"),
            vendor=v["Vendor"], why_chosen=v["Why chosen"],
            must_have=tuple(s.strip() for s in v["Must Have"].split(";") if s.strip()),
        ))
    if not parts:
        raise ProductProfileError(f"{path.name} Parts sheet has no parts")
    return ProductProfile(product=product.upper(), path=path, parts=tuple(parts))
