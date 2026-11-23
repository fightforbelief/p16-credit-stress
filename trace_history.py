"""Trace fixed endpoint loans through the September and December 2022 archives."""
import argparse
import json
import lzma
import platform
import sys
from collections import Counter
from pathlib import Path

from revision_records import ROOT, digest, match, write_csv
from trace_prepare import DATES, EDITIONS
from trace_select import select

OUT = ROOT/"followup"


def bridge(left, right):
    """Compare unique links from both endpoints, rejecting disagreements and reuse."""
    choices = []
    for a,b in zip(left,right):
        if a is not None and b is not None and a != b:
            choices.append((None,"conflict"))
        elif a is not None or b is not None:
            choices.append((a if a is not None else b,
                            "both" if a is not None and b is not None else "2020_only" if a is not None else "2025_only"))
        else:
            choices.append((None,"unmatched"))
    counts = Counter(i for i,_ in choices if i is not None)
    return [(None,"collision") if i is not None and counts[i]>1 else (i,tier) for i,tier in choices]


def field_state(r, original):
    if r is None:
        return ("unlinked",)*3
    charge, status, amount, payoff = r[2:]
    date_code = "blank" if charge is None else "original" if charge == original else "redated"
    amt = "missing" if amount is None else "zero" if amount == 0 else "positive" if amount > 0 else "negative"
    return date_code,status or "(blank)",amt


def amount_change(a,b):
    if a is None or b is None:
        return "unlinked"
    x,y = a[4],b[4]
    if x is None or y is None:
        return "both_missing" if x == y else "became_missing" if y is None else "became_reported"
    return "same" if x == y else "increased" if y > x else "decreased"


def run(file, projection):
    with lzma.open(file,"rt",encoding="utf-8") as f:
        data = json.load(f)
    targets = select(projection)
    assert targets == data["targets"]
    rows = [data["candidates"][e] for e in EDITIONS]
    keys = [[(r[1],None) for r in table] for table in rows]
    positions = [{r[0]:i for i,r in enumerate(table)} for table in rows]
    ends = [(positions[0][i],positions[-1][j]) for i,j,tier,q in targets]
    pairs = match(keys[0],keys[-1])
    for (i,j),(_,_,tier,_) in zip(ends,targets):
        assert pairs[i] == (tier,j)
    links = []
    for k in (1,2):
        old_links, new_links = match(keys[0],keys[k]), match(keys[-1],keys[k])
        links.append(bridge([old_links.get(i,(None,None))[1] for i,j in ends],
                            [new_links.get(j,(None,None))[1] for i,j in ends]))
    paths, changes, payoff_evidence = Counter(), Counter(), Counter()
    totals = [[0,0,0] for _ in EDITIONS]
    for h,(i,j) in enumerate(ends):
        mid = [rows[k][ix] if ix is not None else None for k,(ix,tag) in enumerate((x[h] for x in links),1)]
        trail = [rows[0][i],*mid,rows[-1][j]]
        original = trail[0][2]
        assert original and trail[-1][2] is None
        first = next(k for k,r in enumerate(trail) if r is not None and r[2] is None)
        states = [field_state(r,original) for r in trail]
        diffs = [amount_change(a,b) for a,b in zip(trail,trail[1:])]
        paths[(targets[h][2],links[0][h][1],links[1][h][1],*(s for state in states for s in state),*diffs)] += 1
        prev = max(k for k in range(first) if trail[k] is not None)
        a,b = trail[prev],trail[first]
        changes[(EDITIONS[prev],EDITIONS[first],states[prev][1],states[first][1],states[prev][2],
                 states[first][2],amount_change(a,b))] += 1
        payoff = b[5]
        timing = ("missing" if not payoff else "on_or_before_old_chargeoff" if payoff <= original else
                  "after_chargeoff_by_2020Q3" if payoff <= "2020-09-30" else "after_2020Q3")
        def recorded_payoff(row, asof):
            if not row[5]:
                return "absent"
            return "by_snapshot" if row[5] <= asof else "after_snapshot"
        payoff_evidence[(EDITIONS[first],b[3],timing,recorded_payoff(b,DATES[first]),
                         trail[-1][3],recorded_payoff(trail[-1],DATES[-1]))] += 1
        for k,r in enumerate(trail):
            if r is not None:
                totals[k][0] += 1
                if r[4] is not None:
                    totals[k][1] += 1
                    totals[k][2] += r[4]
    OUT.mkdir(exist_ok=True)
    def table(name, header, counts):
        write_csv(OUT/name,[*header,"loans"],[(*k,n) for k,n in sorted(counts.items())])
    table("paths.csv",["endpoint_tier","sep_link","dec_link",
          *(e+"_"+field for e in EDITIONS for field in ("date","status","amount")),
          "amount_change_1","amount_change_2","amount_change_3"],paths)
    table("first_blank.csv",["prior_observed","first_observed_blank","status_from","status_to","amount_from","amount_to","amount_change"],changes)
    table("payoff.csv",["first_observed_blank","status","payoff_date_vs_original","first_blank_payoff","final_status","final_payoff"],payoff_evidence)
    write_csv(OUT/"amount_totals.csv",["edition","matched","reported_amount","gross_chargeoff_cents"],
              [(e,*v) for e,v in zip(EDITIONS,totals)])
    files = [*OUT.glob("*.csv"),*(ROOT/f for f in ("trace_select.py","trace_prepare.py","trace_history.py",
                 "revision_records.py","revision/projection.json","results/sources.json","review/source.json"))]
    meta = dict(python=sys.version,platform=platform.platform(),source_sha256=data["source_sha256"],
                projection_sha256=digest(file),sha256={p.relative_to(ROOT).as_posix():digest(p) for p in sorted(files)})
    (OUT/"execution.json").write_bytes((json.dumps(meta,indent=2)+"\n").encode())


if __name__=="__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("file",type=Path)
    p.add_argument("projection",type=Path)
    a = p.parse_args()
    run(a.file,a.projection)
