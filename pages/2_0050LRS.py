import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path

# --- 1. 頁面設定 ---
st.set_page_config(page_title="0050LRS 進階戰情室", page_icon="📈", layout="wide")

with st.sidebar:
    st.markdown("### 🚀 導覽")
    st.page_link("Home.py", label="回到首頁", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")

# --- 2. 資料處理 ---
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

###############################################################
# 3. 主頁面：回測條件設定
###############################################################
st.markdown("<h1 style='text-align: center;'>📊 0050LRS + 乖離套利 (修正起始邏輯版)</h1>", unsafe_allow_html=True)

with st.container(border=True):
    st.subheader("⚙️ 核心回測條件")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        target_label = st.selectbox("選擇回測標的", list(ETFS.keys()), index=2)
        target_symbol = ETFS[target_label]
    with c2:
        capital = st.number_input("投入本金 (元)", 1000, 10_000_000, 100_000)
    with c3:
        # 初始狀態設定
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
    df = df_raw.loc[pd.to_datetime(start_d)-dt.timedelta(days=365):pd.to_datetime(end_d)].copy()
    df["MA_200"] = df["Price"].rolling(WINDOW).mean()
    df["Bias_200"] = (df["Price"] - df["MA_200"]) / df["MA_200"] * 100
    df = df.dropna(subset=["MA_200"]).loc[pd.to_datetime(start_d):pd.to_datetime(end_d)]

    # --- 狀態機與訊號紀錄 ---
    h_bias_pos = []
    signals = [] 
    bias_state = "normal"
    
    # 初始化：第一天尊重使用者設定
    current_pos = 1 if "全倉" in pos_init else 0
    
    for i in range(len(df)):
        p = df["Price"].iloc[i]
        ma = df["MA_200"].iloc[i]
        bias = df["Bias_200"].iloc[i]
        date = df.index[i]
        
        last_pos = current_pos
        sig_type = None

        # ✨ 修正點：第一天不進行策略判斷，直接沿用初始設定
        if i == 0:
            h_bias_pos.append(current_pos)
            continue

        # 狀態機判斷 (從第二天開始)
        if bias > bias_high:
            bias_state = "high_lock"
            current_pos = 0
            if last_pos == 1: sig_type = "乖離套利賣"
        elif bias < bias_low:
            bias_state = "normal"
            current_pos = 1
            if last_pos == 0: sig_type = "乖離抄底買"
        elif bias_state == "high_lock":
            # 必須回落到均線下方或交叉才解除鎖定
            if bias <= 0 or p < ma:
                bias_state = "normal"
                current_pos = 1 if p > ma else 0
                if last_pos == 0 and current_pos == 1: sig_type = "LRS 買進(回歸)"
            else:
                current_pos = 0 
        else:
            # 正常 LRS 邏輯
            current_pos = 1 if p > ma else 0
            if last_pos == 0 and current_pos == 1: sig_type = "LRS 買進"
            elif last_pos == 1 and current_pos == 0: sig_type = "LRS 賣出"
            
        h_bias_pos.append(current_pos)
        if sig_type:
            signals.append({"Date": date, "Price": p, "Type": sig_type})

    df["Pos_Bias"] = h_bias_pos
    df_sig = pd.DataFrame(signals).set_index("Date") if signals else pd.DataFrame()

    # 績效計算
    ret = df["Price"].pct_change().fillna(0)
    df["Eq_BH"] = (1 + ret).cumprod()
    
    eq_bias = [1.0]
    for i in range(1, len(df)):
        r = (df["Price"].iloc[i] / df["Price"].iloc[i-1]) if df["Pos_Bias"].iloc[i-1] == 1 else 1.0
        eq_bias.append(eq_bias[-1] * r)
    df["Eq_Bias"] = eq_bias

    ###############################################################
    # 5. 圖表呈現
    ###############################################################
    
    # 圖一：乖離率監控 (補上抄底線與標註)
    st.divider()
    st.subheader("🎯 乖離率監測 (含高位套利/低位抄底)")
    fig_bias = go.Figure()
    fig_bias.add_trace(go.Scatter(x=df.index, y=df["Bias_200"], name="乖離率 (%)", fill='tozeroy', fillcolor='rgba(100, 149, 237, 0.1)'))
    fig_bias.add_hline(y=bias_high, line_dash="dash", line_color="#FF3E3E", annotation_text="高位套利界線")
    fig_bias.add_hline(y=bias_low, line_dash="dash", line_color="#21C354", annotation_text="低位抄底界線") # ✨ 補上抄底線
    fig_bias.update_layout(height=350, template="plotly_white", yaxis=dict(ticksuffix="%"))
    st.plotly_chart(fig_bias, use_container_width=True)

    # 圖二：價格與訊號標記 (補上三角形圖示)
    st.subheader("📌 價格走勢與執行標記")
    fig_p = go.Figure()
    fig_p.add_trace(go.Scatter(x=df.index, y=df["Price"], name="價格", line=dict(color='#FF8C00')))
    fig_p.add_trace(go.Scatter(x=df.index, y=df["MA_200"], name="200SMA", line=dict(color='silver', dash='dash')))
    
    # ✨ 補上買賣圖示
    if not df_sig.empty:
        buys = df_sig[df_sig["Type"].str.contains("買")]
        sells = df_sig[df_sig["Type"].str.contains("賣")]
        
        fig_p.add_trace(go.Scatter(x=buys.index, y=buys["Price"], mode="markers", name="買進訊號",
                                 marker=dict(symbol="triangle-up", size=12, color="#21C354"),
                                 hovertemplate="日期: %{x}<br>類型: %{text}", text=buys["Type"]))
        
        fig_p.add_trace(go.Scatter(x=sells.index, y=sells["Price"], mode="markers", name="賣出訊號",
                                 marker=dict(symbol="triangle-down", size=12, color="#FF3E3E"),
                                 hovertemplate="日期: %{x}<br>類型: %{text}", text=sells["Type"]))
    
    fig_p.update_layout(height=450, template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig_p, use_container_width=True)

    # 圖三：累積報酬率
    st.subheader("💰 累積報酬率比較 (%)")
    fig_e = go.Figure()
    fig_e.add_trace(go.Scatter(x=df.index, y=df["Eq_BH"]-1, name="買入持有", line=dict(color="silver")))
    fig_e.add_trace(go.Scatter(x=df.index, y=df["Eq_Bias"]-1, name="LRS + 乖離套利", line=dict(color="#7C3AED", width=3)))
    fig_e.update_layout(height=450, template="plotly_white", yaxis_tickformat=".1%", hovermode="x unified")
    st.plotly_chart(fig_e, use_container_width=True)

    st.success(f"回測完成！初始狀態：{pos_init}。第一天 (2020-12-18) 的乖離率約為 {df['Bias_200'].iloc[0]:.2f}%。")
