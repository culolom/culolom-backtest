"""
Auto-update price CSVs (append-only, very fast)
- Reads symbols.txt automatically
- CSV schema: Open, High, Low, Close, Volume
- Appends only missing dates (no full re-download)
- Perfect for GitHub Actions daily updates
"""

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf


DATA_DIR = Path("data")
SYMBOLS_FILE = Path("symbols.txt")
REQUIRED_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


# -------------------------------
# Load existing CSV
# -------------------------------
def load_existing(symbol: str) -> pd.DataFrame | None:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists():
        return None

    try:
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
        df = df.sort_index()
        return df
    except Exception:
        print(f"⚠ CSV corrupted for {symbol}, rebuilding...")
        return None


# -------------------------------
# Download only missing dates
# -------------------------------
def download_new_rows(symbol: str, start_date: datetime) -> pd.DataFrame:
    end_date = datetime.today() + timedelta(days=1)

    print(f"⬇ Downloading {symbol} from {start_date.date()} → {end_date.date()}")

    df = yf.download(
        symbol,
        start=start_date.strftime("%Y-%m-%d"),
        end=end_date.strftime("%Y-%m-%d"),
        auto_adjust=False,
        progress=False,
    )

    if df.empty:
        return df

    # Flatten MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[REQUIRED_COLUMNS].copy()
    df.index.name = "Date"
    return df


# -------------------------------
# Main single-symbol update
# -------------------------------
def update_symbol(symbol: str):
    DATA_DIR.mkdir(exist_ok=True)

    existing = load_existing(symbol)

    # First-time download
    if existing is None:
        print(f"📦 No CSV found for {symbol}, downloading full history...")
        df = yf.download(symbol, auto_adjust=False, progress=False)

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df.empty:
            print(f"❌ FAILED: no data for {symbol}")
            return

        df = df[REQUIRED_COLUMNS]
        df.index.name = "Date"
        df.to_csv(DATA_DIR / f"{symbol}.csv")
        print(f"✅ Saved fresh CSV for {symbol} ({len(df)} rows)")
        return

    # Append mode
    last_date = existing.index.max()
    fetch_from = last_date + timedelta(days=1)

    print(f"📄 Existing: {symbol} last = {last_date.date()}")

    if fetch_from.date() > datetime.today().date():
        print(f"⏭ {symbol} already up-to-date")
        return

    new_rows = download_new_rows(symbol, fetch_from)

    if new_rows.empty:
        print(f"⏭ No new rows for {symbol}")
        return

    merged = pd.concat([existing, new_rows])
    merged = merged[~merged.index.duplicated(keep="last")]
    merged = merged.sort_index()

    merged.to_csv(DATA_DIR / f"{symbol}.csv")
    print(f"✅ Updated {symbol}: +{len(new_rows)} rows")


# -------------------------------
# Read symbols.txt automatically
# -------------------------------
def load_symbols() -> list[str]:
    if not SYMBOLS_FILE.exists():
        raise FileNotFoundError("❌ symbols.txt not found! Create it in repo root.")

    with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
        symbols = [
            line.strip()
            for line in f.readlines()
            if line.strip() and not line.startswith("#")
        ]

    print(f"📘 Loaded {len(symbols)} symbols from symbols.txt")
    return symbols


# -------------------------------
# Entry Point
# -------------------------------
def main():
    symbols = load_symbols()
    for sym in symbols:
        print(f"\n=== Processing {sym} ===")
        try:
            update_symbol(sym)
        except Exception as e:
            print(f"⚠ ERROR updating {sym}: {e}")


if __name__ == "__main__":
    main()
