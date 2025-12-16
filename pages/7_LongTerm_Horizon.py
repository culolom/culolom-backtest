###############################################################
# pages/3_LongTerm_Horizon.py — 長線趨勢延續性回測
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
    default_short = [1, 3]
    selected_m = st.multiselect("設定短期濾網 (M)", [1, 2, 3, 4, 5, 6], default=default_short)

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
                # 針對每一個時間視野 (1, 3, 6, 12) 計算統計數據
                row_data = {'策略': label, '短期M': m, '類型': '順勢' if '續漲' in label else '拉回'}
                
                valid_count = 0
                
                for h in horizons:
                    # 取出訊號成立時，對應的未來 h 個月報酬
                    # dropna() 是必須的，因為最後幾個月沒有未來數據
                    rets = df.loc[signal, f'Fwd_{h}M'].dropna()
                    
                    if len(rets) > 0:
                        win_rate = (rets > 0).sum() / len(rets)
                        avg_ret = rets.mean()
                        row_data[f'勝率_{h}M'] = win_rate
                        row_data[f'報酬_{h}M'] = avg_ret
                        if h == 1: valid_count = len(rets) # 記錄樣本數
                    else:
                        row_data[f'勝率_{h}M'] = np.nan
                        row_data[f'報酬_{h}M'] = np.nan

                row_data['發生次數'] = valid_count
                if valid_count > 0:
                    results.append(row_data)

        res_df = pd.DataFrame(results)

    # -----------------------------------------------------
    # 視覺化展示
    # -----------------------------------------------------
    
    # 1. 勝率熱力圖 (Win Rate Heatmap)
    st.markdown("### 🔥 勝率熱力圖：趨勢能延續多久？")
    st.caption("顏色越綠代表勝率越高，越紅代表容易虧損。觀察從 1M 到 12M 的顏色變化。")

    if not res_df.empty:
        # 整理數據給 Heatmap
        heatmap_data = res_df.set_index('策略')[[f'勝率_{h}M' for h in horizons]]
        # 改欄位名稱好讀一點
        heatmap_data.columns = ['1個月後', '3個月後', '6個月後', '12個月後']
        
        fig_win = px.imshow(
            heatmap_data,
            labels=dict(x="持有時間", y="策略情境", color="勝率"),
            x=['1個月後', '3個月後', '6個月後', '12個月後'],
            y=heatmap_data.index,
            text_auto='.1%', # 顯示數值
            color_continuous_scale='RdYlGn', # 紅黃綠
            aspect="auto",
            range_color=[0.4, 0.7] # 設定顏色範圍 (40%~70%) 讓對比明顯
        )
        fig_win.update_layout(height=400 + (len(res_df)*20))
        st.plotly_chart(fig_win, use_container_width=True)

    # 2. 累積報酬長條圖 (Return Bar Chart)
    st.markdown("### 💰 平均累積報酬：抱久一點會賺更多嗎？")
    
    if not res_df.empty:
        # 為了畫圖，我們要把 DataFrame 轉成長格式 (Long Format)
        plot_df = res_df.melt(id_vars=['策略', '類型'], 
                              value_vars=[f'報酬_{h}M' for h in horizons],
                              var_name='持有期間', value_name='平均報酬')
        
        # 替換標籤
        plot_df['持有期間'] = plot_df['持有期間'].replace({
            '報酬_1M': '1個月', '報酬_3M': '3個月', '報酬_6M': '6個月', '報酬_12M': '12個月'
        })
        
        fig_bar = px.bar(
            plot_df, 
            x='策略', 
            y='平均報酬', 
            color='持有期間', 
            barmode='group', # 分組並排
            text_auto='.1%',
            color_discrete_sequence=px.colors.sequential.Blues
        )
        fig_bar.update_layout(yaxis_tickformat='.0%')
        st.plotly_chart(fig_bar, use_container_width=True)

    # 3. 詳細數據表格
    st.markdown("### 📊 詳細回測數據")
    
    if not res_df.empty:
        # 格式化表格
        display_df = res_df.copy()
        
        # 定義欄位格式
        fmt_dict = {'發生次數': '{:.0f}'}
        for h in horizons:
            fmt_dict[f'勝率_{h}M'] = '{:.2%}'
            fmt_dict[f'報酬_{h}M'] = '{:.2%}'
            
        st.dataframe(
            display_df.style.format(fmt_dict).background_gradient(
                subset=[f'勝率_{h}M' for h in horizons], cmap='RdYlGn', vmin=0.4, vmax=0.7
            ),
            use_container_width=True
        )
