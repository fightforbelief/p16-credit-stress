"""Extract only study fields from pinned public archives, without changing row order."""
import argparse
import csv
import gzip
import hashlib
import io
import json
import zipfile
from pathlib import Path

SOURCES = {
    "2020": "thedevastator/sba-loan-guarantee-data-1990-1999",
    "2022": "williecosta/sba-7a-loan-data",
    "2025": "kuldeepmishra0496/sba-loan-data",
}
FIELDS = ["AsOfDate", "ApprovalDate", "FirstDisbursementDate", "ChargeOffDate",
          "LoanStatus", "TermInMonths"]

def prepare(year, archive, directory):
    directory.mkdir(exist_ok=True, parents=True)
    meta = {"source": SOURCES[year], "version": 1, "archive_sha256": None, "members": []}
    with archive.open("rb") as src:
        meta["archive_sha256"] = hashlib.file_digest(src, "sha256").hexdigest()
    output = directory / f"{year}.csv.gz"
    with zipfile.ZipFile(archive) as bundle, output.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0, compresslevel=6) as packed:
            with io.TextIOWrapper(packed, encoding="ascii", newline="") as out:
                writer = csv.writer(out, lineterminator="\n")
                writer.writerow(["program", *FIELDS])
                for name in sorted(bundle.namelist()):
                    if not name.lower().endswith(".csv") or "dictionary" in name.lower():
                        continue
                    program = "504" if "504" in name else "7a"
                    with bundle.open(name) as src:
                        rd = csv.reader(io.TextIOWrapper(src, encoding="latin1", newline=""))
                        header = [s.lower().strip().lstrip("ï»¿") for s in next(rd)]
                        idx = [header.index(s.lower()) for s in FIELDS]
                        count = 0
                        for row in rd:
                            if not row:
                                continue
                            writer.writerow([program, *(row[i].strip() for i in idx)])
                            count += 1
                    meta["members"].append({"file": name, "rows": count})
    with output.open("rb") as src:
        meta["extract_sha256"] = hashlib.file_digest(src, "sha256").hexdigest()
    (directory / f"{year}.json").write_text(json.dumps(meta, indent=2)+"\n", encoding="utf-8")

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("year", choices=SOURCES)
    p.add_argument("archive", type=Path)
    p.add_argument("--output", type=Path, default=Path("inputs"))
    args = p.parse_args()
    prepare(args.year, args.archive, args.output)
