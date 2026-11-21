"""Reconcile two public SBA archives to an aggregate ledger of visible revisions."""
import argparse
import csv
import io
import json
import lzma
import struct
import unicodedata
import zipfile
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from build import ROOT, label, parse, quarter
from review_prepare import digest

OUT = ROOT / "revision"
ISSUE = 2020 * 4 + 2
FIRST, LAST = ISSUE - 26, ISSUE - 7
CUTOFF = date(2020, 9, 30)
EARLIEST = date(FIRST // 4, (FIRST % 4) * 3 + 1, 1) - timedelta(days=365)
LATEST = date(2018, 12, 31)


def normalized(value):
    return "".join(c for c in unicodedata.normalize("NFKC", value).upper() if c.isalnum())


def token_key(*items):
    return items if all(items) else None


def source_rows(path, manifest):
    if digest(path) != manifest["archive_sha256"]:
        raise ValueError(f"Unexpected archive hash: {path.name}")
    member, = [m for m in manifest["members"] if "2010" in m["file"] and "504" not in m["file"]]
    with zipfile.ZipFile(path) as z, z.open(member["file"]) as f:
        reader = csv.reader(io.TextIOWrapper(f, encoding="latin1", newline=""))
        header = [name.lower().strip() for name in next(reader)]
        cols = [header.index(k) for k in ("approvaldate", "borrname",
                "borrzip", "grossapproval", "firstdisbursementdate", "chargeoffdate",
                "borrstreet", "bankname")]
        for count, row in enumerate(reader, 1):
            approval = parse(row[cols[0]].strip())
            if not approval or not EARLIEST <= approval <= LATEST:
                continue
            name, zip_code, gross, start, charge, street, bank = (row[i].strip() for i in cols[1:])
            name = " ".join(name.upper().split())
            amount = Decimal(gross.replace(",", "").replace("$", "")) if gross else None
            entry = parse(start)
            zip5 = zip_code.zfill(5) if zip_code.isdigit() and len(zip_code) <= 5 else zip_code
            common = (approval, amount, zip5)
            bank = normalized(bank)
            keys = (token_key(approval, name, zip_code, amount),
                    token_key(*common, normalized(name)),
                    token_key(*common, bank, normalized(street)),
                    token_key(*common, bank, entry))
            yield keys, approval, entry, parse(charge)
    if count != member["rows"]:
        raise ValueError("Source row count mismatch")


def record_state(approval, entry, event):
    state = None
    if entry and 0 <= (entry - approval).days <= 365 and FIRST <= quarter(entry) <= LAST:
        v = quarter(entry)
        if event is None:
            timing = "blank"
        elif event < entry:
            timing = "before_entry"
        elif event > CUTOFF:
            timing = "post_cutoff"
        elif quarter(event) - v >= 20:
            timing = "after_horizon"
        else:
            timing = "visible"
        age = quarter(event) - v + 1 if timing == "visible" else 0
        state = (v, age, timing, label(quarter(event)) if event else "")
    return state


def unique_index(rows, column):
    index = {}
    for i, (keys, state) in enumerate(rows):
        token = keys[column]
        if token:
            index[token] = None if token in index else i
    return index


def match(old, new):
    """Unique in each full projected file. Conflicting alternative assignments stay open."""
    pairs = {}
    used = set()
    strict, name, street, entry = (
        {i: right[k] for k, i in left.items() if i is not None and right.get(k) is not None}
        for left, right in ((unique_index(old, j), unique_index(new, j)) for j in range(4)))
    for i,j in strict.items():
        pairs[i] = ("literal",j)
        used.add(j)
    proposals = {}
    voters = Counter()
    for i in range(len(old)):
        if i in pairs:
            continue
        choices = {mapping[i] for mapping in (name, street, entry) if i in mapping}
        if len(choices) != 1:
            continue
        j, = choices
        if j in used:
            continue
        if i in name:
            tier = "normalized_name"
        elif i in street and i in entry:
            tier = "address_and_disbursement"
        else:
            continue
        proposals[i] = (tier,j)
        voters[j] += 1
    pairs.update((i, proposal) for i,proposal in proposals.items() if voters[proposal[1]] == 1)
    return pairs


def aligned(old, new, pairs):
    left = {}
    right = {}
    by_tier = Counter()
    for i,(tier,j) in pairs.items():
        key = ("pair",i)
        a,b = old[i][1],new[j][1]
        left[key], right[key] = [a],[b]
        for year, record in (("2020",a),("2025",b)):
            by_tier[tier,year] += int(record is not None)
    used = {j for tier,j in pairs.values()}
    left.update((("old",i),[r]) for i,(_,r) in enumerate(old) if i not in pairs and r)
    right.update((("new",j),[r]) for j,(_,r) in enumerate(new) if j not in used and r)
    return left, right, by_tier


def classify(old, new):
    if old is None or new is None or old[0] != new[0]:
        return "entry_or_vintage"
    if old[1] and new[1]:
        return "retimed_visible"
    if old[1]:
        return "visible_to_" + new[2]
    return old[2] + "_to_visible"


def archive_ledger(old, new):
    ledger, transitions, census, calendar = Counter(), Counter(), Counter(), Counter()
    def book(group, state, sign):
        if state:
            v, age = state[:2]
            ledger[group, v, 0] += sign
            if age:
                ledger[group, v, age] += sign

    def transition(group, a, b):
        transitions[group, a[2] if a else "outside", b[2] if b else "outside"] += 1
        if group != "unlinked":
            calendar[group, a[3] if a else "", b[3] if b else ""] += 1
        book(group, a, -1)
        book(group, b, 1)

    for key in old.keys() | new.keys():
        a, b = old.get(key, []), new.get(key, [])
        if len(a) == len(b) == 1 and key:
            left, right = a[0], b[0]
            if left or right:
                census["linked_union"] += 1
            for edition, state in (("2020", left), ("2025", right)):
                census["linked_" + edition] += int(state is not None)
            if (left and left[:2]) != (right and right[:2]):
                transition(classify(left, right), left, right)
        else:
            for edition, states in (("2020", a), ("2025", b)):
                for state in states:
                    if state:
                        census["unlinked_" + edition] += 1
                        transition("unlinked", state if edition == "2020" else None,
                                   state if edition == "2025" else None)
    return ledger, transitions, census, calendar


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(fields)
        writer.writerows(rows)


# A private, lossless projection of study fields in the relevant approval window.
# An integer token replaces the composite key across both editions. Zero is unmatchable.
PACK = struct.Struct("<7I")
YEARS = ("2020", "2025")


def project(paths, directory):
    directory.mkdir(parents=True, exist_ok=True)
    sources = json.loads((ROOT/"results/sources.json").read_text())
    tokens = [{} for _ in range(4)]
    metadata = {}
    for year, path in zip(YEARS, paths):
        manifest = sources[year]["manifest"]
        dest = directory/(year+".xz")
        with lzma.open(dest, "wb") as f:
            for keys, approval, entry, event in source_rows(path, manifest):
                ids = [book.setdefault(k, len(book)+1) if k else 0 for book,k in zip(tokens,keys)]
                f.write(PACK.pack(*ids, approval.toordinal(), entry.toordinal() if entry else 0,
                                  event.toordinal() if event else 0))
        metadata[year] = dict(archive_sha256=manifest["archive_sha256"], projected_sha256=digest(dest))
    (directory/"projection.json").write_bytes((json.dumps(metadata, indent=2)+"\n").encode())


def projected_rows(path):
    with lzma.open(path, "rb") as f:
        for *keys, a, d, e in PACK.iter_unpack(f.read()):
            yield tuple(keys), record_state(date.fromordinal(a), date.fromordinal(d) if d else None,
                                            date.fromordinal(e) if e else None)


def build(directory):
    sources = json.loads((ROOT/"results/sources.json").read_text())
    metadata = json.loads((directory/"projection.json").read_text())
    groups = []
    for year in YEARS:
        path = directory/(year+".xz")
        if (metadata[year]["projected_sha256"] != digest(path) or
                metadata[year]["archive_sha256"] != sources[year]["manifest"]["archive_sha256"]):
            raise ValueError("Projection provenance mismatch")
        groups.append(list(projected_rows(path)))
    old, new = groups
    pairs = match(old, new)
    OUT.mkdir(exist_ok=True)
    literal = {i:p for i,p in pairs.items() if p[0]=="literal"}
    left, right, _ = aligned(old, new, literal)
    strict, _, _, _ = archive_ledger(left, right)
    write_csv(OUT/"literal_ledger.csv", ["group", "vintage", "age", "net_records"],
              [(*k, n) for k, n in sorted(strict.items()) if n])
    left, right, tiers = aligned(old, new, pairs)
    ledger, transitions, census, calendar = archive_ledger(left, right)
    write_csv(OUT/"link_tiers.csv", ["tier","edition","eligible_records"],
              [(*k,n) for k,n in sorted(tiers.items())])
    (OUT/"projection.json").write_bytes((directory/"projection.json").read_bytes())
    write_csv(OUT / "ledger.csv", ["group", "vintage", "age", "net_records"],
              [(*k, n) for k, n in sorted(ledger.items()) if n])
    write_csv(OUT / "transitions.csv", ["group", "from_state", "to_state", "records"],
              [(*k, n) for k, n in sorted(transitions.items())])
    write_csv(OUT / "event_quarters.csv", ["group", "archived_event_quarter", "revised_event_quarter", "records"],
              [(*k, n) for k, n in sorted(calendar.items())])
    (OUT / "linkage.json").write_bytes((json.dumps(dict(sorted(census.items())), indent=2)+"\n").encode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", nargs=2, type=Path, metavar=("ARCHIVE_2020", "ARCHIVE_2025"))
    parser.add_argument("--directory", type=Path, default=ROOT/"inputs/revision_projection")
    args = parser.parse_args()
    if args.project:
        project(args.project, args.directory)
    else:
        build(args.directory)
