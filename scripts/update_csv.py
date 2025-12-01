"""
Auto-download CSV files for all symbols listed in symbols.txt.
Outputs unified price CSVs to data/{symbol}.csv
"""

from pathlib import Path
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

DATA_DIR = Path("data")
SYMBOL_FILE = Path("symbols.txt")
REQUIRED_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def load_symbols():
    """Read symbols from symbols.txt"""
    if not SYMBOL_FILE.exists():
        raise FileNotFoundError("symbols.txt not found!")
    with open(SYMBOL_FILE, "r") as f:
        return [s.strip() for s in f.readlines() if s.strip()]


def download_symbol(symbol: str, start: str | None, end: str | None):
    df = yf.download(symbol, start=start, end=end, auto_adjust=False)
    if df.empty:
        print(f"❌ {symbol} 無資料")
        return None

    # 清理 multi-index
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # 確保欄位完整
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        print(f"❌ {symbol} 缺少欄位：{missing}")
        return None

    df = df[REQUIRED_COLUMNS].sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def save_csv(symbol, df):
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{symbol}.csv"
    df.to_csv(path)
    print(f"✅ Saved {path} ({len(df)} rows)")


def main():
    symbols = load_symbols()

    end = datetime.today()
    start = end - timedelta(days=365 * 15)

    print("📌 Updating symbols:", symbols)

    for sym in symbols:
        df = download_symbol(sym, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
        if df is not None:
            save_csv(sym, df)


if __name__ == "__main__":
    main()
