"""Replay vintage completion on public count triangles. Python 3.11+ standard library."""
import csv
import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from statistics import mean
from build import RESULTS, SNAPSHOTS, label, quarter, write

H = 20
METHODS = ("carry", "historical", "development", "mature", "period", "frontier")

@dataclass(frozen=True)
class Cell:
    n: int
    undated: int
    events: tuple

    def prefix(self, age):
        return sum(self.events[:age])/self.n

def load():
    tables = defaultdict(dict)
    with (RESULTS/"triangles.csv").open(newline="") as f:
        for r in csv.DictReader(f):
            tables[r["edition"], r["program"], r["group"]][int(r["vintage"])] = Cell(
                int(r["n"]), int(r["undated"]), tuple(int(r[f"d{j}"]) for j in range(1,H+1)))
    return tables

def forecast(table, v, age, width):
    """Only read incidence cells on or above the information diagonal v+age-1."""
    t = v+age-1
    prefix = table[v].prefix(age)
    latest_mature = t-H+1
    mature = [table[q] for q in range(latest_mature-width+1, latest_mature+1)]
    old_rate = mean(c.prefix(H) for c in mature)
    old_tail = mean(c.prefix(H)-c.prefix(age) for c in mature)
    mature_early = sum(sum(c.events[:age]) for c in mature)
    factor = (sum(sum(c.events) for c in mature)/mature_early if mature_early else None)
    tails = []
    newest = []
    for j in range(age+1,H+1):
        last = t-j+1
        rates = [table[q].events[j-1]/table[q].n for q in range(last-width+1,last+1)]
        tails.append(mean(rates))
        newest.append(rates[-1])
    def clip(x):
        return max(prefix,min(1.,x))
    return dict(carry=prefix,historical=clip(old_rate),
                development=clip(prefix*factor) if factor is not None else None,
                mature=clip(prefix+old_tail),period=clip(prefix+sum(tails)),
                frontier=clip(prefix+sum(newest)))

def margin(table, v, age, width):
    errors = []
    last = v+age-H
    for q in range(last-19,last+1):
        try:
            p = forecast(table,q,age,width)["period"]
            errors.append(table[q].prefix(H)-p)
        except KeyError:
            return None
    return max(0.,sorted(errors)[math.ceil(.90*(len(errors)+1))-1])

def score(table, target, v, age, width):
    f = forecast(table,v,age,width)
    m = margin(table,v,age,width)
    pre = table[v].prefix(age)
    truth = target[v].prefix(H)
    p = f["period"]
    return dict(vintage=label(v), age=age, width=width, n=table[v].n, final_n=target[v].n,
                prefix=pre, final_prefix=target[v].prefix(age), truth=truth,
                undated_max=target[v].undated/target[v].n, **f,
                upper=min(1,p+m) if m is not None else None, stress_low=pre+.5*(p-pre),
                stress_high=min(1,pre+2*(p-pre)))

def paired_ci(diffs, length):
    rng = random.Random(160021+length)
    n = len(diffs)
    boot = []
    for _ in range(3000):
        draw = []
        while len(draw)<n:
            start = rng.randrange(n-length+1)
            draw.extend(diffs[start:start+length])
        boot.append(mean(draw[:n]))
    boot.sort()
    return [boot[74]*100,boot[2924]*100]

def summarize(rows):
    output=[]
    for (program,group,w), rs in group_by(rows,("program","group","width")).items():
        for scope, subset in [("all",rs),("stress",[r for r in rs if r["stress"]]),
                              ("other",[r for r in rs if not r["stress"]])]:
            for method in METHODS:
                errors = [r[method]-r["truth"] for r in subset if r[method] is not None]
                if not errors:
                    continue
                output.append(dict(program=program,group=group,width=w,scope=scope,
                    method=method,vintages=len(errors),mae_pp=100*mean(map(abs,errors)),
                    bias_pp=100*mean(errors),worst_under_pp=100*max(0,-min(errors))))
    return output

def group_by(rows, keys):
    groups=defaultdict(list)
    for r in rows:
        groups[tuple(r[k] for k in keys)].append(r)
    return groups

def run():
    tables=load()
    history=[]
    for (edition,program,g), table in tables.items():
        if edition!="2020" or g=="unknown":
            continue
        for v in range(4*1999,quarter(SNAPSHOTS["2020"])-H+2):
            for width in (4,8,12):
                try:
                    r=score(table,table,v,8,width)
                except KeyError:
                    if g=="all":
                        raise
                    continue
                stress=(v+8<=4*2009+1 and v+H-1>=4*2007+3)
                history.append(dict(program=program,group=g,stress=stress,**r))
    write("rolling.csv",history)
    write("metrics.csv",summarize(history))
    external=[]
    for edition in ("2020","2022"):
        t=quarter(SNAPSHOTS[edition])
        for program in ("7a","504"):
            for g in ("all","short","long"):
                inputs=tables.get((edition,program,g))
                if not inputs:
                    continue
                final=tables["2025",program,g]
                for age in range(8,20):
                    v=t-age+1
                    if not 4*2011<=v<=4*2019+2:
                        continue
                    r=score(inputs,final,v,age,8)
                    revised=forecast(final,v,age,8)["period"]
                    shift=r["final_prefix"]-r["prefix"]
                    tail=(r["truth"]-r["final_prefix"])-(r["period"]-r["prefix"])
                    assert abs(shift+tail-(r["truth"]-r["period"]))<1e-12
                    external.append(dict(origin=edition,program=program,group=g,**r,
                        prefix_revision=shift,tail_error=tail,reconstructed_period=revised))
    write("release_pairs.csv", external)
    ci=[]
    for (program,),rs in group_by([r for r in history if r["group"]=="all" and r["width"]==8],("program",)).items():
        diffs=[abs(r["period"]-r["truth"])-abs(r["mature"]-r["truth"]) for r in rs]
        for length in (4,8,12):
            lo,hi=paired_ci(diffs,length)
            ci.append(dict(program=program,block=length,delta_mae_pp=100*mean(diffs),lo=lo,hi=hi))
    write("block_sensitivity.csv",ci)

if __name__=="__main__":
    run()
