#!/usr/bin/env python3
"""
Backtest a simple S&P 500 trend-following strategy against buy-and-hold.

The investable proxy is SPY because the S&P 500 index itself cannot be traded
directly. Use adjusted close data so dividends and splits are reflected in the
return stream.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd


YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
STOOQ_DAILY = "https://stooq.com/q/d/l/?s={symbol}&i=d&d1={start}&d2={end}"


@dataclass
class Lot:
    shares: float
    basis_per_share: float
    opened: date


@dataclass
class Portfolio:
    name: str
    cash: float
    shares: float = 0.0
    lots: list[Lot] = field(default_factory=list)
    realized_short_gain: float = 0.0
    realized_long_gain: float = 0.0
    realized_tax: float = 0.0
    fees_paid: float = 0.0
    trades: list[dict] = field(default_factory=list)

    def value(self, price: float) -> float:
        return self.cash + self.shares * price


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare S&P 500 trend following with buy-and-hold after fees and taxes."
    )
    parser.add_argument("--symbol", default="SPY", help="Investable proxy ticker. Default: SPY.")
    parser.add_argument("--start", default=None, help="Backtest start date, YYYY-MM-DD. Default: five years before --end.")
    parser.add_argument("--end", default=None, help="Backtest end date, YYYY-MM-DD. Default: today.")
    parser.add_argument("--input", type=Path, help="Optional local CSV with Date and Adj Close/Close columns.")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--initial-capital", type=float, default=100_000.0)
    parser.add_argument("--sma-window", type=int, default=200)
    parser.add_argument("--fee-bps", type=float, default=1.0, help="Trading cost in basis points per buy/sell. Default: 1 bp.")
    parser.add_argument("--commission", type=float, default=0.0, help="Fixed commission per trade. Default: 0.")
    parser.add_argument("--short-tax-rate", type=float, default=0.35, help="Tax rate on short-term realized gains. Default: 35%%.")
    parser.add_argument("--long-tax-rate", type=float, default=0.15, help="Tax rate on long-term realized gains. Default: 15%%.")
    parser.add_argument("--risk-free-rate", type=float, default=0.0, help="Annual cash return while out of market. Default: 0.")
    parser.add_argument("--no-download", action="store_true", help="Only use --input; do not try online sources.")
    return parser.parse_args()


def iso_date(value: str | None, default: date) -> date:
    if not value:
        return default
    return datetime.strptime(value, "%Y-%m-%d").date()


def fetch_yahoo(symbol: str, start: date, end: date) -> pd.DataFrame:
    period1 = int(time.mktime(datetime.combine(start, datetime.min.time()).timetuple()))
    period2 = int(time.mktime(datetime.combine(end + timedelta(days=1), datetime.min.time()).timetuple()))
    url = (
        f"{YAHOO_CHART.format(symbol=symbol)}"
        f"?period1={period1}&period2={period2}&interval=1d&events=history%7Cdiv%7Csplit&includeAdjustedClose=true"
    )
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    adj = result["indicators"].get("adjclose", [{}])[0].get("adjclose")
    prices = adj if adj else quote["close"]
    rows = []
    for ts, close, adj_close in zip(timestamps, quote["close"], prices):
        if close is None or adj_close is None:
            continue
        rows.append(
            {
                "Date": datetime.utcfromtimestamp(ts).date(),
                "Close": float(close),
                "Adj Close": float(adj_close),
            }
        )
    return pd.DataFrame(rows)


def fetch_stooq(symbol: str, start: date, end: date) -> pd.DataFrame:
    stooq_symbol = f"{symbol.lower()}.us" if "." not in symbol else symbol.lower()
    url = STOOQ_DAILY.format(
        symbol=stooq_symbol,
        start=start.strftime("%Y%m%d"),
        end=end.strftime("%Y%m%d"),
    )
    with urllib.request.urlopen(url, timeout=30) as response:
        text = response.read().decode("utf-8")
    rows = list(csv.DictReader(text.splitlines()))
    if not rows:
        raise ValueError("Stooq returned no rows")
    data = pd.DataFrame(rows)
    data["Date"] = pd.to_datetime(data["Date"]).dt.date
    data["Close"] = pd.to_numeric(data["Close"])
    data["Adj Close"] = data["Close"]
    return data[["Date", "Close", "Adj Close"]]


def load_prices(args: argparse.Namespace, start: date, end: date) -> tuple[pd.DataFrame, str]:
    if args.input:
        return normalize_prices(pd.read_csv(args.input), start, end), f"local CSV: {args.input}"

    if args.no_download:
        raise RuntimeError("--no-download was set, but --input was not provided")

    errors = []
    for label, loader in (("Yahoo Finance chart API", fetch_yahoo), ("Stooq CSV", fetch_stooq)):
        try:
            return normalize_prices(loader(args.symbol, start, end), start, end), label
        except (KeyError, ValueError, urllib.error.URLError, TimeoutError, OSError) as exc:
            errors.append(f"{label}: {exc}")
    raise RuntimeError("Could not download prices:\n" + "\n".join(errors))


def normalize_prices(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    columns = {col.lower().strip(): col for col in frame.columns}
    date_col = columns.get("date")
    price_col = (
        columns.get("adj close")
        or columns.get("adj_close")
        or columns.get("adjusted close")
        or columns.get("close")
    )
    if not date_col or not price_col:
        raise ValueError("CSV must include Date and Adj Close or Close columns")

    data = frame[[date_col, price_col]].copy()
    data.columns = ["Date", "Price"]
    data["Date"] = pd.to_datetime(data["Date"]).dt.date
    data["Price"] = pd.to_numeric(data["Price"], errors="coerce")
    data = data.dropna().sort_values("Date")
    data = data[(data["Date"] >= start) & (data["Date"] <= end)].reset_index(drop=True)
    if len(data) < 260:
        raise ValueError("Need at least about one trading year of daily prices")
    return data


def trade_cost(trade_value: float, fee_bps: float, commission: float) -> float:
    return abs(trade_value) * fee_bps / 10_000.0 + commission


def buy_all(portfolio: Portfolio, day: date, price: float, fee_bps: float, commission: float) -> None:
    if portfolio.cash <= commission:
        return
    shares = (portfolio.cash - commission) / (price * (1.0 + fee_bps / 10_000.0))
    if shares <= 0:
        return
    gross = shares * price
    fee = trade_cost(gross, fee_bps, commission)
    basis = gross + fee
    portfolio.cash -= basis
    portfolio.shares += shares
    portfolio.lots.append(Lot(shares=shares, basis_per_share=basis / shares, opened=day))
    portfolio.fees_paid += fee
    portfolio.trades.append(
        {
            "strategy": portfolio.name,
            "date": day.isoformat(),
            "action": "BUY",
            "price": round(price, 6),
            "shares": shares,
            "gross": gross,
            "fees": fee,
            "tax": 0.0,
            "cash_after": portfolio.cash,
        }
    )


def sell_all(
    portfolio: Portfolio,
    day: date,
    price: float,
    fee_bps: float,
    commission: float,
    short_tax_rate: float,
    long_tax_rate: float,
    reason: str,
) -> None:
    if portfolio.shares <= 0:
        return
    shares_to_sell = portfolio.shares
    original_shares = shares_to_sell
    gross = shares_to_sell * price
    fee = trade_cost(gross, fee_bps, commission)
    proceeds = gross - fee
    remaining_fee = fee
    realized_short = 0.0
    realized_long = 0.0

    while shares_to_sell > 1e-9 and portfolio.lots:
        lot = portfolio.lots.pop(0)
        sold = min(shares_to_sell, lot.shares)
        fee_alloc = remaining_fee * (sold / shares_to_sell) if shares_to_sell else 0.0
        remaining_fee -= fee_alloc
        cost_basis = sold * lot.basis_per_share
        lot_proceeds = sold * price - fee_alloc
        gain = lot_proceeds - cost_basis
        if (day - lot.opened).days > 365:
            realized_long += gain
        else:
            realized_short += gain
        lot.shares -= sold
        shares_to_sell -= sold
        if lot.shares > 1e-9:
            portfolio.lots.insert(0, lot)
            break

    tax = max(0.0, realized_short) * short_tax_rate + max(0.0, realized_long) * long_tax_rate
    portfolio.cash += proceeds - tax
    portfolio.shares = 0.0
    portfolio.realized_short_gain += realized_short
    portfolio.realized_long_gain += realized_long
    portfolio.realized_tax += tax
    portfolio.fees_paid += fee
    portfolio.trades.append(
        {
            "strategy": portfolio.name,
            "date": day.isoformat(),
            "action": f"SELL_{reason}",
            "price": round(price, 6),
            "shares": original_shares,
            "gross": gross,
            "fees": fee,
            "tax": tax,
            "realized_short_gain": realized_short,
            "realized_long_gain": realized_long,
            "cash_after": portfolio.cash,
        }
    )


def run_backtest(
    prices: pd.DataFrame,
    evaluation_start: date,
    initial_capital: float,
    sma_window: int,
    fee_bps: float,
    commission: float,
    short_tax_rate: float,
    long_tax_rate: float,
    risk_free_rate: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Portfolio]]:
    data = prices.copy()
    data["SMA"] = data["Price"].rolling(sma_window).mean()
    data["Signal"] = (data["Price"] > data["SMA"]).astype(int)
    data["Signal"] = data["Signal"].shift(1).fillna(0).astype(int)

    trend = Portfolio("trend_following", initial_capital)
    hold = Portfolio("buy_and_hold", initial_capital)
    daily_cash_rate = (1.0 + risk_free_rate) ** (1.0 / 252.0) - 1.0
    equity_rows = []

    tradable = data[data["Date"] >= evaluation_start].reset_index(drop=True)
    if tradable.empty:
        raise ValueError("No price rows are available inside the requested evaluation window")

    first_day = tradable.iloc[0]
    buy_all(hold, first_day["Date"], first_day["Price"], fee_bps, commission)

    for _, row in tradable.iterrows():
        day = row["Date"]
        price = float(row["Price"])
        if trend.shares == 0:
            trend.cash *= 1.0 + daily_cash_rate
        if hold.shares == 0:
            hold.cash *= 1.0 + daily_cash_rate

        target_in_market = int(row["Signal"]) == 1
        if target_in_market and trend.shares == 0:
            buy_all(trend, day, price, fee_bps, commission)
        elif not target_in_market and trend.shares > 0:
            sell_all(trend, day, price, fee_bps, commission, short_tax_rate, long_tax_rate, "SIGNAL")

        equity_rows.append(
            {
                "date": day.isoformat(),
                "price": price,
                "sma": None if math.isnan(row["SMA"]) else float(row["SMA"]),
                "signal": int(row["Signal"]),
                "trend_following": trend.value(price),
                "buy_and_hold": hold.value(price),
            }
        )

    final_day = tradable.iloc[-1]["Date"]
    final_price = float(tradable.iloc[-1]["Price"])
    sell_all(trend, final_day, final_price, fee_bps, commission, short_tax_rate, long_tax_rate, "FINAL")
    sell_all(hold, final_day, final_price, fee_bps, commission, short_tax_rate, long_tax_rate, "FINAL")

    equity_rows.append(
        {
            "date": final_day.isoformat(),
            "price": final_price,
            "sma": float(tradable.iloc[-1]["SMA"]),
            "signal": int(tradable.iloc[-1]["Signal"]),
            "trend_following": trend.value(final_price),
            "buy_and_hold": hold.value(final_price),
        }
    )

    trades = pd.DataFrame(trend.trades + hold.trades)
    equity = pd.DataFrame(equity_rows).drop_duplicates(subset=["date"], keep="last")
    return equity, trades, {"trend_following": trend, "buy_and_hold": hold}


def max_drawdown(values: Iterable[float]) -> float:
    peak = -float("inf")
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst


def cagr(start_value: float, end_value: float, start_date: date, end_date: date) -> float:
    years = (end_date - start_date).days / 365.25
    return (end_value / start_value) ** (1.0 / years) - 1.0


def summarize(
    equity: pd.DataFrame,
    portfolios: dict[str, Portfolio],
    initial_capital: float,
    start: date,
    end: date,
) -> pd.DataFrame:
    rows = []
    for name, portfolio in portfolios.items():
        final_value = portfolio.cash
        values = equity[name].tolist()
        rows.append(
            {
                "strategy": name,
                "initial_capital": initial_capital,
                "final_after_tax_value": final_value,
                "total_after_tax_return": final_value / initial_capital - 1.0,
                "after_tax_cagr": cagr(initial_capital, final_value, start, end),
                "max_drawdown": max_drawdown(values),
                "trades": len(portfolio.trades),
                "fees_paid": portfolio.fees_paid,
                "tax_paid": portfolio.realized_tax,
                "realized_short_gain": portfolio.realized_short_gain,
                "realized_long_gain": portfolio.realized_long_gain,
            }
        )
    return pd.DataFrame(rows)


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def money(value: float) -> str:
    return f"${value:,.2f}"


def write_report(
    output_dir: Path,
    summary: pd.DataFrame,
    args: argparse.Namespace,
    source: str,
    start: date,
    end: date,
    rows: int,
) -> None:
    trend = summary.set_index("strategy").loc["trend_following"]
    hold = summary.set_index("strategy").loc["buy_and_hold"]
    winner = "trend following" if trend["final_after_tax_value"] > hold["final_after_tax_value"] else "buy and hold"
    lines = [
        "# S&P 500 Trend Following vs Buy and Hold",
        "",
        f"Period: {start.isoformat()} to {end.isoformat()} ({rows:,} trading rows).",
        f"Data: {source}. SPY is used as the investable S&P 500 proxy.",
        "",
        "## Strategy",
        "",
        f"- Trend following: hold SPY when the prior close is above its {args.sma_window}-day moving average; otherwise hold cash.",
        "- Buy and hold: buy SPY on the first available date and liquidate on the final date.",
        f"- Initial capital: {money(args.initial_capital)}.",
        f"- Transaction cost: {args.fee_bps:.2f} bps per trade plus {money(args.commission)} fixed commission.",
        f"- Tax model: realized gains are taxed at sale time; short-term gains at {pct(args.short_tax_rate)}, long-term gains at {pct(args.long_tax_rate)}. Losses do not create immediate refunds in this simplified model.",
        f"- Cash return while out of market: {pct(args.risk_free_rate)} annualized.",
        "",
        "## Results",
        "",
        "| Strategy | Final after-tax value | Total return | CAGR | Max drawdown | Trades | Fees | Taxes |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in summary.iterrows():
        lines.append(
            "| {strategy} | {final_value} | {total_return} | {cagr} | {drawdown} | {trades:.0f} | {fees} | {taxes} |".format(
                strategy=row["strategy"].replace("_", " "),
                final_value=money(row["final_after_tax_value"]),
                total_return=pct(row["total_after_tax_return"]),
                cagr=pct(row["after_tax_cagr"]),
                drawdown=pct(row["max_drawdown"]),
                trades=row["trades"],
                fees=money(row["fees_paid"]),
                taxes=money(row["tax_paid"]),
            )
        )
    lines.extend(
        [
            "",
            f"Winner on after-tax ending value: **{winner}**.",
            "",
            "## Caveats",
            "",
            "- This is a backtest, not financial or tax advice.",
            "- SPY adjusted close data includes distributions in the return series, but this model does not separately tax dividends.",
            "- Tax law depends on filing status, income, state, wash-sale effects, loss carryforwards, and other details. Change the tax-rate arguments to match the scenario you want to study.",
        ]
    )
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    today = date.today()
    end = iso_date(args.end, today)
    start = iso_date(args.start, end - timedelta(days=365 * 5 + 2))
    fetch_start = start - timedelta(days=max(420, args.sma_window * 3))
    args.output_dir.mkdir(parents=True, exist_ok=True)

    try:
        prices, source = load_prices(args, fetch_start, end)
    except Exception as exc:
        message = (
            f"Price data could not be loaded: {exc}\n\n"
            "To rerun with a local file, provide a CSV containing Date plus Adj Close or Close:\n"
            f"  {Path(sys.argv[0]).name} --input path/to/spy.csv --start {start} --end {end}\n"
        )
        (args.output_dir / "DATA_NEEDED.txt").write_text(message, encoding="utf-8")
        print(message, file=sys.stderr)
        return 2

    equity, trades, portfolios = run_backtest(
        prices=prices,
        evaluation_start=start,
        initial_capital=args.initial_capital,
        sma_window=args.sma_window,
        fee_bps=args.fee_bps,
        commission=args.commission,
        short_tax_rate=args.short_tax_rate,
        long_tax_rate=args.long_tax_rate,
        risk_free_rate=args.risk_free_rate,
    )
    actual_start = datetime.strptime(equity.iloc[0]["date"], "%Y-%m-%d").date()
    actual_end = datetime.strptime(equity.iloc[-1]["date"], "%Y-%m-%d").date()
    summary = summarize(equity, portfolios, args.initial_capital, actual_start, actual_end)

    prices.to_csv(args.output_dir / "prices_used.csv", index=False)
    equity.to_csv(args.output_dir / "equity_curve.csv", index=False)
    trades.to_csv(args.output_dir / "trades.csv", index=False)
    summary.to_csv(args.output_dir / "summary.csv", index=False)
    write_report(args.output_dir, summary, args, source, actual_start, actual_end, len(prices))
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
