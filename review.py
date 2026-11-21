"""Matched-window reviewer diagnostics from public SBA vintage triangles."""
import argparse
import csv
import json
import lzma
import platform
import sys
from collections import Counter, defaultdict
from datetime import date
from math import isclose, prod
from pathlib import Path
from statistics import mean

from analysis import Cell, forecast, load
from build import ROOT, label, parse, quarter
from review_prepare import digest

OUT = ROOT / "review"
H, AGE, WIDTH = 20, 8, 8
FIRST, OLD_END, COMMON_END = 1999*4, 2015*4+3, 2019*4+2
FINAL = 2025*4+2
EPISODES = {"2001": (2001*4,2001*4+3), "GFC": (2007*4+3,2009*4+1),
            "COVID": (2020*4,2020*4+1)}
SEP = "2022Q3"

def write(name, rows):
    with (OUT/name).open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=rows[0], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

def build_edition():
    x=ROOT/"inputs/sep2022.csv.xz"
    meta=json.loads((ROOT/"inputs/sep2022.json").read_text())
    if digest(x)!=meta["extract_sha256"]:
        raise ValueError("Corrupt September extract")
    n, events, raw=Counter(), defaultdict(Counter), Counter()
    asof=date(2022,9,30)
    with lzma.open(x,"rt",newline="") as f:
        rows=csv.reader(f); next(rows)
        for p,a,d,e in rows:
            raw[p]+=1
            approval,entry,charge=map(parse,(a,d,e))
            if not (approval and entry and 0<=(entry-approval).days<=365 and entry<=asof):
                continue
            key=(p,quarter(entry))
            n[key]+=1
            if charge and entry<=charge<=asof:
                events[key][quarter(charge)-key[1]+1]+=1
    if raw!={p:s["rows"] for p,s in meta["sources"].items()}:
        raise ValueError("Unexpected raw census size")
    write("september_counts.csv", [dict(program=p, vintage=v, n=count,
          **{f"d{j}":events[p,v][j] for j in range(1,H+1)})
          for (p,v),count in sorted(n.items())])
    (OUT/"source.json").write_bytes((json.dumps(meta,indent=2)+"\n").encode())

def new_edition():
    tables=defaultdict(dict)
    with (OUT/"september_counts.csv").open(newline="") as f:
        for r in csv.DictReader(f):
            tables[r["program"]][int(r["vintage"])]=Cell(int(r["n"]),0,
                tuple(int(r[f"d{j}"]) for j in range(1,H+1)))
    return tables

def increments(table, last, j, weights):
    pool=[table[u] for u in range(last-WIDTH+1,last+1)]
    if weights=="loan":
        mass=sum(r.n for r in pool)
        return sum(r.events[j-1] for r in pool)/mass, sum(sum(r.events[:j-1]) for r in pool)/mass
    return mean(r.events[j-1]/r.n for r in pool), mean(r.prefix(j-1) for r in pool)

def paired(table,v,age,weights):
    pre=table[v].prefix(age)
    pools={key:[] for key in ("m","r")}
    for j in range(age+1,H+1):
        for key, last in [("m",v+age-H),("r",v+age-j)]:
            pools[key].append(increments(table,last,j,weights))
    estimates={}
    for k in pools:
        estimates["add_"+k]=min(1.,pre+sum(d for d,b in pools[k]))
        for h in pools:
            # The first subscript selects increments, the second selects bases.
            if all(b>0 for d,b in pools[h]):
                factors=[1+d/b for (d,_),(_,b) in zip(pools[k],pools[h])]
                estimates["mult_"+k+h]=min(1.,pre*prod(factors))
            else:
                estimates["mult_"+k+h]=None
    return estimates

def overlaps(lo,hi,episode):
    a,b=EPISODES[episode]
    return lo<=b and hi>=a

def historical(tables):
    rows=[]
    for p in ("7a","504"):
        prior={}
        first_table=tables["2020",p,"all"]
        end=COMMON_END if p=="7a" else FINAL-H+1
        for v in range(min(first_table)+H-AGE+WIDTH-1,end+1):
            edition="2020" if v<=OLD_END else "2025"
            tab=tables[edition,p,"all"]
            y=tab[v].prefix(H)
            base=forecast(tab,v,AGE,WIDTH)
            # Reuse original scores for error calibration up to the old panel boundary.
            last=v+AGE-H
            errors=[prior[u] for u in range(last-19,last+1) if u in prior]
            upper=None if len(errors)<20 else min(1,base["period"]+max(0,sorted(errors)[18]))
            prior[v]=y-base["period"]
            if v<FIRST:
                continue
            for weight in ("vintage","loan"):
                f=paired(tab,v,AGE,weight)
                for a,b in ([("add_m","mature"),("add_r","period")] if weight=="vintage"
                            else [("mult_mm","development"),("mult_rr","chain")]):
                    if not isclose(f[a],base[b],abs_tol=1e-12):
                        raise ValueError("Original method mismatch")
                period="original" if v<=OLD_END else ("later" if v<=COMMON_END else "504_extra")
                rows.append(dict(panel=period,edition=edition,program=p,vintage=label(v),weights=weight,
                    n=tab[v].n,truth=y,period_upper=upper,
                    clean_gfc=int(not overlaps(v-19,v+19,"GFC")),
                    **{k:int(overlaps(v+AGE,v+H-1,k)) for k in EPISODES},**f))
    return rows

