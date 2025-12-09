"""
Auto-update adjusted-price CSVs (Self-Healing Version)
- Automatically detects & repairs missing Stock Splits (like 00663L)
- Forces continuity even if Yahoo Finance data is broken
"""

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta
import re
import pandas as pd
import yfinance as yf
import numpy as np

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

    # 需要 Open 欄位來計算精確的 Split Ratio (Open[t] / Close[t-1])
    # 如果只有 Close，這一步只能用 Close 估算
    has_open = 'Open' in df.columns

    # 計算價格變化率
    closes = df['Close']
    prev_closes = closes.shift(1)
    
    # 偵測閾值：跌幅 > 40% (0.6) 或 漲幅 > 80% (1.8)
    # 00663L 1拆7 約跌 85%
    drops = closes / prev_closes
    
    # 找出異常點 (忽略第一筆 NaN)
    split_candidates = drops[(drops < 0.6) | (drops > 1.8)].dropna()

    if split_candidates.empty:
        return df

    # 開始修復
    df_fixed = df.copy()
    
    for date, ratio_raw in split_candidates.items():
        # 取得該日期的整數索引位置
        loc_idx = df_fixed.index.get_loc(date)
        if loc_idx == 0: continue

        # 計算修正因子 (Split Factor)
        # 理想公式： Factor = Previous Close / Current Open
        # 因為 Split 通常發生在開盤前，Open 應該已經是分割後的價格
        prev_close = df_fixed['Close'].iloc[loc_idx - 1]
        
        if has_open:
            curr_open = df_fixed['Open'].iloc[loc_idx]
            # 避免 Open 為 0 或 NaN
            if pd.isna(curr_open) or curr_open == 0:
                curr_open = df_fixed['Close'].iloc[loc_idx]
        else:
            curr_open = df_fixed['Close'].iloc[loc_idx]

        # Factor > 1 代表拆股 (價格變小，如 175 -> 25，Factor=7)
        # Factor < 1 代表反向拆股 (價格變大)
        factor = prev_close / curr_open

        # 簡單過濾：如果這只是市場大崩盤 (例如跌 10-20%)，Factor 會接近 1.1-1.2
        # 我們只處理 Factor > 1.5 或 Factor < 0.6 的情況
        if 0.6 < factor < 1.5:
            continue

        print(f"🔧 REPAIR: Detected missing split for {symbol} on {date.date()}")
        print(f"   Before: {prev_close:.2f} -> {curr_open:.2f} (Factor: {factor:.4f})")
        
        # 執行回溯修正 (Back Adjustment)
        # 舊價格全部除以 Factor (例如 175 / 7 = 25)
        # 舊成交量全部乘以 Factor (股數變多)
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
# Download & Update Logic
# -----------------------------------------------------
def download_data(symbol: str, start=None, mode="full") -> pd.DataFrame:
    """Generic download wrapper that fetches Open/Close/Volume"""
    print(f"⬇ Fetching {symbol} ({mode})...")
    
    df = yf.download(
        symbol,
        start=start,
        period="max" if mode=="full" else None,
        auto_adjust=True, # 嘗試讓 Yahoo 自動調整
        progress=False
    )
    df = clean_yfinance_columns(df)
    
    # 確保有需要的欄位，若沒有則補 NaN (避免報錯)
    required = ['Open', 'Close', 'Volume']
    for col in required:
        if col not in df.columns:
            df[col] = np.nan
            
    return df

def update_symbol(symbol: str):
    DATA_DIR.mkdir(exist_ok=True)
    csv_path = DATA_DIR / f"{symbol}.csv"
    
    # 1. Load Existing
    existing = None
    if csv_path.exists():
        try:
            existing = pd.read_csv(csv_path, index_col=0, parse_dates=True)
            if "Close" not in existing.columns: existing = None
        except:
            existing = None

    # 2. Determine Fetch Strategy
    if existing is None or existing.empty:
        # Full Download
        new_data = download_data(symbol, mode="full")
    else:
        # Append Update
        last_date = existing.index[-1]
        start_date = (last_date - timedelta(days=10)).strftime("%Y-%m-%d") # 多抓幾天用來接合
        print(f"📄 Appending {symbol} from {start_date}...")
        
        fresh = download_data(symbol, start=start_date, mode="append")
        
        # 合併舊與新 (這裡還沒修復)
        # 先把 fresh 中重疊的部分蓋過 existing (以最新的數據為準)
        existing = existing[existing.index < pd.Timestamp(start_date)]
        new_data = pd.concat([existing, fresh])
        new_data = new_data[~new_data.index.duplicated(keep='last')]
        new_data = new_data.sort_index()

    if new_data.empty:
        print(f"⚠ No data for {symbol}")
        return

    # 3. 執行「自我修復」檢測 (關鍵步驟！)
    # 無論是新下載還是合併後，都要檢查是否有「假崩盤」
    repaired_data = detect_and_repair_splits(new_data, symbol)

    # 4. Save (只保留 Close, Volume 以節省空間，或者保留 Open 也可以)
    # 這裡依照您的需求只留 Date, Close, Volume
    final_output = repaired_data[["Close", "Volume"]].copy()
    final_output.index.name = "Date"
    
    final_output.to_csv(csv_path)
    print(f"✅ Saved {symbol} ({len(final_output)} rows)")

# -----------------------------------------------------
# Main
# -----------------------------------------------------
def main():
    if not SYMBOLS_FILE.exists():
        # Demo mode if file missing
        print("⚠ symbols.txt missing, using demo list.")
        symbols = ["00663L.TW"] 
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
