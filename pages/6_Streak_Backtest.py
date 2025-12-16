###############################################################
# pages/2_Momentum_Backtest.py — 雙動能配置：順勢 vs 拉回決策輔助
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
    page_title="雙動能決策輔助",
    page_icon="⚖️",
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
    "<h1 style='margin-bottom:0.5em;'>⚖️ 雙動能配置決策：順勢追高 vs 拉回低接</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
    <b>策略邏輯 (Dual Momentum)：</b><br>
    1. <b>絕對動能 (Absolute)</b>：鎖定 <b>過去 12 個月</b> 漲幅 > 0 (確保年線多頭架構)。<br>
    2. <b>微操作判斷</b>：當資產符合年線多頭，但 <b>短期 M 個月</b> 出現變化時，歷史數據支持哪種動作？<br>
       🚀 <b>順勢 (Momentum)</b>：短期續漲，強者恆強。<br>
       🛡️ <b>拉回 (Pullback)</b>：短期回檔，低接機會 (均值回歸)。
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
# 3. UI 輸入區
###############################################################

csv_files = get_all_csv_files()

if not csv_files:
    st.error("⚠️ Data 資料夾內沒有 CSV 檔案。")
    st.stop()

col1, col2 = st.columns(2)
with col1:
    target_symbol = st.selectbox("選擇回測標的", csv_files, index=0)

with col2:
    # A. 長期趨勢固定為 12 個月
    st.info("🔒 **主要趨勢 (N)**：固定鎖定為 **12 個月** (年線多頭確認)")
    fixed_n = 12
    
    # B. 短期濾網改為複選
    default_short = [1, 3] # 預設測試 1個月, 3個月
    selected_m = st.multiselect(
        "設定短期濾網月數 (M) - 自動比較「續漲」與「回檔」", 
        [1, 2, 3, 4, 5, 6, 9], 
        default=default_short,
        help="例如選 3，系統會分析「年線漲且近3月漲」vs「年線漲但近3月跌」的績效差異"
    )

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
# 5. 主程式邏輯
###############################################################

