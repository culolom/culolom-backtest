###############################################################
# pages/2_Streak_Backtest.py — 連續上漲動能回測
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go
from pathlib import Path

###############################################################
# 字型設定 (維持原樣)
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

###############################################################
# Streamlit 頁面設定
###############################################################

st.set_page_config(
    page_title="連漲動能回測",
    page_icon="🔥",
    layout="wide",
)

# ------------------------------------------------------
# 🔒 驗證守門員 (保留您的驗證邏輯)
# ------------------------------------------------------
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except ImportError:
    pass # 如果沒有 auth.py 則跳過 (方便測試)
# ------------------------------------------------------

with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

st.markdown(
    "<h1 style='margin-bottom:0.5em;'>🔥 連續上漲動能回測 (Monthly Streak)</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
    <b>策略邏輯：</b><br>
    統計當標的出現 <b>「連續 N 個月上漲」</b> 後，<b>「下一個月」</b> 的漲跌機率與平均報酬。<br>
    這能幫助判斷趨勢是處於 <b>「動能強勢期 (Momentum)」</b> 還是 <b>「過熱反轉期 (Mean Reversion)」</b>。
    """,
    unsafe_allow_html=True,
)

###############################################################
# 資料讀取與處理
###############################################################

DATA_DIR = Path("data")

def get_all_csv_files():
    """掃描 data 資料夾下的所有 csv"""
    if not DATA_DIR.exists():
        os.makedirs(DATA_DIR)
        return []
    files = [f.stem for f in DATA_DIR.glob("*.csv")]
    return sorted(files)

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.sort_index()
    # 確保有 Price 欄位 (相容您的資料格式)
    if "Adj Close" in df.columns:
        df["Price"] = df["Adj Close"]
    elif "Close" in df.columns:
        df["Price"] = df["Close"]
    return df[["Price"]]

###############################################################
# UI 輸入區
###############################################################

csv_files = get_all_csv_files()

if not csv_files:
    st.error("⚠️ Data 資料夾內沒有 CSV 檔案，請先上傳數據。")
    st.stop()

col1, col2 = st.columns(2)
with col1:
    target_symbol = st.selectbox("選擇回測標的", csv_files, index=0)

with col2:
    # 預設連漲月數選項
    default_periods = [3, 5, 6, 9, 12]
    selected_periods = st.multiselect("設定連漲月數 (N)", [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 15, 24], default=default_periods)

###############################################################
# CSS 樣式 (保留原版高級 UI)
###############################################################

st.markdown("""
    <style>
        .kpi-card {
            background-color: var(--secondary-background-color);
            border-radius: 16px;
            padding: 24px 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.04);
            border: 1px solid rgba(128, 128, 128, 0.1);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            height: 100%;
            transition: all 0.3s ease;
        }
        .kpi-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.08);
        }
        .kpi-label {
            font-size: 0.9rem;
            color: var(--text-color);
            opacity: 0.7;
            font-weight: 500;
            margin-bottom: 8px;
            text-transform: uppercase;
        }
        .kpi-value {
            font-size: 2rem;
            font-weight: 800;
            color: var(--text-color);
            font-family: 'Noto Sans TC', sans-serif;
            line-height: 1.2;
        }
        .trophy-icon {
            margin-left: 6px;
            font-size: 1.1em;
            text-shadow: 0 0 5px rgba(255, 215, 0, 0.4);
        }
    </style>
