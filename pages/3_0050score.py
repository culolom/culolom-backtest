###############################################################
# pages/4_Macro_Strategy.py — 國發會景氣燈號策略
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
# 設定
###############################################################
st.set_page_config(page_title="景氣燈號策略", page_icon="🚦", layout="wide")

DATA_DIR = Path("data")

# Sidebar
with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

st.markdown("<h1 style='margin-bottom:0.1em;'>🚦 國發會景氣燈號策略 (Macro Strategy)</h1>", unsafe_allow_html=True)
st.caption("股市名言：「藍燈買股票，紅燈數鈔票」。利用總體經濟指標進行逆勢操作。")
st.divider()

###############################################################
# 資料讀取函式
###############################################################


def load_csv(symbol: str) -> pd.DataFrame:
    # 1. 模糊比對檔名 (支援大小寫與 .TW)
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
        # 2. 先讀取，不強制 parse_dates (避免報錯)
        df = pd.read_csv(path)
        
        # 3. 智慧修正：處理「日期」欄位
        # 如果沒有叫做 'Date' 的欄位，我們就假設「第一欄」是日期
        if "Date" not in df.columns:
            # 把第一欄強制改名為 'Date'
            df = df.rename(columns={df.columns[0]: "Date"})
            
        # 4. 智慧修正：處理「分數/價格」欄位
        # 尋找看起來像價格的欄位
        target_col = None
        
        # 優先順序：Adj Close > Close > Score > Price
        priority_cols = ["Adj Close", "Close", "Score", "Price"]
        for pc in priority_cols:
            if pc in df.columns:
                target_col = pc
                break
        
        # 如果都沒找到，開始找中文關鍵字 (針對景氣分數檔)
        if target_col is None:
            for c in df.columns:
                if "分數" in str(c) or "信號" in str(c) or "score" in str(c).lower():
                    target_col = c
                    break
        
        # 如果還是沒找到，就假設是「最後一欄」 (通常 CSV 最後一欄是數值)
        if target_col is None and len(df.columns) > 1:
            target_col = df.columns[-1]
            
        if target_col is None:
            return pd.DataFrame()

        # 5. 資料清洗與索引設定
        df["Date"] = pd.to_datetime(df["Date"], errors='coerce') # 強制轉日期，錯誤變 NaT
        df = df.dropna(subset=["Date"]) # 刪除日期無效的行 (例如多餘的標題列)
        df = df.set_index("Date").sort_index()
        
        # 統一將數據欄位改名為 "Price" 方便後續計算
        # 強制轉為數字 (處理 '原始數值' 這種文字干擾)
        df["Price"] = pd.to_numeric(df[target_col], errors='coerce')
        df = df.dropna(subset=["Price"]) # 刪除非數字的資料
            
        return df[["Price"]]
        
    except Exception as e:
        print(f"❌ 讀取 {symbol} 失敗: {e}")
        return pd.DataFrame()

###############################################################
# UI 參數設定
###############################################################

col1, col2 = st.columns(2)
with col1:
    ticker = st.text_input("交易標的 (預設 0050)", value="0050.TW")
with col2:
    score_file = st.text_input("景氣分數 CSV 檔名 (不含 .csv)", value="SCORE")

with st.expander("⚙️ 策略參數與燈號定義", expanded=True):
    c1, c2, c3 = st.columns(3)
    with c1:
        buy_threshold = st.number_input("🔵 買進門檻 (分數 <= ?)", 9, 45, 16, help="藍燈區間通常為 9-16 分。低於此分數分批買進。")
    with c2:
        sell_threshold = st.number_input("🔴 賣出門檻 (分數 >= ?)", 9, 45, 32, help="黃紅燈(32-37)或紅燈(38-45)。高於此分數開始減碼或出清。")
    with c3:
        # 關鍵參數：訊號延遲
        lag_months = st.number_input("⏳ 訊號延遲 (月)", 0, 3, 1, help="避免「看圖說故事」。1月的景氣分數通常在2月底才公佈，因此回測時必須延遲 1 個月才能買賣，否則就是作弊。")

    col_d1, col_d2, col_d3 = st.columns(3)
    with col_d1:
        start_date = st.date_input("開始日期", value=dt.date(2003, 1, 1)) # 0050 成立於 2003
    with col_d2:
        end_date = st.date_input("結束日期", value=dt.date.today())
    with col_d3:
        initial_capital = st.number_input("初始本金", value=1_000_000, step=100_000)

###############################################################
# 回測核心邏輯
###############################################################