if st.button("開始回測 🚀") and target_symbol:
    
    with st.spinner(f"正在診斷 {target_symbol} 順勢與逆勢特性..."):
        df_daily = load_csv(target_symbol)
        
        if df_daily.empty:
            st.error(f"讀取 {target_symbol} 失敗")
            st.stop()

        start_date = df_daily.index.min().strftime('%Y-%m-%d')
        end_date = df_daily.index.max().strftime('%Y-%m-%d')
        total_years = (df_daily.index.max() - df_daily.index.min()).days / 365.25

        # 轉月線
        try:
            df_monthly = df_daily['Price'].resample('ME').last().to_frame()
        except Exception:
            df_monthly = df_daily['Price'].resample('M').last().to_frame()
            
        df_monthly['Next_Month_Return'] = df_monthly['Price'].pct_change().shift(-1)
        
        results = []
        
        # --- 1. 計算主要趨勢訊號 (N=12) ---
        # 邏輯：現在價格 > 12個月前價格
        momentum_long = df_monthly['Price'].pct_change(periods=fixed_n)
        signal_long = momentum_long > 0
        
        # --- 2. 迴圈跑不同的「短期濾網 M」 ---
        for m in sorted(selected_m):
            
            momentum_short = df_monthly['Price'].pct_change(periods=m)
            
            # --- 情境 A: 順勢 (年線漲 + 短期漲) ---
            signal_trend = signal_long & (momentum_short > 0)
            
            # --- 情境 B: 拉回 (年線漲 + 短期跌) ---
            signal_pullback = signal_long & (momentum_short < 0)
            
            # 內部計算函式
            def calc_stats(signal_series, label, sort_idx):
                target_returns = df_monthly.loc[signal_series, 'Next_Month_Return'].dropna()
                count = len(target_returns)
                
                if count > 0:
                    win_count = target_returns[target_returns > 0].count()
                    win_rate = win_count / count
                    avg_ret = target_returns.mean()
                    med_ret = target_returns.median()
                    max_ret = target_returns.max()
                    min_ret = target_returns.min()
                else:
                    win_rate, avg_ret, med_ret, max_ret, min_ret = 0, 0, 0, 0, 0
                
                return {
                    '回測設定': label,
                    '排序': sort_idx, 
                    '短期M': m,
                    '類型': '順勢' if '續漲' in label else '拉回',
                    '發生次數': count,
                    '勝率 (Win Rate)': win_rate,
                    '平均報酬': avg_ret,
                    '中位數報酬': med_ret,
                    '最大漲幅': max_ret,
                    '最大跌幅': min_ret
                }

            # 加入結果
            results.append(calc_stats(signal_trend, f"年線多 + {m}月續漲 (順勢)", m * 10 + 1))
            results.append(calc_stats(signal_pullback, f"年線多 + {m}月回檔 (低接)", m * 10 + 2))
            
        res_df = pd.DataFrame(results).sort_values(by='排序')
        
        # 基礎樣本統計
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
    
    # --- KPI 卡片 ---
    best_strategy = res_df.loc[res_df['平均報酬'].idxmax()] if not res_df.empty else None
    
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
            st.markdown(simple_card("🔥 平均報酬最高", f"{best_strategy['回測設定']}"), unsafe_allow_html=True)
    with col_kpi[3]:
        if best_strategy is not None:
            st.markdown(simple_card("該策略平均月酬", f"{best_strategy['平均報酬']:.2%}"), unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 30px'></div>", unsafe_allow_html=True)

    # --- 圖表區 ---
    st.markdown("<h3>📊 順勢 vs 拉回：策略效果對決</h3>", unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["勝率分析", "平均報酬分析"])
    
    with tab1:
        if not res_df.empty:
            fig_win = go.Figure()
            fig_win.add_hline(y=base_win_rate, line_dash="dash", line_color="gray", annotation_text="Buy & Hold 勝率")
            
            # 順勢=綠色, 拉回=橘色
            colors = ['#00CC96' if t == '順勢' else '#FFA15A' for t in res_df['類型']]
            
            fig_win.add_trace(go.Bar(
                x=res_df['回測設定'],
                y=res_df['勝率 (Win Rate)'],
                text=[f"{v:.1%}" for v in res_df['勝率 (Win Rate)']],
                textposition='auto',
                marker_color=colors
            ))
            fig_win.update_layout(
                title="不同策略情境的下月勝率",
                yaxis_tickformat='.0%',
                template="plotly_white",
                height=450,
                xaxis_title="策略組合",
                yaxis_title="勝率"
            )
            st.plotly_chart(fig_win, use_container_width=True)

    with tab2:
        if not res_df.empty:
            fig_ret = go.Figure()
            fig_ret.add_hline(y=base_avg_ret, line_dash="dash", line_color="gray", annotation_text="Buy & Hold 平均報酬")
            
            # 順勢=深藍, 拉回=深紅 (強調報酬)
            colors = ['#636EFA' if t == '順勢' else '#EF553B' for t in res_df['類型']]

            fig_ret.add_trace(go.Bar(
                x=res_df['回測設定'],
                y=res_df['平均報酬'],
                text=[f"{v:.2%}" for v in res_df['平均報酬']],
                textposition='auto',
                name='平均報酬',
                marker_color=colors
            ))
            
            fig_ret.update_layout(
                title="不同策略情境的下月平均報酬",
                yaxis_tickformat='.2%',
                template="plotly_white",
                height=450,
                xaxis_title="策略組合",
                yaxis_title="平均報酬"
            )
            st.plotly_chart(fig_ret, use_container_width=True)

    # --- 表格 (含風險警示邏輯) ---
    if not res_df.empty:
        st.markdown("<h3>🏆 策略績效詳細比較</h3>", unsafe_allow_html=True)
        
        st.info("💡 **判讀技巧**：如果「拉回 (低接)」策略的 **平均報酬為負** (標示為 ⚠️)，代表該資產在多頭回檔時容易直接轉弱，建議 **避開接刀** 或 **減碼**。")

        metrics_map = {
            "發生次數":      {"fmt": lambda x: f"{int(x):,}", "high_is_good": True},
            "勝率 (Win Rate)": {"fmt": lambda x: f"{x:.2%}",   "high_is_good": True},
            "平均報酬":      {"fmt": lambda x: f"{x:.2%}",   "high_is_good": True},
            "中位數報酬":    {"fmt": lambda x: f"{x:.2%}",   "high_is_good": True},
            "最大漲幅":      {"fmt": lambda x: f"{x:.2%}",   "high_is_good": True},
            "最大跌幅":      {"fmt": lambda x: f"{x:.2%}",   "high_is_good": True},
        }

        html = '<table class="comparison-table"><thead><tr><th style="text-align:left; padding-left:16px;">指標</th>'
        
        # 1. 產生表頭
        for name in res_df['回測設定']:
            if "回檔" in name:
                html += f"<th style='color:#E65100; background-color:rgba(255,167,38,0.1)'>{name}</th>"
            else:
                html += f"<th style='color:#1B5E20; background-color:rgba(102,187,106,0.1)'>{name}</th>"
        html += "</tr></thead><tbody>"

        # 2. 產生內容
        for metric, config in metrics_map.items():
            html += f"<tr><td class='metric-name' style='padding-left:16px;'>{metric}</td>"
            
            vals = res_df[metric].values
            best_val = max(vals) if config["high_is_good"] else min(vals)
            
            for i, val in enumerate(vals):
                display_text = config["fmt"](val)
                col_name = res_df['回測設定'].iloc[i]
                
                # ★★★ 風險警示邏輯 ★★★
                # 如果是 平均報酬 且 小於 0 且 是回檔策略 -> 紅色警告
                if metric == "平均報酬" and val < 0 and "回檔" in col_name:
                    display_text = f"<span style='color:#D32F2F; font-weight:bold;'>⚠️ {display_text}</span>"
                
                # ★★★ 冠軍邏輯 ★★★
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
