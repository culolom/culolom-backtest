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
    /* 1. 全局橘色按鈕樣式 */
    div.stButton > button:first-child {
        background-color: #FF6F00; /* 鮮豔橘 */
        color: white;
        border-radius: 10px;
        border: none;
        font-weight: bold;
        font-size: 16px;
        padding: 0.5rem 2rem;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    div.stButton > button:first-child:hover {
        background-color: #E65100; /* 深橘色 hover */
        box-shadow: 0 6px 8px rgba(0,0,0,0.2);
        transform: translateY(-2px);
    }
    
    /* 2. 資訊卡片樣式 */
    .info-card {
        background-color: #f9f9f9;
        padding: 20px;
        border-radius: 12px;
        border-left: 6px solid #FF6F00; /* 左側橘色強調線 */
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        margin-bottom: 25px;
    }
    
    /* 3. Slider 顏色自訂 (簡化版) */
    .stSlider > div > div > div > div {
        background-color: #FF6F00;
    }
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
# 4. 主畫面：參數設定與說明
###############################################################

st.markdown("<h1 style='margin-bottom:0.5em;'>🔭 LRS 策略：台股全維度量化戰情室</h1>", unsafe_allow_html=True)

st.markdown("""
<div class="info-card">
    <h4 style="margin-top:0;">📖 鼠叔量化研究筆記</h4>
    <p style="font-size:1.05em; line-height:1.6;">
        本研究基於經典論文《Leverage for the Long Run》，探討 <b>均線環境</b> 如何決定投資勝率。<br>
        我們將分析：(1) 不同均線對波動率的區隔 (2) 連漲天數機率 (3) 週期佔比 (4) 歷史避險效果。<br>
        <span style="color:#FF6F00; font-weight:bold;">數據核心：避開年線下的高波動，擁抱年線上的正複利。</span>
    </p>
</div>
""", unsafe_allow_html=True)

# --- ⚙️ 全域參數設定區 (置於主畫面) ---
st.markdown("### ⚙️ 全域參數設定")
col_p1, col_p2 = st.columns([1, 1.5])

# 名稱對照表
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

st.write("") # 留白

# --- 開始按鈕 ---
if st.button("開始執行量化分析 🚀"):
    df_raw = load_data(target_symbol)
    if df_raw.empty:
        st.error(f"❌ 找不到 `data/{target_symbol}.csv` 檔案。")
        st.stop()
        
    df = df_raw[df_raw.index.year >= start_year].copy()
    df['Return'] = df['Price'].pct_change()

    # --- 區塊 1: 不同均線波動率對比 (Chart 3) ---
    st.divider()
    st.subheader(f"📊 {selected_name}：不同週期均線之波動率對比")
    ma_periods = [10, 20, 50, 100, 200]
    vol_results = []
    for p in ma_periods:
        ma = df['Price'].rolling(window=p).mean()
        above = df['Price'] > ma
        vol_above = df[above]['Return'].std() * np.sqrt(252)
        vol_below = df[~above]['Return'].std() * np.sqrt(252)
        vol_results.append({"MA": f"{p}-day", "Volatility": vol_above, "Env": "Volatility Above"})
        vol_results.append({"MA": f"{p}-day", "Volatility": vol_below, "Env": "Volatility Below"})
        
    fig_vol = px.bar(pd.DataFrame(vol_results), x="MA", y="Volatility", color="Env",
                     barmode="group", text_auto='.1%',
                     color_discrete_map={"Volatility Above": "#6699CC", "Volatility Below": "#EE7733"})
    fig_vol.update_layout(yaxis_tickformat='.0%', height=450)
    st.plotly_chart(fig_vol, use_container_width=True)

    # --- 區塊 2: 200SMA 連漲天數與市場佔比 (Bar Chart 版) ---
    df['MA200'] = df['Price'].rolling(window=200).mean()
    df['Above200'] = df['Price'] > df['MA200']
    
    is_up = df['Return'] > 0
    df['Streak'] = is_up.groupby((is_up != is_up.shift()).cumsum()).cumcount() + 1
    df.loc[~is_up, 'Streak'] = 0
    
    col_l, col_r = st.columns([1.8, 1.2])
    
    with col_l:
        st.subheader("🔥 200SMA 環境下的連漲機率 (動能持續性)")
        def get_probs(subset):
            total = len(subset)
            return {f"{s}天連漲": (subset['Streak'] >= s).sum() / total for s in [2, 3, 4, 5]}
        
        s_above = get_probs(df[df['Above200']])
        s_below = get_probs(df[~df['Above200']])
        streak_df = pd.DataFrame([{"Streak": k, "Prob": v, "Env": "均線之上 (Above)"} for k, v in s_above.items()] + 
                                 [{"Streak": k, "Prob": v, "Env": "均線之下 (Below)"} for k, v in s_below.items()])
        fig_streak = px.bar(streak_df, x="Streak", y="Prob", color="Env", barmode="group", text_auto='.1%',
                            color_discrete_map={"均線之上 (Above)": "#6699CC", "均線之下 (Below)": "#EE7733"})
        fig_streak.update_layout(yaxis_tickformat='.0%', height=400)
        st.plotly_chart(fig_streak, use_container_width=True)

    with col_r:
        st.subheader("⚖️ 市場週期時間佔比 (對比)")
        counts = df['Above200'].value_counts(normalize=True)
        period_df = pd.DataFrame({
            "環境": ["擴張期 (>200MA)", "衰退期 (<200MA)"],
            "佔比": [counts.get(True, 0), counts.get(False, 0)],
            "Color": ["Expansion", "Recession"]
        })
        fig_cycle = px.bar(period_df, x="環境", y="佔比", color="Color", text_auto='.1%',
                           color_discrete_map={"Expansion": "#6699CC", "Recession": "#EE7733"})
        fig_cycle.update_layout(yaxis_tickformat='.0%', showlegend=False, height=400)
        st.plotly_chart(fig_cycle, use_container_width=True)

    # --- 區塊 3: 滾動回撤對比 (Chart 8) ---
    st.divider()
    st.subheader("🛡️ Chart 8: 歷史滾動回撤對比 (Rolling Drawdown)")
    df['Bench_NAV'] = (1 + df['Return'].fillna(0)).cumprod()
    df['LRS_Ret'] = np.where(df['Above200'].shift(1), df['Return'], 0)
    df['LRS_NAV'] = (1 + df['LRS_Ret'].fillna(0)).cumprod()
    
    def calc_dd(nav): return (nav / nav.cummax()) - 1
    df['Bench_DD'] = calc_dd(df['Bench_NAV'])
    df['LRS_DD'] = calc_dd(df['LRS_NAV'])
    
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['Bench_DD'], name=f"{selected_name} (原汁原味)",
                                line=dict(color='#EE7733', width=1.2), fill='tozeroy', fillcolor='rgba(238,119,51,0.08)'))
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['LRS_DD'], name="LRS 200SMA 策略", line=dict(color='#6699CC', width=2.5)))
    fig_dd.update_layout(yaxis_tickformat='.0%', hovermode="x unified", height=500, margin=dict(l=0,r=0,t=30,b=0))
    fig_dd.update_yaxes(range=[-1, 0.05])
    st.plotly_chart(fig_dd, use_container_width=True)

# --- 區塊 4: 股災統計 (新增 2025 事件) ---
    st.subheader("📋 重大股災避險效果實測 (含 2025 對等關稅股災)")
    crashes = [
        ("2008 金融海嘯", "2008-01-01", "2009-06-30"), 
        ("2020 新冠疫情", "2020-01-01", "2020-04-30"), 
        ("2022 升息縮表", "2022-01-01", "2022-12-31"),
        ("2025 對等關稅股災", "2025-01-01", "2025-12-31") # <--- 新增
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
    
    st.success(f"✨ {selected_name} 全維度量化報告生成完畢！")
else:
    st.info("💡 請在上方選擇標的與年份，並點擊按鈕開始分析。")
