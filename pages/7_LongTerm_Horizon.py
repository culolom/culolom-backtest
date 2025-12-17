###############################################################
# pages/3_LongTerm_Horizon.py — 長期動能全週期研究 (UI 美化終極版)
###############################################################

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
# 2. 全域 CSS 樣式表 (統一管理 UI)
# ------------------------------------------------------
st.markdown("""
<style>
    /* 共用卡片容器 */
    .st-card {
        background-color: var(--secondary-background-color);
        border-radius: 12px;
        padding: 20px;
        border: 1px solid rgba(128, 128, 128, 0.2);
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        height: 100%;
    }
    
    /* 實驗參數區塊 */
    .exp-header { font-size: 1.1em; font-weight: bold; margin-bottom: 15px; }
    .exp-section {
        background-color: rgba(255, 255, 255, 0.5);
        border-left: 4px solid #ccc;
        padding: 10px 15px; margin-bottom: 10px; border-radius: 0 8px 8px 0;
    }
    .exp-section.anchor { border-left-color: #2962FF; background-color: rgba(41, 98, 255, 0.05); } 
    .exp-section.var { border-left-color: #FF9100; background-color: rgba(255, 145, 0, 0.05); } 
    .exp-title { font-weight: bold; font-size: 0.95em; display: block; margin-bottom: 4px; }
    .exp-desc { font-size: 0.85em; opacity: 0.8; margin: 0; line-height: 1.4; }

    /* 現況戰情室卡片 */
    .status-card {
        background-color: var(--secondary-background-color);
        border-radius: 12px;
        padding: 15px;
        text-align: center;
        border: 1px solid rgba(128,128,128,0.1);
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border-top: 5px solid #ccc; /* 頂部色條 */
        height: 100%;
        display: flex; flex-direction: column; justify-content: space-between;
    }
    .status-card.high-win { border-top-color: #00C853; } /* 綠色：高勝率 */
    .status-card.low-win { border-top-color: #D32F2F; }  /* 紅色：低勝率 */
    .status-card.neutral { border-top-color: #FFA000; }   /* 橘色：中性 */
    
    .status-label { font-size: 0.9em; opacity: 0.7; letter-spacing: 0.5px; }
    .status-value { font-size: 1.3em; font-weight: bold; margin: 8px 0; }
    .status-prob { font-size: 2.2em; font-weight: 900; margin-top: 5px; line-height: 1; }
    .status-desc { font-size: 0.85em; font-weight: bold; margin-bottom: 5px; }
    .status-footer { font-size: 0.8em; opacity: 0.6; border-top: 1px dashed rgba(128,128,128,0.3); margin-top: 10px; padding-top: 8px; }

</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------
# 3. 標題區
# ------------------------------------------------------
st.markdown("<h1 style='margin-bottom:0.5em;'>🔭 長期動能全週期研究 (Bull & Bear)</h1>", unsafe_allow_html=True)

DATA_DIR = Path("data")
def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    if "Adj Close" in df.columns: df["Price"] = df["Adj Close"]
    elif "Close" in df.columns: df["Price"] = df["Close"]
    return df[["Price"]]

# ------------------------------------------------------
# 4. 側邊欄與參數設定
# ------------------------------------------------------
col1, col2 = st.columns(2)

ETF_MAPPING = {
    "0050 元大台灣50": "0050.TW",
    "006208 富邦台50": "006208.TW",
}

with col1:
    st.subheader("選擇回測標的")
    selected_name = st.selectbox("請選擇 ETF", list(ETF_MAPPING.keys()), index=0)
    target_symbol = ETF_MAPPING[selected_name]

with col2:
    # 套用剛才定義的 .st-card 與 .exp-section 樣式
    st.markdown("""
    <div class="st-card">
        <div class="exp-header">🧪 實驗參數設定 (Testing Conditions)</div>
        <div class="exp-section anchor">
            <span class="exp-title" style="color:#1565C0">⚓ 長期定錨 (Anchor)</span>
            <p class="exp-desc">
                固定鎖定 <b>持有 12 個月</b> 的未來表現。<br>
                <i>驗證：「現在買進，抱一年後的勝率？」</i>
            </p>
        </div>
        <div class="exp-section var">
            <span class="exp-title" style="color:#E65100">🎲 短期變數 (Variables)</span>
            <p class="exp-desc">
                觀察 <b>1, 3, 6, 9 個月</b> 的動能變化。<br>
                <i>判斷：「短線該順勢追高？還是拉回低接？」</i>
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    target_periods = [1, 3, 6, 9]

# ------------------------------------------------------
# 5. 主計算邏輯
# ------------------------------------------------------
if st.button("開始全週期分析 🚀") and target_symbol:
    with st.spinner(f"正在分析 {selected_name} ({target_symbol})..."):
        df_daily = load_csv(target_symbol)
        
        if df_daily.empty: 
            st.error(f"❌ 找不到 {target_symbol}.csv 檔案。")
            st.stop()

        try: df = df_daily['Price'].resample('ME').last().to_frame()
        except: df = df_daily['Price'].resample('M').last().to_frame()

        # 1. Target: Future 12M Return
        df['Fwd_12M'] = df['Price'].shift(-12) / df['Price'] - 1

        results = []
        
        # 2. Main Trend (12M)
        momentum_12m = df['Price'].pct_change(periods=12)
        signal_bull = momentum_12m > 0
        signal_bear = momentum_12m < 0
        
        # 3. Loop
        for m in target_periods:
            momentum_sub = df['Price'].pct_change(periods=m)
            
            scenarios = {
                f"🐂 牛市 + {m}月續漲": {'signal': signal_bull & (momentum_sub > 0), 'group': 'Bull', 'type': '順勢'},
                f"🐂 牛市 + {m}月回檔": {'signal': signal_bull & (momentum_sub < 0), 'group': 'Bull', 'type': '拉回'},
                f"🐻 熊市 + {m}月反彈": {'signal': signal_bear & (momentum_sub > 0), 'group': 'Bear', 'type': '反彈'},
                f"🐻 熊市 + {m}月續跌": {'signal': signal_bear & (momentum_sub < 0), 'group': 'Bear', 'type': '續跌'},
            }
            
            for label, info in scenarios.items():
                outcomes = df.loc[info['signal'], 'Fwd_12M'].dropna()
                if len(outcomes) > 0:
                    results.append({
                        '策略名稱': label,
                        '大環境': info['group'], 
                        '短期狀態': info['type'],
                        '對照週期': f"{m}個月",
                        '週期數值': m, 
                        '上漲機率': (outcomes > 0).sum() / len(outcomes),
                        '平均漲幅': outcomes.mean(),
                        '樣本數': len(outcomes)
                    })

        res_df = pd.DataFrame(results)

    # -----------------------------------------------------
    # 6. 現況戰情室 (Current Status Dashboard) - 美化版
    # -----------------------------------------------------
    if not res_df.empty:
        st.divider()
        st.markdown(f"### ♟️ 現況戰情室：{selected_name}")
        st.caption("根據最新收盤價，匹配歷史情境，預測未來 12 個月的勝率。")

        last_price = df['Price'].iloc[-1]
        last_date = df.index[-1]
        
        # 年線狀態
        price_12m = df['Price'].shift(12).iloc[-1]
        curr_12m_ret = (last_price / price_12m) - 1 if not pd.isna(price_12m) else 0
        is_bull = curr_12m_ret > 0
        
        # 顯示大環境狀態條
        status_color = "#00C853" if is_bull else "#D32F2F"
        status_text = "🐂 牛市 (年線向上)" if is_bull else "🐻 熊市 (年線向下)"
        
        st.markdown(f"""
        <div style="background-color:rgba({0 if is_bull else 255}, {200 if is_bull else 0}, {83 if is_bull else 0}, 0.1); 
                    border-left: 5px solid {status_color}; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
            <span style="font-weight:bold; font-size:1.1em; color:{status_color}">{status_text}</span>
            <span style="margin-left: 10px;">目前漲幅: <b>{curr_12m_ret:+.2%}</b> (數據日期: {last_date.strftime('%Y-%m-%d')})</span>
        </div>
        """, unsafe_allow_html=True)

        cols = st.columns(4)
        
        for i, m in enumerate(target_periods):
            with cols[i]:
                price_m = df['Price'].shift(m).iloc[-1]
                curr_m_ret = (last_price / price_m) - 1 if not pd.isna(price_m) else 0
                
                # 決定 Key
                if is_bull:
                    cond = "續漲" if curr_m_ret > 0 else "回檔"
                    key = f"🐂 牛市 + {m}月{cond}"
                else:
                    cond = "反彈" if curr_m_ret > 0 else "續跌"
                    key = f"🐻 熊市 + {m}月{cond}"
                
                # 查表
                match = res_df[res_df['策略名稱'] == key]
                
                if not match.empty:
                    win_rate = match['上漲機率'].values[0]
                    avg_ret = match['平均漲幅'].values[0]
                    
                    # 決定卡片樣式 Class
                    if win_rate >= 0.6: card_class, color_code, desc = "high-win", "#00C853", "高勝率 🔥"
                    elif win_rate <= 0.4: card_class, color_code, desc = "low-win", "#D32F2F", "低勝率 ⚠️"
                    else: card_class, color_code, desc = "neutral", "#FFA000", "中性 ⚖️"
                    
                    val_color = "#2962FF" if curr_m_ret > 0 else "#FF9100"

                    # 渲染卡片
                    st.markdown(f"""
                    <div class="status-card {card_class}">
                        <div>
                            <div class="status-label">近 {m} 個月 ({cond})</div>
                            <div class="status-value" style="color:{val_color}">{curr_m_ret:+.2%}</div>
                        </div>
                        <div>
                            <div class="status-label" style="margin-top:10px">歷史 12M 勝率</div>
                            <div class="status-prob" style="color:{color_code}">{win_rate:.0%}</div>
                            <div class="status-desc" style="color:{color_code}">{desc}</div>
                        </div>
                        <div class="status-footer">平均漲幅: {avg_ret:+.1%}</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="status-card neutral">
                        <div class="status-label">近 {m} 個月</div>
                        <div class="status-value">{curr_m_ret:+.2%}</div>
                        <div style="margin-top:20px; opacity:0.5">無歷史數據</div>
                    </div>
                    """, unsafe_allow_html=True)

    # -----------------------------------------------------
    # 7. 視覺化展示 (保持原本的圖表)
    # -----------------------------------------------------
    if not res_df.empty:
        st.divider()
        st.header("🐂 牛市戰區 (年線上漲中)")
        
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

        st.divider()
        st.header("🐻 熊市戰區 (年線下跌中)")
        
        df_bear = res_df[res_df['大環境'] == 'Bear'].copy()
        
        if not df_bear.empty:
            c3, c4 = st.columns(2)
            color_map_bear = {'反彈': '#AA00FF', '續跌': '#D50000'} 
            
            with c3:
                df_bear_win = df_bear.sort_values(by='上漲機率', ascending=True)
                fig_bear_win = px.bar(
                    df_bear_win, x='上漲機率', y='策略名稱', color='短期狀態',
                    text_auto='.1%', orientation='h', color_discrete_map=color_map_bear,
                    title="[熊市] 持有12個月獲利機率"
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
        # 8. 詳細數據表
        # -----------------------------------------------------
        st.divider()
        with st.expander("📄 查看完整詳細數據表"):
            def highlight_group(s):
                return ['background-color: rgba(27, 94, 32, 0.1)' if v == 'Bull' else 'background-color: rgba(183, 28, 28, 0.1)' for v in s]

            st.dataframe(
                res_df.sort_values(by=['大環境', '上漲機率'], ascending=[False, False])
                .style.format({'上漲機率': '{:.2%}', '平均漲幅': '{:.2%}', '樣本數': '{:.0f}'})
                .apply(highlight_group, subset=['大環境']),
                use_container_width=True
            )
