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
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="LRS 策略深度統計", page_icon="📈", layout="wide")

# 🔒 驗證守門員
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except ImportError:
    pass 

# ★★★ CSS 注入區域 ★★★
st.markdown("""
<style>
    div.stButton > button:first-child {
        background-color: #FF6F00; color: white; border-radius: 10px;
        border: none; font-weight: bold; font-size: 16px; padding: 0.5rem 2rem;
        transition: all 0.3s ease; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    div.stButton > button:first-child:hover {
        background-color: #E65100; transform: translateY(-2px);
    }
    .info-card {
        background-color: #f9f9f9; padding: 20px; border-radius: 12px;
        border-left: 6px solid #FF6F00; margin-bottom: 25px;
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
# 3. UI 與 Sidebar
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
st.markdown("<h1 style='margin-bottom:0.5em;'>🔭 LRS 槓桿輪換策略：全維度量化報告</h1>", unsafe_allow_html=True)

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

    # --- 區塊 1: 不同週期均線之波動率對比 (補回這張圖) ---
    st.divider()
    st.subheader(f"📊 {selected_name}：不同週期均線之波動率對比")
    ma_periods = [10, 20, 50, 100, 200]
    vol_results = []
    for p in ma_periods:
        ma_tmp = df['Price'].rolling(window=p).mean()
        above_mask = df['Price'] > ma_tmp
        vol_above = df[above_mask]['Return'].std() * np.sqrt(252)
        vol_below = df[~above_mask]['Return'].std() * np.sqrt(252)
        vol_results.append({"MA": f"{p}-day", "Volatility": vol_above, "Env": "Volatility Above"})
        vol_results.append({"MA": f"{p}-day", "Volatility": vol_below, "Env": "Volatility Below"})
        
    fig_vol_multi = px.bar(pd.DataFrame(vol_results), x="MA", y="Volatility", color="Env",
                           barmode="group", text_auto='.1%',
                           color_discrete_map={"Volatility Above": "#6699CC", "Volatility Below": "#EE7733"})
    fig_vol_multi.update_layout(yaxis_tickformat='.0%', height=450)
    st.plotly_chart(fig_vol_multi, use_container_width=True)

    # --- 區塊 2: 市場週期佔比 (左) 與 漲跌機率統計 (右) ---
    st.divider()
    col_ratio, col_prob = st.columns([1, 1.2])
    
    df['MA200'] = df['Price'].rolling(window=200).mean()
    df['Above200'] = df['Price'] > df['MA200']
    
    with col_ratio:
        st.subheader("⚖️ 市場週期時間佔比")
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

    with col_prob:
        st.subheader("⚖️ 均線環境下之漲跌機率統計")
        above_data = df[df['Above200']].dropna()
        below_data = df[~df['Above200']].dropna()
        
        def get_up_down_ratio(data):
            total = len(data)
            up_c = (data['Return'] > 0).sum()
            down_c = (data['Return'] <= 0).sum()
            return up_c / total, down_c / total

        up_a, down_a = get_up_down_ratio(above_data)
        up_b, down_b = get_up_down_ratio(below_data)
        
        prob_df = pd.DataFrame([
            {"環境": "擴張期 (>200MA)", "漲跌": "上漲天數", "比例": up_a},
            {"環境": "擴張期 (>200MA)", "漲跌": "下跌天數", "比例": down_a},
            {"環境": "衰退期 (<200MA)", "漲跌": "上漲天數", "比例": up_b},
            {"環境": "衰退期 (<200MA)", "漲跌": "下跌天數", "比例": down_b}
        ])
        fig_prob = px.bar(prob_df, x="環境", y="比例", color="漲跌", 
                          barmode="group", text_auto='.1%',
                          color_discrete_map={"上漲天數": "#2962FF", "下跌天數": "#D50000"})
        fig_prob.update_layout(yaxis_tickformat='.0%', height=400)
        st.plotly_chart(fig_prob, use_container_width=True)

    # --- 區塊 3: 連漲與連跌機率 ---
    st.divider()
    st.subheader("🔥 動能基因測試：連漲 vs 連跌天數分佈")
    is_up = df['Return'] > 0
    df['Up_Streak'] = is_up.groupby((is_up != is_up.shift()).cumsum()).cumcount() + 1
    df.loc[~is_up, 'Up_Streak'] = 0
    is_down = df['Return'] < 0
    df['Down_Streak'] = is_down.groupby((is_down != is_down.shift()).cumsum()).cumcount() + 1
    df.loc[~is_down, 'Down_Streak'] = 0

    col_sl, col_sr = st.columns(2)
    def get_streak_probs(subset, col):
        t = len(subset)
        return {f"{s}天": (subset[col] >= s).sum() / t for s in [2, 3, 4, 5]}

    with col_sl:
        st.markdown("**連漲機率**")
        ua = get_streak_probs(df[df['Above200']], 'Up_Streak')
        ub = get_streak_probs(df[~df['Above200']], 'Up_Streak')
        st.plotly_chart(px.bar(pd.DataFrame([{"天數": k, "機率": v, "環境": "均線之上"} for k,v in ua.items()] + [{"天數": k, "機率": v, "環境": "均線之下"} for k,v in ub.items()]), 
                               x="天數", y="機率", color="環境", barmode="group", text_auto='.1%', color_discrete_map={"均線之上": "#6699CC", "均線之下": "#EE7733"}), use_container_width=True)
    with col_sr:
        st.markdown("**連跌機率**")
        da = get_streak_probs(df[df['Above200']], 'Down_Streak')
        db = get_streak_probs(df[~df['Above200']], 'Down_Streak')
        st.plotly_chart(px.bar(pd.DataFrame([{"天數": k, "機率": v, "環境": "均線之上"} for k,v in da.items()] + [{"天數": k, "機率": v, "環境": "均線之下"} for k,v in db.items()]), 
                               x="天數", y="機率", color="環境", barmode="group", text_auto='.1%', color_discrete_map={"均線之上": "#6699CC", "均線之下": "#EE7733"}), use_container_width=True)

    # --- 區塊 4: 滾動回撤與股災統計 ---
    st.divider()
    st.subheader("🛡️ 歷史滾動回撤對比 (Rolling Drawdown)")
    df['Bench_NAV'] = (1 + df['Return'].fillna(0)).cumprod()
    df['LRS_Ret'] = np.where(df['Above200'].shift(1), df['Return'], 0)
    df['LRS_NAV'] = (1 + df['LRS_Ret'].fillna(0)).cumprod()
    df['Bench_DD'] = (df['Bench_NAV'] / df['Bench_NAV'].cummax()) - 1
    df['LRS_DD'] = (df['LRS_NAV'] / df['LRS_NAV'].cummax()) - 1
    
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['Bench_DD'], name="大盤 (B&H)", line=dict(color='#EE7733', width=1.2), fill='tozeroy', fillcolor='rgba(238,119,51,0.08)'))
    fig_dd.add_trace(go.Scatter(x=df.index, y=df['LRS_DD'], name="LRS 策略", line=dict(color='#6699CC', width=2.5)))
    fig_dd.update_layout(yaxis_tickformat='.0%', height=500, hovermode="x unified")
    st.plotly_chart(fig_dd, use_container_width=True)

    st.subheader("📋 重大股災避險實測")
    crashes = [("2008 金融海嘯", "2008-01-01", "2009-06-30"), ("2020 新冠疫情", "2020-01-01", "2020-04-30"), ("2022 升息縮表", "2022-01-01", "2022-12-31"), ("2025 對等關稅", "2025-01-01", "2025-12-31")]
    mdd_sum = []
    for name, s, e in crashes:
        mask = (df.index >= s) & (df.index <= e)
        if mask.any():
            sub = df.loc[mask]
            b_mdd = (sub['Bench_NAV'] / sub['Bench_NAV'].cummax() - 1).min()
            l_mdd = (sub['LRS_NAV'] / sub['LRS_NAV'].cummax() - 1).min()
            mdd_sum.append({"歷史股災": name, "大盤 MDD": f"{b_mdd:.1%}", "LRS MDD": f"{l_mdd:.1%}", "效果": f"減少 {(b_mdd-l_mdd)*-1:.1%} 跌幅"})
    st.table(pd.DataFrame(mdd_sum))
    
    st.success("✨ 分析完成！所有圖表已還原並補齊多週期波動率對比。")
