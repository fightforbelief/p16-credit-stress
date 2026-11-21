"""Check original output bytes and independently reconstruct central comparisons."""
import csv
import hashlib
import json
from math import isclose
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"results"

def read(name):
    with (OUT/name).open(newline="") as f:
        return list(csv.DictReader(f))

def same(x,y):
    if not isclose(float(x),float(y),rel_tol=1e-10,abs_tol=1e-12):
        raise ValueError(f"Mismatch {x} vs {y}")

def audit_extension(tables):
    folder = ROOT/"review"
    manifest = json.loads((folder/"execution.json").read_text())
    for path, expected in manifest["sha256"].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Reviewer extension checksum mismatch in {path}")
    with (folder/"september_counts.csv").open(newline="") as f:
        for r in csv.DictReader(f):
            n = int(r["n"])
            rates = [int(r[f"d{j}"])/n for j in range(1,21)]
            tables.setdefault(("2022Q3", r["program"], "all"), {})[int(r["vintage"])] = n,rates
    with (folder/"archive_pairs.csv").open(newline="") as f:
        pairs = list(csv.DictReader(f))
    for r in pairs:
        program, issue = r["program"], r["origin"]
        age = int(r["age"])
        v = int(r["vintage"][:4])*4+int(r["vintage"][-1])-1
        t = v+age-1
        assert (t//4,t%4+1)==(int(issue[:4]),int(issue[-1]))
        same(sum(tables["2025",program,"all"][v][1]),r["truth"])
        for field,edition in [("archived",issue if issue=="2022Q3" else issue[:4]),("revised","2025")]:
            table=tables[edition,program,"all"]
            for window in ("mature","recent"):
                y=sum(table[v][1][:age])
                for j in range(age+1,21):
                    last=t-(20 if window=="mature" else j)+1
                    pool=[row for u,row in table.items() if last-8<u<=last]
                    assert len(pool)==8
                    if r["family"]=="add":
                        y+=sum(rate[j-1] for n,rate in pool)/8
                    else:
                        counts=sum(n*sum(rate[:j]) for n,rate in pool)
                        prev=sum(n*sum(rate[:j-1]) for n,rate in pool)
                        y*=counts/prev
                same(min(1.,y),r[field+"_"+window])
    with (folder/"contrasts.csv").open(newline="") as f:
        for r in csv.DictReader(f):
            same(float(r["increment_component"])+float(r["base_component"]), r["multiplicative_delta"])
    print(f"Verified extension manifest and {len(pairs)} family-specific archive comparisons.")

def audit_revision(tables):
    from itertools import combinations
    from statistics import mean

    directory = ROOT/"revision"
    manifest = json.loads((directory/"execution.json").read_text())
    for name, checksum in manifest["sha256"].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Revision audit checksum mismatch in {name}")
    def rows(name):
        with (directory/name).open(newline="") as f:
            return list(csv.DictReader(f))
    targets = {r["vintage"]: r for r in rows("targets.csv")}
    assert len(targets) == 12
    gaps = {}
    for r in read_review_pairs():
        if (r["origin"], r["program"], r["family"]) != ("2020Q3", "7a", "mult"):
            continue
        y = float(r["truth"])
        def gap(prefix):
            return 100*(abs(float(r[prefix+"_recent"])-y)-abs(float(r[prefix+"_mature"])-y))
        v = r["vintage"]
        gaps[v] = (gap("archived"), gap("revised"))
        for val, key in zip(gaps[v], ("archive_gap_pp", "replay_gap_pp")):
            same(val, targets[v][key])
    assert set(gaps) == set(targets)
    delta = mean(b-a for a, b in gaps.values())
    for name in ("attribution.csv", "literal_attribution.csv", "roles.csv"):
        same(sum(float(r["order_averaged_shift_pp"]) for r in rows(name)), delta)
    deletion = {tuple(r["vintages"].split()): r for r in rows("influence.csv") if r["test"]=="omit_target"}
    for size in (1,2):
        for excluded in combinations(sorted(gaps), size):
            a,b = map(mean, zip(*(val for v,val in gaps.items() if v not in excluded)))
            row = deletion[excluded]
            same(a, row["archive_gap_pp"])
            same(b, row["perturbed_gap_pp"])
            assert int(row["reversal"]) == int(a < 0 < b)
    assert len(deletion) == 78
    # Re-estimate each switch directly from the raw vintage rates and population sizes.
    issue = 2020*4+2
    inputs = range(issue-26, issue-6)
    labels = {f"{u//4}Q{u%4+1}": u for u in inputs}
    paired = {
        r["vintage"]:float(r["truth"]) for r in read_review_pairs()
        if (r["origin"],r["program"],r["family"]) == ("2020Q3","7a","mult")}
    switches = [r for r in rows("influence.csv") if r["test"] in {"update_input","restore_input"}]
    assert len(switches) == 420
    assert len({(r["test"],r["vintages"]) for r in switches}) == 420
    for r in switches:
        edited = {labels[s] for s in r["vintages"].split()}
        assert len(edited) in (1,2)
        table = {u:tables["2025" if ((u in edited) == (r["test"]=="update_input")) else "2020",
                          "7a","all"][u] for u in inputs}
        losses = []
        for label,y in paired.items():
            v = labels[label]
            age = issue-v+1
            result = {}
            for method in ("recent","mature"):
                f = sum(table[v][1][:age])
                for j in range(age+1,21):
                    last = issue-(j if method=="recent" else 20)+1
                    pool = [table[u] for u in range(last-7,last+1)]
                    f *= sum(n*sum(rate[:j]) for n,rate in pool)/sum(n*sum(rate[:j-1]) for n,rate in pool)
                result[method] = abs(min(1,f)-y)
            losses.append(100*(result["recent"]-result["mature"]))
        val = mean(losses)
        same(val,r["perturbed_gap_pp"])
        same(mean(a for a,b in gaps.values()),r["archive_gap_pp"])
        assert int(r["reversal"]) == int(val > 0)
    print("Verified revision manifests, component totals, 78 target omissions and 420 input switches.")


def read_review_pairs():
    with (ROOT/"review/archive_pairs.csv").open(newline="") as f:
        return list(csv.DictReader(f))


def main():
    manifest=json.loads((OUT/"run.json").read_text())
    for folder,section in [(ROOT,"code_sha256"),(OUT,"output_sha256")]:
        for name,expected in manifest[section].items():
            if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=expected:
                raise ValueError(f"SHA-256 mismatch in {name}")

    supplement = ROOT/"sensitivity"
    sup = json.loads((supplement/"checksums.json").read_text())
    for p in (supplement/"entry_and_margins.csv", ROOT/"sensitivity.py", OUT/"triangles.csv"):
        if hashlib.sha256(p.read_bytes()).hexdigest() != sup[p.name]:
            raise ValueError(f"Sensitivity checksum mismatch in {p.name}")
    sources = json.loads((OUT/"sources.json").read_text())
    if sources["2020"]["manifest"]["extract_sha256"] != sup["2020.csv.gz"]:
        raise ValueError("Sensitivity check used a different 2020 extract")

    tables={}
    for r in read("triangles.csv"):
        key=(r["edition"],r["program"],r["group"])
        n=int(r["n"])
        rates=[int(r[f"d{j}"])/n for j in range(1,21)]
        assert 0<=sum(rates)<=1+1e-12
        tables.setdefault(key,{})[int(r["vintage"])]=(n,rates)

    def audit(r,edition,final):
        s=r["vintage"]; v=int(s[:4])*4+int(s[-1])-1
        age,width=int(r["age"]),int(r["width"])
        hist=tables[edition,r["program"],r["group"]]
        end=tables[final,r["program"],r["group"]]
        n,x=hist[v]
        same(n,r["n"]); same(end[v][0],r["final_n"])
        same(sum(end[v][1]),r["truth"])
        same(sum(x[:age]),r["prefix"])
        t=v+age-1
        mature=period=sum(x[:age])
        for j in range(age+1,21):
            period+=sum(z[j-1] for u,(k,z) in hist.items() if t-width<u+j-1<=t)/width
            mature+=sum(z[j-1] for u,(k,z) in hist.items() if t-width<u+19<=t)/width
        same(min(1,period),r["period"]); same(min(1,mature),r["mature"])

    rolling=read("rolling.csv"); pairs=read("release_pairs.csv")
    for r in rolling:
        audit(r,"2020","2020")
    for r in pairs:
        audit(r,r["origin"],"2025")
        same(float(r["truth"])-float(r["period"]),float(r["prefix_revision"])+float(r["tail_error"]))
    audit_extension(tables)
    audit_revision(tables)
    print(f"Verified manifest and {len(rolling)} rolling / {len(pairs)} archive-paired rows.")

if __name__=="__main__":
    main()
