"""Aggregate the minimal source extracts into calendar vintage triangles."""
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
SNAPSHOTS = {"2020": date(2020, 9, 30), "2022": date(2022, 12, 31), "2025": date(2025, 9, 30)}

@lru_cache(maxsize=160000)
def parse(s):
    if not s or s.upper() in {"NAN", "NULL", "NA"}:
        return None
    for fmt in ("%m-%d-%y", "%m/%d/%Y", "%Y-%m-%d", "%Y%m%d", "%d-%b-%y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Unknown date encoding {s!r}")

def quarter(d):
    return 4 * d.year + (d.month - 1) // 3

def label(q):
    return f"{q//4}Q{q%4+1}"

def write(name, rows):
    rows = list(rows)
    with (RESULTS / name).open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=rows[0].keys(), lineterminator="\n")
        wr.writeheader()
        wr.writerows(rows)

def build():
    RESULTS.mkdir(exist_ok=True)
    audit = {}
    triangles = []
    for edition, asof in SNAPSHOTS.items():
        extract = ROOT / "inputs" / f"{edition}.csv.gz"
        manifest = json.loads(extract.with_suffix("").with_suffix(".json").read_text())
        with extract.open("rb") as f:
            assert hashlib.file_digest(f, "sha256").hexdigest() == manifest["extract_sha256"]
        counts = defaultdict(Counter)
        cells = defaultdict(Counter)
        with gzip.open(extract, "rt", newline="") as f:
            rd = csv.reader(f)
            next(rd)
            for program, sd, ap, start, ch, status, term in rd:
                log = counts[program]
                log["rows"] += 1
                if parse(sd) != asof:
                    raise ValueError(f"Unexpected snapshot {sd} in {edition}")
                a, d = parse(ap), parse(start)
                if not (a and d):
                    log["missing_entry_date"] += 1
                    continue
                if not (0 <= (d-a).days <= 365 and d <= asof):
                    log["outside_entry_window"] += 1
                    continue
                e = parse(ch)
                flag = status.strip().upper().replace(" ", "") in {"CHGOFF", "CHARGEOFF"}
                valid = e is not None and d <= e <= asof
                log["included"] += 1
                log["flag_without_valid_date"] += int(flag and not valid)
                log["valid_date_without_flag"] += int(valid and not flag)
                log["invalid_nonempty_chargeoff_date"] += int(e is not None and not valid)
                try:
                    months = float(term)
                except ValueError:
                    months = 0
                group = ("short" if months <= 120 else "long") if months > 0 else "unknown"
                v = quarter(d)
                for g in ("all", group):
                    c = cells[program, g, v]
                    c["n"] += 1
                    c["undated"] += int(flag and not valid)
                    if valid:
                        c[quarter(e)-v+1] += 1
        for (program, g, v), c in sorted(cells.items()):
            triangles.append(dict(edition=edition, program=program, group=g, vintage=v,
                                  n=c["n"], undated=c["undated"],
                                  **{f"d{j}":c[j] for j in range(1,21)}))
        audit[edition] = dict(manifest=manifest, programs=counts)
    write("triangles.csv", triangles)
    (RESULTS / "sources.json").write_text(json.dumps(audit, indent=2)+"\n", encoding="utf-8")

if __name__ == "__main__":
    build()
