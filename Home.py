"""
HamrLab Backtest Platform main entry.
Main page: Dashboard style layout with Password Protection & Market Signals.
"""

import streamlit as st
import os
import datetime
import pandas as pd
import glob
import auth  # 需確保目錄下有 auth.py

# 1. 頁面設定
st.set_page_config(
    page_title="倉鼠量化戰情室 | 白銀小倉鼠專屬福利",
    page_icon="🐹",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------------------------------------------
# 🔒 會員驗證守門員
# ------------------------------------------------------
if not auth.check_password():
    st.stop()

# ------------------------------------------------------
# ✅ 全域變數與工具函式
# ------------------------------------------------------
DATA_DIR = "data"
# 指定排行榜追蹤標的
TARGET_SYMBOLS = ["0050.TW", "GLD", "QQQ", "SPY", "VT", "ACWI", "VOO", "VXUS", "VEA", "VWO", "BOXX", "VTI", "BIL", "IEF", "IEI"]

def find_csv_for_symbol(symbol: str, files: list):
    """在 data/*.csv 中找符合 symbol 的檔名"""
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
        return df[num_cols[-1]].astype(float).dropna() if len(num_cols) > 0 else None
    except Exception:
        return None

def classify_trend(price: pd.Series):
    """用 200 日均線判斷趨勢"""
    if price is None or len(price) < 200:
        return "資料不足", "⬜"
    ma200 = price.rolling(200).mean().iloc[-1]
    last = price.iloc[-1]
    if pd.isna(ma200) or pd.isna(last):
        return "資料不足", "⬜"
    diff = (last / ma200) - 1.0
    if diff > 0.05: return "多頭", "🟢"
    elif diff > 0: return "偏多", "🟡"
    elif diff > -0.05: return "偏空", "🟠"
    else: return "空頭", "🔴"

def get_momentum_ranking(data_dir="data", symbols=None):
    """計算 3 個月動能與 200SMA 乖離率"""
    if not os.path.exists(data_dir):
        return None, "無資料夾"

    # 計算基準日 (上月底)
    today = pd.Timestamp.today()
    this_month_start = today.replace(day=1)
    end_date = this_month_start - pd.Timedelta(days=1)
    # 改為 3 個月前
    start_date = end_date - pd.DateOffset(months=3)

    results = []
    all_files = [f for f in os.listdir(data_dir) if f.endswith(".csv")]

    if symbols:
        symbols_lower = [s.lower() for s in symbols]
        use_files = [f for f in all_files if f.replace(".csv", "").lower() in symbols_lower]
    else:
        use_files = all_files

    for f in use_files:
        symbol = f.replace(".csv", "")
        try:
            df = pd.read_csv(os.path.join(data_dir, f))
            if "Date" not in df.columns: continue
            
            col_price = "Adj Close" if "Adj Close" in df.columns else "Close"
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date").sort_index()
            
            # 計算 200 均線
            df["MA_200"] = df[col_price].rolling(window=200).mean()

            # 抓取基準日當下的數據
            hist_window = df.loc[:end_date]
            if hist_window.empty: continue
            
            last_valid_date = hist_window.index[-1]
            p_end = hist_window[col_price].iloc[-1]
            ma_end = hist_window["MA_200"].iloc[-1]

            # 1. 計算 3個月報酬 (Momentum)
            start_window = df.loc[:start_date]
            if start_window.empty: continue
            p_start = start_window[col_price].iloc[-1]
            ret_3m = (p_end - p_start) / p_start

            # 2. 計算 200SMA 乖離率 = (收盤價 - 200SMA) / 200SMA
            bias_200 = (p_end - ma_end) / ma_end if ma_end and not pd.isna(ma_end) else None

            results.append({
                "代號": symbol,
                "3月累積報酬": ret_3m * 100,
                "收盤價": p_end,
                "200SMA": ma_end,
                "200SMA乖離率": bias_200 * 100 if bias_200 is not None else None
            })
        except Exception:
            continue

    if not results: return None, end_date

    df_res = pd.DataFrame(results)
    df_res = df_res.sort_values("3月累積報酬", ascending=False).reset_index(drop=True)
    df_res.index += 1
    df_res.index.name = "排名"
    return df_res, end_date

# ------------------------------------------------------
# 2. 側邊欄
# ------------------------------------------------------
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", width=120)
    else: st.title("🐹") 
    st.title("倉鼠量化戰情室")
    st.caption("v1.1.2 | 白銀小倉鼠限定")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="部落格首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@HamrLab", label="YouTube 頻道", icon="📺")
    st.divider()
    if st.button("🚪 登出系統"):
        st.session_state["password_correct"] = False
        st.rerun()

