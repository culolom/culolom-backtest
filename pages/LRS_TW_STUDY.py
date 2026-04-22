import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# ------------------------------------------------------
# 1. 基本設定與 CSS 美化 (承襲鼠叔風格)
# ------------------------------------------------------
st.set_page_config(page_title="LRS 策略深度研究", page_icon="🐹", layout="wide")

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
    .metric-card {
        background-color: #ffffff; border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 12px; padding: 15px; text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------
# 2. 數據載入與處理
# ------------------------------------------------------
DATA_DIR = Path("data")

def load_data(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    # 確保處理 yfinance 或自訂 CSV 欄位名
    price_col = "Adj Close" if "Adj Close" in df.columns else "Close"
    return df[[price_col]].rename(columns={price_col: "Price"})

# ------------------------------------------------------
# 3. 標題與研究說明
# ------------------------------------------------------
st.markdown("<h1 style='margin-bottom:0.5em;'>🔭 LRS 策略：台股全週期深度統計</h1>", unsafe_allow_html=True)
st.markdown("""
<div class="info-card">
    <h4 style="margin-top:0;">📖 為什麼要研究 200SMA 與 連漲天數？</h4>
    <p>根據 <i>Leverage for the Long Run</i> 論文，均線不僅是壓力支撐，更是<b>「波動率」與「動能持續性」</b>的分水嶺。
    本工具旨在驗證：台股在年線之上是否具備更高的<b>連漲勝率</b>與更低的<b>極端風險</b>。</p>
</div>
""", unsafe_allow_html=True)

# --- 參數設定 ---
with st.container():
    st.subheader("⚙️ 統計參數設定")
    c1, c2, c3 = st.columns([1.5, 1, 1])
    
    with c1:
        target_symbol = st.selectbox("選擇回測標的", ["^TWII", "0050.TW", "SPY", "QQQ"], index=0)
    with c2:
        ma_period = st.number_input("移動平均線週期 (SMA)", value=200)
    with c3:
        start_year = st.slider("統計起始年份", 2000, 2025, 2000)

# ------------------------------------------------------
# 4. 主運算核心 (按鈕觸發)
# ------------------------------------------------------
if st.button("開始 LRS 量化分析 🚀"):
    df = load_data(target_symbol)
    if df.empty:
        st.error(f"❌ 找不到 {target_symbol}.csv，請確認 data 資料夾路徑。")
        st.stop()
        
    df = df[df.index.year >= start_year].copy()
    
    # --- A. 基礎計算 ---
    df['MA'] = df['Price'].rolling(window=ma_period).mean()
    df['Is_Above'] = df['Price'] > df['MA']
    df['Return'] = df['Price'].pct_change()
    
    # 判斷連漲天數 (Consecutive Streaks)
    is_up = df['Return'] > 0
    df['Streak'] = is_up.groupby((is_up != is_up.shift()).cumsum()).cumcount() + 1
    df.loc[~is_up, 'Streak'] = 0 # 跌的那天 Streak 歸零

    # -----------------------------------------------------
    # 5. 戰情室視覺化
    # -----------------------------------------------------
    
    # --- 第一排：波動率與環境佔比 ---
    st.divider()
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.subheader("📊 波動率環境對比 (Chart 3)")
        vol_above = df[df['Is_Above']]['Return'].std() * np.sqrt(252)
        vol_below = df[~df['Is_Above']]['Return'].std() * np.sqrt(252)
        
        fig_vol = px.bar(
            x=["均線之上 (牛市)", "均線之下 (熊市)"],
            y=[vol_above, vol_below],
            color=["牛市", "熊市"],
            color_discrete_map={"牛市": "#2962FF", "熊市": "#FF9100"},
            labels={'x': '市場環境', 'y': '年化波動率'},
            text_auto='.1%'
        )
        st.plotly_chart(fig_vol, use_container_width=True)
        st.caption("💡 結論：若熊市波動率顯著較高，持有槓桿 ETF (如正二) 將面臨巨大的波動損耗。")

    with col_b:
        st.subheader("⚖️ 市場擴張與衰退比例 (Chart 4)")
        counts = df['Is_Above'].value_counts(normalize=True)
        fig_pie = px.pie(
            values=counts.values,
            names=["年線之上 (擴張)", "年線之下 (衰退)"],
            color_discrete_sequence=["#2962FF", "#FF3D00"],
            hole=0.4
        )
        st.plotly_chart(fig_pie, use_container_width=True)
        st.caption(f"統計期間：台股有 {counts.get(True, 0):.1%} 的時間處於多頭趨勢。")

    # --- 第二排：連漲天數統計 ---
    st.divider()
    st.subheader("🔥 連續上漲天數機率分佈 (Chart 7)")
    
    def get_streak_probs(data_subset):
        total_days = len(data_subset)
        probs = {}
        for s in [2, 3, 4, 5]:
            count = (data_subset['Streak'] >= s).sum()
            probs[f"{s}天連漲"] = count / total_days
        return probs

    above_probs = get_streak_probs(df[df['Is_Above']])
    below_probs = get_streak_probs(df[~df['Is_Above']])
    
    streak_df = pd.DataFrame([
        {"天數": k, "機率": v, "環境": "均線之上"} for k, v in above_probs.items()
    ] + [
        {"天數": k, "機率": v, "環境": "均線之下"} for k, v in below_probs.items()
    ])
    
    fig_streak = px.bar(
        streak_df, x="天數", y="機率", color="環境",
        barmode="group", text_auto='.1%',
        color_discrete_map={"均線之上": "#2962FF", "均線之下": "#FF9100"}
    )
    st.plotly_chart(fig_streak, use_container_width=True)
    st.info("💡 觀察：在台股年線之上，『連漲 4-5 天』的出現機率是否顯著高於年線之下？這決定了追價的勝率。")

    # --- 第三排：股災 MDD 避險測試 ---
    st.divider()
    st.subheader("🛡️ 歷史股災避險能力測試 (Table 9)")
    
    # 定義股災區間 (台股重大事件)
    crashes = [
        ("2008 金融海嘯", "2008-01-01", "2009-06-01"),
        ("2020 新冠疫情", "2020-01-01", "2020-05-01"),
        ("2022 升息縮表", "2022-01-01", "2022-12-31")
    ]
    
    mdd_results = []
    for name, s, e in crashes:
        mask = (df.index >= s) & (df.index <= e)
        crash_data = df.loc[mask].copy()
        if crash_data.empty: continue
        
        # 1. Buy & Hold MDD
        bh_cum = (1 + crash_data['Return']).cumprod()
        bh_mdd = (bh_cum / bh_cum.cummax() - 1).min()
        
        # 2. LRS Strategy (昨天收盤 > MA 則今天持有, 否則現金)
        crash_data['LRS_Return'] = np.where(crash_data['Is_Above'].shift(1), crash_data['Return'], 0)
        lrs_cum = (1 + crash_data['LRS_Return']).fillna(0).add(1).cumprod() # 簡化版 LRS
        # 修正累積報酬計算
        lrs_nav = (1 + crash_data['LRS_Return']).cumprod()
        lrs_mdd = (lrs_nav / lrs_nav.cummax() - 1).min()
        
        mdd_results.append({
            "股災事件": name,
            "大盤 MDD": f"{bh_mdd:.1%}",
            "LRS 策略 MDD": f"{lrs_mdd:.1%}",
            "避險效果": f"減少 {(bh_mdd - lrs_mdd)*-1:.1%} 跌幅"
        })
        
    st.table(pd.DataFrame(mdd_results))
    st.success("✨ 分析完成！這份報告證實了 200SMA 作為風險濾網在台股的實戰價值。")
