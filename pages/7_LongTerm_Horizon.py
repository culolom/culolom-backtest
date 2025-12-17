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
# 1. 基本設定 & 字型驗證
# ------------------------------------------------------
font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="長期動能研究", page_icon="🔭", layout="wide")

# 引入 auth (如果有的話)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except ImportError: pass

with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()

# ------------------------------------------------------
# 2. 標題與說明
# ------------------------------------------------------
st.markdown("<h1 style='margin-bottom:0.5em;'>🔭 長期動能研究 (12-Month Horizon)</h1>", unsafe_allow_html=True)
st.markdown("""
    <b>研究目標：</b><br>
    在 <b>年線多頭 (過去12月漲)</b> 的大前提下，搭配不同短中期濾網 (1, 3, 6, 9月)，
    統計 <b>「持有 12 個月後」</b> 的 <b>上漲機率</b> 與 <b>平均漲幅</b>。
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

# ------------------------------------------------------
# 3. 側邊欄控制項
# ------------------------------------------------------
col1, col2 = st.columns(2)
with col1:
    target_symbol = st.selectbox("選擇回測標的", csv_files, index=0)
with col2:
    st.info("🔒 **主要趨勢**：固定鎖定為 **過去 12 個月漲幅 > 0**")
    
    # 固定研究 1, 3, 6, 9 個月
    target_periods = [1, 3, 6, 9]
    st.write(f"🛡️ **對照組濾網**：{target_periods} 個月 (漲/跌)")

# ------------------------------------------------------
# 4. 主計算邏輯
# ------------------------------------------------------
if st.button("開始分析 🚀") and target_symbol:
    with st.spinner("正在計算長期持有期望值..."):
        df_daily = load_csv(target_symbol)
        if df_daily.empty: st.stop()

        # 轉月頻率
        try:
            df = df_daily['Price'].resample('ME').last().to_frame()
        except:
            df = df_daily['Price'].resample('M').last().to_frame()

        # 1. 建立「未來 12 個月」的報酬 (Target)
        # shift(-12) 把未來的價格拉到現在，計算報酬率
        df['Fwd_12M'] = df['Price'].shift(-12) / df['Price'] - 1

        results = []
        
        # 2. 定義條件一：年線多頭 (過去 12 個月 > 0)
        momentum_12m = df['Price'].pct_change(periods=12)
        signal_main = momentum_12m > 0
        
        # 3. 針對條件二 (1, 3, 6, 9月) 進行迴圈
        for m in target_periods:
            momentum_sub = df['Price'].pct_change(periods=m)
            
            # 定義兩種情境
            scenarios = {
                f"年線多 + {m}月續漲 (順勢)": signal_main & (momentum_sub > 0),
                f"年線多 + {m}月回檔 (低接)": signal_main & (momentum_sub < 0)
            }
            
            for label, signal in scenarios.items():
                # 取出符合訊號的「未來 12 個月報酬」
                outcomes = df.loc[signal, 'Fwd_12M'].dropna()
                
                count = len(outcomes)
                if count > 0:
                    win_rate = (outcomes > 0).sum() / count
                    avg_ret = outcomes.mean()
                    
                    results.append({
                        '策略名稱': label,
                        '對照週期': f"{m}個月",
                        '類型': '順勢' if '續漲' in label else '拉回',
                        '上漲機率': win_rate,
                        '平均漲幅': avg_ret,
                        '樣本數': count
                    })

        res_df = pd.DataFrame(results)

    # -----------------------------------------------------
    # 5. 視覺化展示 (兩張排名直條圖)
    # -----------------------------------------------------
    if not res_df.empty:
        st.divider()
        
        # 配色設定：順勢=藍色, 拉回=橘色 (互補色，清晰易讀)
        color_map = {'順勢': '#2962FF', '拉回': '#FF9100'}

        # --- 圖表 1: 上漲機率排名 ---
        st.subheader("📊 12個月後「上漲機率」排名 (Win Rate)")
        st.caption("數值越高，代表抱一年賺錢的機會越大。")
        
        # 排序
        df_win = res_df.sort_values(by='上漲機率', ascending=True) # Plotly bar h 預設是由下往上排，所以這裡用 True
        
        fig_win = px.bar(
            df_win,
            x='上漲機率',
            y='策略名稱',
            color='類型',
            text_auto='.1%',
            orientation='h', # 水平直條圖比較好閱讀長標籤
            color_discrete_map=color_map,
            title="持有 12 個月獲利機率"
        )
        fig_win.update_layout(xaxis_tickformat='.0%', height=400 + (len(res_df)*20))
        st.plotly_chart(fig_win, use_container_width=True)

        st.divider()

        # --- 圖表 2: 平均漲幅排名 ---
        st.subheader("💰 12個月後「平均漲幅」排名 (Average Return)")
        st.caption("數值越高，代表抱一年後的預期獲利空間越大。")
        
        # 排序
        df_ret = res_df.sort_values(by='平均漲幅', ascending=True)
        
        fig_ret = px.bar(
            df_ret,
            x='平均漲幅',
            y='策略名稱',
            color='類型',
            text_auto='.1%',
            orientation='h',
            color_discrete_map=color_map,
            title="持有 12 個月平均報酬"
        )
        fig_ret.update_layout(xaxis_tickformat='.1%', height=400 + (len(res_df)*20))
        st.plotly_chart(fig_ret, use_container_width=True)

        # -----------------------------------------------------
        # 6. 詳細數據表格
        # -----------------------------------------------------
        st.divider()
        with st.expander("📄 查看詳細數據表"):
            st.dataframe(
                res_df.sort_values(by='上漲機率', ascending=False).style.format({
                    '上漲機率': '{:.2%}',
                    '平均漲幅': '{:.2%}',
                    '樣本數': '{:.0f}'
                }).background_gradient(subset=['上漲機率', '平均漲幅'], cmap='Blues'),
                use_container_width=True
            )
    else:
        st.warning("沒有足夠的數據進行計算，請檢查該標的歷史資料長度。")
