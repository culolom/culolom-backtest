import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
from pathlib import Path
import sys

# ------------------------------------------------------
# 1. 基本設定與 CSS 美化
# ------------------------------------------------------
font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    import matplotlib.font_manager as fm
    import matplotlib
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"

st.set_page_config(page_title="長期動能研究", page_icon="🔭", layout="wide")

# ★★★ CSS 注入區域：定義橘色按鈕與卡片樣式 ★★★
st.markdown("""
<style>
    /* 1. 全局橘色按鈕樣式 */
    div.stButton > button:first-child {
        background-color: #FF6F00; /* 鮮豔橘 */
        color: white;
        border-radius: 10px;
        border: none;
        font-weight: bold;
        font-size: 16px;
        padding: 0.5rem 2rem;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    div.stButton > button:first-child:hover {
        background-color: #E65100; /* 深橘色 hover */
        box-shadow: 0 6px 8px rgba(0,0,0,0.2);
        transform: translateY(-2px);
    }
    div.stButton > button:first-child:active {
        transform: translateY(0px);
    }

    /* 2. 資訊卡片樣式 (文字說明用) */
    .info-card {
        background-color: var(--secondary-background-color);
        padding: 20px;
        border-radius: 12px;
        border-left: 6px solid #FF6F00; /* 左側橘色強調線 */
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        margin-bottom: 20px;
    }
    
    /* 3. 數據小卡片樣式 */
    .metric-card {
        background-color: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 12px;
        padding: 15px;
        text-align: center;
        height: 100%;
        transition: transform 0.2s;
    }
    .metric-card:hover {
        transform: scale(1.02);
        border-color: #FF6F00;
    }
</style>
""", unsafe_allow_html=True)

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except ImportError: pass

with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()

# ------------------------------------------------------
# 2. 標題與說明 (使用卡片包覆)
# ------------------------------------------------------
st.markdown("<h1 style='margin-bottom:0.5em;'>🔭 長期動能全週期研究 (Bull & Bear)</h1>", unsafe_allow_html=True)

# 使用 CSS class "info-card"
st.markdown("""
<div class="info-card">
    <h4 style="margin-top:0;">📖 研究目標</h4>
    <p style="font-size:1.05em; line-height:1.6;">
        分析在 <b>「年線多頭」</b> 與 <b>「年線空頭」</b> 兩種不同大環境下，
        搭配短期 (1, 3, 6, 9月) 的漲跌變化，統計 <b>持有 12 個月後</b> 的勝率與報酬。<br>
        這能幫助判斷：<span style="color:#FF6F00; font-weight:bold;">何時該右側追價？何時該左側低接？何時該完全空手？</span>
    </p>
</div>
""", unsafe_allow_html=True)

DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    if "Adj Close" in df.columns: df["Price"] = df["Adj Close"]
    elif "Close" in df.columns: df["Price"] = df["Close"]
    return df[["Price"]]

# ------------------------------------------------------
# 3. 參數設定 UI (置於主畫面)
# ------------------------------------------------------
st.subheader("⚙️ 參數設定")
col_input, col_space = st.columns([1, 2])

# ★ 指定 ETF 對照表
ETF_MAPPING = {
    "0050 元大台灣50": "0050.TW",
    "SPY SPDR標準普爾500指數ETF": "SPY",
}

target_symbol = None
with col_input:
    # 讓使用者選擇中文名稱
    selected_name = st.selectbox("請選擇回測標的 (ETF)", list(ETF_MAPPING.keys()), index=0)
    target_symbol = ETF_MAPPING[selected_name]

# 固定回測週期
target_periods = [1, 3, 6, 9]

