"""Utility to download price CSV files with a unified schema.

Usage:
    python update_csv.py 0050.TW 00631L.TW --start 2010-01-01

Outputs ``data/{symbol}.csv`` with date index and columns:
Open, High, Low, Close, Volume.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yfinance as yf

DATA_DIR = Path("data")
REQUIRED_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def download_symbol(symbol: str, start: str | None, end: str | None) -> pd.DataFrame:
    df = yf.download(symbol, start=start, end=end, auto_adjust=False)
    if df.empty:
        raise ValueError(f"No data downloaded for {symbol}")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Downloaded data for {symbol} missing columns: {', '.join(missing)}")

    df = df[REQUIRED_COLUMNS].copy()
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def save_csv(symbol: str, df: pd.DataFrame):
    DATA_DIR.mkdir(exist_ok=True)
    csv_path = DATA_DIR / f"{symbol}.csv"
    df.to_csv(csv_path)
    return csv_path


def parse_args():
    parser = argparse.ArgumentParser(description="Download unified price CSV files")
    parser.add_argument("symbols", nargs="+", help="Symbols accepted by yfinance (e.g., 0050.TW)")
    parser.add_argument("--start", help="Start date YYYY-MM-DD", default=None)
    parser.add_argument("--end", help="End date YYYY-MM-DD", default=None)
    return parser.parse_args()


def main():
    args = parse_args()
    for sym in args.symbols:
        df = download_symbol(sym, start=args.start, end=args.end)
        csv_path = save_csv(sym, df)
        print(f"Saved {csv_path} ({len(df)} rows)")


if __name__ == "__main__":
    main()
