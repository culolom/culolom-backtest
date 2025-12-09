###############################################################
# pages/4_Macro_Strategy.py — 國發會景氣燈號策略 (UI 優化版)
# 核心邏輯：藍燈(低分)買進，紅燈(高分)賣出
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path
import sys

# ------------------------------------------------------
# 🔒 驗證守門員
# ------------------------------------------------------
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth
    if not auth.check_password():
        st.stop()
except ImportError:
    pass 

###############################################################
# 字型與頁面設定
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    import matplotlib.font_manager as fm
    import matplotlib
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"

st.set_page_config(page_title="景氣燈號策略", page_icon="🚦", layout="wide")

# ==========================================
# 🛑 務必保留的 Sidebar 區域
# ==========================================
with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

# ==========================================
# 主頁面標題
# ==========================================
st.markdown("<h1 style='margin-bottom:0.5em;'>🚦 國發會景氣燈號策略 (Macro Strategy)</h1>", unsafe_allow_html=True)
st.markdown("""
<b>股市名言：「藍燈買股票，紅燈數鈔票」。利用總體經濟指標進行長線逆勢操作。</b><br>
1️⃣ <b>藍燈區 (買進)</b>：景氣低迷，分數低於門檻 (通常 16分)，分批佈局。<br>
2️⃣ <b>紅燈區 (賣出)</b>：景氣過熱，分數高於門檻 (通常 32-38分)，獲利了結。<br>
<small>策略特色：交易頻率極低，適合抓取大波段週期。</small>
""", unsafe_allow_html=True)

###############################################################
# 資料處理函式 (超強容錯版)
###############################################################

DATA_DIR = Path("data")

def load_csv_smart(symbol: str) -> pd.DataFrame:
    # 1. 模糊比對檔名
    candidates = [f"{symbol}.csv", f"{symbol.upper()}.csv", f"{symbol.lower()}.csv"]
    path = None
    for c in candidates:
        p = DATA_DIR / c
        if p.exists():
            path = p
            break
            
    if path is None:
        return pd.DataFrame()
    
    try:
        # 2. 先讀取
        df = pd.read_csv(path)
        
        # 3. 處理日期：假設第一欄是日期
        if "Date" not in df.columns:
            df = df.rename(columns={df.columns[0]: "Date"})
            
        df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
        df = df.dropna(subset=["Date"])
        df = df.set_index("Date").sort_index()
        
        # 4. 處理數值 (Price / Score)
        target_col = None
        priority = ["Adj Close", "Close", "Score", "Price"]
        for p in priority:
            if p in df.columns:
                target_col = p
                break
        
        # 關鍵字搜尋 (針對中文)
        if target_col is None:
            for c in df.columns:
                c_str = str(c).lower()
                if "分" in c_str or "score" in c_str or "價" in c_str:
                    target_col = c
                    break
        
        if target_col is None and len(df.columns) > 0:
            target_col = df.columns[-1]
            
        # 統一改名並轉數字
        df["Price"] = pd.to_numeric(df[target_col], errors='coerce')
        df = df.dropna(subset=["Price"])
        
        return df[["Price"]]
        
    except Exception as e:
        return pd.DataFrame()

###############################################################
# UI 輸入區 (仿照塔木德風格)
###############################################################

st.divider()

# 第一排：標的選擇 (2欄)
col1, col2 = st.columns(2)
with col1:
    ticker = st.text_input("📈 交易標的 (ETF/股票)", value="0050.TW")
with col2:
    score_file = st.text_input("🚦 景氣分數檔名 (CSV)", value="SCORE")

# --- 預讀資料以計算有效日期 ---
df_check_p = load_csv_smart(ticker)
df_check_s = load_csv_smart(score_file)

if df_check_p.empty or df_check_s.empty:
    st.warning("⚠️ 等待資料讀取... 請確認 data 資料夾。")
    valid_start = dt.date(2003, 1, 1)
    valid_end = dt.date.today()
else:
    # 取交集
    v_start = max(df_check_p.index.min().date(), df_check_s.index.min().date())
    v_end = min(df_check_p.index.max().date(), df_check_s.index.max().date())
    valid_start, valid_end = v_start, v_end
    st.info(f"📌 {ticker} + {score_file} 的共同資料區間：{valid_start} ~ {valid_end}")

# 第二排：日期與本金 (3欄)
col_d1, col_d2, col_d3 = st.columns(3)
with col_d1:
    start_date = st.date_input("開始日期", value=valid_start, min_value=valid_start, max_value=valid_end)
with col_d2:
    end_date = st.date_input("結束日期", value=valid_end, min_value=valid_start, max_value=valid_end)
with col_d3:
    initial_capital = st.number_input("初始本金 (元)", value=1_000_000, step=100_000)

# 第三排：策略核心參數 (3欄)
col_p1, col_p2, col_p3 = st.columns(3)
with col_p1:
    buy_threshold = st.number_input("🔵 買進門檻 (分數 <= ?)", 9, 45, 16, help="低於此分數視為藍燈，開始買進")
