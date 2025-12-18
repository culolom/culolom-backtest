import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# --- 1. 頁面設定與 Sidebar 導覽 ---
st.set_page_config(page_title="0050LRS 狀態機回測系統", page_icon="📈", layout="wide")

with st.sidebar:
    st.markdown("### 🚀 導覽")
    st.page_link("Home.py", label="回到首頁", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")

# --- 2. 資料讀取 ---
ETFS = {
    "0050 元大台灣50": "0050.TW",
    "006208 富邦台50": "006208.TW",
    "00631L 元大台灣50正2": "00631L.TW",
    "00675L 富邦台灣加權正2": "00675L.TW",
}
DATA_DIR = Path("data")
WINDOW = 200

def load_csv(symbol: str):
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    df["Price"] = df["Close"]
    return df[["Price"]]

# 🔒 認證 (假設已備妥)
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except: pass

###############################################################
# 3. 主頁面：回測條件設定 (不放在 Sidebar)
###############################################################
st.markdown("<h1 style='text-align: center;'>📊 策略績效比較 (含高位套利保護)</h1>", unsafe_allow_html=True)

with st.container(border=True):
    st.subheader("⚙️ 核心回測條件")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        target_label = st.selectbox("選擇回測標的", list(ETFS.keys()), index=2) # 預設正2
        target_symbol = ETFS[target_label]
    with c2:
        capital = st.number_input("投入本金 (元)", 1000, 10_000_000, 100_000)
    with c3:
        pos_init = st.radio("初始狀態", ["空手起跑", "一開始就全倉"], horizontal=True)

    df_raw = load_csv(target_symbol)
    if not df_raw.empty:
        s_min, s_max = df_raw.index.min().date(), df_raw.index.max().date()
        c4, c5, c6, c7 = st.columns(4)
        with c4:
            start_d = st.date_input("開始日期", value=dt.date(2020, 12, 18), min_value=s_min, max_value=s_max)
        with c5:
            end_d = st.date_input("結束日期", value=s_max, min_value=s_min, max_value=s_max)
        with c6:
            bias_high = st.slider("高位套利點 (%)", 10, 60, 30)
        with c7:
            bias_low = st.slider("低位抄底點 (%)", -50, -5, -20)
    else:
        st.error("找不到資料檔案"); st.stop()

    btn_run = st.button("啟動多策略比較回測 🚀", use_container_width=True, type="primary")

###############################################################
# 4. 核心計算邏輯
###############################################################
if btn_run:
    df = df_raw.loc[pd.to_datetime(start_d)-dt.timedelta(days=365):pd.to_datetime(end_d)].copy()
    df["MA_200"] = df["Price"].rolling(WINDOW).mean()
    df["Bias_200"] = (df["Price"] - df["MA_200"]) / df["MA_200"] * 100
    df = df.dropna(subset=["MA_200"]).loc[pd.to_datetime(start_d):pd.to_datetime(end_d)]

    # --- 策略狀態機判斷 ---
    h_lrs = []      # 標準 LRS 倉位
    h_bias = []     # LRS + 乖離套利倉位
    bias_state = "normal" # 狀態：normal, high_lock (高位鎖定空手中)
    
    current_pos_lrs = 1 if "全倉" in pos_init else 0
    current_pos_bias = 1 if "全倉" in pos_init else 0

    for i in range(len(df)):
        p = df["Price"].iloc[i]; ma = df["MA_200"].iloc[i]; bias = df["Bias_200"].iloc[i]
        
        # 1. 標準 LRS 邏輯
        current_pos_lrs = 1 if p > ma else 0
        h_lrs.append(current_pos_lrs)

        # 2. LRS + 乖離套利 (狀態機版)
        if bias > bias_high:
            bias_state = "high_lock"
            current_pos_bias = 0
        elif bias < bias_low:
            bias_state = "normal"
            current_pos_bias = 1
        elif bias_state == "high_lock":
            # ✨ 關鍵：如果處於高位鎖定，必須等乖離率回落到 0 (回到均線) 或是 趨勢轉空 才能解除鎖定
            if bias <= 0 or p < ma:
                bias_state = "normal"
                current_pos_bias = 1 if p > ma else 0
            else:
                current_pos_bias = 0 # 繼續鎖定空手，曲線會變水平
        else:
            # 正常 LRS 邏輯
            current_pos_bias = 1 if p > ma else 0
            
        h_bias.append(current_pos_bias)

    df["Pos_LRS"] = h_lrs
    df["Pos_Bias"] = h_bias
    
    # 績效計算
    ret = df["Price"].pct_change().fillna(0)
    df["Eq_BH"] = (1 + ret).cumprod() # 買進持有
    
    # 策略跑法 (今天收盤決定，明天生效)
    def calc_equity(pos_series):
        eq = [1.0]
        for i in range(1, len(df)):
            r = (df["Price"].iloc[i] / df["Price"].iloc[i-1]) if pos_series.iloc[i-1] == 1 else 1.0
            eq.append(eq[-1] * r)
        return eq

    df["Eq_LRS"] = calc_equity(df["Pos_LRS"])
    df["Eq_Bias"] = calc_equity(df["Pos_Bias"])

    ###############################################################
    # 5. 圖表呈現
    ###############################################################
    
    # 圖一：乖離率與價格對照 (驗證用)
    st.divider()
    st.subheader("🎯 歷史乖離率與價格監測")
    fig_bias = go.Figure()
    fig_bias.add_trace(go.Scatter(x=df.index, y=df["Bias_200"], name="乖離率 (%)", fill='tozeroy', fillcolor='rgba(100, 149, 237, 0.1)', yaxis="y1"))
    fig_bias.add_trace(go.Scatter(x=df.index, y=df["Price"], name="價格", line=dict(color='#FF8C00'), yaxis="y2"))
    fig_bias.add_hline(y=bias_high, line_dash="dash", line_color="red", annotation_text="高位套利界線")
    fig_bias.update_layout(height=400, template="plotly_white", yaxis=dict(ticksuffix="%"), yaxis2=dict(overlaying="y", side="right", showgrid=False))
    st.plotly_chart(fig_bias, use_container_width=True)

    # 圖二：三線績效比較 (重點在看水平線)
    st.subheader("💰 三策略累積報酬率比較 (%)")
    fig_p = go.Figure()
    fig_p.add_trace(go.Scatter(x=df.index, y=df["Eq_BH"]-1, name="買入持有", line=dict(color="silver")))
    fig_p.add_trace(go.Scatter(x=df.index, y=df["Eq_LRS"]-1, name="標準 LRS", line=dict(color="#C084FC", dash="dash")))
    fig_p.add_trace(go.Scatter(x=df.index, y=df["Eq_Bias"]-1, name="LRS + 乖離套利", line=dict(color="#7C3AED", width=3)))
    fig_p.update_layout(height=500, template="plotly_white", yaxis_tickformat=".1%", hovermode="x unified")
    st.plotly_chart(fig_p, use_container_width=True)

    # 績效總結表
    def mdd(eq): return (1 - eq / eq.cummax()).max()
    res = {
        "策略名稱": ["買進持有", "標準 LRS", "LRS + 乖離套利"],
        "總報酬": [f"{(df['Eq_BH'].iloc[-1]-1):.2%}", f"{(df['Eq_LRS'].iloc[-1]-1):.2%}", f"{(df['Eq_Bias'].iloc[-1]-1):.2%}"],
        "最大回撤": [f"{mdd(df['Eq_BH']):.2%}", f"{mdd(df['Eq_LRS']):.2%}", f"{mdd(df['Eq_Bias']):.2%}"],
        "最終資產": [f"{df['Eq_BH'].iloc[-1]*capital:,.0f}", f"{df['Eq_LRS'].iloc[-1]*capital:,.0f}", f"{df['Eq_Bias'].iloc[-1]*capital:,.0f}"]
    }
    st.table(pd.DataFrame(res))
