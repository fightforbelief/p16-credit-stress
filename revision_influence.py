"""Attribute the September 2020 7(a) gap using an aggregate revision ledger."""
import csv
import itertools
import json
import math
import platform
import sys
from collections import defaultdict
from statistics import mean

from analysis import Cell, forecast, load
from build import ROOT, label
from review_prepare import digest
from revision_records import FIRST, ISSUE, LAST, OUT, write_csv

INPUTS = tuple(range(FIRST, LAST + 1))
TARGETS = tuple(range(ISSUE - 18, LAST + 1))
H = 20


def csv_rows(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def gap_rows(table, truth):
    gaps = {}
    for v in TARGETS:
        estimates = forecast(table, v, ISSUE - v + 1, 8)
        gaps[v] = 100 * (abs(estimates["chain"] - truth[v]) -
                         abs(estimates["development"] - truth[v]))
    return gaps


def triangle(table):
    return {v: Cell(table[v].n, 0, tuple(x if v+j <= ISSUE else 0
                    for j, x in enumerate(table[v].events))) for v in INPUTS}


def apply(source, edits, selected):
    new = {v: [cell.n, *cell.events] for v, cell in source.items()}
    for group in selected:
        for v, age, change in edits[group]:
            new[v][age] += change
    if any(min(row) < 0 or sum(row[1:]) > row[0] for row in new.values()):
        raise ValueError("Invalid hybrid count")
    return {v: Cell(row[0], 0, tuple(row[1:])) for v, row in new.items()}


def shapley(scores, groups):
    k = len(groups)
    result = []
    for i, group in enumerate(groups):
        bit = 1 << i
        value = sum((scores[s | bit] - scores[s]) / (k * math.comb(k-1, s.bit_count()))
                    for s in scores if not s & bit)
        result.append((group, scores[bit], scores[(1 << k)-1 ^ bit], value))
    return result


def field_attribution(old, new, truth, prefix):
    edits = defaultdict(list)
    for r in csv_rows(OUT/(prefix+"ledger.csv")):
        edits[r["group"]].append(tuple(int(r[k]) for k in ("vintage", "age", "net_records")))
    if apply(old, edits, edits) != new:
        raise ValueError("Revision ledger does not reproduce all visible input cells")
    groups = sorted(edits)
    scores = {}
    for mask in range(1 << len(groups)):
        active = [group for i, group in enumerate(groups) if mask & (1 << i)]
        scores[mask] = mean(gap_rows(apply(old, edits, active), truth).values())
    attribution = shapley(scores, groups)
    assert math.isclose(sum(row[-1] for row in attribution), scores[max(scores)]-scores[0], abs_tol=1e-10)
    write_csv(OUT/(prefix+"attribution.csv"), ["group", "group_alone_gap_pp", "other_groups_gap_pp",
                                     "order_averaged_shift_pp"], attribution)
    return scores


def main():
    tables = load()
    old = triangle(tables["2020", "7a", "all"])
    final = tables["2025", "7a", "all"]
    new = triangle(final)
    truth = {v: final[v].prefix(H) for v in TARGETS}
    old_gaps, new_gaps = gap_rows(old, truth), gap_rows(new, truth)
    published = {r["vintage"]: r for r in csv_rows(ROOT/"review/archive_pairs.csv")
                 if r["origin"] == "2020Q3" and r["program"] == "7a" and r["family"] == "mult"}
    assert set(published) == {label(v) for v in TARGETS}
    for v in TARGETS:
        r = published[label(v)]
        for edition, gaps in (("archived", old_gaps), ("revised", new_gaps)):
            reproduced = 100 * (abs(float(r[edition+"_recent"])-float(r["truth"])) -
                                abs(float(r[edition+"_mature"])-float(r["truth"])))
            assert math.isclose(reproduced, gaps[v], abs_tol=1e-10)
    write_csv(OUT/"targets.csv", ["vintage", "age", "archive_gap_pp", "replay_gap_pp", "shift_pp"],
              [(label(v), ISSUE-v+1, old_gaps[v], new_gaps[v], new_gaps[v]-old_gaps[v]) for v in TARGETS])
    linkage = json.loads((OUT/"linkage.json").read_text())
    for year, table in (("2020", old), ("2025", new)):
        assert sum(c.n for c in table.values()) == linkage["linked_"+year] + linkage["unlinked_"+year]
    field_attribution(old, new, truth, "literal_")
    scores = field_attribution(old, new, truth, "")
    # Each scored vintage is strictly younger than its donors in both rules.
    roles = ("target_n", "target_events", "donor_events")
    role_scores = {}
    for mask in range(8):
        donors = new if mask & 4 else old
        events = new if mask & 2 else old
        counts = new if mask & 1 else old
        losses = []
        for v in TARGETS:
            hybrid = dict(donors)
            hybrid[v] = Cell(counts[v].n, 0, events[v].events)
            f = forecast(hybrid, v, ISSUE-v+1, 8)
            losses.append(100*(abs(f["chain"]-truth[v])-abs(f["development"]-truth[v])))
        role_scores[mask] = mean(losses)
    assert math.isclose(role_scores[0], scores[0], abs_tol=1e-10)
    assert math.isclose(role_scores[7], scores[max(scores)], abs_tol=1e-10)
    write_csv(OUT/"roles.csv", ["input_role", "role_alone_gap_pp", "other_roles_gap_pp",
                                "order_averaged_shift_pp"], shapley(role_scores, roles))
    rows = []
    for size in (1, 2):
        for removed in itertools.combinations(TARGETS, size):
            keep = [v for v in TARGETS if v not in removed]
            rows.append(("omit_target", " ".join(map(label, removed)),
                        mean(old_gaps[v] for v in keep), mean(new_gaps[v] for v in keep)))
        for restored in itertools.combinations(INPUTS, size):
            for name, base, switched in (("restore_input", new, old), ("update_input", old, new)):
                hybrid = dict(base)
                hybrid.update({v: switched[v] for v in restored})
                rows.append((name, " ".join(map(label, restored)),
                             scores[0], mean(gap_rows(hybrid, truth).values())))
    write_csv(OUT/"influence.csv", ["test", "vintages", "archive_gap_pp", "perturbed_gap_pp", "reversal"],
              [(*r, int(r[2] < 0 < r[3])) for r in rows])
    files = [*OUT.glob("*.csv"), OUT/"linkage.json", OUT/"projection.json", ROOT/"revision_records.py",
             ROOT/"revision_influence.py", ROOT/"results/sources.json", ROOT/"results/triangles.csv",
             ROOT/"review/archive_pairs.csv", ROOT/"analysis.py", ROOT/"build.py", ROOT/"review_prepare.py"]
    manifest = dict(python=sys.version, platform=platform.platform(), sha256={
        f.relative_to(ROOT).as_posix():digest(f) for f in sorted(files)})
    (OUT/"execution.json").write_bytes((json.dumps(manifest, indent=2)+"\n").encode())


if __name__ == "__main__":
    main()
