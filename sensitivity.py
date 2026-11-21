"""Post-protocol checks of entry selection and the center of the upper forecast."""
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from statistics import mean
from analysis import Cell, METHODS, forecast, load
from build import ROOT, SNAPSHOTS, parse, quarter

def extended_tables():
    totals, d = Counter(), defaultdict(Counter)
    with gzip.open(ROOT/"inputs/2020.csv.gz", "rt", newline="") as f:
        rows=csv.reader(f); next(rows)
        for program, _, a, start, chargeoff, _, _ in rows:
            a, start, co = parse(a), parse(start), parse(chargeoff)
            if not (a and start and a<=start<=SNAPSHOTS["2020"]):
                continue
            v=quarter(start)
            totals[program,v]+=1
            if co and start<=co<=SNAPSHOTS["2020"]:
                d[program,v][quarter(co)-v+1]+=1
    tables=defaultdict(dict)
    for (p,v), n in totals.items():
        tables[p][v]=Cell(n,0,tuple(d[p,v][j] for j in range(1,21)))
    return tables

def main():
    base=load()
    groups={"365_days":{p:base["2020",p,"all"] for p in ("504","7a")},
            "unrestricted_delay":extended_tables()}
    out=[]
    for rule,tables in groups.items():
        for p,table in tables.items():
            forecasts={}
            for v in sorted(table):
                if v+19>quarter(SNAPSHOTS["2020"]):
                    continue
                try:
                    forecasts[v]=forecast(table,v,8,8)
                except KeyError:
                    continue
            scored=[v for v in sorted(forecasts) if v>=4*1999]
            for method in METHODS:
                errs={v:table[v].prefix(20)-f[method] for v,f in forecasts.items() if f[method] is not None}
                for period in ("all","overlap","other"):
                    vs=[v for v in scored if v in errs and (period=="all" or
                        (v+8<=4*2009+1 and v+19>=4*2007+3)==(period=="overlap"))]
                    hits=[]
                    margins=[]
                    for v in vs:
                        hist=range(v-12-19,v-12+1)
                        if not all(i in errs for i in hist):
                            continue
                        m=max(0.,sorted(errs[i] for i in hist)[18])
                        margins.append(m)
                        hits.append(table[v].prefix(20)<=min(1.,forecasts[v][method]+m))
                    out.append(dict(rule=rule,program=p,method=method,scope=period,n_quarters=len(vs),
                                    loans=sum(table[v].n for v in vs),
                                    mae_pp=100*mean(abs(errs[v]) for v in vs),
                                    upper_n=len(hits),upper_hits=sum(hits),
                                    mean_margin_pp=100*mean(margins) if margins else None))
    outdir=ROOT/"sensitivity"
    outdir.mkdir(exist_ok=True)
    path=outdir/"entry_and_margins.csv"
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=out[0],lineterminator="\n");w.writeheader();w.writerows(out)
    evidence={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
              [path,ROOT/"sensitivity.py",ROOT/"inputs/2020.csv.gz",ROOT/"results/triangles.csv"]}
    (outdir/"checksums.json").write_text(json.dumps(evidence,indent=2)+"\n")

if __name__=="__main__":
    main()