def summarize(rows):
    out=[]
    for p in ("7a","504"):
        for w in ("vintage","loan"):
            subset=[r for r in rows if r["program"]==p and r["weights"]==w]
            for tag in ("original","original_clean","later","504_extra"):
                s=[r for r in subset if (r["panel"]=="original" and r["clean_gfc"]
                       if tag=="original_clean" else r["panel"]==tag)]
                if not s: continue
                matched=[r for r in s if all(r[k] is not None for k in ("mult_mm","mult_rr","mult_mr","mult_rm"))]
                def loss(k):
                    return 100*mean(abs(r[k]-r["truth"]) for r in matched)
                mm,rr,mr,rm=map(loss,("mult_mm","mult_rr","mult_mr","mult_rm"))
                inc=((rm-mm)+(rr-mr))/2
                den=((mr-mm)+(rr-rm))/2
                out.append(dict(program=p,weights=w,panel=tag,quarters=len(s),matched=len(matched),
                                loans=sum(r["n"] for r in matched),
                                additive_delta=loss("add_r")-loss("add_m"),
                                multiplicative_delta=rr-mm,increment_component=inc,base_component=den))
    return out

def release_scores(tables):
    new=new_edition()
    rows=[]
    for issue,t,programs in [("2020Q3",2020*4+2,("7a","504")),
                             (SEP,2022*4+2,("7a","504")),
                             ("2022Q4",2022*4+3,("7a",))]:
        for p in programs:
            source=(new[p] if issue==SEP else tables[issue[:4],p,"all"])
            final=tables["2025",p,"all"]
            for age in range(8,20):
                v=t-age+1
                # Disbursements through FY2019 have complete approval-year support
                # in the 7(a) scoring file. The 504 file continues to the final date.
                if v<2011*4 or v+H-1>FINAL or (p=="7a" and v>COMMON_END):
                    continue
                y=final[v].prefix(H)
                e=forecast(source,v,age,WIDTH)
                f=forecast(final,v,age,WIDTH)
                for family,m,r in [("add","mature","period"),("mult","development","chain")]:
                    rows.append(dict(origin=issue,program=p,vintage=label(v),age=age,family=family,
                        truth=y,archived_mature=e[m],archived_recent=e[r],
                        revised_mature=f[m],revised_recent=f[r]))
    return rows

def releases_summary(rows):
    groups=defaultdict(list)
    for r in rows:
        groups[r["origin"],r["program"],r["family"]].append(r)
    out=[]
    for (issue,p,fam),rs in groups.items():
        for group in ("available","age8"):
            s=rs if group=="available" else [r for r in rs if r["age"]==8]
            result=dict(origin=issue,program=p,family=fam,ages=group,quarters=len(s),
                        archived_delta=None,revised_delta=None,revision_bound=None)
            if s:
                def gap(k):
                    return 100*mean(abs(r[k+"_recent"]-r["truth"])-abs(r[k+"_mature"]-r["truth"]) for r in s)
                bound=100*mean(sum(abs(r["revised_"+k]-r["archived_"+k]) for k in ("recent","mature")) for r in s)
                if abs(gap("archived")-gap("revised"))>bound+1e-12:
                    raise ValueError("Revision sensitivity bound violated")
                result.update(archived_delta=gap("archived"),revised_delta=gap("revised"),revision_bound=bound)
            out.append(result)
    return out

def episodes(rows):
    out=[]
    for p in ("7a","504"):
        for ep in EPISODES:
            s=[r for r in rows if r["program"]==p and r["weights"]=="vintage" and r[ep]]
            eligible=[r for r in s if r["period_upper"] is not None]
            out.append(dict(program=p,episode=ep,quarters=len(s),eligible=len(eligible),
                            covered=sum(r["truth"]<=r["period_upper"] for r in eligible)))
    return out

def main(rebuild):
    OUT.mkdir(exist_ok=True)
    if rebuild: build_edition()
    tables=load()
    history=historical(tables)
    pairs=release_scores(tables)
    for name,rows in [("quarters",history),("contrasts",summarize(history)),("episodes",episodes(history)),
                      ("archive_pairs",pairs),("archive_contrasts",releases_summary(pairs))]:
        write(name+".csv",rows)
    if rebuild:
        files=[p for p in OUT.iterdir() if p.suffix==".csv"]+[OUT/"source.json",
               ROOT/"results/triangles.csv",ROOT/"review.py",ROOT/"review_prepare.py",
               ROOT/"analysis.py",ROOT/"build.py"]
        manifest=dict(python=sys.version,platform=platform.platform(),sha256={
            p.relative_to(ROOT).as_posix():digest(p) for p in sorted(files)})
        (OUT/"execution.json").write_bytes((json.dumps(manifest,indent=2)+"\n").encode())

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild",action="store_true",help="Rebuild the new archive and record execution.")
    main(parser.parse_args().rebuild)
