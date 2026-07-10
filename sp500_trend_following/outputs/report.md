# S&P 500 Trend Following vs Buy and Hold

The backtest implementation is ready, but this sandbox could not resolve public market-data hosts, so the live five-year comparison could not be completed here.

Run this from the `sp500_trend_following/` folder when network access is available:

```bash
python3 backtest_sp500_trend.py --start 2021-07-10 --end 2026-07-10 --output-dir outputs
```

Or use a local SPY CSV containing `Date` and either `Adj Close` or `Close`:

```bash
python3 backtest_sp500_trend.py --input path/to/spy.csv --start 2021-07-10 --end 2026-07-10 --output-dir outputs
```

Default assumptions:

- SPY is used as the investable S&P 500 proxy.
- Trend following holds SPY when the prior close is above the 200-day moving average; otherwise it holds cash.
- Buy and hold buys SPY at the start and liquidates at the end.
- Starting capital is `$100,000`.
- Trading cost is `1` basis point per buy or sell.
- Capital-gains tax is modeled at `35%` for short-term realized gains and `15%` for long-term realized gains.
- Taxes are applied to positive realized gains at sale time; losses do not create immediate refunds in this simplified model.

The refreshed report writes the comparison as a Markdown table with final after-tax value, total return, CAGR, drawdown, trades, fees, and taxes.
