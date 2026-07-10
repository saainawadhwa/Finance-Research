#!/usr/bin/env python3
"""Write a Markdown comparison table from the trend-following summary CSV."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def money(value: float) -> str:
    return f"${value:,.2f}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a Markdown table from outputs/summary.csv.")
    parser.add_argument("--summary", type=Path, default=Path("outputs/summary.csv"))
    parser.add_argument("--output", type=Path, default=Path("outputs/comparison_table.md"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = pd.read_csv(args.summary)
    lines = [
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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
