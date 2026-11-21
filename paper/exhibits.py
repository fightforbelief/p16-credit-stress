"""Typeset aggregate results and draw the published forecast trajectories."""
import csv
from pathlib import Path
from statistics import mean

PAPER = Path(__file__).resolve().parent
RESULTS = PAPER.parent / "results"
NAMES = {"carry":"Observed prefix","historical":"Historical five-year rate",
         "development":"Mature development factor","mature":"Mature increments",
         "chain":"Age-to-age chain","period":"Period increments","frontier":"Single-vintage frontier"}
PROGRAMS = {"7a":"7(a)","504":"504"}

def read(name):
    with (RESULTS/name).open(newline="") as f:
        return list(csv.DictReader(f))

def num(r,k):
    return float(r[k])

def tex_file(name, rows):
    lines = [" & ".join(row)+r" \\" for row in rows]
    (PAPER/name).write_text("\n".join(lines)+"\n")

def make():
    ms={(r["program"],r["scope"],r["method"]):r for r in read("metrics.csv")
        if r["group"]=="all" and r["width"]=="8"}
    rows=[]
    for m,name in NAMES.items():
        values=[]
        for p in PROGRAMS:
            values.extend([num(ms[p,"all",m],"mae_pp"), num(ms[p,"stress",m],"mae_pp"),
                           num(ms[p,"all",m],"worst_under_pp")])
        rows.append([name]+[f"{v:.2f}" for v in values])
    tex_file("accuracy.tex",rows)
    rolling=[r for r in read("rolling.csv") if r["width"]=="8" and r["group"]=="all"]
    upper=[]
    for p,name in PROGRAMS.items():
        for flag,s in [(None,"All"),("True","Overlap"),("False","Other")]:
            rs=[r for r in rolling if r["program"]==p and r["upper"] and (flag is None or r["stress"]==flag)]
            nonex=sum(num(r,"truth")<=num(r,"upper") for r in rs)
            x2=sum(num(r,"truth")<=num(r,"stress_high") for r in rs)
            inside=sum(num(r,"stress_low")<=num(r,"truth")<=num(r,"stress_high") for r in rs)
            width=mean(num(r,"upper")-num(r,"period") for r in rs)
            gap=max(max(0.,num(r,"truth")-num(r,"upper")) for r in rs)
            upper.append([name,s,str(len(rs)),f"{nonex}/{len(rs)}",f"{100*width:.2f}",
                          f"{100*gap:.2f}",f"{x2}/{len(rs)}",f"{inside}/{len(rs)}"])
    tex_file("upper.tex",upper)
    review = PAPER.parent / "review"
    with (review/"contrasts.csv").open(newline="") as f:
        contrast={(r["program"],r["panel"],r["weights"]):r for r in csv.DictReader(f)}
    matched=[]
    for program, display in PROGRAMS.items():
        for panel, name in [("original","1999--2015"),("original_clean","Exclusion"),("later","2016--19")]:
            pair=[contrast[program,panel,w] for w in ("vintage","loan")]
            vals=[float(r[k]) for r in pair for k in ("additive_delta","multiplicative_delta")]
            matched.append([display,name,pair[0]["matched"]]+[f"{v:+.2f}" for v in vals])
    tex_file("matched.tex",matched)
    with (review/"archive_contrasts.csv").open(newline="") as f:
        gaps={(r["origin"],r["program"],r["family"]):r for r in csv.DictReader(f) if r["ages"]=="available"}
    with (review/"archive_pairs.csv").open(newline="") as f:
        portfolios=list(csv.DictReader(f))
    external=[]
    for origin in ("2020Q3","2022Q3","2022Q4"):
        for program,display in PROGRAMS.items():
            if (origin,program,"add") not in gaps:
                continue
            rows=[r for r in portfolios if r["origin"]==origin and r["program"]==program and r["family"]=="add"]
            ages=[int(r["age"]) for r in rows]
            vals=[float(gaps[origin,program,fam][k]) for fam in ("add","mult") for k in ("archived_delta","revised_delta")]
            external.append([origin,display,f"{min(ages)}--{max(ages)}",str(len(ages))]+[f"{v:+.3f}" for v in vals])
    tex_file("external.tex",external)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    fig,axs=plt.subplots(2,1,figsize=(8,5),sharex=True,layout="constrained")
    for ax,(p,title) in zip(axs,PROGRAMS.items()):
        rs=[r for r in rolling if r["program"]==p]
        idx=list(range(len(rs)))
        stress_idx=[i for i,r in enumerate(rs) if r["stress"]=="True"]
        ax.axvspan(stress_idx[0]-.5,stress_idx[-1]+.5,color="#e5dfd4",alpha=.65)
        for k,lab,color,ls in [("truth","Observed","#20282e","-"),("period","Period","#126b85","-"),
                               ("mature","Mature","#9d682c","--"),("upper","Historical upper","#677a64",":")]:
            ax.plot(idx,[100*float(r[k]) if r[k] else float("nan") for r in rs],label=lab,
                    c=color,ls=ls,lw=1.8 if k=="truth" else 1.4)
        ax.set_title(title,loc="left",weight="bold",fontsize=10)
        ax.set_ylabel("Charge-offs (%)")
        ax.yaxis.set_major_locator(MaxNLocator(5))
        ax.spines[["right","top"]].set_visible(False)
        ax.grid(axis="y",alpha=.2)
    ticks=list(range(0,len(rs),8))
    axs[-1].set_xticks(ticks,[rs[i]["vintage"][:4] for i in ticks])
    axs[-1].set_xlabel("First-disbursement vintage")
    axs[0].legend(ncol=4,fontsize=8,frameon=False,loc="upper right")
    fig.savefig(PAPER/"vintages.pdf",metadata={"CreationDate":None,"ModDate":None})

def revision_figure():
    import matplotlib.pyplot as plt

    with (PAPER.parent/"revision/targets.csv").open(newline="") as f:
        targets = list(csv.DictReader(f))
    archive = [float(r["archive_gap_pp"]) for r in targets]
    replay = [float(r["replay_gap_pp"]) for r in targets]
    positions = range(len(targets))
    fig, ax = plt.subplots(figsize=(6.3, 2.45), layout="constrained")
    ax.axhline(0, color="#606060", lw=0.8)
    ax.vlines(positions, archive, replay, color="#929292", linewidth=1.5)
    ax.scatter(positions, archive, facecolors="white", edgecolors="#204766", s=37,
               label="September 2020 archive", zorder=3)
    ax.scatter(positions, replay, c="#a14f28", marker="D", s=13,
               label="September 2025 replay", zorder=4)
    labels = [r["vintage"][-2:] + ("\n"+r["vintage"][:4] if r["vintage"].endswith("Q1") else "")
              for r in targets]
    ax.set_xticks(positions, labels, fontsize=8)
    ax.set_yticks([-1, -0.5, 0, 0.5, 1])
    ax.set_ylabel("Absolute error gap (pp)", fontsize=9)
    ax.set_xlabel("First-disbursement quarter", fontsize=9)
    ax.spines[["right","top"]].set_visible(False)
    ax.legend(loc="upper left", frameon=False, fontsize=8)
    fig.savefig(PAPER/"revision_gaps.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


if __name__=="__main__":
    make()
    revision_figure()
