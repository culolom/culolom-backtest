import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
from pathlib import Path

# --- 1. 基礎與頁面設定 ---
st.set_page_config(page_title="倉鼠量化戰情室 - 動能旋轉", page_icon="🐹", layout="wide")

# 🔒 驗證 (請確保 auth.py 存在)
try:
    import auth
    if not auth.check_password():
        st.stop()
except:
    pass

# --- 2. 標的配置 (統一使用 .TW 後綴符合你的 GitHub 結構) ---
ETF_CONFIG = {
    "台股大盤 (0050 / 00631L)": {"base": "0050.TW", "lev": "00631L.TW"},
    "NASDAQ 100 (00662 / 00670L)": {"base": "00662.TW", "lev": "00670L.TW"},
    "S&P 500 (00646 / 00647L)": {"base": "00646.TW", "lev": "00647L.TW"}
}

DATA_DIR = Path("data")
if not DATA_DIR.exists():
    DATA_DIR.mkdir()

# --- 3. 工具函式：自動檢查並下載缺失資料 ---
def get_data(symbol):
    file_path = DATA_DIR / f"{symbol}.csv"
    
    # 如果檔案不存在，立即從 yfinance 下載
    if not file_path.exists():
        with st.status(f"📥 正在補齊缺失資料: {symbol}...", expanded=False):
            df = yf.download(symbol, period="max")
            if not df.empty:
                # 處理 yfinance 可能產生的 MultiIndex
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df.to_csv(file_path)
                st.write(f"✅ {symbol} 下載完成")
            else:
                st.error(f"❌ 無法從 Yahoo Finance 取得 {symbol} 資料")
                return pd.DataFrame()

    # 讀取檔案
    df = pd.read_csv(file_path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    return df[["Close"]].rename(columns={"Close": "Price"})

# --- 4. UI 介面 ---
st.title("📊 三標動態 LRS 動能旋轉策略")
st.info("策略邏輯：原型 > 200MA 時，持有【近12個月報酬最高】的標的之正2 ETF；全破均線則空手。")

with st.sidebar:
    st.header("⚙️ 參數設定")
    selected_pool = st.multiselect("選擇投資池", options=list(ETF_CONFIG.keys()), default=list(ETF_CONFIG.keys()))
    capital = st.number_input("本金 (元)", value=100000, step=10000)
    lookback = st.slider("動能參考天數 (12個月約252天)", 100, 300, 252)
    ma_val = st.number_input("均線天數", value=200)

if not selected_pool:
    st.warning("請至少選擇一個標的")
    st.stop()

# --- 5. 執行回測 ---
if st.button("開始回測並補齊資料 🚀"):
    all_dfs = {}
    
    # 下載與讀取
    for key in selected_pool:
        cfg = ETF_CONFIG[key]
        base_df = get_data(cfg["base"])
        lev_df = get_data(cfg["lev"])
        
        if base_df.empty or lev_df.empty:
            st.error(f"無法載入 {key}，請檢查網路或代號")
            st.stop()
            
        # 計算指標
        base_df["MA"] = base_df["Price"].rolling(ma_val).mean()
        base_df["Mom"] = base_df["Price"].pct_change(lookback)
        base_df["Above"] = base_df["Price"] > base_df["MA"]
        base_df["Lev_Ret"] = lev_df["Price"].pct_change().fillna(0)
        
        all_dfs[key] = base_df

    # 取時間交集
    common_idx = None
    for key in all_dfs:
        if common_idx is None: common_idx = all_dfs[key].index
        else: common_idx = common_idx.intersection(all_dfs[key].index)
    
    # 逐日模擬邏輯
    res_list = []
    current_equity = 1.0
    
    for date in common_idx:
        candidates = []
        for key in selected_pool:
            if all_dfs[key].loc[date, "Above"]:
                candidates.append((key, all_dfs[key].loc[date, "Mom"]))
        
        if not candidates:
            choice = "Cash (空手)"
            daily_ret = 0.0
        else:
            # 挑選 Mom 最高者
            choice = max(candidates, key=lambda x: x[1])[0]
            daily_ret = all_dfs[choice].loc[date, "Lev_Ret"]
            
        current_equity *= (1 + daily_ret)
        res_list.append({"Date": date, "Holding": choice, "Equity": current_equity, "Daily_Ret": daily_ret})

    df_res = pd.DataFrame(res_list).set_index("Date")

    # --- 6. 顯示結果 ---
    c1, c2, c3 = st.columns(3)
    final_asset = capital * df_res["Equity"].iloc[-1]
    total_ret = df_res["Equity"].iloc[-1] - 1
    mdd = (df_res["Equity"] / df_res["Equity"].cummax() - 1).min()
    
    c1.metric("期末資產", f"${final_asset:,.0f}")
    c2.metric("總報酬率", f"{total_ret:.2%}")
    c3.metric("最大回撤 (MDD)", f"{mdd:.2%}", delta_color="inverse")

    # 圖表
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_res.index, y=df_res["Equity"]*capital, name="LRS 旋轉策略", line=dict(color="orange", width=3)))
    
    # 對照組
    for key in selected_pool:
        bench_p = all_dfs[key].loc[common_idx, "Price"]
        bench_eq = (bench_p / bench_p.iloc[0]) * capital
        fig.add_trace(go.Scatter(x=common_idx, y=bench_eq, name=f"持有 {key}", opacity=0.3))
        
    fig.update_layout(title="資金曲線比較", template="plotly_white", height=500)
    st.plotly_chart(fig, use_container_width=True)

    # 持倉看板
    st.write("### 🕒 最近 10 天持倉狀態")
    st.table(df_res[["Holding"]].tail(10))
