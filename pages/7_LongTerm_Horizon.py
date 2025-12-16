###############################################################
# pages/3_LongTerm_Horizon.py — 長線趨勢延續性 (分頁版)
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
    <b>策略邏輯：</b><br>
    當訊號出現時（年線多頭 + 短期順勢/回檔），統計 <b>持有 1個月、3個月、6個月、12個月</b> 後的表現。<br>
    這能幫助判斷：<b>「這個訊號是短線反彈，還是長線波段的起點？」</b>
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
    default_short = [1, 3, 6]
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
            # shift(-h) 代表把未來的價格拉到現在這一行
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
                        row_data[f'勝率_{h}M'] = win_rate
                        row_data[f'報酬_{h}M'] = avg_ret
                        if h == 1: valid_count = len(rets)
                    else:
                        row_data[f'勝率_{h}M'] = np.nan
                        row_data[f'報酬_{h}M'] = np.nan

                row_data['發生次數'] = valid_count
                if valid_count > 0:
                    results.append(row_data)

        res_df = pd.DataFrame(results)

    # -----------------------------------------------------
    # 視覺化展示 (分頁版)
    # -----------------------------------------------------
    
    st.markdown("### 💰 平均累積報酬：抱得越久，誰賺越多？")
    
    if not res_df.empty:
        # 建立 4 個 Tabs
        tab1, tab2, tab3, tab4 = st.tabs(["1個月展望 (短線)", "3個月展望 (季)", "6個月展望 (半年)", "12個月展望 (長線)"])
        
        # 定義繪圖函式 (避免重複代碼)
        def plot_horizon_bar(horizon_month, container):
            col_name = f'報酬_{horizon_month}M'
            
            # 依照報酬率排序，讓強的排左邊
            sorted_df = res_df.sort_values(by=col_name, ascending=False)
            
            fig = px.bar(
                sorted_df, 
                x='策略', 
                y=col_name, 
                color='類型', # 用類型來分顏色
                text_auto='.1%',
                title=f"持有 {horizon_month} 個月後的平均報酬排序",
                # 自定義顏色：順勢用深綠，拉回用深橘紅 (加強對比)
                color_discrete_map={'順勢': '#00CC96', '拉回': '#EF553B'}
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
    # 詳細數據表格 (保持熱力圖概念)
    # -----------------------------------------------------
    st.divider()
    st.markdown("### 📊 詳細回測數據總表")
    
    if not res_df.empty:
        # 格式化表格
        display_df = res_df.copy()
        
        # 準備格式字典
        fmt_dict = {'發生次數': '{:.0f}'}
        for h in horizons:
            fmt_dict[f'勝率_{h}M'] = '{:.2%}'
            fmt_dict[f'報酬_{h}M'] = '{:.2%}'
        
        # 使用 Pandas Styler 加上背景色
        st.dataframe(
            display_df.style.format(fmt_dict)
            .background_gradient(subset=[f'報酬_{h}M' for h in horizons], cmap='RdYlGn', axis=None) 
            # axis=None 代表用全表的數值來決定顏色深淺，更容易看出誰是長線冠軍
            ,
            use_container_width=True
        )
