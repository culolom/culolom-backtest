"""
HamrLab Backtest Platform main entry.
Main page: Dashboard style layout with Password Protection & Market Signals.
"""

import streamlit as st
import os
import datetime
import pandas as pd
import auth  # <---【修改點 1】引入剛剛建立的 auth.py

# 1. 頁面設定 (必須放在第一行)
st.set_page_config(
    page_title="倉鼠量化戰情室 | 白銀小倉鼠專屬福利",
    page_icon="🐹",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------------------------------------------
# 🔒 會員驗證守門員 (Password Protection)
# ------------------------------------------------------
if not auth.check_password():
    st.stop()  # 驗證沒過就停在這裡

# ------------------------------------------------------
# ✅ 正式內容開始
# ------------------------------------------------------

# 共有用：資料夾、工具函式
DATA_DIR = "data"
TARGET_SYMBOLS = ["0050.TW", "GLD", "QQQ", "SPY", "VT", "ACWI", "VOO","SPY", "VXUS", "VEA", "VWO", "BOXX", "VTI", "BIL", "IEF", "IEI"]

def find_csv_for_symbol(symbol: str, files: list):
    """在 data/*.csv 中找符合 symbol 的檔名（模糊搜尋）"""
    symbol_lower = symbol.lower()
    for f in files:
        name = os.path.basename(f).lower()
        if symbol_lower in name:
            return f
    return None

def load_price_series(csv_path: str):
    """從 CSV 讀出價格序列"""
    try:
        df = pd.read_csv(csv_path)
        df.iloc[:, 0] = pd.to_datetime(df.iloc[:, 0], errors="coerce")
        df = df.set_index(df.columns[0]).sort_index()
        candidates = ["Close", "Adj Close", "close", "adjclose"]
        for c in candidates:
            if c in df.columns:
                return df[c].astype(float).dropna()
        num_cols = df.select_dtypes(include="number").columns
        if len(num_cols) == 0:
            return None
        return df[num_cols[-1]].astype(float).dropna()
    except Exception:
        return None

def classify_trend(price: pd.Series):
    """用 200 日 + 價格位置簡易判斷趨勢。"""
    if price is None or len(price) < 200:
        return "資料不足", "⬜"
    ma200 = price.rolling(200).mean().iloc[-1]
    last = price.iloc[-1]
    if pd.isna(ma200) or pd.isna(last):
        return "資料不足", "⬜"
    diff = (last / ma200) - 1.0
    if diff > 0.05:
        return "多頭", "🟢"
    elif diff > 0:
        return "偏多", "🟡"
    elif diff > -0.05:
        return "偏空", "🟠"
    else:
        return "空頭", "🔴"

def get_momentum_ranking(data_dir="data", symbols=None):
    if not os.path.exists(data_dir):
        return None, "無資料夾"

    today = pd.Timestamp.today()
    this_month_start = today.replace(day=1)
    end_date = this_month_start - pd.Timedelta(days=1)
    start_date = end_date - pd.DateOffset(months=12)

    results = []
    all_files = [f for f in os.listdir(data_dir) if f.endswith(".csv")]

    if symbols:
        symbols_lower = [s.lower() for s in symbols]
        use_files = [f for f in all_files if f.replace(".csv", "").lower() in symbols_lower]
    else:
        use_files = all_files

    if not use_files:
        return None, end_date

    for f in use_files:
        symbol = f.replace(".csv", "")
        try:
            df = pd.read_csv(os.path.join(data_dir, f))
            if "Date" not in df.columns: continue

            col_price = "Adj Close" if "Adj Close" in df.columns else "Close"
            if col_price not in df.columns: continue

            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date").sort_index()
            df["MA_200"] = df[col_price].rolling(window=200).mean()

            hist_window = df.loc[:end_date]
            if hist_window.empty: continue

            last_valid = hist_window.index[-1]
            if (end_date - last_valid).days > 15: continue

            p_end = hist_window[col_price].iloc[-1]
            ma_end = df.loc[last_valid, "MA_200"]

            # 【新增計算】200SMA 乖離率 = (收盤價 - 200SMA) / 200SMA
            bias_rate = (p_end - ma_end) / ma_end if ma_end and not pd.isna(ma_end) else 0

            start_window = df.loc[:start_date]
            if start_window.empty: continue

            p_start = start_window[col_price].iloc[-1]
            ret = (p_end - p_start) / p_start

            results.append({
                "代號": symbol,
                "12月累積報酬": ret * 100,
                "收盤價": p_end,
                "200SMA": ma_end,
                "200SMA乖離率": bias_rate * 100  # 轉為百分比
            })
        except Exception:
            continue

    if not results: return None, end_date

    df = pd.DataFrame(results)
    df = df.sort_values("12月累積報酬", ascending=False).reset_index(drop=True)
    df.index += 1
    df.index.name = "排名"
    return df, end_date

# ------------------------------------------------------
# 側邊欄與標題 (略，保持原樣)
# ------------------------------------------------------
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", width=120)
    else: st.title("🐹") 
    st.title("倉鼠量化戰情室")
    st.caption("v1.1.1 Beta | 白銀小倉鼠限定")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="部落格首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@HamrLab", label="YouTube 頻道", icon="📺")
    st.divider()
    if st.button("🚪 登出系統"):
        st.session_state["password_correct"] = False
        st.rerun()

st.title("🚀 戰情室主頁面")
# ... (資料狀態顯示略)

# ------------------------------------------------------
# 🏆 本月動能排行榜
# ------------------------------------------------------
st.markdown("### 🏆 本月動能排行榜（過去 12 個月績效）")

rank_df, calc_date = get_momentum_ranking(DATA_DIR, symbols=TARGET_SYMBOLS)

if rank_df is not None and not isinstance(calc_date, str):
    st.caption(f"📅 統計基準日：**{calc_date.strftime('%Y-%m-%d')}**（上個月底） | 過去 12 個月累積報酬")

    st.dataframe(
        rank_df,
        column_config={
            "12月累積報酬": st.column_config.ProgressColumn(
                "12月累積報酬 (Momentum)",
                help="過去 12 個月的漲跌幅",
                format="%.2f%%",
                min_value=-50,
                max_value=100,
            ),
            "收盤價": st.column_config.NumberColumn(
                "收盤價 (Price)",
                format="$%.2f",
            ),
            "200SMA": st.column_config.NumberColumn(
                "200 日均線",
                format="$%.2f",
            ),
            # 【新增 UI 欄位設定】
            "200SMA乖離率": st.column_config.NumberColumn(
                "200SMA 乖離率",
                help="(收盤價 - 200SMA) / 200SMA",
                format="%.2f%%",
            ),
        },
        use_container_width=True,
    )
else:
    st.info("❗ 尚無足夠資料可計算動能排行。")

st.markdown("---")
st.caption("🚧 更多策略正在開發中，敬請期待！")
