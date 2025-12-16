###############################################################
# pages/2_Momentum_Backtest.py — 動能趨勢回測 (Momentum) + 雙重濾網
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
import sys

###############################################################
# 1. 字型與基本設定
###############################################################

font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

st.set_page_config(
    page_title="動能趨勢回測",
    page_icon="🚀",
    layout="wide",
)

# ------------------------------------------------------
# 🔒 驗證模組
# ------------------------------------------------------
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except ImportError:
    pass

# ------------------------------------------------------
# Sidebar
# ------------------------------------------------------
with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

# ------------------------------------------------------
# 主標題
# ------------------------------------------------------
st.markdown(
    "<h1 style='margin-bottom:0.5em;'>🚀 動能趨勢回測 (Time Series Momentum)</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
    <b>策略邏輯：</b><br>
    檢查過去 <b>N 個月</b> 的累積漲幅是否大於 0 (即目前價格 > N個月前價格)。<br>
    若滿足條件，統計 <b>「下一個月」</b> 的續漲機率與平均報酬。這是經典的 <b>趨勢跟隨 (Trend Following)</b> 策略。
    """,
    unsafe_allow_html=True,
)

###############################################################
# 2. 資料讀取
###############################################################

DATA_DIR = Path("data")

def get_all_csv_files():
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
    
    if "Adj Close" in df.columns:
        df["Price"] = df["Adj Close"]
    elif "Close" in df.columns:
        df["Price"] = df["Close"]
        
    return df[["Price"]]

###############################################################
# 3. UI 輸入區 (新增雙重濾網選項)
###############################################################

csv_files = get_all_csv_files()

if not csv_files:
    st.error("⚠️ Data 資料夾內沒有 CSV 檔案。")
    st.stop()

col1, col2 = st.columns(2)
with col1:
    target_symbol = st.selectbox("選擇回測標的", csv_files, index=0)

with col2:
    # 修改預設值，這些是常用的動能週期
    default_periods = [3, 6, 9, 12]
    selected_periods = st.multiselect("設定主要趨勢月數 (N)", [1, 3, 6, 9, 10, 12, 18, 24], default=default_periods)
    
    # --- 新增：雙重確認濾網 UI ---
    st.markdown("---")
    use_double_filter = st.checkbox("✅ 開啟「雙重確認」濾網 (Double Confirmation)", value=False, help="同時滿足「長週期」與「短週期」漲幅皆 > 0 才進場")
    
    filter_period = 1
    if use_double_filter:
        filter_period = st.number_input("設定短期濾網月數 (M)", min_value=1, value=1, help="通常設為 1，代表除了看長線，也要確認上個月是漲的")

###############################################################
# 4. CSS
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
        .trophy-icon {
            margin-left: 6px;
            font-size: 1.1em;
            text-shadow: 0 0 5px rgba(255, 215, 0, 0.4);
        }
    </style>
""", unsafe_allow_html=True)

###############################################################
# 5. 主程式邏輯 (核心修改處：雙重條件)
###############################################################