with col_p2:
    sell_threshold = st.number_input("🔴 賣出門檻 (分數 >= ?)", 9, 45, 32, help="高於此分數視為紅燈/黃紅燈，開始賣出")
with col_p3:
    lag_months = st.number_input("⏳ 訊號延遲 (月)", 0, 3, 1, help="模擬真實公佈時間差，避免看圖說故事。建議設為 1。")

###############################################################
# 回測執行
###############################################################

if st.button("開始回測 🚀", type="primary"):
    with st.spinner("正在整合數據與計算訊號..."):
        
        # 1. 使用預讀的資料並切割時間
        df_price = df_check_p.loc[str(start_date):str(end_date)]
        df_score = df_check_s # 分數保留完整以供 Shift 使用

        if df_price.empty:
            st.error("❌ 選定區間無股價資料")
            st.stop()

        # 2. 合併資料 (Resample)
        df = df_price.rename(columns={"Price": "Close"}).copy()
        
        # 擴展分數到日頻率
        df_score_daily = df_score.reindex(df.index, method='ffill')
        df["Score_Raw"] = df_score_daily["Price"]
        
        # 3. 處理延遲
        shift_days = int(lag_months * 22)
        df["Score_Signal"] = df["Score_Raw"].shift(shift_days)
        df = df.dropna()

        if df.empty:
            st.error("❌ 資料經過延遲處理後為空，請選擇更長的區間。")
            st.stop()

        # 4. 產生訊號
        # 1=持有, 0=空手
        pos = 0
        pos_list = []
        for i in range(len(df)):
            s = df["Score_Signal"].iloc[i]
            if s <= buy_threshold:
                pos = 1
            elif s >= sell_threshold:
                pos = 0
            pos_list.append(pos)
            
        df["Position"] = pos_list
        
        # 5. 計算績效
        df["Ret"] = df["Close"].pct_change().fillna(0)
        df["Strategy_Ret"] = df["Position"].shift(1) * df["Ret"]
        
        df["Equity_Strategy"] = initial_capital * (1 + df["Strategy_Ret"]).cumprod()
        df["Equity_Benchmark"] = initial_capital * (1 + df["Ret"]).cumprod()

        # ---------------- KPI 計算 ----------------
        def calc_metrics(equity_series):
            total_ret = (equity_series.iloc[-1] / equity_series.iloc[0]) - 1
            years = (equity_series.index[-1] - equity_series.index[0]).days / 365.25
            cagr = (1 + total_ret) ** (1/years) - 1 if years > 0 else 0
            mdd = (equity_series / equity_series.cummax() - 1).min()
            
            daily_ret = equity_series.pct_change().fillna(0)
            vol = daily_ret.std() * np.sqrt(252)
            sharpe = (cagr - 0.04) / vol if vol > 0 else 0
            return total_ret, cagr, mdd, vol, sharpe

        res_strat = calc_metrics(df["Equity_Strategy"])
        res_bench = calc_metrics(df["Equity_Benchmark"])

        # ==========================================================
        # 顯示結果
        # ==========================================================

        # CSS 樣式 (塔木德風格)
        st.markdown("""
        <style>
            .kpi-card {
                background-color: var(--secondary-background-color);
                border-radius: 12px; padding: 15px; text-align: center;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1); border: 1px solid rgba(128,128,128,0.1);
            }
            .kpi-val { font-size: 1.6rem; font-weight: 700; color: var(--text-color); }
            .kpi-lbl { font-size: 0.9rem; opacity: 0.7; }
            .kpi-sub { font-size: 0.8rem; color: #666; margin-top: 5px; }
            .pos { color: #21c354; font-weight: bold; }
            .neg { color: #ff3c3c; font-weight: bold; }
        </style>
        """, unsafe_allow_html=True)

        def kpi_html(label, val, bench_val, is_pct=False):
            val_str = f"{val:.2%}" if is_pct else f"${val:,.0f}"
            bench_str = f"{bench_val:.2%}" if is_pct else f"${bench_val:,.0f}"
            return f"""
            <div class="kpi-card">
                <div class="kpi-lbl">{label}</div>
                <div class="kpi-val">{val_str}</div>
                <div class="kpi-sub">基準: {bench_str}</div>
            </div>
            """

        # 1. KPI 卡片
        row_kpi = st.columns(4)
        with row_kpi[0]: st.markdown(kpi_html("期末總資產", res_strat[0]*initial_capital + initial_capital, res_bench[0]*initial_capital + initial_capital), unsafe_allow_html=True)
        with row_kpi[1]: st.markdown(kpi_html("年化報酬 (CAGR)", res_strat[1], res_bench[1], True), unsafe_allow_html=True)
        with row_kpi[2]: st.markdown(kpi_html("最大回撤 (MDD)", res_strat[2], res_bench[2], True), unsafe_allow_html=True)
        with row_kpi[3]: st.markdown(kpi_html("波動率 (Risk)", res_strat[3], res_bench[3], True), unsafe_allow_html=True)

        st.markdown("---")

        # 2. 圖表區域
        tab1, tab2 = st.tabs(["💰 資金與燈號", "📊 交易點位詳情"])

        with tab1:
            # 主圖：資金
            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"], name="燈號策略", line=dict(color="#00C853", width=2)))
            fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Benchmark"], name=f"買進持有 ({ticker})", line=dict(color="#B0BEC5", width=2, dash='dash')))
            
            fig_eq.update_layout(template="plotly_white", height=450, hovermode="x unified", title="策略績效比較", legend=dict(orientation="h", y=1.02))
            st.plotly_chart(fig_eq, use_container_width=True)

            # 副圖：燈號
            fig_s = go.Figure()
            fig_s.add_trace(go.Scatter(x=df.index, y=df["Score_Signal"], name="景氣分數", line=dict(color="#FFA000")))
            
            # 色帶
            fig_s.add_hrect(y0=0, y1=buy_threshold, fillcolor="blue", opacity=0.15, layer="below", annotation_text="藍燈區 (買)")
            fig_s.add_hrect(y0=sell_threshold, y1=55, fillcolor="red", opacity=0.15, layer="below", annotation_text="紅燈區 (賣)")
            
            fig_s.update_layout(template="plotly_white", height=250, title="景氣對策信號走勢", yaxis=dict(range=[9, 48]), showlegend=False)
            st.plotly_chart(fig_s, use_container_width=True)

        with tab2:
            # 準備買賣點
            buys = df[(df["Position"] == 1) & (df["Position"].shift(1) == 0)]
            sells = df[(df["Position"] == 0) & (df["Position"].shift(1) == 1)]
            
            fig_pt = go.Figure()
            fig_pt.add_trace(go.Scatter(x=df.index, y=df["Close"], name="股價", line=dict(color="#333", width=1)))
            fig_pt.add_trace(go.Scatter(x=buys.index, y=buys["Close"], mode="markers", name="買進訊號", marker=dict(symbol="triangle-up", color="blue", size=10)))
            fig_pt.add_trace(go.Scatter(x=sells.index, y=sells["Close"], mode="markers", name="賣出訊號", marker=dict(symbol="triangle-down", color="red", size=10)))
            
            fig_pt.update_layout(template="plotly_white", height=450, hovermode="x unified", title="進出點位標記")
            st.plotly_chart(fig_pt, use_container_width=True)

        # 3. 交易列表 (Pandas Styler)
        st.markdown("### 📋 歷年交易紀錄")
        
        # 產生交易清單
        trades = []
        temp_buy = None
        
        # 找出所有訊號點
        signals = df[df["Position"] != df["Position"].shift(1)].dropna()
        
        for date, row in signals.iterrows():
            if row["Position"] == 1: # 買進
                temp_buy = (date, row["Close"])
            elif row["Position"] == 0 and temp_buy: # 賣出
                b_date, b_price = temp_buy
                s_price = row["Close"]
                ret = (s_price - b_price) / b_price
                trades.append({
                    "買入日期": b_date.strftime("%Y-%m-%d"),
                    "買入價格": b_price,
                    "賣出日期": date.strftime("%Y-%m-%d"),
                    "賣出價格": s_price,
                    "報酬率": ret,
                    "持有天數": (date - b_date).days
                })
                temp_buy = None
                
        if trades:
            df_trades = pd.DataFrame(trades)
            st.dataframe(
                df_trades.style
                .format({
                    "買入價格": "{:.2f}", 
                    "賣出價格": "{:.2f}", 
                    "報酬率": "{:.2%}"
                })
                .background_gradient(cmap="RdYlGn", subset=["報酬率"]),
                use_container_width=True
            )
        else:
            st.info("區間內無完整一進一出之交易紀錄")

        # 4. 總結比較表
        st.markdown("### 📊 詳細數據總結")
        comp_data = {
            "策略": ["景氣燈號策略", f"基準 ({ticker})"],
            "總報酬率": [res_strat[0], res_bench[0]],
            "CAGR (年化)": [res_strat[1], res_bench[1]],
            "最大回撤 (MDD)": [res_strat[2], res_bench[2]],
            "年化波動率": [res_strat[3], res_bench[3]],
            "Sharpe Ratio": [res_strat[4], res_bench[4]]
        }
        df_comp = pd.DataFrame(comp_data).set_index("策略")
        
        st.dataframe(
            df_comp.style
            .format("{:.2%}", subset=["總報酬率", "CAGR (年化)", "最大回撤 (MDD)", "年化波動率"])
            .format("{:.2f}", subset=["Sharpe Ratio"])
            .background_gradient(cmap="RdYlGn", subset=["總報酬率", "CAGR (年化)", "Sharpe Ratio"])
            .background_gradient(cmap="RdYlGn_r", subset=["最大回撤 (MDD)", "年化波動率"]),
            use_container_width=True
        )
