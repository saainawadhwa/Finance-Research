# Finance Research

This repository contains finance research projects covering weak-form market efficiency tests and S&P 500 trading-strategy backtests.

## Current Analyses

- **SPY market-period weak-form EMH analysis**: tests SPY across selected market periods using variance ratio, autocorrelation, and runs tests.
- **International market efficiency analysis**: compares weak-form EMH evidence across global equity-market ETFs and market regimes.
- **U.S. sector market efficiency analysis**: compares weak-form EMH rejection patterns across U.S. sector ETFs and market regimes.
- **S&P 500 trend-following backtest**: compares a trend-following strategy with buy-and-hold after fees and taxes.
- **Market Classification Analysis**: compares Developed, Emerging, and Frontier/Selected Emerging equity-market proxies across the same market regimes, with variance-ratio, autocorrelation, and runs tests.

## Key Files

- `emh_spy_analysis.py`
- `international_emh_analysis.py`
- `sector_emh_analysis.py`
- `sp500_trend_following/`
- `outputs/international_emh/`
- `outputs/sector_emh_*`
- `outputs/market_classification_*`
- `outputs/variance_ratio_by_market_classification.*`

## Run Locally

Install the shared dependencies:

```bash
python -m pip install -r requirements.txt
```

Run the EMH analyses:

```bash
python emh_spy_analysis.py
python international_emh_analysis.py
python sector_emh_analysis.py
```

Run the S&P 500 trend-following backtest:

```bash
cd sp500_trend_following
python -m pip install -r requirements.txt
python backtest_sp500_trend.py --start 2021-07-10 --end 2026-07-10 --output-dir outputs
```

## Outputs

Generated tables and figures are committed under `outputs/` and `sp500_trend_following/outputs/` so the results can be reviewed without rerunning the scripts.
