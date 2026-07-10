# S&P 500 Trend-Following Backtest

This folder compares a simple S&P 500 trend-following strategy with buy and hold in table form.

SPY is used as the investable S&P 500 proxy because the index itself is not directly tradable. The script prefers adjusted close data so dividends and splits are included in the return path.

## Default Strategy

- Trend following: hold SPY when the prior close is above the 200-day moving average; otherwise hold cash.
- Buy and hold: buy SPY at the start of the evaluation window and sell at the end.
- Default starting capital: `$100,000`.
- Default transaction fee: `1` basis point per buy or sell.
- Default tax rates: `35%` short-term realized gains, `15%` long-term realized gains.

The tax model is deliberately simple: positive realized gains are taxed when a sale happens, while losses do not create immediate refunds. Real tax outcomes depend on filing status, income, state taxes, loss carryforwards, wash-sale rules, and other details.

## Run

```bash
python3 backtest_sp500_trend.py --start 2021-07-10 --end 2026-07-10 --output-dir outputs
```

If online download is unavailable, provide a local CSV containing `Date` and either `Adj Close` or `Close`:

```bash
python3 backtest_sp500_trend.py --input path/to/spy.csv --start 2021-07-10 --end 2026-07-10 --output-dir outputs
```

Useful knobs:

```bash
--initial-capital 100000
--sma-window 200
--fee-bps 1
--commission 0
--short-tax-rate 0.35
--long-tax-rate 0.15
--risk-free-rate 0.00
```

## Table Output

The generated report presents the strategy comparison as a Markdown table with:

- final after-tax value
- total return
- CAGR
- max drawdown
- trade count
- transaction fees paid
- capital gains taxes paid

To write the table as its own file after the backtest produces `outputs/summary.csv`, run:

```bash
python3 make_comparison_table.py --summary outputs/summary.csv --output outputs/comparison_table.md
```

## Outputs

The scripts write:

- `outputs/report.md`: human-readable comparison table and assumptions.
- `outputs/comparison_table.md`: standalone Markdown results table.
- `outputs/summary.csv`: key metrics backing the table.
- `outputs/equity_curve.csv`: daily equity values.
- `outputs/trades.csv`: all buys, sells, fees, and taxes.
- `outputs/prices_used.csv`: normalized input prices.
