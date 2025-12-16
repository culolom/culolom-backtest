###############################################################
# pages/3_LongTerm_Horizon.py — 長線趨勢延續性 (熱力圖版)
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
import sys

# ------------------------------------------------------
# 基本設定 & 驗證
# ------------------------------------------------------
font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="長線延續性分析", page_icon="🔭", layout="wide")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except ImportError: pass

with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()

# ------------------------------------------------------
# 主程式
# ------------------------------------------------------
st.markdown("<h1 style='margin-bottom:0.5em;'>🔭 長線趨勢延續性 (Signal Horizon)</h1>", unsafe_allow_html=True)
st.markdown("""
    <b>視覺化解讀：</b><br>
    使用 <b>熱力圖 (Heatmap)</b> 觀察策略隨時間推移的表現變化。<br>
    👉 <b>橫軸</b>：持有時間 (1個月 $\\to$ 12個月)。<br>
    👉 <b>縱軸</b>：不同的策略設定。<br>
    尋找顏色 <b>「由淺變深」</b> 的路徑，代表該策略具有長線複利效應。
""", unsafe_allow_html=True)

DATA_DIR = Path("data")

def get_all_csv_files():
    if not DATA_DIR.exists(): return []
    return sorted([f.stem for f in DATA_DIR.glob("*.csv")])

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    if "Adj Close" in df.columns: df["Price"] = df["Adj Close"]
    elif "Close" in df.columns: df["Price"] = df["Close"]
    return df[["Price"]]

csv_files = get_all_csv_files()
if not csv_files: st.stop()

col1, col2 = st.columns(2)
with col1:
    target_symbol = st.selectbox("選擇回測標的", csv_files, index=0)
with col2:
    st.info("🔒 **主要趨勢 (N)**：固定鎖定為 **12 個月** (年線多頭)")
    # 預設多選一點，方便比較長線效果
    default_short = [1, 2, 3, 4, 5, 6]
    selected_m = st.multiselect("設定短期濾網 (M)", [1, 2, 3, 4, 5, 6, 9], default=default_short)

if st.button("開始長線回測 🚀") and target_symbol:
    with st.spinner("正在生成熱力圖數據..."):
        df_daily = load_csv(target_symbol)
        if df_daily.empty: st.stop()

        try:
            df = df_daily['Price'].resample('ME').last().to_frame()
        except:
            df = df_daily['Price'].resample('M').last().to_frame()

        # --- 核心：建立未來 N 個月的報酬欄位 ---
        horizons = [1, 3, 6, 12]
        for h in horizons:
            df[f'Fwd_{h}M'] = df['Price'].shift(-h) / df['Price'] - 1

        results = []
        
        # 主要趨勢
        momentum_long = df['Price'].pct_change(periods=12)
        signal_long = momentum_long > 0
        
        for m in sorted(selected_m):
            momentum_short = df['Price'].pct_change(periods=m)
            
            # 定義兩種狀態
            scenarios = {
                f"年線多 + {m}月續漲 (順勢)": signal_long & (momentum_short > 0),
                f"年線多 + {m}月回檔 (低接)": signal_long & (momentum_short < 0)
            }
            
            for label, signal in scenarios.items():
                row_data = {'策略': label, '短期M': m, '類型': '順勢' if '續漲' in label else '拉回'}
                
                valid_count = 0
                for h in horizons:
                    rets = df.loc[signal, f'Fwd_{h}M'].dropna()
                    
                    if len(rets) > 0:
                        win_rate = (rets > 0).sum() / len(rets)
                        avg_ret = rets.mean()
                        row_data[f'{h}個月'] = avg_ret # 為了熱力圖顯示方便，改短欄位名
                        row_data[f'勝率_{h}M'] = win_rate
                        if h == 1: valid_count = len(rets)
                    else:
                        row_data[f'{h}個月'] = np.nan
                        row_data[f'勝率_{h}M'] = np.nan

                row_data['發生次數'] = valid_count
                if valid_count > 0:
                    results.append(row_data)

        res_df = pd.DataFrame(results)

    # -----------------------------------------------------
    # 視覺化展示：雙熱力圖
    # -----------------------------------------------------
    
    if not res_df.empty:
        st.divider()
        
        # 1. 報酬率熱力圖 (Return Heatmap)
        st.markdown("### 🔥 累積報酬熱力圖 (Profitability)")
        st.caption("觀察顏色變化：:green[**深綠色**] 代表高報酬，:red[**紅色**] 代表虧損。理想路徑是 **由左至右顏色變深綠**。")

        # 整理數據
        return_cols = ['1個月', '3個月', '6個月', '12個月']
        heatmap_ret = res_df.set_index('策略')[return_cols]
        
        # 繪圖
        fig_ret = px.imshow(
            heatmap_ret,
            labels=dict(x="持有期間", y="策略設定", color="平均報酬"),
            x=return_cols,
            y=heatmap_ret.index,
            text_auto='.2%', # 顯示百分比
            color_continuous_scale='RdYlGn', # 紅-黃-綠 配色
            aspect="auto"
        )
        fig_ret.update_layout(height=150 + (len(res_df) * 30), xaxis_side="top") # x軸標籤放上面比較好對照
        st.plotly_chart(fig_ret, use_container_width=True)

        # 2. 勝率熱力圖 (Win Rate Heatmap)
        st.markdown("### 🎯 勝率熱力圖 (Reliability)")
        st.caption("觀察顏色變化：:blue[**深藍色**] 代表高勝率。這能幫助你判斷策略的穩定性。")

        # 整理數據
        win_cols = [f'勝率_{h}M' for h in horizons]
        heatmap_win = res_df.set_index('策略')[win_cols]
        heatmap_win.columns = ['1個月勝率', '3個月勝率', '6個月勝率', '12個月勝率'] # 顯示友善名稱

        # 繪圖
        fig_win = px.imshow(
            heatmap_win,
            labels=dict(x="持有期間", y="策略設定", color="勝率"),
            x=heatmap_win.columns,
            y=heatmap_win.index,
            text_auto='.1%',
            color_continuous_scale='Blues', # 藍色系
            aspect="auto",
            range_color=[0.4, 0.8] # 固定顏色範圍 40%~80% 方便比較
        )
        fig_win.update_layout(height=150 + (len(res_df) * 30))
        st.plotly_chart(fig_win, use_container_width=True)

    # -----------------------------------------------------
    # 原始數據 (摺疊起來，讓想看細節的人再打開)
    # -----------------------------------------------------
    st.divider()
    with st.expander("📄 點擊查看詳細數據表格 (原始資料)"):
        if not res_df.empty:
            fmt_dict = {'發生次數': '{:.0f}'}
            for col in res_df.columns:
                if '個月' in col or '勝率' in col:
                    fmt_dict[col] = '{:.2%}'
            
            st.dataframe(res_df.style.format(fmt_dict), use_container_width=True)
