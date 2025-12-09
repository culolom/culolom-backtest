###############################################################
# pages/4_Macro_Strategy.py — 國發會景氣燈號策略 (日期強力修復版)
# UI 風格：仿照塔木德策略 (Sidebar + 4欄排版 + KPI 卡片)
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
# 🛑 Sidebar 區域
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

DATA_DIR = Path("data")

###############################################################
# 🔧 萬能日期解析工具 (解決您的痛點)
###############################################################

def parse_magic_date(x):
    """ 強力解析各種奇葩日期格式，統一轉為 datetime """
    s = str(x).strip()
    try:
        # 1. 標準格式 YYYY-MM-DD
        return pd.to_datetime(s)
    except:
        pass
    
    try:
        # 2. 處理 6位數 "198401" -> 1984-01-01
        if len(s) == 6 and s.isdigit():
            return dt.datetime.strptime(s, "%Y%m")
        
        # 3. 處理 民國年 "07301" -> 1984-01-01
        if len(s) == 5 and s.isdigit():
            year = int(s[:3]) + 1911
            month = int(s[3:])
            return dt.datetime(year, month, 1)
            
        # 4. 處理 "1984/1" 或 "112/01"
        if "/" in s or "-" in s:
            sep = "/" if "/" in s else "-"
            parts = s.split(sep)
            if len(parts) >= 2:
                y = int(parts[0])
                m = int(parts[1])
                d = 1
                if len(parts) > 2: d = int(parts[2])
                
                # 民國年修正
                if y < 1911: y += 1911
                return dt.datetime(y, m, d)
    except:
        return pd.NaT # 解析失敗回傳空值
        
    return pd.NaT

def load_csv_smart(symbol: str) -> pd.DataFrame:
    # 模糊比對檔名
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
        # 讀取 (不指定 parse_dates，自己手動處理最穩)
        df = pd.read_csv(path)
        
        # 1. 找日期欄位 (假設第一欄)
        date_col = df.columns[0] 
        # 如果有名為 'Date' 或 '日期' 的欄位優先使用
        for c in df.columns:
            if "date" in str(c).lower() or "日期" in str(c):
                date_col = c
                break
        
        # 2. 套用萬能解析器
        df["Date_Clean"] = df[date_col].apply(parse_magic_date)
        df = df.dropna(subset=["Date_Clean"])
        df = df.set_index("Date_Clean").sort_index()
        
        # 3. 找數值欄位
        target_col = None
        priority = ["Adj Close", "Close", "Score", "Price"]
        for p in priority:
            if p in df.columns:
                target_col = p
                break
        
        if target_col is None:
            # 關鍵字搜尋 (中文)
            for c in df.columns:
                c_str = str(c).lower()
                if "分" in c_str or "score" in c_str or "價" in c_str:
                    target_col = c
                    break
        
        if target_col is None: 
            target_col = df.columns[-1] # 最後一欄當作數值
            
        # 轉數字
        df["Price"] = pd.to_numeric(df[target_col], errors='coerce')
        df = df.dropna(subset=["Price"])
        
        return df[["Price"]]
        
    except Exception as e:
        # st.error(f"讀取 {symbol} 發生錯誤: {e}") # Debug 用
        return pd.DataFrame()

###############################################################
# UI 輸入區 (仿照塔木德風格)
###############################################################

st.divider()

# 第一排：標的與檔案 (2欄)
col1, col2 = st.columns(2)
with col1:
    ticker = st.text_input("📈 交易標的 (ETF/股票)", value="0050.TW")
with col2:
    score_file = st.text_input("🚦 景氣分數檔名 (CSV)", value="SCORE")

# --- 預讀資料檢查 ---
df_check_p = load_csv_smart(ticker)
df_check_s = load_csv_smart(score_file)

valid_start = dt.date(2003, 1, 1)
valid_end = dt.date.today()

if df_check_p.empty:
    st.warning(f"⚠️ 讀取失敗：{ticker}。請確認 CSV 格式 (第一欄日期, 數值欄)。")
elif df_check_s.empty:
    st.warning(f"⚠️ 讀取失敗：{score_file}。請確認 CSV 格式。")
else:
    # 取交集
    v_start = max(df_check_p.index.min().date(), df_check_s.index.min().date())
    v_end = min(df_check_p.index.max().date(), df_check_s.index.max().date())
    
    if v_start > v_end:
        st.error(f"❌ 日期無交集！\n股票: {df_check_p.index.min().date()}~{df_check_p.index.max().date()}\n分數: {df_check_s.index.min().date()}~{df_check_s.index.max().date()}")
        st.stop()
    else:
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

