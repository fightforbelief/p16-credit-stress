"""Freeze the published visible-to-blank pairs using the original endpoint projection."""
import argparse
import json
from pathlib import Path

from revision_records import ROOT, classify, digest, match, projected_rows


def select(directory):
    metadata = json.loads((ROOT/"revision/projection.json").read_text())
    rows = []
    for year in ("2020", "2025"):
        path = directory/(year+".xz")
        if digest(path) != metadata[year]["projected_sha256"]:
            raise ValueError(f"Endpoint projection mismatch: {year}")
        rows.append(list(projected_rows(path)))
    old, new = rows
    targets = []
    for i, (tier, j) in sorted(match(old, new).items()):
        a, b = old[i][1], new[j][1]
        if a and b and a[2] == "visible" and b[2] == "blank" and classify(a,b) == "visible_to_blank":
            targets.append([i, j, tier, a[3]])
    if len(targets) != 602 or sum(p[2] == "literal" for p in targets) != 345:
        raise ValueError("Published endpoint population not recovered")
    return targets


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("--output",type=Path)
    args = p.parse_args()
    payload = json.dumps(select(args.directory), separators=(",", ":"))
    if args.output:
        args.output.write_bytes((payload+"\n").encode())
    else:
        print(payload)
