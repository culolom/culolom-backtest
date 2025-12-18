import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# --- 1. 頁面設定與 Sidebar ---
st.set_page_config(page_title="0050LRS 策略對照系統", page_icon="📈", layout="wide")

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
# 3. 主頁面：回測條件設定 (主畫面佈局)
###############################################################
st.markdown("<h1 style='text-align: center;'>📊 三策略績效對照 (趨勢 vs 抄底套利)</h1>", unsafe_allow_html=True)

with st.container(border=True):
    st.subheader("⚙️ 核心回測條件")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        target_label = st.selectbox("選擇回測標的", list(ETFS.keys()), index=2)
        target_symbol = ETFS[target_label]
    with c2:
        capital = st.number_input("投入本金 (元)", 1000, 10_000_000, 100_000)
    with c3:
        pos_init = st.radio("初始狀態", ["一開始就全倉", "空手起跑"], horizontal=True, index=0)

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

    btn_run = st.button("啟動回測 🚀", use_container_width=True, type="primary")

###############################################################
# 4. 核心計算邏輯
###############################################################
if btn_run:
    # 準備資料
    df = df_raw.loc[pd.to_datetime(start_d)-dt.timedelta(days=365):pd.to_datetime(end_d)].copy()
    df["MA_200"] = df["Price"].rolling(WINDOW).mean()
    df["Bias_200"] = (df["Price"] - df["MA_200"]) / df["MA_200"] * 100
    df = df.dropna(subset=["MA_200"]).loc[pd.to_datetime(start_d):pd.to_datetime(end_d)]

    # --- 策略並行計算 ---
    h_lrs = []      # 策略1：標準 LRS
    h_bias = []     # 策略2：LRS + 乖離套利
    bias_state = "normal"
    
    # 初始化狀態 (尊重使用者選擇)
    start_pos = 1 if "全倉" in pos_init else 0
    curr_lrs = start_pos
    curr_bias = start_pos

    for i in range(len(df)):
        p = df["Price"].iloc[i]; ma = df["MA_200"].iloc[i]; b = df["Bias_200"].iloc[i]
        
        # A. 標準 LRS 計算
        curr_lrs = 1 if p > ma else 0
        h_lrs.append(curr_lrs)

        # B. LRS + 乖離套利計算 (狀態機邏輯)
        if b > bias_high:
            bias_state = "high_lock"
            curr_bias = 0
        elif b < bias_low:
            bias_state = "normal"
            curr_bias = 1
        elif bias_state == "high_lock":
            # 必須等乖離回落到 0% 以下或趨勢轉空才買回
            if b <= 0 or p < ma:
                bias_state = "normal"
                curr_bias = 1 if p > ma else 0
            else:
                curr_bias = 0 # ✨ 關鍵：這裡會產生水平線
        else:
            curr_bias = 1 if p > ma else 0
        h_bias.append(curr_bias)

    df["Pos_LRS"] = h_lrs
    df["Pos_Bias"] = h_bias
    
    # 績效計算 (D-1 訊號，D 漲跌)
    def calc_eq(pos_list):
        eq = [1.0]
        for j in range(1, len(df)):
            ret = (df["Price"].iloc[j] / df["Price"].iloc[j-1]) if pos_list[j-1] == 1 else 1.0
            eq.append(eq[-1] * ret)
        return eq

    df["Eq_BH"] = (df["Price"] / df["Price"].iloc[0]) # 買進持有
    df["Eq_LRS"] = calc_eq(df["Pos_LRS"])
    df["Eq_Bias"] = calc_eq(df["Pos_Bias"])

    ###############################################################
    # 5. 圖表呈現
    ###############################################################
    
    # 圖一：乖離率監控 (補上抄底線與賣出標記)
    st.divider()
    st.subheader("🎯 乖離率監測與策略執行界線")
    fig_bias = go.Figure()
    fig_bias.add_trace(go.Scatter(x=df.index, y=df["Bias_200"], name="乖離率 (%)", fill='tozeroy', fillcolor='rgba(100, 149, 237, 0.1)'))
    fig_bias.add_hline(y=bias_high, line_dash="dash", line_color="#FF3E3E", annotation_text="高位套利界線")
    fig_bias.add_hline(y=bias_low, line_dash="dash", line_color="#21C354", annotation_text="低位抄底界線")
    fig_bias.update_layout(height=350, template="plotly_white", yaxis=dict(ticksuffix="%"))
    st.plotly_chart(fig_bias, use_container_width=True)

    # 圖二：三策略資金曲線比較 (這張最重要，看水平線)
    st.subheader("💰 三策略累積報酬率比較 (%)")
    fig_e = go.Figure()
    fig_e.add_trace(go.Scatter(x=df.index, y=df["Eq_BH"]-1, name="買入持有 (B&H)", line=dict(color="silver")))
    fig_e.add_trace(go.Scatter(x=df.index, y=df["Eq_LRS"]-1, name="標準 LRS (均線)", line=dict(color="#C084FC", dash="dash")))
    fig_e.add_trace(go.Scatter(x=df.index, y=df["Eq_Bias"]-1, name="LRS + 乖離套利", line=dict(color="#7C3AED", width=3)))
    
    # 標註買賣訊號點 (僅針對 Bias 策略)
    df["Sig_Diff"] = df["Pos_Bias"].diff()
    buys = df[df["Sig_Diff"] == 1]
    sells = df[df["Sig_Diff"] == -1]
    fig_e.add_trace(go.Scatter(x=buys.index, y=df.loc[buys.index, "Eq_Bias"]-1, mode="markers", name="買進點", marker=dict(symbol="triangle-up", size=10, color="green")))
    fig_e.add_trace(go.Scatter(x=sells.index, y=df.loc[sells.index, "Eq_Bias"]-1, mode="markers", name="賣出點", marker=dict(symbol="triangle-down", size=10, color="red")))

    fig_e.update_layout(height=500, template="plotly_white", yaxis_tickformat=".1%", hovermode="x unified")
    st.plotly_chart(fig_e, use_container_width=True)

    # 績效總結
    def get_mdd(eq): return (1 - eq / eq.cummax()).max()
    res_data = {
        "策略名稱": ["買進持有", "標準 LRS", "LRS + 乖離套利"],
        "總報酬率": [f"{(df['Eq_BH'].iloc[-1]-1):.2%}", f"{(df['Eq_LRS'].iloc[-1]-1):.2%}", f"{(df['Eq_Bias'].iloc[-1]-1):.2%}"],
        "最大回撤 (MDD)": [f"{get_mdd(df['Eq_BH']):.2%}", f"{get_mdd(df['Eq_LRS']):.2%}", f"{get_mdd(df['Eq_Bias']):.2%}"],
        "期末淨資產": [f"{df['Eq_BH'].iloc[-1]*capital:,.0f}", f"{df['Eq_LRS'].iloc[-1]*capital:,.0f}", f"{df['Eq_Bias'].iloc[-1]*capital:,.0f}"]
    }
    st.table(pd.DataFrame(res_data))
