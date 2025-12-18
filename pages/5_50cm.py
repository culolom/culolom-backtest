import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# 1. 頁面設定
st.set_page_config(
    page_title="ETF SMA 戰情室 (量化分析版)",
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
    "GD 黃金 - 00635U (期元大S&P黃金)": {
        "symbol": "00635U.TW",
        "leverage_options": {
            "00708L (期元大S&P黃金正2)": "00708L.TW" 
        }
    }
}

with st.sidebar:
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.divider()

st.title("📊 ETF 多維度量化分析戰情室")

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

@st.cache_data(ttl=3600)
def get_common_date_range(sym1, sym2):
    try:
        df1 = yf.download(sym1, period="max", progress=False, auto_adjust=False)
        df2 = yf.download(sym2, period="max", progress=False, auto_adjust=False)
        if df1.empty or df2.empty: return None, None
        common_start = max(df1.index.min().date(), df2.index.min().date())
        common_end = min(df1.index.max().date(), df2.index.max().date())
        return common_start, common_end
    except:
        return None, None

with st.spinner("正在偵測可回測區間..."):
    min_date, max_date = get_common_date_range(proto_symbol, lev_symbol)

if not min_date:
    st.error("❌ 無法抓取標的資料，請確認網路連線。")
    st.stop()

st.info(f"📌 **可分析區間** ： {min_date} ~ {max_date}")

# ===============================================================
# 區塊 2: 日期與參數設定
# ===============================================================
if 'start_date' not in st.session_state: st.session_state['start_date'] = max_date - pd.DateOffset(years=3)
if 'end_date' not in st.session_state: st.session_state['end_date'] = max_date

def update_dates(years=None, is_all=False):
    st.session_state['end_date'] = max_date
    if is_all: st.session_state['start_date'] = min_date
    elif years: st.session_state['start_date'] = max(max_date - pd.DateOffset(years=years), min_date)

st.subheader("🛠️ 參數設定")
btn_cols = st.columns(5)
with btn_cols[0]: st.button("一年", on_click=update_dates, kwargs={'years': 1}, use_container_width=True)
with btn_cols[1]: st.button("三年", on_click=update_dates, kwargs={'years': 3}, use_container_width=True)
with btn_cols[2]: st.button("五年", on_click=update_dates, kwargs={'years': 5}, use_container_width=True)
with btn_cols[3]: st.button("十年", on_click=update_dates, kwargs={'years': 10}, use_container_width=True)
with btn_cols[4]: st.button("全都要", on_click=update_dates, kwargs={'is_all': True}, use_container_width=True)

with st.form("param_form"):
    c1, c2, c3 = st.columns(3)
    with c1: start_date = st.date_input("開始日期", key="start_date", min_value=min_date, max_value=max_date)
    with c2: end_date = st.date_input("結束日期", key="end_date", min_value=min_date, max_value=max_date)
    with c3: sma_window = st.number_input("SMA 均線週期 (日)", min_value=10, max_value=500, value=200, step=10)
    submitted = st.form_submit_button("🚀 開始量化分析", use_container_width=True)

# ===============================================================
# 區塊 3: 資料處理與繪圖
# ===============================================================
@st.cache_data
def load_analysis_data(start, end, p_sym, l_sym):
    # 下載時多抓一年份資料，以計算移動平均與年報酬率
    extended_start = pd.to_datetime(start) - pd.DateOffset(days=500)
    raw = yf.download([p_sym, l_sym], start=extended_start, end=end, progress=False)
    if raw.empty: return None
    
    # 簡化欄位處理 (支援 MultiIndex)
    df = raw['Adj Close'] if 'Adj Close' in raw.columns else raw['Close']
    df = df.rename(columns={p_sym: "Base", l_sym: "Lev"}).dropna()
    return df

