###############################################################
# app.py — 0050 vs 00631L SMA 策略機率統計 & 延遲分析
###############################################################

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 頁面設定
st.set_page_config(
    page_title="0050 vs 00631L SMA 戰情室",
    layout="wide",

)
with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")
     
st.title("📊 0050 vs 00631L — SMA 深度量化分析")

# 2. 上方控制面板
with st.form("param_form"):
    st.subheader("🛠️ 參數設定")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        start_date = st.date_input("開始日期", pd.to_datetime("2015-01-01"))
    with c2:
        end_date = st.date_input("結束日期", pd.to_datetime("today"))
    with c3:
        sma_window = st.number_input("SMA 均線週期 (日)", min_value=10, max_value=500, value=200, step=10)
    
    submitted = st.form_submit_button("🚀 開始量化回測", use_container_width=True)

###############################################################
# 資料下載函數
###############################################################
@st.cache_data
def load_data(start, end):
    tickers = ["0050.TW", "00631L.TW"]
    try:
        raw = yf.download(tickers, start=start, end=end, auto_adjust=False)
    except Exception:
        return None

    if raw.empty:
        return None

    df = pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        try:
            if "Adj Close" in raw.columns.levels[0]:
                df = raw["Adj Close"].copy()
            elif "Close" in raw.columns.levels[0]:
                df = raw["Close"].copy()
            else:
                df = raw.xs("Adj Close", axis=1, level=0, drop_level=True)
        except:
            try:
                df = raw.xs("Close", axis=1, level=0, drop_level=True)
            except:
                return None
    else:
        if "Adj Close" in raw.columns:
            df = raw[["Adj Close"]]
        elif "Close" in raw.columns:
            df = raw[["Close"]]
        else:
            df = raw
            
    cols_map = {}
    for col in df.columns:
        if "0050" in str(col): cols_map[col] = "0050"
        elif "00631L" in str(col): cols_map[col] = "00631L"
    
    df = df.rename(columns=cols_map).dropna()
    
    if "0050" not in df.columns or "00631L" not in df.columns:
        return None
        
    return df

