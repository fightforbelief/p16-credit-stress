"""Project the pinned September 2022 release onto its three required dates."""
import argparse
import csv
import hashlib
import io
import json
import lzma
import tarfile
from contextlib import ExitStack
from pathlib import Path

BASE = "https://raw.githubusercontent.com/cmcau/makeover_monday_archive/011e5e1e7d19bc8be7eed43c90403dd87c75f8f0/output/2023/w06/data/"
FILES = {
    "7a": ("foia-7afy2010-fy2019-asof-220930.csv.tar.gz",
           "c41701ee7f3a4b583cf065579d70bcafae4f736502b99e7078ea080a92fc7429"),
    "504": ("foia-504-fy2010-present-asof-220930.csv",
            "2811ab47598cd2784bfda296153f6d6d7c36dac578a32650a060d9e1c003b9b6"),
}

def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def project(directory, out):
    out.mkdir(exist_ok=True, parents=True)
    output = out / "sep2022.csv.xz"
    meta = {}
    with lzma.open(output, "wt", encoding="ascii", newline="") as target:
        wr = csv.writer(target, lineterminator="\n")
        wr.writerow(["program", "approval", "disbursement", "chargeoff"])
        for program, (name, expected) in FILES.items():
            path = directory / name
            if digest(path) != expected:
                raise ValueError(f"Source hash mismatch in {name}")
            with ExitStack() as stack:
                if name.endswith(".tar.gz"):
                    bundle = stack.enter_context(tarfile.open(path))
                    source = bundle.extractfile(name.removesuffix(".tar.gz"))
                else:
                    source = path.open("rb")
                stream = stack.enter_context(io.TextIOWrapper(source, encoding="latin1", newline=""))
                rows = csv.DictReader(stream)
                n = 0
                for row in rows:
                    if row["AsOfDate"].strip() != "20220930" or row["Program"].upper().strip() != program.upper():
                        raise ValueError("Unexpected program or edition")
                    wr.writerow([program, row["ApprovalDate"], row["FirstDisbursementDate"], row["ChargeOffDate"]])
                    n += 1
                meta[program] = dict(url=BASE+name, sha256=expected, rows=n)
    (out/"sep2022.json").write_text(json.dumps(dict(sources=meta, extract_sha256=digest(output)),indent=2)+"\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    parser.add_argument("--output",type=Path,default=Path("inputs"))
    args = parser.parse_args()
    project(args.directory,args.output)
