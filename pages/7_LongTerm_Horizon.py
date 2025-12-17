import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
from pathlib import Path
import sys

# ------------------------------------------------------
# 1. 基本設定
# ------------------------------------------------------
font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    import matplotlib.font_manager as fm
    import matplotlib
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"

st.set_page_config(page_title="長期動能研究", page_icon="🔭", layout="wide")

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
st.markdown("<h1 style='margin-bottom:0.5em;'>🔭 長期動能全週期研究 (Bull & Bear)</h1>", unsafe_allow_html=True)
st.markdown("""
    <b>研究目標：</b>分析在 <b>「年線多頭」</b> 與 <b>「年線空頭」</b> 兩種不同大環境下，
    搭配短期 (1, 3, 6, 9月) 的漲跌變化，統計 <b>持有 12 個月後</b> 的勝率與報酬。<br>
    這能幫助判斷：<b>何時該右側追價？何時該左側低接？何時該完全空手？</b>
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
# 3. 側邊欄
# ------------------------------------------------------
col1, col2 = st.columns(2)
with col1:
    target_symbol = st.selectbox("選擇回測標的", csv_files, index=0)
with col2:
    st.info("🔒 **回測架構**：固定鎖定 **持有 12 個月** 的未來表現")
    target_periods = [1, 3, 6, 9]
    st.write(f"🛡️ **短期濾網**：{target_periods} 個月 (漲/跌)")

# ------------------------------------------------------
# 4. 主計算邏輯
# ------------------------------------------------------
if st.button("開始全週期分析 🚀") and target_symbol:
    with st.spinner("正在進行牛熊雙情境演算..."):
        df_daily = load_csv(target_symbol)
        if df_daily.empty: st.stop()

        try:
            df = df_daily['Price'].resample('ME').last().to_frame()
        except:
            df = df_daily['Price'].resample('M').last().to_frame()

        # 1. 建立「未來 12 個月」的報酬 (Target)
        df['Fwd_12M'] = df['Price'].shift(-12) / df['Price'] - 1

        results = []
        
        # 2. 定義大環境 (年線)
        momentum_12m = df['Price'].pct_change(periods=12)
        
        # 情境一：牛市 (年線 > 0)
        signal_bull = momentum_12m > 0
        # 情境二：熊市 (年線 < 0)
        signal_bear = momentum_12m < 0
        
        # 3. 迴圈計算
        for m in target_periods:
            momentum_sub = df['Price'].pct_change(periods=m)
            
            # 定義 4 種情境
            scenarios = {
                # --- 牛市組 ---
                f"🐂 牛市 + {m}月續漲 (順勢)": {'signal': signal_bull & (momentum_sub > 0), 'group': 'Bull', 'type': '順勢'},
                f"🐂 牛市 + {m}月回檔 (低接)": {'signal': signal_bull & (momentum_sub < 0), 'group': 'Bull', 'type': '拉回'},
                
                # --- 熊市組 ---
                f"🐻 熊市 + {m}月反彈 (逃命?)": {'signal': signal_bear & (momentum_sub > 0), 'group': 'Bear', 'type': '反彈'},
                f"🐻 熊市 + {m}月續跌 (抄底?)": {'signal': signal_bear & (momentum_sub < 0), 'group': 'Bear', 'type': '續跌'},
            }
            
            for label, info in scenarios.items():
                outcomes = df.loc[info['signal'], 'Fwd_12M'].dropna()
                
                count = len(outcomes)
                if count > 0:
                    win_rate = (outcomes > 0).sum() / count
                    avg_ret = outcomes.mean()
                    
                    results.append({
                        '策略名稱': label,
                        '大環境': info['group'], # Bull or Bear
                        '短期狀態': info['type'], # 順勢, 拉回, 反彈, 續跌
                        '對照週期': f"{m}個月",
                        '上漲機率': win_rate,
                        '平均漲幅': avg_ret,
                        '樣本數': count
                    })

        res_df = pd.DataFrame(results)

    # -----------------------------------------------------
    # 5. 視覺化展示
    # -----------------------------------------------------
    if not res_df.empty:
        
        # === A. 牛市戰區 (Bull Market) ===
        st.divider()
        st.header("🐂 牛市戰區 (年線上漲中)")
        st.caption("當大趨勢向上時，我們該追高 (順勢) 還是 等拉回 (低接)？")
        
        df_bull = res_df[res_df['大環境'] == 'Bull'].copy()
        
        if not df_bull.empty:
            c1, c2 = st.columns(2)
            color_map_bull = {'順勢': '#2962FF', '拉回': '#FF9100'} # 藍/橘
            
            with c1:
                df_bull_win = df_bull.sort_values(by='上漲機率', ascending=True)
                fig_bull_win = px.bar(
                    df_bull_win, x='上漲機率', y='策略名稱', color='短期狀態',
                    text_auto='.1%', orientation='h', color_discrete_map=color_map_bull,
                    title="[牛市] 持有12個月獲利機率"
                )
                fig_bull_win.update_layout(xaxis_tickformat='.0%', height=350)
                st.plotly_chart(fig_bull_win, use_container_width=True)
                
            with c2:
                df_bull_ret = df_bull.sort_values(by='平均漲幅', ascending=True)
                fig_bull_ret = px.bar(
                    df_bull_ret, x='平均漲幅', y='策略名稱', color='短期狀態',
                    text_auto='.1%', orientation='h', color_discrete_map=color_map_bull,
                    title="[牛市] 持有12個月平均報酬"
                )
                fig_bull_ret.update_layout(xaxis_tickformat='.1%', height=350)
                st.plotly_chart(fig_bull_ret, use_container_width=True)
        else:
            st.info("無牛市樣本數據")

        # === B. 熊市戰區 (Bear Market) ===
        st.divider()
        st.header("🐻 熊市戰區 (年線下跌中)")
        st.caption("當大趨勢向下時，短線反彈能追嗎？還是等跌爛了再去抄底 (左側交易)？")
        
        df_bear = res_df[res_df['大環境'] == 'Bear'].copy()
        
        if not df_bear.empty:
            c3, c4 = st.columns(2)
            # 紫色代表反彈(誘多?), 紅色代表續跌(殺盤)
            color_map_bear = {'反彈': '#AA00FF', '續跌': '#D50000'} 
            
            with c3:
                df_bear_win = df_bear.sort_values(by='上漲機率', ascending=True)
                fig_bear_win = px.bar(
                    df_bear_win, x='上漲機率', y='策略名稱', color='短期狀態',
                    text_auto='.1%', orientation='h', color_discrete_map=color_map_bear,
                    title="[熊市] 持有12個月獲利機率 (翻身機率)"
                )
                fig_bear_win.update_layout(xaxis_tickformat='.0%', height=350)
                st.plotly_chart(fig_bear_win, use_container_width=True)
                
            with c4:
                df_bear_ret = df_bear.sort_values(by='平均漲幅', ascending=True)
                fig_bear_ret = px.bar(
                    df_bear_ret, x='平均漲幅', y='策略名稱', color='短期狀態',
                    text_auto='.1%', orientation='h', color_discrete_map=color_map_bear,
                    title="[熊市] 持有12個月平均報酬"
                )
                fig_bear_ret.update_layout(xaxis_tickformat='.1%', height=350)
                st.plotly_chart(fig_bear_ret, use_container_width=True)
        else:
            st.info("歷史上未出現熊市樣本 (或樣本不足)")

        # -----------------------------------------------------
        # 6. 綜合數據表
        # -----------------------------------------------------
        st.divider()
        with st.expander("📄 查看完整詳細數據表"):
            # 為了閱讀方便，我們把牛熊分開標示
            def highlight_group(s):
                return ['background-color: rgba(27, 94, 32, 0.1)' if v == 'Bull' else 'background-color: rgba(183, 28, 28, 0.1)' for v in s]

            st.dataframe(
                res_df.sort_values(by=['大環境', '上漲機率'], ascending=[False, False])
                .style.format({
                    '上漲機率': '{:.2%}',
                    '平均漲幅': '{:.2%}',
                    '樣本數': '{:.0f}'
                })
                .apply(highlight_group, subset=['大環境']),
                use_container_width=True
            )
    else:
        st.warning("數據不足，無法生成報表。")
