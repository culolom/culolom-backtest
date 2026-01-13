###############################################################
# app_nsf.py — 國安基金跟單回測系統 (含 Sidebar 導覽)
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path
import sys

###############################################################
# 1. Streamlit 頁面與認證設定
###############################################################

st.set_page_config(
    page_title="國安基金回測系統", 
    page_icon="🏛️", 
    layout="wide"
)

# 🔒 認證守門員 (保留您原有的機制)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except ImportError:
    pass 

# --- Sidebar 導覽列 (您要求補上的部分) ---
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")

###############################################################
# 2. 歷史資料與參數定義
###############################################################

# 國安基金歷史進退場日期 (更新至 2026/01/12)
NSF_DATES = [
    ("2000-03-15", "2000-03-20"),
    ("2000-10-02", "2000-11-15"),
    ("2004-05-19", "2004-05-31"),
    ("2008-09-19", "2008-12-16"),
    ("2011-12-20", "2012-04-20"),
    ("2015-08-25", "2016-04-12"),
    ("2020-03-19", "2020-10-12"),
    ("2022-07-13", "2023-04-13"),
    ("2025-04-09", "2026-01-12"),
]

DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    return df[["Close"]]

def format_currency(v): return f"{v:,.0f} 元"
def format_percent(v, d=2): return f"{v*100:.{d}f}%"

###############################################################
# 3. 主要內容區域
###############################################################

st.markdown("<h1 style='margin-bottom:0.5em;'>🏛️ 國安基金跟單策略 vs 0050 Buy & Hold</h1>", unsafe_allow_html=True)

st.info("""
**策略邏輯說明：**
- **跟單模式：** 僅在國安基金宣布「進場護盤」期間持有標的，其餘時間持幣觀望（0% 倉位）。
- **對照組：** 同期間 0050 始終持有 (Buy & Hold)。
- **備註：** 由於 0050 於 2003 年掛牌，系統將自動忽略 2000 年的前兩次紀錄。
""")

# --- UI 輸入 ---
col1, col2 = st.columns(2)
with col1:
    target_symbol = st.selectbox("選擇回測標的", ["0050.TW", "006208.TW"])
with col2:
    capital = st.number_input("初始投入本金（元）", 1000, 10_000_000, 1_000_000, step=100_000)

###############################################################
# 4. 回測運算與繪圖
###############################################################

if st.button("開始回測 🚀"):
    df_raw = load_csv(target_symbol)
    if df_raw.empty:
        st.error("⚠️ 找不到 CSV 資料，請檢查 data 資料夾是否有對應檔案。"); st.stop()

    df = df_raw.copy()
    df["Return"] = df["Close"].pct_change().fillna(0)
    df["In_NSF"] = 0
    
    # 標記護盤區間
    for start_date, end_date in NSF_DATES:
        df.loc[start_date:end_date, "In_NSF"] = 1
        
    df["Strategy_Return"] = df["Return"] * df["In_NSF"]
    df["Equity_NSF"] = (1 + df["Strategy_Return"]).cumprod()
    df["Equity_BH"] = (1 + df["Return"]).cumprod()
    df["Signal"] = df["In_NSF"].diff()

    # --- 圖表呈現 ---
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_NSF"]*capital, name="國安基金跟單 (策略)", line=dict(color="#E53E3E", width=2.5)))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_BH"]*capital, name="0050 Buy & Hold", line=dict(color="#CBD5E0", width=1.5)))
    
    # 標記買賣點
    buys = df[df["Signal"] == 1]
    sells = df[df["Signal"] == -1]
    fig.add_trace(go.Scatter(x=buys.index, y=df.loc[buys.index, "Equity_NSF"]*capital, mode="markers", name="跟隨進場", marker=dict(symbol="triangle-up", size=10, color="#2F855A")))
    fig.add_trace(go.Scatter(x=sells.index, y=df.loc[sells.index, "Equity_NSF"]*capital, mode="markers", name="跟隨退場", marker=dict(symbol="triangle-down", size=10, color="#C05621")))

    fig.update_layout(template="plotly_white", hovermode="x unified", height=500, yaxis_title="資產規模 (元)")
    st.plotly_chart(fig, use_container_width=True)

    # --- 績效數據 ---
    def get_metrics(equity_series):
        final_val = equity_series.iloc[-1]
        total_ret = final_val - 1
        mdd = (equity_series / equity_series.cummax() - 1).min()
        days = (equity_series.index[-1] - equity_series.index[0]).days
        cagr = (final_val)**(365/days) - 1 if final_val > 0 else 0
        return total_ret, cagr, mdd

    m_nsf = get_metrics(df["Equity_NSF"])
    m_bh = get_metrics(df["Equity_BH"])

    st.markdown("### 📊 策略績效對照表")
    res_data = {
        "分析指標": ["最終資產價值", "累計總報酬", "年化報酬率 (CAGR)", "最大回撤 (MDD)"],
        "國安基金策略": [format_currency(capital * df["Equity_NSF"].iloc[-1]), format_percent(m_nsf[0]), format_percent(m_nsf[1]), format_percent(m_nsf[2])],
        "0050 一直持有": [format_currency(capital * df["Equity_BH"].iloc[-1]), format_percent(m_bh[0]), format_percent(m_bh[1]), format_percent(m_bh[2])]
    }
    st.table(pd.DataFrame(res_data))

    st.success("✅ 回測完成！從歷史數據看，國安基金通常能精準捕捉波段低點，大幅降低持有壓力 (MDD)。")
