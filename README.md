# Finance Research

## Weak-Form EMH Sector Analysis

This project tests weak-form market efficiency across major U.S. SPDR sector ETFs and distinct market environments using:

- Variance Ratio Test
- Lag-1 Autocorrelation Test
- Runs Test

Each test uses a 5% significance level. The primary comparison is the sector-by-period matrix: sectors are rows, market periods are columns, and each cell shows how many of the three tests rejected weak-form EMH.

![Weak-Form EMH Rejections by Sector and Market Period](outputs/sector_emh_heatmap.png)

### Outputs

- [Detailed sector-period results](outputs/sector_emh_detailed_results.md)
- [Detailed results CSV](outputs/sector_emh_detailed_results.csv)
- [Sector comparison matrix CSV](outputs/sector_emh_summary_matrix.csv)
- [Heatmap PNG](outputs/sector_emh_heatmap.png)

### Run Locally

```bash
python -m pip install -r requirements.txt
python sector_emh_analysis.py
```
