"""Loads a product profile workbook (docs/products/<product>/ProductProfile.<PRODUCT>.xlsx).

The workbook is maintained in Excel by the teams, so the loader accepts extra
columns and known header variants, and stops with a named column or row when
something it needs is missing or invalid. Costs are read for code-side
arithmetic only; `Part.brief()` is what a prompt receives, and it has none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from .paths import PRODUCTS_DIR

TO_CONFIRM = "[to confirm]"
#: Marks a part whose must-haves come from the current part's datasheet at search time.
BASELINE_MARK = "[not documented"

#: Header variants seen in the teams' BOM sheets, mapped to the profile's column names.
ALIASES = {
    "item description": "Item Name",
    "leadtime for deilvery": "Leadtime for delivery",
    "lead time": "Leadtime for delivery",
    "qty": "Per Device usage Qty",
}
REQUIRED = ("Part ID", "Subsystem", "Item Name", "Per Device usage Qty", "Rate", "Must-have specs", "Search")
CHOICES = {
    "Subsystem": {"Embedded", "Electrical", "Mechanical"},
    "Search": {"yes", "no"},
}


class ProductProfileError(ValueError):
    """The workbook is missing, or a sheet, column or value the pipeline needs is wrong."""


@dataclass(frozen=True)
class Part:
    part_id: str
    subsystem: str
    item_name: str
    qty: float | None
    rate: float | None
    must_have: tuple[str, ...]
    baseline_from_datasheet: bool
    search: bool
    #: Every other column, as text, keyed by its header.
    fields: dict[str, str] = field(default_factory=dict)

    def get(self, column: str) -> str:
        """A column's value, or "" when absent or still to be confirmed."""
        value = self.fields.get(column, "")
        return "" if value == TO_CONFIRM else value

    def brief(self) -> str:
        """What a prompt may see about this part: role, model and requirements, never cost."""
        lines = [
            f"Part: {self.item_name}",
            f"Role: {self.get('Role') or 'not stated'}",
            f"Current part: {' '.join(v for v in (self.get('Manufacturer'), self.get('Part number')) if v) or 'not stated'}",
            "Must-have: " + ("; ".join(self.must_have) if self.must_have else
                             "not documented; take the current part's datasheet as the baseline"),
        ]
        for column in ("Why chosen", "Status", "Candidate"):
            if value := self.get(column):
                lines.append(f"{column}: {value}")
        return "\n".join(lines)


@dataclass(frozen=True)
class ProductProfile:
    product: str
    path: Path
    facts: dict[str, str]
    parts: tuple[Part, ...]

    def searchable(self) -> tuple[Part, ...]:
        return tuple(p for p in self.parts if p.search)


def _number(value, where: str) -> float | None:
    if value is None or str(value).strip() in ("", TO_CONFIRM):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        raise ProductProfileError(f"{where}: expected a number, found {value!r}") from None


def _header(cell) -> str:
    text = str(cell or "").strip()
    if text.lower().startswith("revised price on"):
        return "Rate"
    return ALIASES.get(text.lower(), text)


def profile_path(product: str) -> Path:
    return PRODUCTS_DIR / product.lower() / f"ProductProfile.{product.upper()}.xlsx"


def load_product_profile(product: str, path: Path | None = None) -> ProductProfile:
    """Read and validate one product's workbook; raises ProductProfileError on anything it cannot use."""
    path = path or profile_path(product)
    if not path.exists():
        raise ProductProfileError(f"no product profile at {path}")
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    for sheet in ("Product", "Parts"):
        if sheet not in book.sheetnames:
            raise ProductProfileError(f"{path.name} has no '{sheet}' sheet")

    facts = {
        str(r[0]).strip(): str(r[1]).strip()
        for r in book["Product"].iter_rows(min_row=2, values_only=True)
        if r and r[0] and r[1] is not None
    }

    rows = book["Parts"].iter_rows(values_only=True)
    header = [_header(c) for c in next(rows, ())]
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        raise ProductProfileError(f"{path.name} Parts sheet is missing column(s): {', '.join(missing)}")

    parts = []
    for n, row in enumerate(rows, 2):
        values = {h: ("" if v is None else str(v).strip()) for h, v in zip(header, row) if h}
        if not values.get("Item Name"):
            continue
        where = f"{path.name} Parts row {n} ({values['Item Name'][:40]})"
        for column, allowed in CHOICES.items():
            if values.get(column) not in allowed:
                raise ProductProfileError(f"{where}: {column} must be one of {sorted(allowed)}, found {values.get(column)!r}")
        must = values.get("Must-have specs", "")
        documented = must not in ("", TO_CONFIRM) and not must.startswith(BASELINE_MARK)
        parts.append(Part(
            part_id=values.get("Part ID") or f"row-{n}",
            subsystem=values["Subsystem"],
            item_name=values["Item Name"],
            qty=_number(values.get("Per Device usage Qty"), f"{where} quantity"),
            rate=_number(values.get("Rate"), f"{where} rate"),
            must_have=tuple(s.strip() for s in must.split(";") if s.strip()) if documented else (),
            baseline_from_datasheet=not documented,
            search=values["Search"] == "yes",
            fields={k: v for k, v in values.items() if k not in ("Rate",)},
        ))
    if not parts:
        raise ProductProfileError(f"{path.name} Parts sheet has no parts")
    return ProductProfile(product=product.upper(), path=path, facts=facts, parts=tuple(parts))