if st.button("開始回測 🚀", type="primary", use_container_width=True):
    with st.spinner("正在整合數據與計算訊號..."):
        # 1. 讀取資料
        df_price = load_csv(ticker)
        df_score = load_csv(score_file)

        if df_price.empty:
            st.error(f"❌ 找不到 {ticker}.csv，請確認 data 資料夾。")
            st.stop()
        if df_score.empty:
            st.error(f"❌ 找不到 {score_file}.csv，請確認 data 資料夾。")
            st.stop()

        # 2. 時間對齊
        # 截取使用者選擇的時間段
        df_price = df_price.loc[str(start_date):str(end_date)]
        
        if df_price.empty:
            st.error("選定區間無股價資料。")
            st.stop()

        # 3. 合併資料 (Resample: Month to Day)
        # 建立一個主表，以股價的日資料為準
        df = df_price.rename(columns={"Price": "Close"}).copy()
        
        # 處理分數資料：
        # 景氣分數是「月資料」，通常標示為該月1號 (例如 2024-01-01)
        # 我們使用 reindex + ffill (前值填充) 將其擴展到每一天
        # 例如：1/1 是 20分，那 1/2 ~ 1/31 每天都視為 20分
        df_score_daily = df_score.reindex(df.index, method='ffill')
        
        # 將分數併入主表
        df["Score_Raw"] = df_score_daily["Price"]
        
        # 4. 處理「公告延遲 (Lag)」
        # 重要：如果是 Lag=1，代表 2/1 才能看到 1/1 的分數
        # 我們簡單用「交易日」來推算，一個月約 20~22 交易日
        shift_days = int(lag_months * 22)
        df["Score_Signal"] = df["Score_Raw"].shift(shift_days)
        
        # 去除因為 Shift 產生的空值
        df = df.dropna()

        # 5. 產生買賣訊號
        # 1 = 持有, 0 = 空手
        position = 0
        pos_list = []
        
        for i in range(len(df)):
            score = df["Score_Signal"].iloc[i]
            
            # 進場邏輯：分數掉入藍燈區 (<= 16)
            if score <= buy_threshold:
                position = 1
            # 出場邏輯：分數衝上紅燈區 (>= 32)
            elif score >= sell_threshold:
                position = 0
            # 中間區間 (黃綠燈)：維持原狀 (Hold)
            
            pos_list.append(position)
            
        df["Position"] = pos_list
        
        # 6. 計算績效
        df["Ret"] = df["Close"].pct_change().fillna(0)
        # 策略報酬 = 昨天的持倉狀態 * 今天的漲跌幅
        df["Strategy_Ret"] = df["Position"].shift(1) * df["Ret"]
        
        # 資金曲線
        df["Equity_Strategy"] = initial_capital * (1 + df["Strategy_Ret"]).cumprod()
        df["Equity_Benchmark"] = initial_capital * (1 + df["Ret"]).cumprod() # 買入持有

        # ----------------------------------------------
        # 視覺化展示
        # ----------------------------------------------
        
        # 計算 KPI
        def calc_kpi(series):
            total_ret = (series.iloc[-1] / initial_capital) - 1
            days = (series.index[-1] - series.index[0]).days
            cagr = (1 + total_ret) ** (365 / days) - 1 if days > 0 else 0
            mdd = (series / series.cummax() - 1).min()
            return total_ret, cagr, mdd

        ret_str, cagr_str, mdd_str = calc_kpi(df["Equity_Strategy"])
        ret_bch, cagr_bch, mdd_bch = calc_kpi(df["Equity_Benchmark"])

        # KPI 卡片
        kpi_cols = st.columns(4)
        with kpi_cols[0]: st.metric("期末總資產", f"${df['Equity_Strategy'].iloc[-1]:,.0f}", f"vs 買進持有: ${df['Equity_Benchmark'].iloc[-1]:,.0f}")
        with kpi_cols[1]: st.metric("總報酬率", f"{ret_str:.1%}", f"差額: {(ret_str-ret_bch):.1%}")
        with kpi_cols[2]: st.metric("年化報酬 (CAGR)", f"{cagr_str:.1%}", f"基準: {cagr_bch:.1%}")
        with kpi_cols[3]: st.metric("最大回撤 (MDD)", f"{mdd_str:.1%}", f"基準: {mdd_bch:.1%}", delta_color="inverse")

        st.markdown("---")

        # 圖表 1: 資金曲線
        tab1, tab2 = st.tabs(["💰 資金成長曲線", "🚦 買賣點與燈號"])
        
        with tab1:
            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Strategy"], name="景氣燈號策略", line=dict(color="#00C853", width=2)))
            fig_eq.add_trace(go.Scatter(x=df.index, y=df["Equity_Benchmark"], name="買進持有 (0050)", line=dict(color="gray", width=1, dash='dot')))
            fig_eq.update_layout(height=450, template="plotly_white", hovermode="x unified", title="策略 vs 大盤 績效比較")
            st.plotly_chart(fig_eq, use_container_width=True)

        with tab2:
            # 準備買賣點資料
            # 買點：今天 Position=1 且 昨天=0
            buys = df[(df["Position"] == 1) & (df["Position"].shift(1) == 0)]
            # 賣點：今天 Position=0 且 昨天=1
            sells = df[(df["Position"] == 0) & (df["Position"].shift(1) == 1)]

            fig_sig = go.Figure()

            # 股價線
            fig_sig.add_trace(go.Scatter(x=df.index, y=df["Close"], name="股價", line=dict(color="#333", width=1.5)))

            # 標記買賣點
            fig_sig.add_trace(go.Scatter(
                x=buys.index, y=buys["Close"], mode="markers", name="買進 (藍燈)",
                marker=dict(symbol="triangle-up", size=12, color="blue", line=dict(width=1, color="white"))
            ))
            fig_sig.add_trace(go.Scatter(
                x=sells.index, y=sells["Close"], mode="markers", name="賣出 (紅燈)",
                marker=dict(symbol="triangle-down", size=12, color="red", line=dict(width=1, color="white"))
            ))

            # 加上景氣分數背景 (使用 Heatmap 或區間)
            # 這裡我們用「副圖」來畫分數，比較清晰
            
            fig_sig.update_layout(height=400, template="plotly_white", hovermode="x unified", title="進出場點位回顧")
            st.plotly_chart(fig_sig, use_container_width=True)
            
            # 副圖：景氣分數
            fig_score = go.Figure()
            fig_score.add_trace(go.Scatter(x=df.index, y=df["Score_Signal"], name="景氣分數 (已延遲)", line=dict(color="orange")))
            
            # 畫出燈號區間 (背景色帶)
            # 藍燈 (<=16)
            fig_score.add_hrect(y0=9, y1=16, fillcolor="blue", opacity=0.1, layer="below", annotation_text="藍燈 (買)")
            # 紅燈 (>=38, 這裡畫到32當作警戒)
            fig_score.add_hrect(y0=32, y1=37, fillcolor="orange", opacity=0.1, layer="below", annotation_text="黃紅")
            fig_score.add_hrect(y0=38, y1=55, fillcolor="red", opacity=0.1, layer="below", annotation_text="紅燈 (賣)")
            
            # 門檻線
            fig_score.add_hline(y=buy_threshold, line_dash="dash", line_color="blue")
            fig_score.add_hline(y=sell_threshold, line_dash="dash", line_color="red")
            
            fig_score.update_layout(height=250, template="plotly_white", title="景氣對策信號走勢", yaxis=dict(range=[9, 45]))
            st.plotly_chart(fig_score, use_container_width=True)

        # 詳細數據表
        st.markdown("### 📋 歷年交易紀錄")
        trades = pd.concat([
            buys["Close"].rename("買入價格"),
            sells["Close"].rename("賣出價格")
        ], axis=1).sort_index()
        
        # 整理成表格
        trade_list = []
        # 簡單配對邏輯 (僅供參考)
        temp_buy = None
        for date, row in trades.iterrows():
            if not pd.isna(row["買入價格"]):
                temp_buy = (date, row["買入價格"])
            elif not pd.isna(row["賣出價格"]) and temp_buy:
                buy_date, buy_price = temp_buy
                sell_price = row["賣出價格"]
                ret = (sell_price - buy_price) / buy_price
                trade_list.append({
                    "買入日期": buy_date.strftime("%Y-%m-%d"),
                    "買入價格": buy_price,
                    "賣出日期": date.strftime("%Y-%m-%d"),
                    "賣出價格": sell_price,
                    "報酬率": ret
                })
                temp_buy = None
        
        if trade_list:
            df_trades = pd.DataFrame(trade_list)
            st.dataframe(
                df_trades.style.format({
                    "買入價格": "{:.2f}", 
                    "賣出價格": "{:.2f}", 
                    "報酬率": "{:.2%}"
                }).background_gradient(cmap="RdYlGn", subset=["報酬率"]),
                use_container_width=True
            )
        else:
            st.info("區間內無完整買賣交易紀錄 (可能一直持有或空手)")
