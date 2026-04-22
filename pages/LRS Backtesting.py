import os
import sys
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib
from pathlib import Path

###############################################################
# 1. 環境設定與字型
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

# ★ st.set_page_config 必須是第一個 Streamlit 命令
st.set_page_config(page_title="LRS 策略深度統計", page_icon="📈", layout="wide")

# 🔒 驗證守門員
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except ImportError:
    pass 

# ★★★ CSS 注入區域：定義鼠叔橘視覺風格 ★★★
st.markdown("""
<style>
    div.stButton > button:first-child {
        background-color: #FF6F00; color: white; border-radius: 10px;
        border: none; font-weight: bold; font-size: 16px; padding: 0.5rem 2rem;
        transition: all 0.3s ease; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    div.stButton > button:first-child:hover {
        background-color: #E65100; box-shadow: 0 6px 8px rgba(0,0,0,0.2); transform: translateY(-2px);
    }
    .info-card {
        background-color: #f9f9f9; padding: 20px; border-radius: 12px;
        border-left: 6px solid #FF6F00; box-shadow: 0 2px 5px rgba(0,0,0,0.05); margin-bottom: 25px;
    }
    .stSlider > div > div > div > div { background-color: #FF6F00; }
</style>
""", unsafe_allow_html=True)

###############################################################
# 2. 數據載入邏輯
###############################################################
DATA_DIR = Path("data")

