###############################################################
# app.py — ETF SMA 策略戰情室 (通用版 - Bug修復)
###############################################################

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# 1. 頁面設定
st.set_page_config(
    page_title="ETF SMA 戰情室 (通用版)",
    layout="wide",
)

# ===============================================================
# 全域設定：ETF 對照表
# ===============================================================
ETF_MAPPING = {
    "🇹🇼 台股 - 0050 (元大台灣50)": {
        "symbol": "0050.TW",
        "leverage_options": {
            "00631L (元大台灣50正2)": "00631L.TW",
            "00663L (國泰臺灣加權正2)": "00663L.TW"
        }
    },
    "🇺🇸 美股 - QQQ (納斯達克100)": {
        "symbol": "QQQ",
        "leverage_options": {
            "QLD (ProShares 兩倍做多)": "QLD",
            "TQQQ (ProShares 三倍做多)": "TQQQ"
        }
    },
    "🇺🇸 美股 - SPY (標普500)": {
        "symbol": "SPY",
        "leverage_options": {
            "SSO (ProShares 兩倍做多)": "SSO",
            "UPRO (ProShares 三倍做多)": "UPRO"
        }
    },
    "🇺🇸 美股 - VTI (整體股市)": {
        "symbol": "VTI",
        "leverage_options": {
            "SSO (因無VTI正2，暫用SPY正2代替)": "SSO" 
        }
    }
}

with st.sidebar:
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.divider()

st.title("📊 原型 vs 槓桿 ETF — SMA 深度量化分析")

# ===============================================================
# 區塊 1: 標的選擇與區間偵測
# ===============================================================

sel_col1, sel_col2 = st.columns(2)

with sel_col1:
    proto_keys = list(ETF_MAPPING.keys())
    selected_proto_name = st.selectbox("原型 ETF (訊號來源)", proto_keys)
    proto_symbol = ETF_MAPPING[selected_proto_name]["symbol"]

with sel_col2:
    lev_options = ETF_MAPPING[selected_proto_name]["leverage_options"]
    selected_lev_name = st.selectbox("槓桿 ETF (實際進出場標的)", list(lev_options.keys()))
    lev_symbol = lev_options[selected_lev_name]

# ---------------------------------------------------------------
# 自動偵測可回測區間 (Metadata Fetch)
# ---------------------------------------------------------------
@st.cache_data(ttl=3600)
def get_common_date_range(sym1, sym2):
    try:
        df1 = yf.download(sym1, period="max", progress=False, auto_adjust=False)
        df2 = yf.download(sym2, period="max", progress=False, auto_adjust=False)
        
        if df1.empty or df2.empty:
            return None, None
            
        if isinstance(df1.columns, pd.MultiIndex): df1 = df1.xs("Close", axis=1, level=0, drop_level=True)
        if isinstance(df2.columns, pd.MultiIndex): df2 = df2.xs("Close", axis=1, level=0, drop_level=True)
        
        start1 = df1.index.min().date()
        start2 = df2.index.min().date()
        end1 = df1.index.max().date()
        end2 = df2.index.max().date()
        
        common_start = max(start1, start2)
        common_end = min(end1, end2)
        
        return common_start, common_end
    except Exception as e:
        return None, None

with st.spinner("正在偵測可回測區間..."):
    min_date, max_date = get_common_date_range(proto_symbol, lev_symbol)

if min_date and max_date:
    st.info(f"📌 **可回測區間** ： {min_date} ~ {max_date}")
    st.session_state['data_min_date'] = min_date
else:
    st.error("❌ 無法抓取標的資料，請確認代號正確或網路連線。")
    st.stop()

# ===============================================================
# 區塊 2: 日期選擇與按鈕控制 (Bug Fix 重點區)
# ===============================================================

# 1. 初始化 session_state
if 'start_date' not in st.session_state:
    st.session_state['start_date'] = pd.to_datetime("2015-01-01").date()
if 'end_date' not in st.session_state:
    st.session_state['end_date'] = pd.to_datetime("today").date()

# --- [關鍵修復] 強制校正日期範圍，防止報錯 ---
# 確保 start_date 不早於 min_date
if st.session_state['start_date'] < min_date:
    st.session_state['start_date'] = min_date

# 確保 end_date 不早於 min_date (防止切換到新上市股票時出錯)
if st.session_state['end_date'] < min_date:
    st.session_state['end_date'] = min_date

# 確保 end_date 不晚於 max_date
if st.session_state['end_date'] > max_date:
    st.session_state['end_date'] = max_date

# 確保 start_date 不晚於 end_date (邏輯保護)
if st.session_state['start_date'] > st.session_state['end_date']:
    st.session_state['start_date'] = min_date