if st.button("開始回測 🚀") and target_symbol:
    
    with st.spinner(f"正在分析 {target_symbol} 動能數據..."):
        # 1. 讀取與時間處理
        df_daily = load_csv(target_symbol)
        
        if df_daily.empty:
            st.error(f"讀取 {target_symbol} 失敗")
            st.stop()

        start_date = df_daily.index.min().strftime('%Y-%m-%d')
        end_date = df_daily.index.max().strftime('%Y-%m-%d')
        total_years = (df_daily.index.max() - df_daily.index.min()).days / 365.25

        # 2. 轉換為月線
        try:
            df_monthly = df_daily['Price'].resample('ME').last().to_frame()
        except Exception:
            df_monthly = df_daily['Price'].resample('M').last().to_frame()
            
        # 計算「下個月」的報酬 (這是我們要預測的目標)
        df_monthly['Next_Month_Return'] = df_monthly['Price'].pct_change().shift(-1)
        
        results = []
        
        # 3. 迴圈跑不同的「過去 N 個月漲幅」
        for n in sorted(selected_periods):
            
            # --- A. 主要條件：長期趨勢 ---
            momentum_long = df_monthly['Price'].pct_change(periods=n)
            signal_long = momentum_long > 0
            
            # --- B. 次要條件：短期濾網 (如果有勾選) ---
            if use_double_filter:
                momentum_short = df_monthly['Price'].pct_change(periods=filter_period)
                signal_short = momentum_short > 0
                
                # ★ 核心邏輯：兩者皆為 True 才持有
                final_signal = signal_long & signal_short
                strategy_name = f"過去{n}月且{filter_period}月皆漲"
            else:
                final_signal = signal_long
                strategy_name = f"過去{n}月漲幅>0"
            
            # 找出訊號成立時，「下個月」的表現
            target_returns = df_monthly.loc[final_signal, 'Next_Month_Return'].dropna()
            
            count = len(target_returns)
            
            if count > 0:
                win_count = target_returns[target_returns > 0].count()
                win_rate = win_count / count
                avg_ret = target_returns.mean()
                med_ret = target_returns.median()
                max_ret = target_returns.max()
                min_ret = target_returns.min()
            else:
                win_rate = 0
                avg_ret = 0
                med_ret = 0
                max_ret = 0
                min_ret = 0

            results.append({
                '回測設定': strategy_name,
                'N': n,
                '發生次數': count,
                '勝率 (Win Rate)': win_rate,
                '平均報酬': avg_ret,
                '中位數報酬': med_ret,
                '最大漲幅': max_ret,
                '最大跌幅': min_ret
            })
            
        res_df = pd.DataFrame(results)
        
        # 4. 基礎樣本統計 (Base Rate)
        base_returns = df_monthly['Next_Month_Return'].dropna()
        if not base_returns.empty:
            base_win_rate = base_returns[base_returns > 0].count() / len(base_returns)
            base_avg_ret = base_returns.mean()
        else:
            base_win_rate = 0
            base_avg_ret = 0

    # -----------------------------------------------------
    # 6. 顯示結果
    # -----------------------------------------------------

    st.success(f"📅 **回測區間**：{start_date} ~ {end_date} (共 {total_years:.1f} 年)")
    if use_double_filter:
        st.info(f"🛡️ **濾網已開啟**：除了主要趨勢外，系統額外檢查「過去 {filter_period} 個月」是否也上漲。這通常能避開長期趨勢轉折初期的假訊號。")

    # --- KPI 卡片 ---
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
            # 簡化顯示 best strategy name
            st.markdown(simple_card("🔥 最佳勝率設定", f"{best_strategy['回測設定']}"), unsafe_allow_html=True)
    with col_kpi[3]:
        if best_strategy is not None:
            st.markdown(simple_card("該設定勝率", f"{best_strategy['勝率 (Win Rate)']:.1%}"), unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 30px'></div>", unsafe_allow_html=True)

    # --- 圖表區 ---
    st.markdown("<h3>📊 動能訊號出現後的下月表現</h3>", unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["勝率分析", "平均報酬分析"])
    
    with tab1:
        if not res_df.empty:
            fig_win = go.Figure()
            fig_win.add_hline(y=base_win_rate, line_dash="dash", line_color="gray", annotation_text="Buy & Hold 勝率")
            
            colors = ['#EF553B' if val < base_win_rate else '#00CC96' for val in res_df['勝率 (Win Rate)']]
            
            fig_win.add_trace(go.Bar(
                x=res_df['回測設定'],
                y=res_df['勝率 (Win Rate)'],
                text=[f"{v:.1%}" for v in res_df['勝率 (Win Rate)']],
                textposition='auto',
                marker_color=colors
            ))
            fig_win.update_layout(
                title="各策略設定下個月上漲機率",
                yaxis_tickformat='.0%',
                template="plotly_white",
                height=400,
                xaxis_title="策略設定",
                yaxis_title="勝率"
            )
            st.plotly_chart(fig_win, use_container_width=True)

    with tab2:
        if not res_df.empty:
            fig_ret = go.Figure()
            fig_ret.add_hline(y=base_avg_ret, line_dash="dash", line_color="gray", annotation_text="Buy & Hold 平均報酬")
            
            fig_ret.add_trace(go.Bar(
                x=res_df['回測設定'],
                y=res_df['平均報酬'],
                name='平均報酬',
                marker_color='#636EFA'
            ))
            fig_ret.add_trace(go.Scatter(
                x=res_df['回測設定'],
                y=res_df['中位數報酬'],
                mode='markers+lines',
                name='中位數報酬',
                line=dict(color='#FFA15A', width=2)
            ))
            
            fig_ret.update_layout(
                title="各策略設定下個月平均報酬 vs 中位數",
                yaxis_tickformat='.2%',
                template="plotly_white",
                height=400,
                hovermode="x unified"
            )
            st.plotly_chart(fig_ret, use_container_width=True)

    # --- 表格 ---
    if not res_df.empty:
        st.markdown("<h3>🏆 動能策略詳細績效</h3>", unsafe_allow_html=True)

        metrics_map = {
            "發生次數":      {"fmt": lambda x: f"{int(x):,}", "high_is_good": True},
            "勝率 (Win Rate)": {"fmt": lambda x: f"{x:.2%}",   "high_is_good": True},
            "平均報酬":      {"fmt": lambda x: f"{x:.2%}",   "high_is_good": True},
            "中位數報酬":    {"fmt": lambda x: f"{x:.2%}",   "high_is_good": True},
            "最大漲幅":      {"fmt": lambda x: f"{x:.2%}",   "high_is_good": True},
            "最大跌幅":      {"fmt": lambda x: f"{x:.2%}",   "high_is_good": True},
        }

        html = '<table class="comparison-table"><thead><tr><th style="text-align:left; padding-left:16px;">指標</th>'
        
        for name in res_df['回測設定']:
            html += f"<th>{name}</th>"
        html += "</tr></thead><tbody>"

        for metric, config in metrics_map.items():
            html += f"<tr><td class='metric-name' style='padding-left:16px;'>{metric}</td>"
            
            vals = res_df[metric].values
            best_val = max(vals) if config["high_is_good"] else min(vals)
            
            for val in vals:
                display_text = config["fmt"](val)
                is_winner = (val == best_val) and (metric != "發生次數") and (metric != "最大跌幅")
                
                if metric == "最大跌幅" and val == max(vals): is_winner = True

                if is_winner:
                    display_text += " <span class='trophy-icon'>🏆</span>"
                    html += f"<td style='font-weight:bold; color:#00CC96;'>{display_text}</td>"
                else:
                    html += f"<td>{display_text}</td>"
            html += "</tr>"
            
        html += "</tbody></table>"
        st.write(html, unsafe_allow_html=True)
