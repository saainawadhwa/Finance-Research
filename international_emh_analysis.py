"""Compare weak-form EMH evidence across global equity-market ETFs.

The script downloads each ETF independently, validates data availability for the
2015-01-01 through 2024-12-31 sample, analyzes the same market periods used by
the U.S. sector study, and writes tables and figures under outputs/international_emh/.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
import numpy as np
import pandas as pd
import yfinance as yf


ALPHA = 0.05
Q_VALUES = [2, 5, 10, 20, 40]
SAMPLE_START = "2015-01-01"
SAMPLE_END = "2024-12-31"
MIN_OBSERVATIONS = max(Q_VALUES) + 2
OUTPUT_DIR = Path("outputs/international_emh")


@dataclass(frozen=True)
class Market:
    name: str
    ticker: str


@dataclass(frozen=True)
class MarketPeriod:
    name: str
    start: str
    end: str


MARKETS = [
    Market("United States benchmark", "SPY"),
    Market("United Kingdom", "EWU"),
    Market("Germany", "EWG"),
    Market("Japan", "EWJ"),
    Market("China", "MCHI"),
    Market("India", "INDA"),
    Market("Brazil", "EWZ"),
    Market("Australia", "EWA"),
    Market("South Korea", "EWY"),
    Market("Canada", "EWC"),
    Market("Developed Markets benchmark", "EFA"),
    Market("Emerging Markets benchmark", "EEM"),
]

PERIODS = [
    MarketPeriod("Normal Pre-COVID Period", "2019-01-01", "2019-12-31"),
    MarketPeriod("COVID Shock", "2020-02-01", "2021-03-31"),
    MarketPeriod("Post-COVID Recovery", "2021-04-01", "2021-12-31"),
    MarketPeriod("Inflation / Interest Rate Shock", "2022-01-01", "2022-12-31"),
    MarketPeriod("AI Market Period", "2023-01-01", "2024-12-31"),
]


def normal_two_sided_p_value(z_score: float) -> float:
    """Return a two-sided p-value for a standard-normal z statistic."""
    return math.erfc(abs(z_score) / math.sqrt(2.0))


def get_adjusted_close(data: pd.DataFrame, ticker: str) -> pd.Series:
    """Extract adjusted close prices from yfinance output."""
    if data.empty:
        return pd.Series(dtype=float, name=ticker)

    if isinstance(data.columns, pd.MultiIndex):
        if ("Adj Close", ticker) in data.columns:
            prices = data[("Adj Close", ticker)]
        elif ("Close", ticker) in data.columns:
            prices = data[("Close", ticker)]
        elif "Adj Close" in data.columns.get_level_values(0):
            prices = data["Adj Close"].iloc[:, 0]
        elif "Close" in data.columns.get_level_values(0):
            prices = data["Close"].iloc[:, 0]
        else:
            raise ValueError(f"Could not find adjusted close prices for {ticker}.")
    elif "Adj Close" in data.columns:
        prices = data["Adj Close"]
    elif "Close" in data.columns:
        prices = data["Close"]
    else:
        raise ValueError(f"Could not find adjusted close prices for {ticker}.")

    prices = pd.to_numeric(prices, errors="coerce").dropna()
    prices = prices.loc[SAMPLE_START:SAMPLE_END]
    return prices.rename(ticker)


def download_market_prices(markets: list[Market]) -> dict[str, pd.Series]:
    """Download and validate adjusted close prices for each ETF independently."""
    end = (datetime.fromisoformat(SAMPLE_END) + timedelta(days=1)).date().isoformat()
    prices_by_ticker: dict[str, pd.Series] = {}
    unavailable = []

    for market in markets:
        data = yf.download(
            market.ticker,
            start=SAMPLE_START,
            end=end,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        prices = get_adjusted_close(data, market.ticker)
        if len(prices) < MIN_OBSERVATIONS:
            unavailable.append(f"{market.ticker} ({market.name}): {len(prices)} valid observations")
        else:
            prices_by_ticker[market.ticker] = prices

    if unavailable:
        joined = "\n".join(f"- {item}" for item in unavailable)
        raise RuntimeError(f"Unavailable or insufficient ETF data:\n{joined}")

    return prices_by_ticker


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
    if one_period_variance == 0 or math.isnan(one_period_variance):
        raise ValueError("Return variance is zero or invalid.")

    for q_value in q_values:
        q_period_returns = returns.rolling(q_value).sum().dropna()
        q_period_variance = q_period_returns.var(ddof=1)
        variance_ratio = q_period_variance / (q_value * one_period_variance)

        z_variance = 2 * (2 * q_value - 1) * (q_value - 1) / (3 * q_value * n_observations)
        z_score = (variance_ratio - 1) / math.sqrt(z_variance)
        p_value = normal_two_sided_p_value(z_score)

        rows.append(
            {
                "q": q_value,
                "VR(q)": variance_ratio,
                "z": z_score,
                "p-value": p_value,
                "Result": "Reject EMH" if p_value < ALPHA else "Fail to Reject EMH",
            }
        )

    return pd.DataFrame(rows)


def autocorrelation_test(returns: pd.Series, lag: int = 1) -> tuple[float, float, str]:
    """Run a lag-1 autocorrelation test with a large-sample normal statistic."""
    autocorrelation = returns.autocorr(lag=lag)
    z_score = autocorrelation * math.sqrt(len(returns))
    p_value = normal_two_sided_p_value(z_score)
    result = "Reject EMH" if p_value < ALPHA else "Fail to Reject EMH"
    return autocorrelation, p_value, result


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
    result = "Reject EMH" if p_value < ALPHA else "Fail to Reject EMH"
    return z_score, p_value, result


def analyze_market_period(market: Market, prices: pd.Series, period: MarketPeriod) -> dict[str, object]:
    """Run all weak-form EMH tests for one market and period."""
    period_prices = prices.loc[period.start : period.end].dropna()
    returns = daily_log_returns(period_prices)
    if len(returns) < MIN_OBSERVATIONS:
        raise ValueError(
            f"{market.ticker} ({market.name}) has only {len(returns)} returns during {period.name}."
        )

    vr_results = variance_ratio_results(returns, Q_VALUES)
    strongest_vr = vr_results.sort_values("p-value").iloc[0]
    vr_result = "Reject EMH" if (vr_results["p-value"] < ALPHA).any() else "Fail to Reject EMH"
    autocorr_stat, autocorr_p_value, autocorr_result = autocorrelation_test(returns, lag=1)
    runs_stat, runs_p_value, runs_result = runs_test(returns)
    test_results = [vr_result, autocorr_result, runs_result]

    return {
        "Market": market.name,
        "Ticker": market.ticker,
        "Market Period": period.name,
        "Number of observations": len(returns),
        "Variance Ratio statistic": strongest_vr["VR(q)"],
        "Variance Ratio p-value": strongest_vr["p-value"],
        "Variance Ratio result": vr_result,
        "Lag-1 autocorrelation": autocorr_stat,
        "Autocorrelation p-value": autocorr_p_value,
        "Autocorrelation result": autocorr_result,
        "Runs Test statistic": runs_stat,
        "Runs Test p-value": runs_p_value,
        "Runs Test result": runs_result,
        "Number of tests rejecting EMH": sum(result == "Reject EMH" for result in test_results),
    }


def markdown_table(dataframe: pd.DataFrame) -> str:
    """Render a DataFrame as a GitHub-flavored Markdown table."""
    formatted = dataframe.copy().astype(str)
    headers = list(formatted.columns)
    rows = formatted.values.tolist()
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def create_summary_matrix(detailed_results: pd.DataFrame) -> pd.DataFrame:
    """Create a market-by-period matrix formatted as n/3 rejection counts."""
    matrix = detailed_results.pivot(
        index="Market",
        columns="Market Period",
        values="Number of tests rejecting EMH",
    )
    market_order = [market.name for market in MARKETS]
    period_order = [period.name for period in PERIODS]
    matrix = matrix.loc[market_order, period_order].astype(int)
    return matrix.map(lambda value: f"{int(value)}/3")


def create_summary_table(detailed_results: pd.DataFrame) -> pd.DataFrame:
    """Create a compact market-period comparison table."""
    summary = detailed_results[
        [
            "Market",
            "Ticker",
            "Market Period",
            "Variance Ratio result",
            "Autocorrelation result",
            "Runs Test result",
            "Number of tests rejecting EMH",
        ]
    ].copy()
    summary["Tests Rejecting EMH"] = summary["Number of tests rejecting EMH"].map(lambda value: f"{int(value)}/3")
    return summary.drop(columns=["Number of tests rejecting EMH"]).rename(
        columns={
            "Variance Ratio result": "Variance Ratio Test",
            "Autocorrelation result": "Autocorrelation Test",
            "Runs Test result": "Runs Test",
        }
    )


def create_heatmap(summary_matrix: pd.DataFrame, output_path: Path) -> None:
    """Save a country-by-period heatmap of EMH test rejection counts."""
    numeric = summary_matrix.map(lambda value: int(str(value).split("/")[0]))
    cmap = ListedColormap(["#2e7d32", "#f9c74f", "#f8961e", "#c62828"])
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], cmap.N)

    fig, ax = plt.subplots(figsize=(14.5, 8))
    image = ax.imshow(numeric.values, cmap=cmap, norm=norm, aspect="auto")
    ax.set_title("Weak-Form EMH Rejections Across Global Equity Markets", fontsize=16, pad=18)
    ax.set_xticks(np.arange(summary_matrix.shape[1]))
    ax.set_yticks(np.arange(summary_matrix.shape[0]))
    ax.set_xticklabels(summary_matrix.columns, rotation=28, ha="right")
    ax.set_yticklabels(summary_matrix.index)
    ax.set_xlabel("Market Period")
    ax.set_ylabel("Market")

    for row_index in range(summary_matrix.shape[0]):
        for column_index in range(summary_matrix.shape[1]):
            label = summary_matrix.iloc[row_index, column_index]
            ax.text(column_index, row_index, label, ha="center", va="center", color="black", fontsize=11)

    colorbar = fig.colorbar(image, ax=ax, ticks=[0, 1, 2, 3])
    colorbar.set_label("Number of tests rejecting EMH")
    ax.set_xticks(np.arange(-0.5, summary_matrix.shape[1], 1), minor=True)
    ax.set_yticks(np.arange(-0.5, summary_matrix.shape[0], 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=1.5)
    ax.tick_params(which="minor", bottom=False, left=False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def create_variance_ratio_plot(prices_by_ticker: dict[str, pd.Series], output_path: Path) -> None:
    """Plot full-sample VR(q) curves for every market."""
    fig, ax = plt.subplots(figsize=(14.5, 8))
    markers = ["o", "s", "^", "D", "v", "P", "X", "*", "<", ">", "h", "8"]
    line_styles = ["-", "--", "-.", ":", (0, (5, 1)), (0, (3, 1, 1, 1))]

    for index, market in enumerate(MARKETS):
        returns = daily_log_returns(prices_by_ticker[market.ticker])
        vr_results = variance_ratio_results(returns, Q_VALUES)
        ax.plot(
            vr_results["q"],
            vr_results["VR(q)"],
            marker=markers[index % len(markers)],
            linestyle=line_styles[index % len(line_styles)],
            linewidth=2,
            markersize=6,
            label=f"{market.name} ({market.ticker})",
        )

    ax.axhline(1, color="black", linestyle="--", linewidth=1)
    ax.set_title("Variance Ratio Test Across Global Equity Markets")
    ax.set_xlabel("q")
    ax.set_ylabel("VR(q)")
    ax.set_xticks(Q_VALUES)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def verify_outputs(paths: list[Path]) -> None:
    """Verify that every generated file exists, is non-empty, and is readable."""
    missing_or_empty = [path for path in paths if not path.exists() or path.stat().st_size == 0]
    if missing_or_empty:
        formatted = ", ".join(str(path) for path in missing_or_empty)
        raise RuntimeError(f"Output verification failed for: {formatted}")

    detailed = pd.read_csv(OUTPUT_DIR / "international_emh_detailed_results.csv")
    summary = pd.read_csv(OUTPUT_DIR / "international_emh_summary.csv", index_col=0)
    if len(detailed) != len(MARKETS) * len(PERIODS):
        raise RuntimeError("Detailed output does not contain one row per market-period.")
    if list(summary.index) != [market.name for market in MARKETS]:
        raise RuntimeError("Summary matrix market order does not match the configured order.")
    if list(summary.columns) != [period.name for period in PERIODS]:
        raise RuntimeError("Summary matrix period order does not match the configured order.")
    if not summary.map(lambda value: str(value) in {"0/3", "1/3", "2/3", "3/3"}).all().all():
        raise RuntimeError("Summary matrix cells must be formatted as n/3.")
    plt.imread(OUTPUT_DIR / "international_emh_heatmap.png")
    plt.imread(OUTPUT_DIR / "international_emh_variance_ratio.png")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices_by_ticker = download_market_prices(MARKETS)

    rows = []
    for market in MARKETS:
        prices = prices_by_ticker[market.ticker]
        for period in PERIODS:
            rows.append(analyze_market_period(market, prices, period))

    detailed_results = pd.DataFrame(rows)
    summary_matrix = create_summary_matrix(detailed_results)
    summary_table = create_summary_table(detailed_results)

    detailed_csv = OUTPUT_DIR / "international_emh_detailed_results.csv"
    summary_csv = OUTPUT_DIR / "international_emh_summary.csv"
    summary_md = OUTPUT_DIR / "international_emh_summary.md"
    heatmap_png = OUTPUT_DIR / "international_emh_heatmap.png"
    variance_ratio_png = OUTPUT_DIR / "international_emh_variance_ratio.png"

    detailed_results.to_csv(detailed_csv, index=False)
    summary_matrix.to_csv(summary_csv)
    summary_md.write_text(markdown_table(summary_table), encoding="utf-8")
    create_heatmap(summary_matrix, heatmap_png)
    create_variance_ratio_plot(prices_by_ticker, variance_ratio_png)

    verify_outputs([detailed_csv, summary_csv, summary_md, heatmap_png, variance_ratio_png])

    print("International weak-form EMH analysis completed.")
    print("Each ETF was processed on its own valid trading observations without cross-market date intersection.")
    print(f"Detailed rows: {len(detailed_results)}")
    print(f"Outputs written to: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