# ---------------------------------------------

# 2. 定義更新日期的 Callback
def update_dates(years=None, is_all=False):
    today = pd.to_datetime("today").date()
    # 限制結束日期不超過資料極限
    effective_end = min(today, max_date) if max_date else today
    st.session_state['end_date'] = effective_end
    
    if is_all:
        available_min = st.session_state.get('data_min_date', min_date)
        st.session_state['start_date'] = available_min
    elif years:
        target_start = effective_end - pd.DateOffset(years=years)
        final_start = max(target_start.date(), min_date) if min_date else target_start.date()
        st.session_state['start_date'] = final_start

# 3. 顯示快速按鈕
st.subheader("🛠️ 參數設定")
btn_col1, btn_col2, btn_col3, btn_col4, btn_col5 = st.columns(5)

with btn_col1: st.button("一年", on_click=update_dates, kwargs={'years': 1}, use_container_width=True)
with btn_col2: st.button("三年", on_click=update_dates, kwargs={'years': 3}, use_container_width=True)
with btn_col3: st.button("五年", on_click=update_dates, kwargs={'years': 5}, use_container_width=True)
with btn_col4: st.button("十年", on_click=update_dates, kwargs={'years': 10}, use_container_width=True)
with btn_col5: st.button("全都要", on_click=update_dates, kwargs={'is_all': True}, use_container_width=True)

st.caption(f"📅 目前設定分析區間：{st.session_state['start_date']} — {st.session_state['end_date']}")

# 4. 表單與執行按鈕
with st.form("param_form"):
    c1, c2, c3 = st.columns(3)
    with c1:
        # 這裡會讀取已經「校正」過的 session_state，所以不會崩潰
        start_date = st.date_input("開始日期", key="start_date", min_value=min_date, max_value=max_date)
    with c2:
        end_date = st.date_input("結束日期", key="end_date", min_value=min_date, max_value=max_date)
    with c3:
        sma_window = st.number_input("SMA 均線週期 (日)", min_value=10, max_value=500, value=200, step=10)
    
    submitted = st.form_submit_button("🚀 開始量化回測", use_container_width=True)

# ===============================================================
# 資料處理與分析核心
# ===============================================================
@st.cache_data
def load_analysis_data(start, end, p_sym, l_sym):
    tickers = [p_sym, l_sym]
    try:
        raw = yf.download(tickers, start=start, end=end, auto_adjust=False, progress=False)
    except Exception:
        return None

    if raw.empty: return None

    df = pd.DataFrame()
    target_col = "Adj Close" if "Adj Close" in str(raw.columns) else "Close"
    
    try:
        if isinstance(raw.columns, pd.MultiIndex):
            if "Adj Close" in raw.columns.levels[0]:
                df = raw["Adj Close"].copy()
            elif "Close" in raw.columns.levels[0]:
                df = raw["Close"].copy()
            else:
                df = raw.xs(target_col, axis=1, level=0, drop_level=True)
        else:
            df = raw[[target_col]] if target_col in raw.columns else raw
    except:
        return None

    cols_map = {}
    for col in df.columns:
        col_str = str(col)
        clean_p = p_sym.replace(".TW", "")
        clean_l = l_sym.replace(".TW", "")
        
        if clean_p in col_str: cols_map[col] = "Base"
        elif clean_l in col_str: cols_map[col] = "Lev"
    
    df = df.rename(columns=cols_map)
    df = df.dropna()
    
    if "Base" not in df.columns or "Lev" not in df.columns:
        return None
        
    return df