# ------------------------------------------------------
# 3. 主畫面
# ------------------------------------------------------
st.title("🚀 戰情室主頁面")

# 資料狀態檢測
files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
last_update = "N/A"
if files:
    latest_file = max(files, key=os.path.getmtime)
    last_update = datetime.datetime.fromtimestamp(os.path.getmtime(latest_file)).strftime("%Y-%m-%d")

st.caption(f"✅ 系統數據正常 | 📅 最後更新：{last_update}")
st.markdown("歡迎來到 **倉鼠量化戰情室**！下方顯示主要標的的 **3個月動能排行榜** 與 **200日線乖離率**。")

st.divider()

# ==========================================
# 🛠️ 策略選擇區
# ==========================================
st.subheader("🛠️ 選擇你的實驗策略")
# (此處保留你原本的 META_INFO 與自動掃描 logic...)
# ... [省略中間重複的頁面掃描代碼以節省篇幅] ...

# ==========================================
# 📊 功能 1：市場即時摘要
# ==========================================
st.subheader("📌 今日市場摘要 (SMA200 趨勢)")
summary_cols = st.columns(4)
ASSET_CONFIG = [
    {"label": "美股科技", "symbol": "QQQ"},
    {"label": "美股大盤", "symbol": "SPY"},
    {"label": "台股大盤", "symbol": "0050"},
    {"label": "全球股市", "symbol": "VT"},
]

for i, asset in enumerate(ASSET_CONFIG):
    with summary_cols[i]:
        csv_path = find_csv_for_symbol(asset["symbol"], files)
        if csv_path:
            p_series = load_price_series(csv_path)
            txt, icon = classify_trend(p_series)
            st.metric(asset["label"], txt, icon)
        else:
            st.metric(asset["label"], "無資料", "⬜")

# ==========================================
# 🏆 功能 2：本月動能排行榜 (3個月)
# ==========================================
st.divider()
st.markdown("### 🏆 本月動能排行榜（過去 3 個月績效）")

rank_df, calc_date = get_momentum_ranking(DATA_DIR, symbols=TARGET_SYMBOLS)

if rank_df is not None:
    st.caption(f"📅 統計基準日：**{calc_date.strftime('%Y-%m-%d')}** | 排序依據：3個月累積報酬率")

    st.dataframe(
        rank_df,
        column_config={
            "3月累積報酬": st.column_config.ProgressColumn(
                "3月累積報酬",
                help="過去 3 個月的漲跌幅",
                format="%.2f%%",
                min_value=-30,
                max_value=60,
            ),
            "收盤價": st.column_config.NumberColumn("收盤價", format="$%.2f"),
            "200SMA": st.column_config.NumberColumn("200SMA", format="$%.2f"),
            "200SMA乖離率": st.column_config.NumberColumn(
                "200SMA 乖離率",
                help="(收盤價 - 200SMA) / 200SMA",
                format="%.2f%%",
            ),
        },
        use_container_width=True,
    )
else:
    st.info("❗ 尚無足夠資料計算排行榜。")

st.markdown("---")
st.caption("🚧 更多策略持續開發中...")