""", unsafe_allow_html=True)

###############################################################
# 主程式邏輯
###############################################################

if st.button("開始回測 🚀") and target_symbol:
    
    with st.spinner(f"正在分析 {target_symbol} 歷史數據..."):
        # 1. 讀取數據
        df_daily = load_csv(target_symbol)
        
        if df_daily.empty:
            st.error("讀取失敗或無數據")
            st.stop()

        # 2. 轉換為月線 (取每個月最後一天的價格)
        # 使用 'ME' (Month End) 
        try:
            df_monthly = df_daily['Price'].resample('ME').last().to_frame()
        except Exception:
            # 相容舊版 Pandas
            df_monthly = df_daily['Price'].resample('M').last().to_frame()
            
        # 計算月報酬
        df_monthly['Return'] = df_monthly['Price'].pct_change()
        
        # 判斷是否上漲
        is_positive = df_monthly['Return'] > 0
        
        results = []
        
        # 3. 迴圈跑不同的「連漲月數」設定
        for n in sorted(selected_periods):
            # 核心邏輯：滾動視窗總和是否等於 n (True=1, False=0)
            streak_signal = is_positive.rolling(window=n).sum() == n
            
            # 找出訊號觸發後的「下個月」
            # shift(1) 代表訊號成立(月底)的「次月」
            target_months = df_monthly['Return'][streak_signal.shift(1).fillna(False)]
            
            count = len(target_months)
            
            if count > 0:
                win_count = target_months[target_months > 0].count()
                win_rate = win_count / count
                avg_ret = target_months.mean()
                med_ret = target_months.median()
                max_ret = target_months.max()
                min_ret = target_months.min()
            else:
                win_rate = 0
                avg_ret = 0
                med_ret = 0
                max_ret = 0
                min_ret = 0

            results.append({
                '連漲月數': f"連漲{n}月",
                'N': n, # 用於排序
                '發生次數': count,
                '勝率 (Win Rate)': win_rate,
                '平均報酬': avg_ret,
                '中位數報酬': med_ret,
                '最大漲幅': max_ret,
                '最大跌幅': min_ret
            })
            
        # 轉為 DataFrame
        res_df = pd.DataFrame(results)
        
        # 4. 基礎樣本統計 (Base Rate) - 所有月份的平均表現
        base_win_rate = len(df_monthly[df_monthly['Return'] > 0]) / len(df_monthly)
        base_avg_ret = df_monthly['Return'].mean()

    # -----------------------------------------------------
    # 顯示結果區
    # -----------------------------------------------------

    # --- KPI 卡片區 (顯示整體基準 vs 最佳策略) ---
    best_strategy = res_df.loc[res_df['勝率 (Win Rate)'].idxmax()] if not res_df.empty else None
    
    col_kpi = st.columns(4)
    
    def simple_card(label, value):
        return f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
        </div>
        """

    with col_kpi[0]:
        st.markdown(simple_card("總交易月數", f"{len(df_monthly):,} 月"), unsafe_allow_html=True)
    with col_kpi[1]:
        st.markdown(simple_card("基準月勝率 (Base)", f"{base_win_rate:.1%}"), unsafe_allow_html=True)
    with col_kpi[2]:
        if best_strategy is not None:
            st.markdown(simple_card("🔥 最高勝率設定", f"{best_strategy['連漲月數']}"), unsafe_allow_html=True)
    with col_kpi[3]:
        if best_strategy is not None:
            st.markdown(simple_card("該設定勝率", f"{best_strategy['勝率 (Win Rate)']:.1%}"), unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 30px'></div>", unsafe_allow_html=True)

    # --- 圖表區 (Plotly) ---
    st.markdown("<h3>📊 連漲後的下月表現分析</h3>", unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["勝率分析", "平均報酬分析"])
    
    with tab1:
        # 勝率 Bar Chart
        fig_win = go.Figure()
        # 加入基準線
        fig_win.add_hline(y=base_win_rate, line_dash="dash", line_color="gray", annotation_text="基準勝率")
        
        colors = ['#EF553B' if val < base_win_rate else '#00CC96' for val in res_df['勝率 (Win Rate)']]
        
        fig_win.add_trace(go.Bar(
            x=res_df['連漲月數'],
            y=res_df['勝率 (Win Rate)'],
            text=[f"{v:.1%}" for v in res_df['勝率 (Win Rate)']],
            textposition='auto',
            marker_color=colors
        ))
        fig_win.update_layout(
            title="各連漲週期下個月上漲機率",
            yaxis_tickformat='.0%',
            template="plotly_white",
            height=400
        )
        st.plotly_chart(fig_win, use_container_width=True)

    with tab2:
        # 報酬率 Bar Chart
        fig_ret = go.Figure()
        fig_ret.add_hline(y=base_avg_ret, line_dash="dash", line_color="gray", annotation_text="基準平均報酬")
        
        fig_ret.add_trace(go.Bar(
            x=res_df['連漲月數'],
            y=res_df['平均報酬'],
            name='平均報酬',
            marker_color='#636EFA'
        ))
        fig_ret.add_trace(go.Scatter(
            x=res_df['連漲月數'],
            y=res_df['中位數報酬'],
            mode='markers+lines',
            name='中位數報酬',
            line=dict(color='#FFA15A', width=2)
        ))
        
        fig_ret.update_layout(
            title="各連漲週期下個月平均報酬 vs 中位數",
            yaxis_tickformat='.2%',
            template="plotly_white",
            height=400,
            hovermode="x unified"
        )
        st.plotly_chart(fig_ret, use_container_width=True)

    # --- HTML 冠軍比較表格 (重構資料結構以符合您的 Table 樣式) ---
    st.markdown("<h3>🏆 策略績效詳細比較</h3>", unsafe_allow_html=True)

    # 1. 轉置 DataFrame 讓直行變成策略(N個月)，橫列變成指標
    # 我們需要構建一個 dict 來生成 HTML
    metrics_map = {
        "發生次數": {"fmt": lambda x: f"{int(x):,}", "high_is_good": True}, # 次數多通常統計意義較大
        "勝率 (Win Rate)": {"fmt": lambda x: f"{x:.2%}", "high_is_good": True},
        "平均報酬": {"fmt": lambda x: f"{x:.2%}", "high_is_good": True},
        "中位數報酬": {"fmt": lambda x: f"{x:.2%}", "high_is_good": True},
        "最大漲幅": {"fmt": lambda x: f"{x:.2%}", "high_is_good": True},
        "最大跌幅": {"fmt": lambda x: f"{x:.2%}", "high_is_good": True}, # 這裡是數值(負數)，通常希望越接近0越好(越大越好)
    }

    # CSS 樣式 (極簡版 Table)
    st.markdown("""
    <style>
        .comparison-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            border-radius: 12px;
            border: 1px solid var(--secondary-background-color);
            font-family: 'Noto Sans TC', sans-serif;
            margin-bottom: 1rem;
            font-size: 0.95rem;
        }
        .comparison-table th {
            background-color: var(--secondary-background-color);
            color: var(--text-color);
            padding: 14px;
            text-align: center;
            font-weight: 600;
            border-bottom: 1px solid rgba(128,128,128, 0.1);
        }
        .comparison-table td {
            text-align: center;
            padding: 12px;
            color: var(--text-color);
            border-bottom: 1px solid rgba(128,128,128, 0.1);
        }
        .comparison-table td.metric-name {
            text-align: left;
            font-weight: 500;
            background-color: rgba(128,128,128, 0.02);
            width: 20%;
        }
        .comparison-table tr:hover td {
            background-color: rgba(128,128,128, 0.05);
        }
    </style>
    """, unsafe_allow_html=True)

    # 生成 HTML
    html = '<table class="comparison-table"><thead><tr><th style="text-align:left; padding-left:16px;">指標</th>'
    
    # 表頭 (策略名稱)
    for name in res_df['連漲月數']:
        html += f"<th>{name}</th>"
    html += "</tr></thead><tbody>"

    # 內容
    for metric, config in metrics_map.items():
        html += f"<tr><td class='metric-name' style='padding-left:16px;'>{metric}</td>"
        
        # 找出該列的最大值(用於頒發獎盃)
        vals = res_df[metric].values
        best_val = max(vals) if config["high_is_good"] else min(vals)
        
        for val in vals:
            display_text = config["fmt"](val)
            is_winner = (val == best_val)
            
            if is_winner and metric != "發生次數": # 發生次數不一定要給獎盃
                display_text += " <span class='trophy-icon'>🏆</span>"
                html += f"<td style='font-weight:bold; color:#00CC96;'>{display_text}</td>"
            else:
                html += f"<td>{display_text}</td>"
        html += "</tr>"
        
    html += "</tbody></table>"
    st.write(html, unsafe_allow_html=True)
