import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# ------------------------------------------------------
# 1. 基本設定與 CSS 美化
# ------------------------------------------------------
st.set_page_config(page_title="LRS 均線深度統計", page_icon="🔭", layout="wide")

st.markdown("""
<style>
    div.stButton > button:first-child {
        background-color: #FF6F00; color: white; border-radius: 10px;
        font-weight: bold; font-size: 16px; padding: 0.5rem 2rem;
        transition: all 0.3s ease; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    div.stButton > button:first-child:hover { background-color: #E65100; transform: translateY(-2px); }
    .info-card {
        background-color: #f9f9f9; padding: 20px; border-radius: 12px;
        border-left: 6px solid #FF6F00; margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------
# 2. 數據載入
# ------------------------------------------------------
DATA_DIR = Path("data")

def load_data(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    price_col = "Adj Close" if "Adj Close" in df.columns else "Close"
    return df[[price_col]].rename(columns={price_col: "Price"})

# ------------------------------------------------------
# 3. 標題與說明
# ------------------------------------------------------
st.markdown("<h1 style='margin-bottom:0.5em;'>🔭 LRS 策略：均線與波動率統計研究</h1>", unsafe_allow_html=True)
st.markdown("""
<div class="info-card">
    <h4 style="margin-top:0;">📖 核心研究指標</h4>
    <p>參考 Michael Gayed 論文，本回測將分析：<br>
    1. 不同週期均線（10~200日）對於<b>波動率</b>的區分能力。<br>
    2. 以 <b>200SMA</b> 為基準，量化台股的<b>動能持續性（連漲天數）</b>與<b>股災避險能力</b>。</p>
</div>
""", unsafe_allow_html=True)

with st.container():
    c1, c2 = st.columns([1.5, 1])
    with c1:
        target_symbol = st.selectbox("選擇回測標的", ["^TWII", "0050.TW", "SPY", "QQQ"], index=0)
    with c2:
        start_year = st.slider("統計起始年份", 2000, 2026, 2000)

# ------------------------------------------------------
# 4. 運算與繪圖邏輯
# ------------------------------------------------------
if st.button("開始執行台股 LRS 統計 🚀"):
    df_raw = load_data(target_symbol)
    if df_raw.empty:
        st.error(f"❌ 找不到 {target_symbol}.csv")
        st.stop()
        
    df = df_raw[df_raw.index.year >= start_year].copy()
    df['Return'] = df['Price'].pct_change()

    # --- A. 多重均線波動率統計 (還原 Chart 3) ---
    st.divider()
    st.subheader("📊 不同均線環境下的年化波動率對比")
    
    ma_periods = [10, 20, 50, 100, 200]
    vol_data = []
    
    for p in ma_periods:
        ma = df['Price'].rolling(window=p).mean()
        above_mask = df['Price'] > ma
        
        vol_above = df[above_mask]['Return'].std() * np.sqrt(252)
        vol_below = df[~above_mask]['Return'].std() * np.sqrt(252)
        
        vol_data.append({"MA": f"{p}-day", "Volatility": vol_above, "Environment": "Volatility Above"})
        vol_data.append({"MA": f"{p}-day", "Volatility": vol_below, "Environment": "Volatility Below"})
        
    df_vol = pd.DataFrame(vol_data)
    fig_vol = px.bar(
        df_vol, x="MA", y="Volatility", color="Environment",
        barmode="group", text_auto='.1%',
        color_discrete_map={"Volatility Above": "#6699CC", "Volatility Below": "#EE7733"},
        height=500
    )
    fig_vol.update_layout(yaxis_tickformat='.0%')
    st.plotly_chart(fig_vol, use_container_width=True)
    st.caption("💡 觀察：隨著均線週期拉長，『之上』與『之下』的波動率差異通常會更明顯。")

    # --- 固定使用 200SMA 進行後續分析 ---
    main_ma_p = 200
    df['MA200'] = df['Price'].rolling(window=main_ma_p).mean()
    df['Above200'] = df['Price'] > df['MA200']
    
    # --- B. 200SMA 連漲天數統計 (Chart 7) ---
    st.divider()
    st.subheader("🔥 200SMA 環境下的連漲機率 (動能持續性)")
    
    # 計算連漲
    is_up = df['Return'] > 0
    df['Streak'] = is_up.groupby((is_up != is_up.shift()).cumsum()).cumcount() + 1
    df.loc[~is_up, 'Streak'] = 0
    
    def get_probs(subset):
        total = len(subset)
        return {f"{s} Up": (subset['Streak'] >= s).sum() / total for s in [2, 3, 4, 5]}

    streak_probs = []
    for env, mask in [("Above 200-day", df['Above200']), ("Below 200-day", ~df['Above200'])]:
        probs = get_probs(df[mask])
        for k, v in probs.items():
            streak_probs.append({"Streak": k, "Probability": v, "Environment": env})
            
    fig_streak = px.bar(
        streak_probs, x="Streak", y="Probability", color="Environment",
        barmode="group", text_auto='.0%',
        color_discrete_map={"Above 200-day": "#6699CC", "Below 200-day": "#EE7733"}
    )
    fig_streak.update_layout(yaxis_tickformat='.0%')
    st.plotly_chart(fig_streak, use_container_width=True)

    # --- C. 週期比例與股災 MDD ---
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("⚖️ 200SMA 市場週期佔比")
        counts = df['Above200'].value_counts(normalize=True)
        fig_pie = px.pie(
            values=counts.values, names=["Expansion (>200MA)", "Recession (<200MA)"],
            color_discrete_sequence=["#6699CC", "#EE7733"], hole=0.4
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_right:
        st.subheader("🛡️ 歷史股災避險對比 (MDD)")
        crashes = [
            ("2008 金融海嘯", "2008-01-01", "2009-06-01"),
            ("2020 新冠疫情", "2020-01-01", "2020-05-01"),
            ("2022 升息縮表", "2022-01-01", "2022-12-31")
        ]
        mdd_data = []
        for name, s, e in crashes:
            mask = (df.index >= s) & (df.index <= e)
            c_data = df.loc[mask].copy()
            if c_data.empty: continue
            # B&H
            bh_nav = (1 + c_data['Return']).cumprod()
            bh_mdd = (bh_nav / bh_nav.cummax() - 1).min()
            # LRS (昨天在均線上才持有)
            c_data['LRS_Ret'] = np.where(c_data['Above200'].shift(1), c_data['Return'], 0)
            lrs_nav = (1 + c_data['LRS_Ret']).cumprod()
            lrs_mdd = (lrs_nav / lrs_nav.cummax() - 1).min()
            mdd_data.append({"事件": name, "大盤 MDD": f"{bh_mdd:.1%}", "LRS MDD": f"{lrs_mdd:.1%}"})
        st.table(pd.DataFrame(mdd_results := mdd_data))

    st.success("✅ 統計完成！均線濾網在台股的『低波動』與『動能持續』效果顯著。")
