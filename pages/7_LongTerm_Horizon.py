###############################################################
# pages/3_LongTerm_Horizon.py — 長線趨勢延續性 (中性配色版)
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
    <b>雙視角分析：</b><br>
    1. <b>🔥 熱力圖 (Heatmap)</b>：觀察策略隨時間推移的變化，<b>顏色越深藍</b> 代表數值越高。<br>
    2. <b>📊 直條圖 (Bar Chart)</b>：比較不同策略的績效排名 (<span style='color:#2962FF'><b>順勢</b></span> vs <span style='color:#FF9100'><b>拉回</b></span>)。
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
    default_short = [1, 2, 3, 4, 6]
    selected_m = st.multiselect("設定短期濾網 (M)", [1, 2, 3, 4, 5, 6, 9], default=default_short)

if st.button("開始長線回測 🚀") and target_symbol:
    with st.spinner("正在計算多週期未來回報..."):
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
                        row_data[f'{h}個月'] = avg_ret # 熱力圖用
                        row_data[f'報酬_{h}M'] = avg_ret # 直條圖用
                        row_data[f'勝率_{h}M'] = win_rate
                        if h == 1: valid_count = len(rets)
                    else:
                        row_data[f'{h}個月'] = np.nan
                        row_data[f'報酬_{h}M'] = np.nan
                        row_data[f'勝率_{h}M'] = np.nan

                row_data['發生次數'] = valid_count
                if valid_count > 0:
                    results.append(row_data)

        res_df = pd.DataFrame(results)

    # -----------------------------------------------------
    # 視覺化展示
    # -----------------------------------------------------
    
    if not res_df.empty:
        st.divider()
        
        # ==========================================
        # 1. 上半部：熱力圖 (上帝視角)
        # ==========================================
        st.markdown("### 💠 全局視野：熱力圖 (Heatmap)")
        st.caption("透過顏色深淺觀察策略延續性。:blue[**深藍色**] 代表高報酬/高勝率，白色代表低數值。")

        # 整理數據
        return_cols = ['1個月', '3個月', '6個月', '12個月']
        heatmap_ret = res_df.set_index('策略')[return_cols]
        
        # 繪圖 - 使用 'Blues' 色階 (單色系，越深越好，完全避免紅綠誤會)
        fig_ret = px.imshow(
            heatmap_ret,
            labels=dict(x="持有期間", y="策略設定", color="平均報酬"),
            x=return_cols,
            y=heatmap_ret.index,
            text_auto='.2%', 
            color_continuous_scale='Blues', # ★ 修改處：使用藍色系
            aspect="auto"
        )
        fig_ret.update_layout(height=150 + (len(res_df) * 30), xaxis_side="top")
        st.plotly_chart(fig_ret, use_container_width=True)

        st.divider()

        # ==========================================
        # 2. 下半部：直條圖 (排行榜視角)
        # ==========================================
        st.markdown("### 📊 績效排行：分頁直條圖 (Rankings)")
        st.caption("藍色 = 順勢策略，橘色 = 拉回策略。")

        # 建立 4 個 Tabs
        tab1, tab2, tab3, tab4 = st.tabs(["1個月展望", "3個月展望", "6個月展望", "12個月展望"])
        
        # 定義繪圖函式
        def plot_horizon_bar(horizon_month, container):
            col_name = f'報酬_{horizon_month}M'
            
            # 依照報酬率排序
            sorted_df = res_df.sort_values(by=col_name, ascending=False)
            
            fig = px.bar(
                sorted_df, 
                x='策略', 
                y=col_name, 
                color='類型', 
                text_auto='.1%',
                title=f"持有 {horizon_month} 個月後的平均報酬排序",
                # ★ 修改處：使用 科技藍 vs 活力橘
                color_discrete_map={'順勢': '#2962FF', '拉回': '#FF9100'}
            )
            
            fig.update_layout(
                yaxis_tickformat='.1%',
                xaxis_title="",
                yaxis_title="平均累積報酬",
                height=450,
                showlegend=True
            )
            container.plotly_chart(fig, use_container_width=True)

        # 分別繪製
        with tab1: plot_horizon_bar(1, tab1)
        with tab2: plot_horizon_bar(3, tab2)
        with tab3: plot_horizon_bar(6, tab3)
        with tab4: plot_horizon_bar(12, tab4)

    # -----------------------------------------------------
    # 原始數據
    # -----------------------------------------------------
    st.divider()
    with st.expander("📄 點擊查看詳細數據表格 (原始資料)"):
        if not res_df.empty:
            fmt_dict = {'發生次數': '{:.0f}'}
            for col in res_df.columns:
                if '個月' in col or '勝率' in col or '報酬' in col:
                    fmt_dict[col] = '{:.2%}'
            
            # ★ 修改處：表格背景色也改為藍色系 'Blues'
            st.dataframe(
                res_df.style.format(fmt_dict)
                .background_gradient(subset=[f'勝率_{h}M' for h in horizons], cmap='Blues'),
                use_container_width=True
            )
