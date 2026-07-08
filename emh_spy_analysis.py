"""Test weak-form EMH for SPY across selected market periods.

The script downloads daily SPY prices with yfinance, calculates daily log
returns, runs three weak-form EMH tests, prints a classification table, and
saves a combined table/variance-ratio plot.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf


ALPHA = 0.05
Q_VALUES = [2, 5, 10, 20, 40]
OUTPUT_FILE = Path("spy_emh_results.png")


@dataclass(frozen=True)
class MarketPeriod:
    name: str
    start: str
    end: str | None


PERIODS = [
    MarketPeriod("Dot-com Bubble", "1999-01-01", "2002-12-31"),
    MarketPeriod("Global Financial Crisis", "2007-01-01", "2009-12-31"),
    MarketPeriod("COVID Crash", "2020-01-01", "2021-12-31"),
    MarketPeriod("AI / ChatGPT Period", "2022-11-30", None),
]


def normal_two_sided_p_value(z_score: float) -> float:
    """Return a two-sided p-value for a standard-normal z statistic."""
    return math.erfc(abs(z_score) / math.sqrt(2.0))


def get_adjusted_close(data: pd.DataFrame) -> pd.Series:
    """Extract SPY adjusted close prices from yfinance output."""
    if isinstance(data.columns, pd.MultiIndex):
        if ("Adj Close", "SPY") in data.columns:
            prices = data[("Adj Close", "SPY")]
        elif ("Close", "SPY") in data.columns:
            prices = data[("Close", "SPY")]
        else:
            raise ValueError("Could not find SPY close prices in downloaded data.")
    elif "Adj Close" in data.columns:
        prices = data["Adj Close"]
    elif "Close" in data.columns:
        prices = data["Close"]
    else:
        raise ValueError("Could not find adjusted close prices in downloaded data.")

    return prices.dropna().rename("SPY Adjusted Close")


def download_spy_prices(periods: list[MarketPeriod]) -> pd.Series:
    """Download enough SPY data to cover all requested periods."""
    min_start = min(period.start for period in periods)
    latest_end = date.today() + timedelta(days=1)

    data = yf.download(
        "SPY",
        start=min_start,
        end=latest_end.isoformat(),
        auto_adjust=False,
        progress=False,
    )
    if data.empty:
        raise RuntimeError("No SPY data was returned by yfinance.")

    return get_adjusted_close(data)


def daily_log_returns(prices: pd.Series) -> pd.Series:
    """Calculate daily log returns from adjusted close prices."""
    return np.log(prices).diff().dropna()


def variance_ratio_results(returns: pd.Series, q_values: list[int]) -> pd.DataFrame:
    """Calculate VR(q), asymptotic z statistics, and p-values."""
    one_period_variance = returns.var(ddof=1)
    n_observations = len(returns)
    rows = []

    if n_observations < max(q_values) + 1:
        raise ValueError("Not enough observations to calculate variance ratios.")

    for q_value in q_values:
        q_period_returns = returns.rolling(q_value).sum().dropna()
        q_period_variance = q_period_returns.var(ddof=1)
        variance_ratio = q_period_variance / (q_value * one_period_variance)

        # Homoskedastic random-walk approximation from Lo and MacKinlay.
        z_variance = 2 * (2 * q_value - 1) * (q_value - 1) / (3 * q_value * n_observations)
        z_score = (variance_ratio - 1) / math.sqrt(z_variance)
        p_value = normal_two_sided_p_value(z_score)

        rows.append(
            {
                "q": q_value,
                "VR(q)": variance_ratio,
                "z": z_score,
                "p-value": p_value,
                "Classification": "Reject EMH" if p_value < ALPHA else "Fail to Reject EMH",
            }
        )

    return pd.DataFrame(rows)


def autocorrelation_test(returns: pd.Series, lag: int = 1) -> tuple[float, float, str]:
    """Run a lag-1 autocorrelation test with a large-sample normal statistic."""
    autocorrelation = returns.autocorr(lag=lag)
    z_score = autocorrelation * math.sqrt(len(returns))
    p_value = normal_two_sided_p_value(z_score)
    classification = "Reject EMH" if p_value < ALPHA else "Fail to Reject EMH"
    return autocorrelation, p_value, classification


def runs_test(returns: pd.Series) -> tuple[float, float, str]:
    """Run the Wald-Wolfowitz runs test on positive vs. negative returns."""
    signs = returns[returns != 0].gt(0).astype(int).to_numpy()
    n_positive = int(signs.sum())
    n_negative = int(len(signs) - n_positive)

    if n_positive == 0 or n_negative == 0:
        raise ValueError("Runs test requires both positive and negative returns.")

    runs = 1 + int(np.sum(signs[1:] != signs[:-1]))
    expected_runs = 1 + (2 * n_positive * n_negative) / (n_positive + n_negative)
    variance_runs = (
        2
        * n_positive
        * n_negative
        * (2 * n_positive * n_negative - n_positive - n_negative)
        / (((n_positive + n_negative) ** 2) * (n_positive + n_negative - 1))
    )
    z_score = (runs - expected_runs) / math.sqrt(variance_runs)
    p_value = normal_two_sided_p_value(z_score)
    classification = "Reject EMH" if p_value < ALPHA else "Fail to Reject EMH"
    return z_score, p_value, classification


def analyze_period(prices: pd.Series, period: MarketPeriod) -> tuple[dict[str, str], pd.DataFrame]:
    """Run all EMH tests for one market period."""
    period_end = period.end or date.today().isoformat()
    period_prices = prices.loc[period.start:period_end]
    returns = daily_log_returns(period_prices)

    if returns.empty:
        raise ValueError(f"No returns available for {period.name}.")

    vr_results = variance_ratio_results(returns, Q_VALUES)
    _, _, autocorr_classification = autocorrelation_test(returns, lag=1)
    _, _, runs_classification = runs_test(returns)

    summary_row = {
        "Market Period": period.name,
        "Variance Ratio Test": (
            "Reject EMH"
            if (vr_results["p-value"] < ALPHA).any()
            else "Fail to Reject EMH"
        ),
        "Autocorrelation Test": autocorr_classification,
        "Runs Test": runs_classification,
    }

    return summary_row, vr_results


def plot_results(summary: pd.DataFrame, vr_by_period: dict[str, pd.DataFrame]) -> None:
    """Save a side-by-side classification table and VR(q) chart."""
    fig, (table_axis, plot_axis) = plt.subplots(
        1,
        2,
        figsize=(16, 6),
        gridspec_kw={"width_ratios": [1.35, 1.65]},
    )

    table_axis.axis("off")
    table = table_axis.table(
        cellText=summary.values,
        colLabels=summary.columns,
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.8)

    for column_index in range(len(summary.columns)):
        table.auto_set_column_width(column_index)

    for period_name, vr_results in vr_by_period.items():
        plot_axis.plot(vr_results["q"], vr_results["VR(q)"], marker="o", label=period_name)

    plot_axis.axhline(1, color="black", linestyle="--", linewidth=1)
    plot_axis.set_title("Variance Ratio Test by Market Period")
    plot_axis.set_xlabel("q (holding period)")
    plot_axis.set_ylabel("VR(q)")
    plot_axis.set_xticks(Q_VALUES)
    plot_axis.legend()
    plot_axis.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(OUTPUT_FILE, dpi=200, bbox_inches="tight")


def main() -> None:
    prices = download_spy_prices(PERIODS)

    summary_rows = []
    vr_by_period = {}
    for period in PERIODS:
        summary_row, vr_results = analyze_period(prices, period)
        summary_rows.append(summary_row)
        vr_by_period[period.name] = vr_results

    summary = pd.DataFrame(summary_rows).set_index("Market Period")
    print("\nWeak-Form EMH Test Classifications (5% significance level)\n")
    print(summary.to_string())

    plot_results(summary.reset_index(), vr_by_period)
    print(f"\nSaved table and variance-ratio graph to: {OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    main()
