###############################################################
# app_nsf.py — 國安基金加碼系統 (自選日期與多標的版)
###############################################################

import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path
import sys
from datetime import date

###############################################################
# 1. 頁面與認證設定
###############################################################

st.set_page_config(
    page_title="國安基金槓桿回測系統", 
    page_icon="🏛️", 
    layout="wide"
)

# 🔒 認證 (保留原有機制)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except ImportError:
    pass 

# --- Sidebar 導覽 ---
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

###############################################################
# 2. 參數與資料讀取定義
###############################################################

NSF_DATES = [
    ("2000-03-15", "2000-03-20"), ("2000-10-02", "2000-11-15"),
    ("2004-05-19", "2004-05-31"), ("2008-09-19", "2008-12-16"),
    ("2011-12-20", "2012-04-20"), ("2015-08-25", "2016-04-12"),
    ("2020-03-19", "2020-10-12"), ("2022-07-13", "2023-04-13"),
    ("2025-04-09", "2026-01-12"),
]

# 槓桿標的選單 (對應截圖內容)
LEV_OPTIONS = {
    "00631L 元大台灣50正2": "00631L.TW",
    "00663L 國泰台灣加權正2": "00663L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW",
    "00685L 群益台灣加權正2": "00685L.TW"
}

DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    return df[["Close"]]

###############################################################
# 3. UI 配置 (參考截圖排版)
###############################################################

st.title("🏛️ 國安基金跟單：加碼正2策略回測")

# 第一列：標的選擇
c1, c2 = st.columns(2)
with c1:
    base_label = st.selectbox("原型 ETF（訊號來源）", ["0050 元大台灣50", "006208 富邦台50"])
    base_symbol = "0050.TW" if "0050" in base_label else "006208.TW"
with c2:
    lev_label = st.selectbox("槓桿 ETF（實際進出場標的）", list(LEV_OPTIONS.keys()))
    lev_symbol = LEV_OPTIONS[lev_label]

# 預載資料以取得可回測日期範圍
df_base_raw = load_csv(base_symbol)
df_lev_raw = load_csv(lev_symbol)

if not df_base_raw.empty and not df_lev_raw.empty:
    common_start = max(df_base_raw.index.min(), df_lev_raw.index.min())
    common_end = min(df_base_raw.index.max(), df_lev_raw.index.max())
    
    st.info(f"📌 可回測區間：{common_start.date()} ~ {common_end.date()}")

    # 第二列：日期與金額
    c3, c4, c5 = st.columns([1.5, 1.5, 1])
    with c3:
        start_date = st.date_input("開始日期", value=date(2021, 1, 13), min_value=common_start.date(), max_value=common_end.date())
    with c4:
        end_date = st.date_input("結束日期", value=common_end.date(), min_value=common_start.date(), max_value=common_end.date())
    with c5:
        capital = st.number_input("投入本金 (元)", value=100000, step=10000)
else:
    st.error("⚠️ 找不到 CSV 資料，請確認 data 資料夾檔案是否存在。")
    st.stop()

###############################################################
# 4. 回測運算
###############################################################

if st.button("開始回測 🚀", use_container_width=True):
    # 1. 合併並過濾日期
    df = pd.merge(df_base_raw, df_lev_raw, left_index=True, right_index=True, suffixes=('_Base', '_Lev'))
    df = df.loc[str(start_date):str(end_date)].copy()
    
    # 2. 計算報酬
    df["Ret_Base"] = df["Close_Base"].pct_change().fillna(0)
    df["Ret_Lev"] = df["Close_Lev"].pct_change().fillna(0)
    
    # 3. 標記國安基金區間
    df["In_NSF"] = 0
    for s, e in NSF_DATES:
        df.loc[s:e, "In_NSF"] = 1
    
    # 4. 執行策略切換
    df["Strategy_Return"] = np.where(df["In_NSF"] == 1, df["Ret_Lev"], df["Ret_Base"])
    
    # 5. 累積淨值 (需從 1 開始)
    df["Equity_Strategy"] = (1 + df["Strategy_Return"]).cumprod()
    df["Equity_BH"] = (1 + df["Ret_Base"]).cumprod()
    df["Signal"] = df["In_NSF"].diff()

    # --- 圖表 ---
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"]*capital, name="加碼正2策略", line=dict(color="#E53E3E", width=2.5)))
    fig.add_trace(go.Scatter(x=df.index, y=df["Equity_BH"]*capital, name="原型 Buy & Hold", line=dict(color="#CBD5E0", width=1.5)))
    
    # 標記
    buys = df[df["Signal"] == 1]; sells = df[df["Signal"] == -1]
    fig.add_trace(go.Scatter(x=buys.index, y=df.loc[buys.index, "Equity_Strategy"]*capital, mode="markers", name="切換至正2", marker=dict(symbol="triangle-up", size=10, color="#2F855A")))
    fig.add_trace(go.Scatter(x=sells.index, y=df.loc[sells.index, "Equity_Strategy"]*capital, mode="markers", name="切回原型", marker=dict(symbol="triangle-down", size=10, color="#C05621")))

    fig.update_layout(template="plotly_white", hovermode="x unified", height=500)
    st.plotly_chart(fig, use_container_width=True)

    # --- 績效表 ---
    def get_stats(eq, ret):
        final = eq.iloc[-1]
        total = final - 1
        days = (eq.index[-1] - eq.index[0]).days
        cagr = (final)**(365/days) - 1 if final > 0 else 0
        mdd = (eq / eq.cummax() - 1).min()
        return [final * capital, total, cagr, mdd]

    s_strat = get_stats(df["Equity_Strategy"], df["Strategy_Return"])
    s_bh = get_stats(df["Equity_BH"], df["Ret_Base"])

    metrics = ["期末淨值", "總報酬率", "年化報酬 (CAGR)", "最大回撤 (MDD)"]
    res_df = pd.DataFrame({"指標": metrics, "策略": s_strat, "基準": s_bh})
    
    # 簡單格式化顯示
    st.subheader("🏆 績效總表")
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("最終資產", f"{s_strat[0]:,.0f} 元", f"{(s_strat[0]-s_bh[0]):,.0f}")
    col_m2.metric("策略總報酬", f"{s_strat[1]:.2%}")
    col_m3.metric("最大回撤", f"{s_strat[3]:.2%}")

# --- Footer ---
st.markdown("---")
st.caption("© 2026 倉鼠人生實驗室 Hamr-Lab.com | 國安基金加碼研究系統")
