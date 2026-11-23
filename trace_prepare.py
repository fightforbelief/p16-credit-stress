"""Prepare de-identified four-edition candidate blocks for the frozen endpoint pairs."""
import argparse
import csv
import io
import json
import lzma
import tarfile
import zipfile
from contextlib import ExitStack
from decimal import Decimal
from pathlib import Path

from revision_records import EARLIEST, LATEST, ROOT, digest, normalized, parse, token_key

EDITIONS = ("2020Q3", "2022Q3", "2022Q4", "2025Q3")
DATES = ("2020-09-30", "2022-09-30", "2022-12-31", "2025-09-30")


def money(text):
    if not text or text.upper() in {"NA", "NAN", "NULL"}:
        return None
    return Decimal(text.replace(",", "").replace("$", ""))


def rows(path, edition):
    sources = json.loads((ROOT/"results/sources.json").read_text())
    september = json.loads((ROOT/"review/source.json").read_text())["sources"]["7a"]
    with ExitStack() as stack:
        if edition == "2022Q3":
            assert digest(path) == september["sha256"]
            bundle = stack.enter_context(tarfile.open(path))
            member, = [m for m in bundle if m.isfile() and m.name.endswith(".csv")]
            src = bundle.extractfile(member)
            expected = september["rows"]
        else:
            manifest = sources[edition[:4]]["manifest"]
            assert digest(path) == manifest["archive_sha256"]
            member, = [m for m in manifest["members"] if "2010" in m["file"] and "504" not in m["file"]]
            src = stack.enter_context(zipfile.ZipFile(path)).open(member["file"])
            expected = member["rows"]
        reader = csv.reader(stack.enter_context(io.TextIOWrapper(src, encoding="latin1", newline="")))
        header = [c.strip().lower() for c in next(reader)]
        fields = ("approvaldate", "grossapproval", "borrname", "borrzip", "borrstreet", "bankname",
                  "firstdisbursementdate", "chargeoffdate", "loanstatus", "grosschargeoffamount",
                  "paidinfulldate", "asofdate", "program")
        cols = [header.index(k) for k in fields]
        asof = parse(DATES[EDITIONS.index(edition)])
        position = 0
        for count, row in enumerate(reader, 1):
            if parse(row[cols[-2]].strip()) != asof or row[cols[-1]].strip().upper() != "7A":
                raise ValueError("Unexpected snapshot or program")
            a = parse(row[cols[0]].strip())
            if a and EARLIEST <= a <= LATEST:
                yield position, (a, money(row[cols[1]].strip())), [row[i].strip() for i in cols[2:-2]]
                position += 1
        assert count == expected


def prepare(paths, pairs, output):
    targets = json.loads(pairs.read_text())
    old_ids = {i for i, j, tier, q in targets}
    blocks = {block for pos, block, data in rows(paths[0], EDITIONS[0]) if pos in old_ids}
    books = [{} for _ in range(4)]
    candidates = {}
    for edition, path in zip(EDITIONS, paths):
        records = []
        for pos, block, data in rows(path, edition):
            if block not in blocks:
                continue
            name, zip_code, street, bank, entry, charge, status, amount, payoff = data
            approval, gross = block
            name = " ".join(name.upper().split())
            zip5 = zip_code.zfill(5) if zip_code.isdigit() and len(zip_code) <= 5 else zip_code
            common = (approval, gross, zip5)
            bank = normalized(bank)
            keys = (token_key(approval, name, zip_code, gross), token_key(*common, normalized(name)),
                    token_key(*common, bank, normalized(street)), token_key(*common, bank, parse(entry)))
            ids = [book.setdefault(k, len(book)+1) if k else 0 for book,k in zip(books,keys)]
            value = money(amount)
            if value is not None and value * 100 != (value * 100).to_integral_value():
                raise ValueError("Sub-cent charge-off amount")
            def iso(s):
                day = parse(s)
                return day.isoformat() if day else None
            records.append([pos,ids,iso(charge),status.strip().upper(),int(value*100) if value is not None else None,iso(payoff)])
        candidates[edition] = records
    with lzma.open(output,"wt",encoding="utf-8") as f:
        json.dump(dict(targets=targets,candidates=candidates,source_sha256=dict(zip(EDITIONS,map(digest,paths)))),f,separators=(",",":"))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pairs",type=Path)
    p.add_argument("output",type=Path)
    p.add_argument("archives",nargs=4,type=Path)
    a = p.parse_args()
    prepare(a.archives,a.pairs,a.output)