###############################################################
# 核心邏輯
###############################################################
if submitted:
    with st.spinner("正在進行 Quant 運算..."):
        price = load_data(start_date, end_date)
        
        if price is None or price.empty:
            st.error("❌ 無法下載資料，請檢查日期區間或網路連線。")
        else:
            # 1. 基礎指標計算
            price["SMA_50"] = price["0050"].rolling(sma_window).mean()
            price["SMA_L"]  = price["00631L"].rolling(sma_window).mean()
            
            # 計算 Gap (乖離率)
            price["Gap_50"] = (price["0050"] - price["SMA_50"]) / price["SMA_50"]
            price["Gap_L"]  = (price["00631L"] - price["SMA_L"]) / price["SMA_L"]

            df = price.dropna().copy()
            
            st.success(f"✅ 數據區間: {df.index.min().date()} ~ {df.index.max().date()} (共 {len(df)} 交易日)")

            # ==========================================
            # PART A: SMA Gap 分佈圖 (乖離率視覺化)
            # ==========================================
            st.subheader("📉 SMA Gap 乖離率分佈圖 (距離均線 %)")
            st.markdown("""
            此圖呈現 **「價格距離 200SMA 的百分比」**。
            - **0 軸**：代表價格剛好在均線上（穿越點）。
            - 觀察重點：誰的線先穿過 0 軸？以及兩者的開口大小。
            """)
            
            fig_gap = go.Figure()
            fig_gap.add_trace(go.Scatter(x=df.index, y=df["Gap_50"], name="0050 Gap%", 
                                         line=dict(color='blue', width=1.5)))
            fig_gap.add_trace(go.Scatter(x=df.index, y=df["Gap_L"], name="00631L Gap%", 
                                         line=dict(color='red', width=1.5)))
            
            # 加入 0 軸參考線
            fig_gap.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.5)
            
            fig_gap.update_layout(
                title="與 200SMA 的乖離程度比較 (大於0=多頭, 小於0=空頭)",
                yaxis_tickformat=".1%",
                hovermode="x unified",
                height=400
            )
            st.plotly_chart(fig_gap, use_container_width=True)

            # ==========================================
            # PART B: 原始價格與 SMA 走勢對照 (新增圖表)
            # ==========================================
            st.subheader(f"📈 原始價格與 {sma_window}SMA 走勢對照")
            
            fig_price = make_subplots(specs=[[{"secondary_y": True}]])
            
            # 0050 (左軸)
            fig_price.add_trace(go.Scatter(
                x=df.index, y=df["0050"], name="0050 收盤價",
                line=dict(color='rgba(0,0,255,0.5)', width=1)), secondary_y=False)
            fig_price.add_trace(go.Scatter(
                x=df.index, y=df["SMA_50"], name=f"0050 SMA",
                line=dict(color='blue', width=2)), secondary_y=False)
            
            # 00631L (右軸)
            fig_price.add_trace(go.Scatter(
                x=df.index, y=df["00631L"], name="00631L 收盤價",
                line=dict(color='rgba(255,0,0,0.5)', width=1)), secondary_y=True)
            fig_price.add_trace(go.Scatter(
                x=df.index, y=df["SMA_L"], name=f"00631L SMA",
                line=dict(color='red', width=2)), secondary_y=True)
            
            fig_price.update_layout(
                title_text="雙軸價格走勢圖 (左軸: 0050 / 右軸: 00631L)",
                hovermode="x unified",
                height=500
            )
            fig_price.update_yaxes(title_text="0050 價格", secondary_y=False)
            fig_price.update_yaxes(title_text="00631L 價格", secondary_y=True)
            
            st.plotly_chart(fig_price, use_container_width=True)

            # ==========================================
            # PART C: 穿越時間差統計 (Lag Analysis)
            # ==========================================
            st.subheader("⏱️ 穿越延遲時間統計 (Time Lag Analysis)")
            st.markdown("計算當 0050 發生穿越訊號時，00631L 是**提早 (Lead)** 還是 **延遲 (Lag)** 發生。")

            # 1. 偵測穿越點
            # True if Price > SMA
            bull_50 = df["0050"] > df["SMA_50"]
            bull_L  = df["00631L"] > df["SMA_L"]

            # 向上突破 (前一天 False, 今天 True)
            cross_up_50 = df[(bull_50) & (~bull_50.shift(1).fillna(True))].index
            cross_up_L  = df[(bull_L) & (~bull_L.shift(1).fillna(True))].index

            # 向下跌破 (前一天 True, 今天 False)
            cross_dn_50 = df[(~bull_50) & (bull_50.shift(1).fillna(False))].index
            cross_dn_L  = df[(~bull_L) & (bull_L.shift(1).fillna(False))].index

            # 2. 配對演算法 (以 0050 為基準，找前後 60 天內最近的 00631L 事件)
            def calc_lag_stats(base_dates, target_dates, event_name):
                lags = []
                for d in base_dates:
                    # 找前後 60 天內的配對
                    candidates = [t for t in target_dates if abs((t - d).days) <= 60]
                    if candidates:
                        # 找最近的一天
                        nearest = min(candidates, key=lambda x: abs((x - d).days))
                        # 差距 = Target(L) - Base(50)
                        # 負值 = L 日期較小 = L 提早發生
                        # 正值 = L 日期較大 = L 延遲發生
                        diff = (nearest - d).days
                        lags.append(diff)
                
                if not lags:
                    return 0, 0, "無事件"
                
                avg_lag = np.mean(lags)
                count = len(lags)
                return avg_lag, count, lags

            # 計算統計
            lag_up_val, count_up, lags_up = calc_lag_stats(cross_up_50, cross_up_L, "向上突破")
            lag_dn_val, count_dn, lags_dn = calc_lag_stats(cross_dn_50, cross_dn_L, "向下跌破")

            # 3. 呈現結果表格
            col_stat1, col_stat2 = st.columns(2)
            
            with col_stat1:
                st.markdown("### 🔻 下跌趨勢 (跌破 200SMA)")
                
                status_text = ""
                if lag_dn_val < 0:
                    status_text = f"⚡ 00631L 平均 **提早 {abs(lag_dn_val):.1f} 天** 轉空"
                    color = "red"
                else:
                    status_text = f"🐢 00631L 平均 **延遲 {lag_dn_val:.1f} 天** 轉空"
                    color = "green"
                    
                st.info(f"""
                **統計結果 ({count_dn} 次事件):**
                
                ### {status_text}
                
                (負值代表 00631L 對下跌更敏感)
                """)

            with col_stat2:
                st.markdown("### 🚀 上漲趨勢 (突破 200SMA)")
                
                status_text = ""
                if lag_up_val > 0:
                    status_text = f"🐢 00631L 平均 **延遲 {lag_up_val:.1f} 天** 轉多"
                    color = "orange" # Warning color
                else:
                    status_text = f"⚡ 00631L 平均 **提早 {abs(lag_up_val):.1f} 天** 轉多"
                    color = "blue"
                
                st.warning(f"""
                **統計結果 ({count_up} 次事件):**
                
                ### {status_text}
                
                (正值代表 00631L 需要更多時間修復均線)
                """)

            # 詳細數據表格
            st.markdown("#### 📜 穿越事件詳細數據")
            summary_data = {
                "事件類型": ["00631L 跌破 200SMA", "00631L 突破 200SMA"],
                "基準 (0050)": ["0050 跌破時", "0050 突破時"],
                "平均時間差 (天)": [f"{lag_dn_val:.1f} 天", f"{lag_up_val:.1f} 天"],
                "量化解讀": [
                    "00631L 因槓桿放大跌幅，通常會**先跌破**均線 (負值)",
                    "00631L 因波動耗損，通常需**更久**才能漲回均線 (正值)"
                ]
            }
            st.table(pd.DataFrame(summary_data))

            # ==========================================
            # 簡單總結
            # ==========================================
            st.markdown("---")
            st.info("""
            **🎯 最終量化結論：**
            1. **下跌不對稱性**：從 Gap 圖可見，00631L 下跌時乖離率擴大極快，導致它比 0050 更早跌破均線（保護機制反應快）。
            2. **上漲滯後性**：0050 穿越 0 軸轉正時，00631L 往往還在水下（Gap < 0），這就是著名的「波動率拖累 (Volatility Drag)」。
            3. **操作啟示**：若以 200SMA 為進出依據，操作 00631L 會比 0050 頻繁停損（早破），且較晚進場（晚穿）。
            """)

else:
    st.info("👆 請在上方設定參數，並點擊「🚀 開始量化回測」按鈕以查看報告。")