# 第三排：策略參數 (3欄)
col_p1, col_p2, col_p3 = st.columns(3)
with col_p1:
    buy_threshold = st.number_input("🔵 買進門檻 (分數 <= ?)", 9, 45, 16, help="低於此分數(含)視為藍燈買點")
with col_p2:
    sell_threshold = st.number_input("🔴 賣出門檻 (分數 >= ?)", 9, 45, 32, help="高於此分數(含)視為紅燈賣點")
with col_p3:
    lag_months = st.number_input("⏳ 訊號延遲 (月)", 0, 3, 1, help="1月的分數2月底才公佈，真實操作需延遲1個月")

###############################################################
# 回測執行
###############################################################

if st.button("開始回測 🚀", type="primary"):
    with st.spinner("正在執行回測..."):
        
        # 1. 資料準備
        df_price = df_check_p.loc[str(start_date):str(end_date)]
        df_score = df_check_s # 分數不切，保留給 shift 用

        if df_price.empty:
            st.error("選定區間無股價資料")
            st.stop()

        # 2. 合併資料
        df = df_price.rename(columns={"Price": "Close"}).copy()
        
        # 將分數 (月資料) 擴展到 (日資料)
        # 使用 ffill (前值填充)，確保整個月都是同一個分數
        df_score_daily = df_score.reindex(df.index, method='ffill')
        df["Score_Raw"] = df_score_daily["Price"]
        
        # 3. 處理延遲
        # 1個月約 20 交易日
        shift_days = int(lag_months * 20)
        df["Score_Signal"] = df["Score_Raw"].shift(shift_days)
        df = df.dropna() # 移除因 shift 產生的空值

        if df.empty:
            st.error("扣除延遲後無資料，請選擇更長的區間。")
            st.stop()

        # 4. 產生訊號
        # 1=持有, 0=空手
        # 這裡使用「狀態機」邏輯：
        # 訊號 > 賣出線 -> 空手
        # 訊號 < 買進線 -> 持有
        # 中間 -> 維持昨天的狀態
        
        pos = 0 # 初始狀態 (假設空手)
        pos_list = []
        
        # 為了加速，轉 numpy 計算
        scores = df["Score_Signal"].values
        
        for s in scores:
            if s <= buy_threshold:
                pos = 1
            elif s >= sell_threshold:
                pos = 0
            # else: pos = pos (維持不變)
            pos_list.append(pos)
            
        df["Position"] = pos_list
        
        # 5. 計算績效
        df["Ret"] = df["Close"].pct_change().fillna(0)
        # 策略報酬 = 昨天收盤後的持倉 * 今天漲跌
        df["Strategy_Ret"] = df["Position"].shift(1) * df["Ret"]
        
        df["Equity_Strategy"] = initial_capital * (1 + df["Strategy_Ret"]).cumprod()
        df["Equity_Benchmark"] = initial_capital * (1 + df["Ret"]).cumprod()

        # ---------------- KPI 計算 ----------------
        def calc_metrics(equity_series):
            total_ret = (equity_series.iloc[-1] / initial_capital) - 1
            days = (equity_series.index[-1] - equity_series.index[0]).days
            cagr = (1 + total_ret) ** (365 / days) - 1 if days > 0 else 0
            mdd = (equity_series / equity_series.cummax() - 1).min()
            
            daily_ret = equity_series.pct_change().fillna(0)
            vol = daily_ret.std() * np.sqrt(252)
            sharpe = (cagr - 0.04) / vol if vol > 0 else 0
            return total_ret, cagr, mdd, vol, sharpe

        res_s = calc_metrics(df["Equity_Strategy"])
        res_b = calc_metrics(df["Equity_Benchmark"])

        # ==========================================================
        # 結果顯示
        # ==========================================================

        # CSS
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
        </style>
        """, unsafe_allow_html=True)

        def kpi_html(label, val, bench_val, is_pct=False):
            val_str = f"{val:.2%}" if is_pct else f"${val:,.0f}"
            bench_str = f"{bench_val:.2%}" if is_pct else f"${bench_val:,.0f}"
            return f"""<div class="kpi-card"><div class="kpi-lbl">{label}</div><div class="kpi-val">{val_str}</div><div class="kpi-sub">基準: {bench_str}</div></div>"""

        # KPI 卡片
        row_kpi = st.columns(4)
        with row_kpi[0]: st.markdown(kpi_html("期末總資產", df["Equity_Strategy"].iloc[-1], df["Equity_Benchmark"].iloc[-1]), unsafe_allow_html=True)
        with row_kpi[1]: st.markdown(kpi_html("年化報酬 (CAGR)", res_s[1], res_b[1], True), unsafe_allow_html=True)
        with row_kpi[2]: st.markdown(kpi_html("最大回撤 (MDD)", res_s[2], res_b[2], True), unsafe_allow_html=True)
        with row_kpi[3]: st.markdown(kpi_html("夏普值 (Sharpe)", res_s[4], res_b[4], False), unsafe_allow_html=True)

        st.markdown("---")

        # 圖表
        tab1, tab2 = st.tabs(["💰 資金與燈號區間", "📊 交易點位詳情"])

        with tab1:
            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"], name="燈號策略", line=dict(color="#00C853", width=2)))
            fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Benchmark"], name="買進持有", line=dict(color="#B0BEC5", width=2, dash='dot')))
            fig_eq.update_layout(height=450, template="plotly_white", hovermode="x unified", title="策略績效 vs 大盤")
            st.plotly_chart(fig_eq, use_container_width=True)

            # 燈號區間圖
            fig_score = go.Figure()
            fig_score.add_trace(go.Scatter(x=df.index, y=df["Score_Signal"], name="景氣分數", line=dict(color="#FFA000")))
            # 色帶
            fig_score.add_hrect(y0=0, y1=buy_threshold, fillcolor="blue", opacity=0.15, layer="below", annotation_text="藍燈 (買)")
            fig_score.add_hrect(y0=sell_threshold, y1=55, fillcolor="red", opacity=0.15, layer="below", annotation_text="紅燈 (賣)")
            fig_score.update_layout(height=250, template="plotly_white", title="景氣對策信號走勢", yaxis=dict(range=[9, 48]), showlegend=False)
            st.plotly_chart(fig_score, use_container_width=True)

        with tab2:
            buys = df[(df["Position"] == 1) & (df["Position"].shift(1) == 0)]
            sells = df[(df["Position"] == 0) & (df["Position"].shift(1) == 1)]
            
            fig_pt = go.Figure()
            fig_pt.add_trace(go.Scatter(x=df.index, y=df["Close"], name="股價", line=dict(color="#333", width=1)))
            fig_pt.add_trace(go.Scatter(x=buys.index, y=buys["Close"], mode="markers", name="買進", marker=dict(symbol="triangle-up", color="blue", size=10)))
            fig_pt.add_trace(go.Scatter(x=sells.index, y=sells["Close"], mode="markers", name="賣出", marker=dict(symbol="triangle-down", color="red", size=10)))
            fig_pt.update_layout(height=450, template="plotly_white", hovermode="x unified", title="進出點位標記")
            st.plotly_chart(fig_pt, use_container_width=True)

        # 交易列表
        st.markdown("### 📋 歷年交易紀錄")
        
        trades = []
        temp_buy = None
        # 找出訊號轉換點
        signals = df[df["Position"] != df["Position"].shift(1)]
        
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
                .format({"買入價格":"{:.2f}", "賣出價格":"{:.2f}", "報酬率":"{:.2%}"})
                .background_gradient(cmap="RdYlGn", subset=["報酬率"]),
                use_container_width=True
            )
        else:
            st.info("區間內無完整交易紀錄 (可能一直持有或空手)")

        # 總結表格
        st.markdown("### 📊 詳細數據總結")
        comp_data = {
            "策略": ["景氣燈號策略", f"基準 ({ticker})"],
            "總報酬率": [res_s[0], res_b[0]],
            "CAGR (年化)": [res_s[1], res_b[1]],
            "最大回撤 (MDD)": [res_s[2], res_b[2]],
            "年化波動率": [res_s[3], res_b[3]],
            "夏普值 (Sharpe)": [res_s[4], res_b[4]]
        }
        df_comp = pd.DataFrame(comp_data).set_index("策略")
        
        st.dataframe(
            df_comp.style
            .format("{:.2%}", subset=["總報酬率", "CAGR (年化)", "最大回撤 (MDD)", "年化波動率"])
            .format("{:.2f}", subset=["夏普值 (Sharpe)"])
            .background_gradient(cmap="RdYlGn", subset=["總報酬率", "CAGR (年化)", "夏普值 (Sharpe)"])
            .background_gradient(cmap="RdYlGn_r", subset=["最大回撤 (MDD)", "年化波動率"]),
            use_container_width=True
        )
