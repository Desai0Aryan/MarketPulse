from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: object) -> object:
    """Neutralise spreadsheet formula injection for TEXT cells (OWASP): prefix a single quote when a
    string starts with = + - @ tab or CR. Numbers are written as-is (a negative float is not a formula)."""
    if isinstance(value, str) and value.startswith(_DANGEROUS):
        return "'" + value
    return value


def build_csv(header: Sequence[str], rows: Iterable[Sequence[object]], metadata: dict[str, str]) -> str:
    """CSV with '#'-prefixed metadata lines (source, basis, generation date) followed by the table."""
    buf = io.StringIO()
    for k, v in metadata.items():
        buf.write(f"# {k}: {str(v).replace(chr(10), ' ').replace(chr(13), ' ')}\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow([csv_safe(c) for c in r])
    return buf.getvalue()


def filename(symbol: str, kind: str, range_key: str, as_of: date) -> str:
    safe = "".join(c for c in symbol if c.isalnum() or c in "-.")
    return f"marketpulse_{safe}_{kind}_{range_key}_{as_of.isoformat()}.csv"
