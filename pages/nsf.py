###############################################################
# app_nsf.py — 國安基金跟單策略 vs 0050 Buy & Hold
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# --- 國安基金歷史進場與退場時間表 ---
# 格式：(進場日期, 退場決議日期)
NSF_DATES = [
    ("2000-03-15", "2000-03-20"),
    ("2000-10-02", "2000-11-15"),
    ("2004-05-19", "2004-05-31"),
    ("2008-09-19", "2008-12-16"),
    ("2011-12-20", "2012-04-20"),
    ("2015-08-25", "2016-04-12"),
    ("2020-03-19", "2020-10-12"),
    ("2022-07-13", "2023-04-13"),
    ("2025-04-09", "2026-01-12"), # 最新一次
]

###############################################################
# Streamlit 頁面設定
###############################################################

st.set_page_config(page_title="國安基金跟單回測系統", page_icon="🏛️", layout="wide")

st.markdown("# 🏛️ 國安基金跟單策略回測")
st.info("""
**策略邏輯：** 1. **進場：** 當國安基金宣布進場當日，以收盤價買入 0050。
2. **出場：** 當國安基金決議退場當日，以收盤價全數賣出 0050 回到現金。
3. **對照組：** 同期間 0050 一直持有 (Buy & Hold)。
*註：由於 0050 於 2003/06 掛牌，回測將從 2004 年第 3 次護盤開始計算。*
""")

DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    return df[["Close"]]

def format_currency(v): return f"{v:,.0f} 元"
def format_percent(v, d=2): return f"{v*100:.{d}f}%"

###############################################################
# UI 輸入
###############################################################

col1, col2, col3 = st.columns(3)
with col1:
    target_symbol = st.selectbox("選擇回測標的", ["0050.TW", "006208.TW"])
with col2:
    capital = st.number_input("投入本金（元）", 1000, 10_000_000, 1_000_000, step=100_000)
with col3:
    # 讀取資料確認區間
    df_raw = load_csv(target_symbol)
    if not df_raw.empty:
        s_min, s_max = df_raw.index.min().date(), df_raw.index.max().date()
        st.write(f"📊 資料區間：{s_min} ~ {s_max}")
    else:
        st.error("找不到資料文件"); st.stop()

###############################################################
# 核心邏輯
###############################################################

if st.button("開始執行國安基金回測 🚀"):
    df = df_raw.copy()
    df["Return"] = df["Close"].pct_change().fillna(0)
    
    # 初始化訊號：0 為空手，1 為跟著國安基金持有
    df["In_NSF"] = 0
    
    # 標記國安基金在場時間
    for start_date, end_date in NSF_DATES:
        df.loc[start_date:end_date, "In_NSF"] = 1
        
    # 計算策略報酬
    # 我們假設是當天看到新聞進場，所以當天就參與報酬 (簡化模型)
    df["Strategy_Return"] = df["Return"] * df["In_NSF"]
    
    # 計算累積淨值
    df["Equity_NSF"] = (1 + df["Strategy_Return"]).cumprod()
    df["Equity_BH"] = (1 + df["Return"]).cumprod()
    
    # 找出買賣點作圖用
    df["Signal"] = df["In_NSF"].diff() # 1 為買進, -1 為賣出
    
    ###############################################################
    # 圖表呈現
    ###############################################################
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_NSF"]*capital, name="國安基金跟單策略", line=dict(color="#E53E3E", width=2)))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_BH"]*capital, name="0050 一直持有", line=dict(color="#CBD5E0", width=1.5)))
    
    # 標記進出場點
    buys = df[df["Signal"] == 1]
    sells = df[df["Signal"] == -1]
    fig.add_trace(go.Scatter(x=buys.index, y=df.loc[buys.index, "Equity_NSF"]*capital, mode="markers", name="跟隨進場", marker=dict(symbol="triangle-up", size=10, color="green")))
    fig.add_trace(go.Scatter(x=sells.index, y=df.loc[sells.index, "Equity_NSF"]*capital, mode="markers", name="跟隨退場", marker=dict(symbol="triangle-down", size=10, color="orange")))

    fig.update_layout(title="淨值曲線比較 (Equity Curve)", template="plotly_white", hovermode="x unified", yaxis_title="資產總額")
    st.plotly_chart(fig, use_container_width=True)

    # 績效計算
    def get_metrics(equity_series, return_series):
        final_val = equity_series.iloc[-1]
        total_ret = final_val - 1
        mdd = (equity_series / equity_series.cummax() - 1).min()
        # 年化報酬 (以總天數計算)
        days = (equity_series.index[-1] - equity_series.index[0]).days
        cagr = (final_val)**(365/days) - 1 if final_val > 0 else 0
        return total_ret, cagr, mdd

    m_nsf = get_metrics(df["Equity_NSF"], df["Strategy_Return"])
    m_bh = get_metrics(df["Equity_BH"], df["Return"])

    # 顯示結果
    st.markdown("### 📊 績效對照表")
    res_data = {
        "指標": ["最終資產", "累計報酬率", "年化報酬率 (CAGR)", "最大回撤 (MDD)"],
        "國安基金跟單": [format_currency(capital * df["Equity_NSF"].iloc[-1]), format_percent(m_nsf[0]), format_percent(m_nsf[1]), format_percent(m_nsf[2])],
        "0050 Buy & Hold": [format_currency(capital * df["Equity_BH"].iloc[-1]), format_percent(m_bh[0]), format_percent(m_bh[1]), format_percent(m_bh[2])]
    }
    st.table(pd.DataFrame(res_data))

    st.warning(f"💡 **鼠叔筆記**：回測顯示，國安基金策略因為大部分時間都在「空手待命」，雖然 MDD（最大回撤）會大幅優於一直持有，但長期的累積報酬通常會輸給 Buy & Hold，因為它錯過了大部分的牛市成長期。這個策略更像是一種『避險後的加碼』工具。")
