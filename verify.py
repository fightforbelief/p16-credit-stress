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
    print(f"Verified manifest and {len(rolling)} rolling / {len(pairs)} archive-paired rows.")

if __name__=="__main__":
    main()
