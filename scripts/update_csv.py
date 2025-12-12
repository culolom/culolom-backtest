"""
Auto-update adjusted-price CSVs (Hybrid Version: FinMind + Yahoo)
- Uses FinMind for deep history (2000+) to fix Yahoo's Taiwan stock data gap (2003-2008).
- Uses Yahoo Finance for daily updates (speed & convenience).
- Automatically detects & repairs missing Stock Splits.
"""

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta
import re
import pandas as pd
import yfinance as yf
import numpy as np

# 嘗試匯入 FinMind
try:
    from FinMind.data import DataLoader
    FINMIND_AVAILABLE = True
except ImportError:
    FINMIND_AVAILABLE = False
    print("⚠ FinMind not installed. Running in yfinance-only mode.")

# -----------------------------------------------------
# Paths & Config
# -----------------------------------------------------
DATA_DIR = Path("data")
SYMBOLS_FILE = Path("symbols.txt")

# -----------------------------------------------------
# Normalize symbol
# -----------------------------------------------------
def normalize_symbol(sym: str) -> str:
    s = sym.strip().upper()
    if s.endswith(".TW"):
        return s
    if re.match(r"^\d+[A-Z]*$", s):
        return s + ".TW"
    return s

# -----------------------------------------------------
# Helper: Fix yfinance MultiIndex columns
# -----------------------------------------------------
def clean_yfinance_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Fix (Price, Ticker) -> Price
    if isinstance(df.columns, pd.MultiIndex):
        try:
            df.columns = df.columns.get_level_values(0)
        except IndexError:
            pass
    return df