# ------------------------------------------------------
# 4. 主計算邏輯
# ------------------------------------------------------
# 按鈕會自動應用上面的 CSS 樣式
if st.button("開始全週期分析 🚀") and target_symbol:
    
    with st.spinner(f"正在分析 {selected_name} ({target_symbol})..."):
        df_daily = load_csv(target_symbol)
        
        if df_daily.empty: 
            st.error(f"❌ 找不到 {target_symbol}.csv 檔案，請確認 data 資料夾內是否有該檔案。")
            st.stop()

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
                f"🐂 牛市 + {m}月續漲": {'signal': signal_bull & (momentum_sub > 0), 'group': 'Bull', 'type': '順勢'},
                f"🐂 牛市 + {m}月回檔": {'signal': signal_bull & (momentum_sub < 0), 'group': 'Bull', 'type': '拉回'},
                
                # --- 熊市組 ---
                f"🐻 熊市 + {m}月反彈": {'signal': signal_bear & (momentum_sub > 0), 'group': 'Bear', 'type': '反彈'},
                f"🐻 熊市 + {m}月續跌": {'signal': signal_bear & (momentum_sub < 0), 'group': 'Bear', 'type': '續跌'},
            }
            
            for label, info in scenarios.items():
                outcomes = df.loc[info['signal'], 'Fwd_12M'].dropna()
                
                count = len(outcomes)
                if count > 0:
                    win_rate = (outcomes > 0).sum() / count
                    avg_ret = outcomes.mean()
                    
                    results.append({
                        '策略名稱': label,
                        '大環境': info['group'], 
                        '短期狀態': info['type'],
                        '對照週期': f"{m}個月",
                        '週期數值': m, 
                        '上漲機率': win_rate,
                        '平均漲幅': avg_ret,
                        '樣本數': count
                    })

        res_df = pd.DataFrame(results)

    # -----------------------------------------------------
    # 5. 現況戰情室 (Current Status Dashboard)
    # -----------------------------------------------------
    if not res_df.empty:
        st.divider()
        st.markdown(f"### ♟️ 現況戰情室：{selected_name}")
        
        # 使用卡片包裹說明
        st.markdown("""
        <div style="background-color:rgba(255, 111, 0, 0.1); padding:10px 15px; border-radius:8px; margin-bottom:15px; border-left: 4px solid #FF6F00;">
            <small>💡 說明：根據<b>最新收盤價</b>判斷目前狀態，並顯示該狀態在歷史上 <b>持有12個月</b> 的勝率。</small>
        </div>
        """, unsafe_allow_html=True)

        # 取得最新收盤
        last_date = df.index[-1]
        last_price = df['Price'].iloc[-1]
        
        # 判斷年線 (大環境)
        price_12m = df['Price'].shift(12).iloc[-1]
        curr_12m_ret = (last_price / price_12m) - 1 if not pd.isna(price_12m) else 0
        
        is_bull = curr_12m_ret > 0
        trend_text = "🐂 牛市 (年線向上)" if is_bull else "🐻 熊市 (年線向下)"
        trend_color = "green" if is_bull else "red"

        # 資訊列
        st.info(f"📅 **最新數據日期**: {last_date.strftime('%Y-%m-%d')} | **最新價**: {last_price:,.2f} | **年線狀態**: :{trend_color}[**{trend_text}**] ({curr_12m_ret:+.2%})")

        # 顯示 1, 3, 6, 9 月的現況卡片
        cols = st.columns(4)
        
        for i, m in enumerate(target_periods): # [1, 3, 6, 9]
            with cols[i]:
                # 計算該周期的現況
                price_m = df['Price'].shift(m).iloc[-1]
                curr_m_ret = (last_price / price_m) - 1 if not pd.isna(price_m) else 0
                
                # 組合出對應的策略名稱 key
                if is_bull:
                    condition = "續漲" if curr_m_ret > 0 else "回檔"
                    key_name = f"🐂 牛市 + {m}月{condition}"
                else:
                    condition = "反彈" if curr_m_ret > 0 else "續跌"
                    key_name = f"🐻 熊市 + {m}月{condition}"
                
                # 查找歷史數據
                match = res_df[res_df['策略名稱'] == key_name]
                
                # 卡片顯示邏輯
                if not match.empty:
                    win_rate = match['上漲機率'].values[0]
                    avg_ret = match['平均漲幅'].values[0]
                    
                    if win_rate >= 0.6: 
                        rate_color = "#00C853" # Green
                        desc = "高勝率🔥"
                    elif win_rate <= 0.4: 
                        rate_color = "#D32F2F" # Red
                        desc = "低勝率⚠️"
                    else: 
                        rate_color = "#FFA000" # Orange
                        desc = "中性⚖️"

                    chg_color = "#2962FF" if curr_m_ret > 0 else "#FF9100"

                    # 使用 CSS class "metric-card"
                    st.markdown(f"""
                    <div class="metric-card">
                        <div style="font-size:0.9em; opacity:0.8; margin-bottom:5px;">近 {m} 個月 ({condition})</div>
                        <div style="font-size:1.4em; font-weight:bold; color:{chg_color}">
                            {curr_m_ret:+.2%}
                        </div>
                        <div style="height:1px; background-color:#ddd; margin:10px 0; opacity:0.5;"></div>
                        <div style="font-size:0.8em; opacity:0.8">歷史12M上漲機率</div>
                        <div style="font-size:2.2em; font-weight:900; color:{rate_color}; line-height:1.2;">
                            {win_rate:.0%}
                        </div>
                        <div style="font-size:0.9em; color:{rate_color}; font-weight:bold; margin-bottom:4px">{desc}</div>
                        <div style="font-size:0.8em; opacity:0.7">平均漲幅: {avg_ret:+.1%}</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="metric-card" style="display:flex; align-items:center; justify-content:center;">
                        <div style="color:gray;">近{m}月<br>無歷史數據</div>
                    </div>
                    """, unsafe_allow_html=True)

    # -----------------------------------------------------
    # 6. 視覺化展示 (牛熊雙戰區)
    # -----------------------------------------------------
    if not res_df.empty:
        
        # === A. 牛市戰區 (Bull Market) ===
        st.divider()
        st.markdown("### 🐂 牛市戰區 (年線上漲中)")
        st.caption("當大趨勢向上時，我們該追高 (順勢) 還是 等拉回 (低接)？")
        
        df_bull = res_df[res_df['大環境'] == 'Bull'].copy()
        
        if not df_bull.empty:
            c1, c2 = st.columns(2)
            color_map_bull = {'順勢': '#2962FF', '拉回': '#FF9100'} 
            
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
        st.markdown("### 🐻 熊市戰區 (年線下跌中)")
        st.caption("當大趨勢向下時，短線反彈能追嗎？還是等跌爛了再去抄底 (左側交易)？")
        
        df_bear = res_df[res_df['大環境'] == 'Bear'].copy()
        
        if not df_bear.empty:
            c3, c4 = st.columns(2)
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
            st.info("歷史上未出現熊市樣本")

        # -----------------------------------------------------
        # 7. 綜合數據表
        # -----------------------------------------------------
        st.divider()
        with st.expander("📄 查看完整詳細數據表"):
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
        # 初次進入或無數據時的提示，也可以用卡片包起來
        if target_symbol is None:
            st.warning("請先選擇 ETF 並點擊開始分析。")