@st.cache_data
def load_data(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    price_col = "Adj Close" if "Adj Close" in df.columns else "Close"
    return df[[price_col]].rename(columns={price_col: "Price"})

###############################################################
# 3. UI 與 Sidebar (快速連結)
###############################################################

with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")
    st.divider()
    st.caption("🐹 倉鼠人生實驗室製作")

###############################################################
# 4. 主畫面內容
###############################################################

st.markdown("<h1 style='margin-bottom:0.5em;'>🔭 LRS 槓桿輪換策略：動能對稱性統計</h1>", unsafe_allow_html=True)

st.markdown("""
<div class="info-card">
    <h4 style="margin-top:0;">📖 鼠叔量化研究筆記：Regime Discovery Index</h4>
    <p style="font-size:1.05em; line-height:1.6;">
        為什麼要在均線之下「空手」？因為數據顯示：<b>環境會改變動能的基因。</b><br>
        均線之上，市場傾向「連漲而不連跌」；均線之下，市場傾向「連跌而不連漲」。<br>
        <span style="color:#FF6F00; font-weight:bold;">本統計將揭露：均線是如何作為「動能之盾 (Momentum Aegis)」，保護你不被連續下跌摧毀。</span>
    </p>
</div>
""", unsafe_allow_html=True)

# --- ⚙️ 全域參數設定 ---
st.markdown("### ⚙️ 全域參數設定")
col_p1, col_p2 = st.columns([1, 1.5])

TICKER_MAPPING = {
    "台灣加權指數": "^TWII",
    "元大台灣50指數ETF": "0050.TW",
    "標普500指數ETF": "SPY",
    "那斯達克100指數ETF": "QQQ"
}

with col_p1:
    selected_name = st.selectbox("選擇回測標的", list(TICKER_MAPPING.keys()), index=0)
    target_symbol = TICKER_MAPPING[selected_name]

with col_p2:
    start_year = st.slider("統計起始年份", 2000, 2026, 2000)

if st.button("開始執行量化分析 🚀"):
    df_raw = load_data(target_symbol)
    if df_raw.empty:
        st.error(f"❌ 找不到 `data/{target_symbol}.csv` 檔案。")
        st.stop()
        
    df = df_raw[df_raw.index.year >= start_year].copy()
    df['Return'] = df['Price'].pct_change()

    # --- 區塊 1: 波動率對比 ---
    st.divider()
    st.subheader(f"📊 {selected_name}：不同週期均線之波動率對比")
    ma_periods = [10, 20, 50, 100, 200]
    vol_results = []
    for p in ma_periods:
        ma = df['Price'].rolling(window=p).mean()
        above = df['Price'] > ma
        vol_above = df[above]['Return'].std() * np.sqrt(252)
        vol_below = df[~above]['Return'].std() * np.sqrt(252)
        vol_results.append({"MA週期": f"{p}日線", "年化波動率": vol_above, "環境": "均線之上 (Above)"})
        vol_results.append({"MA週期": f"{p}日線", "年化波動率": vol_below, "環境": "均線之下 (Below)"})
    
    fig_vol = px.bar(pd.DataFrame(vol_results), x="MA週期", y="年化波動率", color="環境",
                     barmode="group", text_auto='.1%', 
                     color_discrete_map={"均線之上 (Above)": "#6699CC", "均線之下 (Below)": "#EE7733"})
    fig_vol.update_layout(yaxis_tickformat='.0%', height=400)
    st.plotly_chart(fig_vol, use_container_width=True)

    # --- 區塊 2: 連漲與連跌機率對比 (核心新增) ---
    st.divider()
    df['MA200'] = df['Price'].rolling(window=200).mean()
    df['Above200'] = df['Price'] > df['MA200']
    
    # 計算連漲
    is_up = df['Return'] > 0
    df['Up_Streak'] = is_up.groupby((is_up != is_up.shift()).cumsum()).cumcount() + 1
    df.loc[~is_up, 'Up_Streak'] = 0
    
    # 計算連跌
    is_down = df['Return'] < 0
    df['Down_Streak'] = is_down.groupby((is_down != is_down.shift()).cumsum()).cumcount() + 1
    df.loc[~is_down, 'Down_Streak'] = 0

    st.subheader("🔥 動能基因測試：200SMA 之連漲與連跌統計")
    col_streak_l, col_streak_r = st.columns(2)

    def get_streak_probs(subset, streak_col):
        total = len(subset)
        return {f"{s}天": (subset[streak_col] >= s).sum() / total for s in [2, 3, 4, 5]}

    with col_streak_l:
        st.markdown("**[正向動能] 連續上漲機率**")
        u_above = get_streak_probs(df[df['Above200']], 'Up_Streak')
        u_below = get_streak_probs(df[~df['Above200']], 'Up_Streak')
        df_u = pd.DataFrame([{"天數": k, "機率": v, "環境": "均線之上 (牛市)"} for k, v in u_above.items()] + 
                            [{"天數": k, "機率": v, "環境": "均線之下 (熊市)"} for k, v in u_below.items()])
        fig_u = px.bar(df_u, x="天數", y="機率", color="環境", barmode="group", text_auto='.1%',
                       color_discrete_map={"均線之上 (牛市)": "#6699CC", "均線之下 (熊市)": "#EE7733"})
        fig_u.update_layout(yaxis_tickformat='.0%', height=350, showlegend=False)
        st.plotly_chart(fig_u, use_container_width=True)
        st.caption("💡 觀察：牛市中連漲 4-5 天的機率是否顯著較高？")

    with col_streak_r:
        st.markdown("**[負向動能] 連續下跌機率**")
        d_above = get_streak_probs(df[df['Above200']], 'Down_Streak')
        d_below = get_streak_probs(df[~df['Above200']], 'Down_Streak')
        df_d = pd.DataFrame([{"天數": k, "機率": v, "環境": "均線之上 (牛市)"} for k, v in d_above.items()] + 
                            [{"天數": k, "機率": v, "環境": "均線之下 (熊市)"} for k, v in d_below.items()])
        fig_d = px.bar(df_d, x="天數", y="機率", color="環境", barmode="group", text_auto='.1%',
                       color_discrete_map={"均線之上 (牛市)": "#6699CC", "均線之下 (熊市)": "#EE7733"})
        fig_d.update_layout(yaxis_tickformat='.0%', height=350)
        st.plotly_chart(fig_d, use_container_width=True)
        st.caption("💡 警告：熊市中連跌 4-5 天的機率通常會大幅飆升！")

    # --- 區塊 3: 市場週期佔比 ---
    st.divider()
    st.subheader("⚖️ 市場週期時間佔比")
    counts = df['Above200'].value_counts(normalize=True)
    period_df = pd.DataFrame({"環境": ["擴張期 (>200MA)", "衰退期 (<200MA)"], "佔比": [counts.get(True, 0), counts.get(False, 0)], "Color": ["Exp", "Rec"]})
    st.plotly_chart(px.bar(period_df, x="環境", y="佔比", color="Color", text_auto='.1%', color_discrete_map={"Exp": "#6699CC", "Rec": "#EE7733"}), use_container_width=True)

    # --- 區塊 4: 滾動回撤 ---
    st.divider()
    st.subheader("🛡️ 歷史滾動回撤對比 (Rolling Drawdown)")
    df['Bench_NAV'] = (1 + df['Return'].fillna(0)).cumprod()
    df['LRS_Ret'] = np.where(df['Above200'].shift(1), df['Return'], 0)
    df['LRS_NAV'] = (1 + df['LRS_Ret'].fillna(0)).cumprod()
    df['Bench_DD'] = (df['Bench_NAV'] / df['Bench_NAV'].cummax()) - 1
    df['LRS_DD'] = (df['LRS_NAV'] / df['LRS_NAV'].cummax()) - 1
    
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['Bench_DD'], name="原汁原味 (B&H)", line=dict(color='#EE7733', width=1.2), fill='tozeroy', fillcolor='rgba(238,119,51,0.08)'))
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['LRS_DD'], name="LRS 200SMA 策略", line=dict(color='#6699CC', width=2.5)))
    fig_dd.update_layout(yaxis_tickformat='.0%', hovermode="x unified", height=500)
    st.plotly_chart(fig_dd, use_container_width=True)

    # --- 區塊 5: 股災統計 ---
    st.subheader("📋 重大股災避險效果實測 (含 2025 對等關稅股災)")
    crashes = [
        ("2008 金融海嘯", "2008-01-01", "2009-06-30"), 
        ("2020 新冠疫情", "2020-01-01", "2020-04-30"), 
        ("2022 升息縮表", "2022-01-01", "2022-12-31"),
        ("2025 對等關稅", "2025-01-01", "2025-12-31")
    ]
    mdd_sum = []
    for name, s, e in crashes:
        mask = (df.index >= s) & (df.index <= e)
        if mask.any():
            sub = df.loc[mask]
            b_mdd = (sub['Bench_NAV'] / sub['Bench_NAV'].cummax() - 1).min()
            l_mdd = (sub['LRS_NAV'] / sub['LRS_NAV'].cummax() - 1).min()
            mdd_sum.append({"歷史股災": name, "大盤 MDD": f"{b_mdd:.1%}", "LRS MDD": f"{l_mdd:.1%}", "避險效果": f"減少 {(b_mdd-l_mdd)*-1:.1%} 跌幅"})
    st.table(pd.DataFrame(mdd_sum))
    st.success("✨ 報告已更新，包含『動能對稱性』連漲連跌統計！")
