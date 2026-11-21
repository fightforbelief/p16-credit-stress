# Do newer loan vintages improve charge-off forecasts? Evidence from SBA portfolios and archived releases

Yunjie Guo and Hanqing Yang · Independent Researcher, Suzhou, China

[Paper (PDF)](paper/main.pdf) · [Study protocol](PROTOCOL.md) · [Review extension design](REVIEW_DESIGN.md) · [Forecasts from archived releases](review/archive_pairs.csv)

How much of a young portfolio's future charge-off incidence can be inferred from older loans? We reconstruct quarterly first-disbursement cohorts from four public SBA FOIA snapshots, compare seven forecast rules on the same vintages and check earlier editions against a later release. The target is the number of dated charge-offs through the twentieth calendar quarter per original eligible loan. Each program and vintage receives its own score. These forecasts describe funded portfolios and use no borrower names, risk scores or payoff dates.

## Findings

In the original 68 quarters (957,406 loans across both programs), using recent additive increments reduced MAE by 1.28 percentage points in 7(a) and 0.75 in 504. Among the 23 quarters whose entire donor and target span avoids the Great Recession, the changes are +0.04 and −0.14 points (recent minus mature). In 15 later disbursement quarters per program, the corresponding changes are −0.15 and +0.01. The broad historical advantage does not support a universal window choice.

The 7(a) historical upper forecast covered 0/17 eligible vintages overlapping the Great Recession and 7/13 overlapping the pandemic. Coverage in 504 was 7/17 and 10/13. Each event is one common macroeconomic episode. Three archived reference dates offer a different check. On the same September 2020 7(a) portfolios, recent multiplicative factors improved MAE by 0.185 points with archived inputs but worsened MAE by 0.215 points in a date-masked replay from 2025. The archive demonstrates a possible ranking reversal. Its frequency in other cycles remains unknown.

## Reproduce the comparisons from the published counts

From the project root, with Python 3.11 or later:

```shell
python verify.py
python -m unittest -v test_analysis test_review
python analysis.py
python review.py
```

The standard library is sufficient. Run the verifier on the original checked-out files before regenerating them. It validates the execution checksums and recomputes the period and mature-window forecasts directly from calendar-date membership for every scored row. The code reads `results/triangles.csv` and regenerates the rolling forecasts, the cross-release comparisons, the block sensitivity and the error metrics. Each vintage is encoded as four times the year plus the zero-based calendar quarter. Columns `d1` to `d20` count dated charge-offs by age. The disbursement quarter is age one. A zero at a future age in an immature row denotes an unobserved cell. Only cells with vintage + age − 1 at or before the issue quarter can be used. Group `all` includes every eligible record, including unknown contractual terms. The other groups partition the same population.

`rolling.csv` repeats each group and vintage for three window widths. Select `group=all,width=8` for the primary comparison. With the exception of columns explicitly labeled `_pp`, rate, error and margin fields are in fractions of the original cohort. Empty upper forecasts indicate insufficient mature history. `release_pairs.csv` scores forecasts from earlier files on a common quarterly population in the 2025 archive. A loan may appear in multiple editions. Counts across editions do not represent distinct loans.

## Rebuild the counts from the archives

The [SBA catalog](https://data.sba.gov/dataset/7a-504-foia) updates quarterly. The following version-1 mirrors preserve the editions used here. At each URL the version parameter must be retained. Save the returned ZIP under the indicated local name.

| Edition | Archive | Local name |
|---|---|---|
| September 2020 | [7(a) and 504 archives](https://api.kaggle.com/v1/datasets/download/thedevastator/sba-loan-guarantee-data-1990-1999?datasetVersionNumber=1) | `2020.zip` |
| December 2022 | [7(a) archive](https://api.kaggle.com/v1/datasets/download/williecosta/sba-7a-loan-data?datasetVersionNumber=1) | `2022.zip` |
| September 2025 | [7(a) and 504 archives](https://api.kaggle.com/v1/datasets/download/kuldeepmishra0496/sba-loan-data?datasetVersionNumber=1) | `2025.zip` |

Compare the three ZIP SHA-256 values with [the source manifest](results/sources.json). In the project's Windows environment, the complete rebuild is:

```powershell
py -3.12 -m venv .venv
$py = '.\.venv\Scripts\python.exe'
& $py prepare.py 2020 2020.zip
& $py prepare.py 2022 2022.zip
& $py prepare.py 2025 2025.zip
& $py run.py
```

The preparation step copies six public fields and the program identifier. The full run first executes the chronology and forecast tests, then builds the counts, estimates and scores. [The execution record](results/run.json) identifies the research-host Python version and the code and output checksums. The source manifest records the raw archive hashes, source member row counts, exclusions and charge-off date diagnostics. In an independent environment, platform metadata, line endings and compressed stream encodings can differ. The aggregate counts and numerical forecasts are the reproducibility targets.

## Rebuild the manuscript

```shell
python -m pip install matplotlib==3.10.8
python paper/exhibits.py
cd paper
tectonic main.tex
```

The checked-in tables and figure also allow the LaTeX manuscript to be built without Matplotlib. The paper discusses census scope, reporting revisions, overlapping quarters and the observed performance of the upper forecasts.

## Sensitivity checks

After the main comparison, we removed the 365-day entry limit in the 2020 archive and recalibrated a separate upper margin for each point forecast. From the same project environment, run `python sensitivity.py` after `run.py`. The [output](sensitivity/entry_and_margins.csv) reports the portfolio count, MAE, eligible upper forecasts, coverage count and mean margin for each rule. Its [checksums](sensitivity/checksums.json) identify the input, code, primary triangle and output.

## Reproduce the reviewer extension

The [matched-window contrasts](review/contrasts.csv) and [age-specific archive forecast pairs](review/archive_pairs.csv) are derived from the published count triangles with `python review.py`. Gaps in the contrast files are recent minus mature MAE, in percentage points. Forecasts and truth in the row-level files are fractions. `age8` rows in [the release summary](review/archive_contrasts.csv) count distinct target portfolios at the primary landmark. A missing gap with zero quarters denotes insufficient coverage. Each 2022 origin is identified by its calendar quarter.

To rebuild the fourth snapshot, download the two pinned files linked in [source.json](review/source.json) to one directory without changing their filenames. Run `python review_prepare.py DIRECTORY` and then `python review.py --rebuild` from the project root after building the original results. The first command verifies the original hashes and every row's edition and program, then copies the three dates used by the eligibility and outcome rules. The second builds the September 2022 aggregate counts and all review tables. [Execution manifest](review/execution.json) records the Windows environment, code and output hashes. No new third-party Python packages are required.