if submitted:
    with st.spinner(f"正在計算 {selected_proto_name} vs {selected_lev_name} ..."):
        price = load_analysis_data(start_date, end_date, proto_symbol, lev_symbol)
        
        if price is None or price.empty:
            st.error("❌ 無法下載資料或資料不足，請檢查日期區間。")
        else:
            base_label = selected_proto_name.split(" ")[2]
            lev_label = selected_lev_name.split(" ")[0]

            # 1. 指標計算
            price["SMA_Base"] = price["Base"].rolling(sma_window).mean()
            price["SMA_Lev"]  = price["Lev"].rolling(sma_window).mean()
            price["Gap_Base"] = (price["Base"] - price["SMA_Base"]) / price["SMA_Base"]
            price["Gap_Lev"]  = (price["Lev"] - price["SMA_Lev"]) / price["SMA_Lev"]

            df = price.dropna().copy()
            
            st.success(f"✅ 分析完成！ 數據區間: {df.index.min().date()} ~ {df.index.max().date()} (共 {len(df)} 交易日)")

            # PART A: SMA Gap
            st.subheader(f"📉 SMA Gap 乖離率分佈圖 ({base_label} vs {lev_label})")
            fig_gap = go.Figure()
            fig_gap.add_trace(go.Scatter(x=df.index, y=df["Gap_Base"], name=f"{base_label} Gap%", line=dict(color='blue', width=1.5)))
            fig_gap.add_trace(go.Scatter(x=df.index, y=df["Gap_Lev"], name=f"{lev_label} Gap%", line=dict(color='red', width=1.5)))
            fig_gap.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.5)
            fig_gap.update_layout(title=f"與 {sma_window}SMA 的乖離程度比較", yaxis_tickformat=".1%", hovermode="x unified", height=400)
            st.plotly_chart(fig_gap, use_container_width=True)

            # PART B: 價格走勢
            st.subheader(f"📈 價格走勢對照")
            fig_price = make_subplots(specs=[[{"secondary_y": True}]])
            fig_price.add_trace(go.Scatter(x=df.index, y=df["Base"], name=f"{base_label} 收盤價", line=dict(color='rgba(0,0,255,0.5)', width=1)), secondary_y=False)
            fig_price.add_trace(go.Scatter(x=df.index, y=df["SMA_Base"], name=f"{base_label} SMA", line=dict(color='blue', width=2)), secondary_y=False)
            fig_price.add_trace(go.Scatter(x=df.index, y=df["Lev"], name=f"{lev_label} 收盤價", line=dict(color='rgba(255,0,0,0.5)', width=1)), secondary_y=True)
            fig_price.add_trace(go.Scatter(x=df.index, y=df["SMA_Lev"], name=f"{lev_label} SMA", line=dict(color='red', width=2)), secondary_y=True)
            fig_price.update_layout(title_text=f"左軸: {base_label} / 右軸: {lev_label}", hovermode="x unified", height=500)
            st.plotly_chart(fig_price, use_container_width=True)

            # PART C: 穿越統計
            st.subheader("⏱️ 穿越延遲時間統計 (Time Lag Analysis)")
            bull_Base = df["Base"] > df["SMA_Base"]
            bull_Lev  = df["Lev"] > df["SMA_Lev"]

            cross_up_Base = df[(bull_Base) & (~bull_Base.shift(1).fillna(True))].index
            cross_up_Lev  = df[(bull_Lev) & (~bull_Lev.shift(1).fillna(True))].index
            cross_dn_Base = df[(~bull_Base) & (bull_Base.shift(1).fillna(False))].index
            cross_dn_Lev  = df[(~bull_Lev) & (bull_Lev.shift(1).fillna(False))].index

            def calc_lag_stats(base_dates, target_dates):
                lags = []
                for d in base_dates:
                    candidates = [t for t in target_dates if abs((t - d).days) <= 60]
                    if candidates:
                        nearest = min(candidates, key=lambda x: abs((x - d).days))
                        diff = (nearest - d).days
                        lags.append(diff)
                if not lags: return 0, 0
                return np.mean(lags), len(lags)

            lag_up_val, count_up = calc_lag_stats(cross_up_Base, cross_up_Lev)
            lag_dn_val, count_dn = calc_lag_stats(cross_dn_Base, cross_dn_Lev)

            c_stat1, c_stat2 = st.columns(2)
            with c_stat1:
                st.markdown("### 🔻 下跌趨勢 (跌破 SMA)")
                if lag_dn_val < 0: status = f"⚡ {lev_label} 提早 {abs(lag_dn_val):.1f} 天"
                else: status = f"🐢 {lev_label} 延遲 {lag_dn_val:.1f} 天"
                st.info(f"**統計 {count_dn} 次事件:**\n### {status}")

            with c_stat2:
                st.markdown("### 🚀 上漲趨勢 (突破 SMA)")
                if lag_up_val > 0:
                    status = f"🐢 {lev_label} 延遲 {lag_up_val:.1f} 天"
                    color = "orange"
                else:
                    status = f"⚡ {lev_label} 提早 {abs(lag_up_val):.1f} 天"
                    color = "blue"
                st.warning(f"**統計 {count_up} 次事件:**\n### {status}")

            st.table(pd.DataFrame({
                "事件": [f"{lev_label} 跌破", f"{lev_label} 突破"],
                "基準": [f"{base_label} 跌破時", f"{base_label} 突破時"],
                "平均時差": [f"{lag_dn_val:.1f} 天", f"{lag_up_val:.1f} 天"]
            }))

else:
    st.info("👆 請選擇上方標的與參數，並點擊「🚀 開始量化回測」")