# -----------------------------------------------------
# CORE: Detect & Repair Splits Manually
# -----------------------------------------------------
def detect_and_repair_splits(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    Scans for massive price discontinuities (>50% drop or >100% gain)
    and back-adjusts historical data if Yahoo missed the split.
    """
    if df.empty or len(df) < 2:
        return df

    has_open = 'Open' in df.columns
    closes = df['Close']
    prev_closes = closes.shift(1)
    
    # 偵測閾值
    drops = closes / prev_closes
    split_candidates = drops[(drops < 0.6) | (drops > 1.8)].dropna()

    if split_candidates.empty:
        return df

    df_fixed = df.copy()
    
    for date, ratio_raw in split_candidates.items():
        loc_idx = df_fixed.index.get_loc(date)
        if loc_idx == 0: continue

        prev_close = df_fixed['Close'].iloc[loc_idx - 1]
        
        if has_open:
            curr_open = df_fixed['Open'].iloc[loc_idx]
            if pd.isna(curr_open) or curr_open == 0:
                curr_open = df_fixed['Close'].iloc[loc_idx]
        else:
            curr_open = df_fixed['Close'].iloc[loc_idx]

        factor = prev_close / curr_open

        if 0.6 < factor < 1.5:
            continue

        print(f"🔧 REPAIR: Detected missing split for {symbol} on {date.date()}")
        print(f"   Before: {prev_close:.2f} -> {curr_open:.2f} (Factor: {factor:.4f})")
        
        mask = df_fixed.index < date
        
        cols_to_fix = ['Close', 'Open', 'High', 'Low']
        for col in cols_to_fix:
            if col in df_fixed.columns:
                df_fixed.loc[mask, col] = df_fixed.loc[mask, col] / factor
        
        if 'Volume' in df_fixed.columns:
            df_fixed.loc[mask, 'Volume'] = df_fixed.loc[mask, 'Volume'] * factor

        print(f"   ✅ History adjusted. New prev close: {df_fixed.loc[mask, 'Close'].iloc[-1]:.2f}")

    return df_fixed

# -----------------------------------------------------
# FinMind Logic (Deep History)
# -----------------------------------------------------
def download_finmind_full(symbol: str) -> pd.DataFrame:
    """
    Uses FinMind to download full history (starts from 2000-01-01).
    """
    if not FINMIND_AVAILABLE:
        return pd.DataFrame()

    # FinMind 使用 "0050" 而非 "0050.TW"
    stock_id = symbol.replace(".TW", "")
    
    # 簡單過濾：如果看起來像美股代號 (全英文且無.TW)，直接跳過 FinMind
    if not any(char.isdigit() for char in stock_id) and ".TW" not in symbol:
        return pd.DataFrame()

    print(f"🌍 FinMind: Fetching deep history for {stock_id}...")
    
    try:
        loader = DataLoader()
        df = loader.taiwan_stock_daily(
            stock_id=stock_id,
            start_date='2000-01-01'
        )
    except Exception as e:
        print(f"⚠ FinMind Error: {e}")
        return pd.DataFrame()
    
    if df.empty:
        return df

    # Normalize columns to match yfinance
    # FinMind: date, open, high, low, close, Trading_Volume
    df = df.rename(columns={
        'date': 'Date',
        'open': 'Open',
        'max': 'High',
        'min': 'Low',
        'close': 'Close',
        'Trading_Volume': 'Volume'
    })

    # Convert types
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date')
    
    numeric_cols = ['Open', 'Close', 'High', 'Low', 'Volume']
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
            
    return df[numeric_cols]

# -----------------------------------------------------
# Yahoo Logic
# -----------------------------------------------------
def download_yahoo_data(symbol: str, start=None, mode="full") -> pd.DataFrame:
    """Generic download wrapper that fetches Open/Close/Volume from Yahoo"""
    print(f"⬇ Yahoo: Fetching {symbol} ({mode})...")
    
    df = yf.download(
        symbol,
        start=start,
        period="max" if mode=="full" else None,
        auto_adjust=True,
        progress=False
    )
    df = clean_yfinance_columns(df)
    
    required = ['Open', 'Close', 'Volume']
    for col in required:
        if col not in df.columns:
            df[col] = np.nan
            
    return df

# -----------------------------------------------------
# Main Update Logic
# -----------------------------------------------------
def update_symbol(symbol: str):
    DATA_DIR.mkdir(exist_ok=True)
    csv_path = DATA_DIR / f"{symbol}.csv"
    
    existing = None
    if csv_path.exists():
        try:
            existing = pd.read_csv(csv_path, index_col=0, parse_dates=True)
            if "Close" not in existing.columns: existing = None
        except:
            existing = None

    new_data = pd.DataFrame()

    # -------------------------------------------------
    # STRATEGY 1: Full Download (Priority: FinMind -> Yahoo)
    # -------------------------------------------------
    if existing is None or existing.empty:
        # 1. Try FinMind first for deep history (Taiwan stocks)
        if FINMIND_AVAILABLE:
            new_data = download_finmind_full(symbol)
        
        # 2. If FinMind failed or returned empty (e.g. US stock), use Yahoo
        if new_data.empty:
            if FINMIND_AVAILABLE:
                print(f"⚠ FinMind no data, falling back to Yahoo for {symbol}")
            new_data = download_yahoo_data(symbol, mode="full")
        else:
            print(f"✅ FinMind loaded {len(new_data)} rows.")

    # -------------------------------------------------
    # STRATEGY 2: Append Update (Always Yahoo)
    # -------------------------------------------------
    else:
        last_date = existing.index[-1]
        start_date = (last_date - timedelta(days=10)).strftime("%Y-%m-%d")
        print(f"📄 Appending {symbol} from {start_date}...")
        
        fresh = download_yahoo_data(symbol, start=start_date, mode="append")
        
        existing = existing[existing.index < pd.Timestamp(start_date)]
        new_data = pd.concat([existing, fresh])
        new_data = new_data[~new_data.index.duplicated(keep='last')]
        new_data = new_data.sort_index()

    if new_data.empty:
        print(f"⚠ No data for {symbol}")
        return

    # -------------------------------------------------
    # 3. Self-Healing & Save
    # -------------------------------------------------
    repaired_data = detect_and_repair_splits(new_data, symbol)

    # Save only necessary columns
    final_output = repaired_data[["Close", "Volume"]].copy()
    final_output.index.name = "Date"
    
    final_output.to_csv(csv_path)
    print(f"✅ Saved {symbol} ({len(final_output)} rows)")

# -----------------------------------------------------
# Entry Point
# -----------------------------------------------------
def main():
    if not SYMBOLS_FILE.exists():
        print("⚠ symbols.txt missing, using demo list.")
        symbols = ["0050.TW"] 
    else:
        with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
            symbols = [normalize_symbol(line.strip()) for line in f if line.strip() and not line.startswith("#")]

    for sym in symbols:
        print("-" * 40)
        try:
            update_symbol(sym)
        except Exception as e:
            print(f"❌ Error {sym}: {e}")

if __name__ == "__main__":
    main()
