"""Analyze weak-form EMH evidence across U.S. sector ETFs.

The script downloads adjusted closing prices with yfinance, calculates daily log
returns, applies the same three weak-form EMH tests used by the SPY project, and
writes detailed tables, summary matrices, and a heatmap to outputs/.
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
OUTPUT_DIR = Path("outputs")


@dataclass(frozen=True)
class Sector:
    name: str
    etf: str


@dataclass(frozen=True)
class MarketPeriod:
    name: str
    start: str
    end: str


SECTORS = [
    Sector("Communication Services", "XLC"),
    Sector("Consumer Discretionary", "XLY"),
    Sector("Consumer Staples", "XLP"),
    Sector("Energy", "XLE"),
    Sector("Financials", "XLF"),
    Sector("Health Care", "XLV"),
    Sector("Industrials", "XLI"),
    Sector("Materials", "XLB"),
    Sector("Real Estate", "XLRE"),
    Sector("Technology", "XLK"),
    Sector("Utilities", "XLU"),
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


def download_adjusted_close_prices() -> pd.DataFrame:
    """Download adjusted close prices for all configured sector ETFs."""
    tickers = [sector.etf for sector in SECTORS]
    start = min(period.start for period in PERIODS)
    latest_end = max(datetime.fromisoformat(period.end) for period in PERIODS)
    end = (latest_end + timedelta(days=1)).date().isoformat()

    data = yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=False,
        progress=False,
        group_by="column",
        threads=True,
    )
    if data.empty:
        raise RuntimeError("No sector ETF data was returned by yfinance.")

    if isinstance(data.columns, pd.MultiIndex):
        if "Adj Close" in data.columns.get_level_values(0):
            prices = data["Adj Close"].copy()
        elif "Close" in data.columns.get_level_values(0):
            prices = data["Close"].copy()
        else:
            raise ValueError("Downloaded data does not contain adjusted close prices.")
    elif "Adj Close" in data.columns:
        prices = data[["Adj Close"]].copy()
        prices.columns = tickers
    elif "Close" in data.columns:
        prices = data[["Close"]].copy()
        prices.columns = tickers
    else:
        raise ValueError("Downloaded data does not contain adjusted close prices.")

    missing_tickers = [ticker for ticker in tickers if ticker not in prices.columns]
    if missing_tickers:
        raise ValueError(f"Missing adjusted close data for: {', '.join(missing_tickers)}")

    prices = prices[tickers].dropna(how="all")
    incomplete = [ticker for ticker in tickers if prices[ticker].dropna().empty]
    if incomplete:
        raise ValueError(f"No usable adjusted close data for: {', '.join(incomplete)}")

    return prices


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
                "Result": "Rejects EMH" if p_value < ALPHA else "Fails to Reject EMH",
            }
        )

    return pd.DataFrame(rows)


def autocorrelation_test(returns: pd.Series, lag: int = 1) -> tuple[float, float, str]:
    """Run a lag-1 autocorrelation test with a large-sample normal statistic."""
    autocorrelation = returns.autocorr(lag=lag)
    z_score = autocorrelation * math.sqrt(len(returns))
    p_value = normal_two_sided_p_value(z_score)
    result = "Rejects EMH" if p_value < ALPHA else "Fails to Reject EMH"
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
    result = "Rejects EMH" if p_value < ALPHA else "Fails to Reject EMH"
    return z_score, p_value, result


def analyze_sector_period(prices: pd.Series, sector: Sector, period: MarketPeriod) -> dict[str, object]:
    """Run all configured weak-form EMH tests for one sector and period."""
    period_prices = prices.loc[period.start : period.end].dropna()
    returns = daily_log_returns(period_prices)
    if returns.empty:
        raise ValueError(f"No returns available for {sector.etf} during {period.name}.")

    vr_results = variance_ratio_results(returns, Q_VALUES)
    vr_result = "Rejects EMH" if (vr_results["p-value"] < ALPHA).any() else "Fails to Reject EMH"
    _, _, autocorr_result = autocorrelation_test(returns, lag=1)
    _, _, runs_result = runs_test(returns)
    test_results = [vr_result, autocorr_result, runs_result]

    return {
        "Sector": sector.name,
        "ETF": sector.etf,
        "Market Period": period.name,
        "Variance Ratio Result": vr_result,
        "Autocorrelation Result": autocorr_result,
        "Runs Test Result": runs_result,
        "Number of Tests Rejecting EMH": sum(result == "Rejects EMH" for result in test_results),
    }


def markdown_table(dataframe: pd.DataFrame) -> str:
    """Render a DataFrame as a GitHub-flavored Markdown table."""
    formatted = dataframe.copy()
    formatted = formatted.astype(str)
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
    """Create a sector-by-period matrix of rejection counts."""
    matrix = detailed_results.pivot(
        index="Sector",
        columns="Market Period",
        values="Number of Tests Rejecting EMH",
    )
    period_order = [period.name for period in PERIODS]
    sector_order = [sector.name for sector in SECTORS]
    return matrix.loc[sector_order, period_order].astype(int)


def create_period_summary(summary_matrix: pd.DataFrame) -> pd.DataFrame:
    """Count how many sectors show each rejection-count level by period."""
    rows = []
    for period in summary_matrix.columns:
        counts = summary_matrix[period].value_counts().to_dict()
        rows.append(
            {
                "Market Period": period,
                "Sectors with 0 Tests Rejecting": int(counts.get(0, 0)),
                "Sectors with 1 Test Rejecting": int(counts.get(1, 0)),
                "Sectors with 2 Tests Rejecting": int(counts.get(2, 0)),
                "Sectors with 3 Tests Rejecting": int(counts.get(3, 0)),
            }
        )
    return pd.DataFrame(rows)


def create_heatmap(summary_matrix: pd.DataFrame, output_path: Path) -> None:
    """Save a heatmap where higher values indicate more tests rejecting EMH."""
    cmap = ListedColormap(["#2e7d32", "#f9c74f", "#f8961e", "#c62828"])
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], cmap.N)

    fig, ax = plt.subplots(figsize=(13.5, 7.5))
    image = ax.imshow(summary_matrix.values, cmap=cmap, norm=norm, aspect="auto")

    ax.set_title("Weak-Form EMH Rejections by Sector and Market Period", fontsize=16, pad=18)
    ax.set_xticks(np.arange(summary_matrix.shape[1]))
    ax.set_yticks(np.arange(summary_matrix.shape[0]))
    ax.set_xticklabels(summary_matrix.columns, rotation=30, ha="right")
    ax.set_yticklabels(summary_matrix.index)
    ax.set_xlabel("Market Period")
    ax.set_ylabel("Sector")

    for row_index in range(summary_matrix.shape[0]):
        for column_index in range(summary_matrix.shape[1]):
            value = int(summary_matrix.iloc[row_index, column_index])
            ax.text(column_index, row_index, str(value), ha="center", va="center", color="black", fontsize=12)

    colorbar = fig.colorbar(image, ax=ax, ticks=[0, 1, 2, 3])
    colorbar.set_label("Number of tests rejecting EMH")
    ax.set_xticks(np.arange(-0.5, summary_matrix.shape[1], 1), minor=True)
    ax.set_yticks(np.arange(-0.5, summary_matrix.shape[0], 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=1.5)
    ax.tick_params(which="minor", bottom=False, left=False)

    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def verify_outputs(paths: list[Path]) -> None:
    """Verify that every requested output exists and is non-empty."""
    missing_or_empty = [path for path in paths if not path.exists() or path.stat().st_size == 0]
    if missing_or_empty:
        formatted = ", ".join(str(path) for path in missing_or_empty)
        raise RuntimeError(f"Output verification failed for: {formatted}")

    pd.read_csv(OUTPUT_DIR / "sector_emh_detailed_results.csv")
    pd.read_csv(OUTPUT_DIR / "sector_emh_summary_matrix.csv", index_col=0)
    pd.read_csv(OUTPUT_DIR / "sector_emh_period_summary.csv")
    plt.imread(OUTPUT_DIR / "sector_emh_heatmap.png")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_prices = download_adjusted_close_prices()
    rows = []
    for sector in SECTORS:
        for period in PERIODS:
            rows.append(analyze_sector_period(all_prices[sector.etf], sector, period))

    detailed_results = pd.DataFrame(rows)
    summary_matrix = create_summary_matrix(detailed_results)
    period_summary = create_period_summary(summary_matrix)

    detailed_csv = OUTPUT_DIR / "sector_emh_detailed_results.csv"
    detailed_md = OUTPUT_DIR / "sector_emh_detailed_results.md"
    summary_csv = OUTPUT_DIR / "sector_emh_summary_matrix.csv"
    heatmap_png = OUTPUT_DIR / "sector_emh_heatmap.png"
    period_summary_csv = OUTPUT_DIR / "sector_emh_period_summary.csv"

    detailed_results.to_csv(detailed_csv, index=False)
    detailed_md.write_text(markdown_table(detailed_results), encoding="utf-8")
    summary_matrix.to_csv(summary_csv)
    period_summary.to_csv(period_summary_csv, index=False)
    create_heatmap(summary_matrix, heatmap_png)

    verify_outputs([detailed_csv, detailed_md, summary_csv, heatmap_png, period_summary_csv])

    print("Weak-form EMH sector analysis completed.")
    print(f"Detailed rows: {len(detailed_results)}")
    print(f"Outputs written to: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