if submitted:
    with st.spinner("分析中..."):
        price = load_analysis_data(start_date, end_date, proto_symbol, lev_symbol)
        
        if price is not None and not price.empty:
            base_label = selected_proto_name.split(" ")[2]
            lev_label = selected_lev_name.split(" ")[0]

            # 計算指標
            price["SMA_Base"] = price["Base"].rolling(sma_window).mean()
            price["SMA_Lev"]  = price["Lev"].rolling(sma_window).mean()
            price["Gap_Base"] = (price["Base"] - price["SMA_Base"]) / price["SMA_Base"]
            price["Gap_Lev"]  = (price["Lev"] - price["SMA_Lev"]) / price["SMA_Lev"]
            price["Ret12M_Base"] = price["Base"].pct_change(periods=252) * 100
            price["Ret12M_Lev"] = price["Lev"].pct_change(periods=252) * 100

            # 裁切回使用者選擇的日期區間
            df = price.loc[pd.to_datetime(start_date):].copy()

            # --- 圖表 1: SMA Gap 乖離率 ---
            st.subheader("📉 SMA Gap 乖離率分佈圖")
            fig_gap = go.Figure()
            fig_gap.add_trace(go.Scatter(x=df.index, y=df["Gap_Base"], name=f"{base_label} Gap%", line=dict(color='blue', width=1.5)))
            fig_gap.add_trace(go.Scatter(x=df.index, y=df["Gap_Lev"], name=f"{lev_label} Gap%", line=dict(color='red', width=1.5)))
            fig_gap.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.5)
            fig_gap.update_layout(yaxis_tickformat=".1%", hovermode="x unified", height=350)
            st.plotly_chart(fig_gap, use_container_width=True)

            # --- 圖表 2: 絕對價格與 SMA (雙軸) ---
            st.subheader("📈 價格走勢與 SMA 對照 (絕對價格)")
            fig_p = make_subplots(specs=[[{"secondary_y": True}]])
            fig_p.add_trace(go.Scatter(x=df.index, y=df["Base"], name=f"{base_label} 價", line=dict(color='rgba(0,0,255,0.3)', width=1)), secondary_y=False)
            fig_p.add_trace(go.Scatter(x=df.index, y=df["SMA_Base"], name=f"{base_label} SMA", line=dict(color='blue', width=2.5)), secondary_y=False)
            fig_p.add_trace(go.Scatter(x=df.index, y=df["Lev"], name=f"{lev_label} 價", line=dict(color='rgba(255,0,0,0.3)', width=1)), secondary_y=True)
            fig_p.add_trace(go.Scatter(x=df.index, y=df["SMA_Lev"], name=f"{lev_label} SMA", line=dict(color='red', width=2.5)), secondary_y=True)
            fig_p.update_layout(hovermode="x unified", height=450, title=f"左軸: {base_label} / 右軸: {lev_label}")
            st.plotly_chart(fig_p, use_container_width=True)

            # --- 圖表 3: 歸一化起跑點對齊圖 (單軸) ---
            st.subheader("🏁 累計漲幅對照 (第一天起點 = 100)")
            df_norm = df.copy()
            b0, l0 = df_norm["Base"].iloc[0], df_norm["Lev"].iloc[0]
            fig_norm = go.Figure()
            fig_norm.add_trace(go.Scatter(x=df_norm.index, y=(df_norm["Base"]/b0)*100, name=f"{base_label} 累計", line=dict(color='blue')))
            fig_norm.add_trace(go.Scatter(x=df_norm.index, y=(df_norm["Lev"]/l0)*100, name=f"{lev_label} 累計", line=dict(color='red')))
            fig_norm.update_layout(hovermode="x unified", height=450, yaxis_title="指數化價格 (起始=100)")
            st.plotly_chart(fig_norm, use_container_width=True)

            # --- 圖表 4: 12 個月滾動報酬率 (雙軸) ---
            st.subheader("📊 近 12 個月滾動報酬率對照 (年報酬走勢)")
            fig_ret = make_subplots(specs=[[{"secondary_y": True}]])
            fig_ret.add_trace(go.Scatter(x=df.index, y=df["Ret12M_Base"], name=f"{base_label} 12M%", line=dict(color='blue', dash='dot')), secondary_y=False)
            fig_ret.add_trace(go.Scatter(x=df.index, y=df["Ret12M_Lev"], name=f"{lev_label} 12M%", line=dict(color='red')), secondary_y=True)
            fig_ret.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.3)
            fig_ret.update_layout(hovermode="x unified", height=450, title="越過 0 代表年度轉正獲利")
            fig_ret.update_yaxes(title_text=f"{base_label} 報酬(%)", secondary_y=False)
            fig_ret.update_yaxes(title_text=f"{lev_label} 報酬(%)", secondary_y=True)
            st.plotly_chart(fig_ret, use_container_width=True)

        else:
            st.error("❌ 無法讀取選定區間的資料。")
else:
    st.info("👆 請設定參數後點擊執行按鈕")
