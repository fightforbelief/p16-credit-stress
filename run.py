"""Run from the project root using its own Python environment."""
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import analysis
import build

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    start=datetime.now(timezone.utc)
    subprocess.run([sys.executable,"-m","unittest","-v","test_analysis"], check=True)
    build.build()
    analysis.run()
    results=build.RESULTS
    files=sorted(p for p in results.glob("*") if p.suffix in {".json",".csv"} and p.name!="run.json")
    report=dict(started_utc=start.isoformat(),completed_utc=datetime.now(timezone.utc).isoformat(),
                python=sys.version,platform=platform.platform(),command="python run.py",
                code_sha256={p.name:digest(p) for p in Path(".").glob("*.py") if p.stem in
                             {"build","analysis","prepare","run","test_analysis"}},
                output_sha256={p.name:digest(p) for p in files})
    (results/"run.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__":
    main()
