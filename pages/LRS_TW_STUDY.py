import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# ------------------------------------------------------
# 1. 頁面配置與 CSS 鼠叔風格美化
# ------------------------------------------------------
st.set_page_config(page_title="LRS 策略深度研究", page_icon="🔭", layout="wide")

st.markdown("""
<style>
    /* 橘色按鈕 */
    div.stButton > button:first-child {
        background-color: #FF6F00; color: white; border-radius: 10px;
        font-weight: bold; font-size: 16px; padding: 0.5rem 2rem;
        transition: all 0.3s ease; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border: none;
    }
    div.stButton > button:first-child:hover { background-color: #E65100; transform: translateY(-2px); }
    
    /* 資訊卡片 */
    .info-card {
        background-color: #f9f9f9; padding: 20px; border-radius: 12px;
        border-left: 6px solid #FF6F00; margin-bottom: 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* 標題與副標題 */
    h1, h2, h3 { font-family: 'Noto Sans TC', sans-serif; }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------
# 2. 數據處理核心函數
# ------------------------------------------------------
DATA_DIR = Path("data")

@st.cache_data
def load_and_preprocess(symbol: str, start_year: int):
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists():
        return None
    
    # 載入數據，確保日期格式正確
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    price_col = "Adj Close" if "Adj Close" in df.columns else "Close"
    df = df[[price_col]].rename(columns={price_col: "Price"})
    
    # 篩選年份
    df = df[df.index.year >= start_year].copy()
    
    # 計算基礎回報
    df['Return'] = df['Price'].pct_change()
    
    # 計算 200SMA 核心指標 (用於大部分圖表)
    df['MA200'] = df['Price'].rolling(window=200).mean()
    df['Above200'] = df['Price'] > df['MA200']
    
    # 計算連漲天數 (Consecutive Streaks)
    is_up = df['Return'] > 0
    df['Streak'] = is_up.groupby((is_up != is_up.shift()).cumsum()).cumcount() + 1
    df.loc[~is_up, 'Streak'] = 0
    
    return df

# ------------------------------------------------------
# 3. 儀表板 Header 與側邊欄
# ------------------------------------------------------
st.markdown("<h1 style='margin-bottom:0.1em;'>🔭 LRS 策略：台股全維度量化戰情室</h1>", unsafe_allow_html=True)
st.markdown(f"<p style='color:gray;'>數據更新至：{pd.Timestamp.now().strftime('%Y-%m-%d')}</p>", unsafe_allow_html=True)

st.markdown("""
<div class="info-card">
    <h4 style="margin-top:0;">📖 鼠叔量化筆記</h4>
    <p style="margin-bottom:0;">本儀表板還原了 Michael Gayed 經典論文中的四項關鍵統計。我們不只看績效，更要看<b>「波動率壓制」</b>與<b>「連漲動能」</b>在台股的實戰表現。這才是長期持有正二而不被震出場的科學依據。</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ 全域參數")
    target_symbol = st.selectbox("選擇回測標的", ["^TWII", "0050.TW", "SPY", "QQQ"], index=0)
    start_year = st.slider("統計起始年份", 2000, 2026, 2000)
    st.divider()
    st.caption("🐹 倉鼠人生實驗室製作")

# ------------------------------------------------------
# 4. 主執行區域
# ------------------------------------------------------
if st.button("更新統計報告 🚀"):
    df = load_and_preprocess(target_symbol, start_year)
    
    if df is None:
        st.error(f"❌ 找不到 `data/{target_symbol}.csv`。請確保檔案已上傳至正確目錄。")
    else:
        # --- 區塊 A: 不同均線波動率對比 (Chart 3) ---
        st.subheader("📊 不同均線週期之波動率壓制對比")
        ma_periods = [10, 20, 50, 100, 200]
        vol_results = []
        for p in ma_periods:
            ma_temp = df['Price'].rolling(window=p).mean()
            above = df['Price'] > ma_temp
            vol_above = df[above]['Return'].std() * np.sqrt(252)
            vol_below = df[~above]['Return'].std() * np.sqrt(252)
            vol_results.append({"MA": f"{p}-day", "Volatility": vol_above, "Environment": "Volatility Above"})
            vol_results.append({"MA": f"{p}-day", "Volatility": vol_below, "Environment": "Volatility Below"})
        
        fig_vol = px.bar(pd.DataFrame(vol_results), x="MA", y="Volatility", color="Environment",
                         barmode="group", text_auto='.1%', 
                         color_discrete_map={"Volatility Above": "#6699CC", "Volatility Below": "#EE7733"})
        st.plotly_chart(fig_vol, use_container_width=True)

        # --- 區塊 B: 連漲天數與市場佔比 ---
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("🔥 200SMA 環境下的連漲機率 (動能持續性)")
            def get_streak_stats(subset):
                total = len(subset)
                return {f"{s}天": (subset['Streak'] >= s).sum() / total for s in [2, 3, 4, 5]}
            
            s_above = get_streak_stats(df[df['Above200']])
            s_below = get_streak_stats(df[~df['Above200']])
            streak_df = pd.DataFrame([
                {"連漲": k, "機率": v, "環境": "Above 200-day"} for k, v in s_above.items()
            ] + [
                {"連漲": k, "機率": v, "環境": "Below 200-day"} for k, v in s_below.items()
            ])
            fig_streak = px.bar(streak_df, x="連漲", y="機率", color="環境", barmode="group", text_auto='.0%',
                                color_discrete_map={"Above 200-day": "#6699CC", "Below 200-day": "#EE7733"})
            st.plotly_chart(fig_streak, use_container_width=True)

        with col2:
            st.subheader("⚖️ 市場週期佔比")
            counts = df['Above200'].value_counts(normalize=True)
            fig_pie = px.pie(values=counts.values, names=["Expansion (>200MA)", "Recession (<200MA)"],
                             color_discrete_sequence=["#6699CC", "#EE7733"], hole=0.5)
            st.plotly_chart(fig_pie, use_container_width=True)

        # --- 區塊 C: 滾動回撤對比 (Chart 8) ---
        st.subheader("🛡️ Chart 8: 歷史滾動回撤對比 (Rolling Drawdown)")
        # 策略淨值計算 (考慮 1 天訊號延遲)
        df['Bench_NAV'] = (1 + df['Return'].fillna(0)).cumprod()
        df['LRS_Ret'] = np.where(df['Above200'].shift(1), df['Return'], 0)
        df['LRS_NAV'] = (1 + df['LRS_Ret'].fillna(0)).cumprod()
        
        def calc_dd(nav): return (nav / nav.cummax()) - 1
        df['Bench_DD'] = calc_dd(df['Bench_NAV'])
        df['LRS_DD'] = calc_dd(df['LRS_NAV'])
        
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=df.index, y=df['Bench_DD'], name="大盤 (Buy & Hold)",
                                    line=dict(color='#EE7733', width=1), fill='tozeroy', fillcolor='rgba(238,119,51,0.1)'))
        fig_dd.add_trace(go.Scatter(x=df.index, y=df['LRS_DD'], name="LRS 策略 (200SMA)",
                                    line=dict(color='#6699CC', width=2)))
        fig_dd.update_layout(yaxis_tickformat='.0%', hovermode="x unified", height=500, margin=dict(l=0,r=0,t=30,b=0))
        st.plotly_chart(fig_dd, use_container_width=True)

        # --- 區塊 D: 股災 MDD 數據表 ---
        st.subheader("📋 重大股災避險能力統計")
        crashes = [
            ("2000 科技泡沫", "2000-01-01", "2002-12-31"),
            ("2008 金融海嘯", "2008-01-01", "2009-06-30"),
            ("2020 新冠疫情", "2020-01-01", "2020-04-30"),
            ("2022 升息縮表", "2022-01-01", "2022-12-31")
        ]
        mdd_summary = []
        for name, s, e in crashes:
            mask = (df.index >= s) & (df.index <= e)
            if mask.any():
                sub = df.loc[mask]
                b_mdd = (sub['Bench_NAV'] / sub['Bench_NAV'].cummax() - 1).min()
                l_mdd = (sub['LRS_NAV'] / sub['LRS_NAV'].cummax() - 1).min()
                mdd_summary.append({"股災區間": name, "大盤 MDD": f"{b_mdd:.1%}", "LRS MDD": f"{l_mdd:.1%}", 
                                    "避險效果": f"減少 {(b_mdd - l_mdd)*-1:.1%} 跌幅"})
        st.table(pd.DataFrame(mdd_summary))
        
        st.success(f"🐹 {target_symbol} 統計報告生成完畢！")
else:
    st.info("💡 點擊上方按鈕開始分析。請確保 `data/` 資料夾中包含標的的 CSV 檔案。")
