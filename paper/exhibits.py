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
    pairs=[r for r in read("release_pairs.csv") if r["group"]=="all"]
    external=[]
    for yr,p in [("2020","7a"),("2020","504"),("2022","7a")]:
        rs=[r for r in pairs if r["origin"]==yr and r["program"]==p]
        vals=[100*mean(abs(num(r,k)-num(r,"truth")) for r in rs) for k in ("mature","period","chain")]
        vals.extend([100*max(abs(num(r,"prefix_revision")) for r in rs),
                     100*max(abs(num(r,"reconstructed_period")-num(r,"period")) for r in rs)])
        external.append([yr,PROGRAMS[p],str(len(rs))]+[f"{v:.3f}" for v in vals])
    tex_file("external.tex",external)

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

if __name__=="__main__":
    make()
