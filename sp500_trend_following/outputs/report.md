# S&P 500 Trend Following vs Buy and Hold

Period: 2021-07-12 to 2026-07-10 (1,668 trading rows).
Data: local CSV: outputs/spy_yfinance_prices.csv. SPY is used as the investable S&P 500 proxy.

## Strategy

- Trend following: hold SPY when the prior close is above its 200-day moving average; otherwise hold cash.
- Buy and hold: buy SPY on the first available date and liquidate on the final date.
- Initial capital: $100,000.00.
- Transaction cost: 1.00 bps per trade plus $0.00 fixed commission.
- Tax model: realized gains are taxed at sale time; short-term gains at 35.00%, long-term gains at 15.00%. Losses do not create immediate refunds in this simplified model.
- Cash return while out of market: 0.00% annualized.

## Results

| Strategy | Final after-tax value | Total return | CAGR | Max drawdown | Trades | Fees | Taxes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| trend following | $127,864.80 | 27.86% | 5.05% | -24.02% | 32 | $313.82 | $16,793.20 |
| buy and hold | $172,054.12 | 72.05% | 11.48% | -24.50% | 2 | $28.48 | $12,715.43 |

Winner on after-tax ending value: **buy and hold**.

## Caveats

- This is a backtest, not financial or tax advice.
- SPY adjusted close data includes distributions in the return series, but this model does not separately tax dividends.
- Tax law depends on filing status, income, state, wash-sale effects, loss carryforwards, and other details. Change the tax-rate arguments to match the scenario you want to study.
