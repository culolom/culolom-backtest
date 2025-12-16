###############################################################
# pages/2_Momentum_Backtest.py — 雙動能 + 凱利/半凱利資金管理
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
    page_title="雙動能凱利決策(短線空手專用)",
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
    "<h1 style='margin-bottom:0.5em;'>⚖️ 雙動能凱利決策(短線空手專用) (Kelly Criterion)</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    """
    <b>策略邏輯 (Markov Chain + Kelly)：</b><br>
    1. <b>狀態定義</b>：鎖定 <b>年線多頭 (12月漲)</b>，並區分 <b>短期順勢 (M月漲)</b> 與 <b>短期回檔 (M月跌)</b>。<br>
    2. <b>資金管理</b>：利用 <b>凱利公式</b> 計算最佳下注比例。系統同時提供 <b>「全凱利 (理論值)」</b> 與 <b>「半凱利 (實戰建議)」</b>。<br>
       <span style="color:#00C853"><b>正凱利值</b></span>：具備數學優勢。<br>
       <span style="color:#D32F2F"><b>負凱利值</b></span>：期望值為負，應避開。
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
    st.info("🔒 **主要趨勢 (N)**：固定鎖定為 **12 個月** (年線多頭確認)")
    fixed_n = 12
    
    default_short = [1, 3] 
    selected_m = st.multiselect(
        "設定短期濾網月數 (M) - 自動計算凱利值", 
        [1, 2, 3, 4, 5, 6, 9], 
        default=default_short
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
# 5. 主程式邏輯 (含半凱利計算)
###############################################################

if st.button("開始回測 🚀") and target_symbol:
    
    with st.spinner(f"正在計算凱利公式與狀態期望值: {target_symbol} ..."):
        df_daily = load_csv(target_symbol)
        
        if df_daily.empty:
            st.error(f"讀取 {target_symbol} 失敗")
            st.stop()

        start_date = df_daily.index.min().strftime('%Y-%m-%d')
        end_date = df_daily.index.max().strftime('%Y-%m-%d')
        total_years = (df_daily.index.max() - df_daily.index.min()).days / 365.25

        try:
            df_monthly = df_daily['Price'].resample('ME').last().to_frame()
        except Exception:
            df_monthly = df_daily['Price'].resample('M').last().to_frame()
            
        df_monthly['Next_Month_Return'] = df_monthly['Price'].pct_change().shift(-1)
        
        results = []
        
        momentum_long = df_monthly['Price'].pct_change(periods=fixed_n)
        signal_long = momentum_long > 0
        
        for m in sorted(selected_m):
            momentum_short = df_monthly['Price'].pct_change(periods=m)
            
            signal_trend = signal_long & (momentum_short > 0)
            signal_pullback = signal_long & (momentum_short < 0)
            
            def calc_stats_kelly(signal_series, label, sort_idx):
                target_returns = df_monthly.loc[signal_series, 'Next_Month_Return'].dropna()
                count = len(target_returns)
                
                if count > 0:
                    wins = target_returns[target_returns > 0]
                    losses = target_returns[target_returns <= 0]
                    
                    win_count = wins.count()
                    loss_count = losses.count()
                    
                    win_rate = win_count / count
                    avg_ret = target_returns.mean()
                    
                    avg_win_pct = wins.mean() if win_count > 0 else 0
                    avg_loss_pct = abs(losses.mean()) if loss_count > 0 else 0
                    
                    if avg_loss_pct > 0:
                        payoff_ratio = avg_win_pct / avg_loss_pct
                    else:
                        payoff_ratio = 0 

                    # 計算 全凱利 (Full Kelly)
                    if payoff_ratio > 0:
                        kelly_pct = win_rate - ((1 - win_rate) / payoff_ratio)
                    else:
                        kelly_pct = 0
                    
                    if win_count == 0: kelly_pct = -1.0 
                    if loss_count == 0: kelly_pct = 1.0 

                    # 計算 半凱利 (Half Kelly)
                    # 如果凱利值是負的，半凱利依然是負的(無意義)，如果是正的，則減半
                    half_kelly_pct = kelly_pct * 0.5

                    med_ret = target_returns.median()
                    max_ret = target_returns.max()
                    min_ret = target_returns.min()
                else:
                    win_rate, avg_ret, med_ret, max_ret, min_ret = 0, 0, 0, 0, 0
                    avg_win_pct, avg_loss_pct, payoff_ratio, kelly_pct, half_kelly_pct = 0, 0, 0, 0, 0
                
                return {
                    '回測設定': label,
                    '排序': sort_idx, 
                    '短期M': m,
                    '類型': '順勢' if '續漲' in label else '拉回',
                    '發生次數': count,
                    '勝率': win_rate,
                    '賠率 (盈虧比)': payoff_ratio,
                    '凱利值 (理論全倉)': kelly_pct,
                    '半凱利 (建議穩健)': half_kelly_pct, # 新增欄位
                    '平均獲利': avg_win_pct,
                    '平均虧損': avg_loss_pct,
                    '平均報酬': avg_ret,
                    '最大跌幅': min_ret
                }

            results.append(calc_stats_kelly(signal_trend, f"年線多 + {m}月續漲 (順勢)", m * 10 + 1))
            results.append(calc_stats_kelly(signal_pullback, f"年線多 + {m}月回檔 (低接)", m * 10 + 2))
            
        res_df = pd.DataFrame(results).sort_values(by='排序')
        
        # Base Rate
        base_returns = df_monthly['Next_Month_Return'].dropna()
        if not base_returns.empty:
            base_win_rate = base_returns[base_returns > 0].count() / len(base_returns)
        else:
            base_win_rate = 0

    # -----------------------------------------------------
    # 6. 顯示結果
    # -----------------------------------------------------

    st.success(f"📅 **回測區間**：{start_date} ~ {end_date} (共 {total_years:.1f} 年)")
    
    # KPI 改為顯示「半凱利」
    best_strategy = res_df.loc[res_df['半凱利 (建議穩健)'].idxmax()] if not res_df.empty else None
    
    col_kpi = st.columns(4)
    
    def simple_card(label, value, sub_value=""):
        return f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div style="font-size:0.8em; opacity:0.7; margin-top:4px">{sub_value}</div>
        </div>
        """

    with col_kpi[0]:
        st.markdown(simple_card("總交易月數", f"{len(df_monthly):,} 月"), unsafe_allow_html=True)
    with col_kpi[1]:
        st.markdown(simple_card("基準月勝率", f"{base_win_rate:.1%}"), unsafe_allow_html=True)
    with col_kpi[2]:
        if best_strategy is not None:
            st.markdown(simple_card("🔥 最佳策略", f"{best_strategy['回測設定']}"), unsafe_allow_html=True)
    with col_kpi[3]:
        if best_strategy is not None:
            # 這裡顯示半凱利
            hk_val = best_strategy['半凱利 (建議穩健)']
            st.markdown(simple_card("最佳半凱利", f"{hk_val:.1%}", "(穩健倉位建議)"), unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 30px'></div>", unsafe_allow_html=True)

    # --- 表格 ---
    if not res_df.empty:
        st.markdown("<h3>🎲 凱利公式詳細分析 (Kelly Analysis)</h3>", unsafe_allow_html=True)
        
        # 修正後的 info (使用 Markdown 顏色語法)
        st.info("""
        **指標說明：**
        * **賠率 (盈虧比)**：平均獲利 / 平均虧損。
        * **凱利值 (Kelly)**：
            * :green[**綠色**]：期望值為正，可進場。
            * :red[**紅色**]：期望值為負，應避開。
        * **半凱利 (Half-Kelly)**：全凱利 x 0.5，波動較小，適合實戰資金配置。
        """)

        metrics_map = {
            "發生次數":      {"fmt": lambda x: f"{int(x):,}", "high_is_good": True},
            "勝率":          {"fmt": lambda x: f"{x:.2%}",   "high_is_good": True},
            "賠率 (盈虧比)":  {"fmt": lambda x: f"{x:.2f}",   "high_is_good": True},
            "平均獲利":      {"fmt": lambda x: f"<span style='color:#00CC96'>+{x:.2%}</span>", "high_is_good": True},
            "平均虧損":      {"fmt": lambda x: f"<span style='color:#EF553B'>-{x:.2%}</span>", "high_is_good": False},
            "凱利值 (理論全倉)": {"fmt": lambda x: f"{x:.2%}",   "high_is_good": True},
            "半凱利 (建議穩健)": {"fmt": lambda x: f"{x:.2%}",   "high_is_good": True}, # 新欄位
        }

        html = '<table class="comparison-table"><thead><tr><th style="text-align:left; padding-left:16px;">指標</th>'
        
        for name in res_df['回測設定']:
            if "回檔" in name:
                html += f"<th style='color:#E65100; background-color:rgba(255,167,38,0.1)'>{name}</th>"
            else:
                html += f"<th style='color:#1B5E20; background-color:rgba(102,187,106,0.1)'>{name}</th>"
        html += "</tr></thead><tbody>"

        for metric, config in metrics_map.items():
            html += f"<tr><td class='metric-name' style='padding-left:16px;'>{metric}</td>"
            
            vals = res_df[metric].values
            
            if metric == "平均虧損": 
                 best_val = min(vals)
            else:
                 best_val = max(vals)
            
            for i, val in enumerate(vals):
                display_text = config["fmt"](val)
                count = res_df['發生次數'].iloc[i]
                
                # 特殊邏輯
                if "凱利" in metric:
                    if val > 0:
                        # 讓半凱利顯示得更醒目一點
                        weight = "900" if "半凱利" in metric else "bold" 
                        display_text = f"<span style='color:#00C853; font-weight:{weight}'>{display_text}</span>"
                    else:
                        display_text = f"<span style='color:#D32F2F; font-weight:bold'>避開</span>"
                
                if count < 10 and "凱利" in metric:
                     display_text += " <span style='font-size:0.8em; color:gray'>(少)</span>"

                is_winner = (val == best_val) and (metric != "發生次數") and (metric != "平均獲利") and (metric != "平均虧損")
                if "凱利" in metric and val <= 0: is_winner = False

                if is_winner:
                    display_text += " <span class='trophy-icon'>🏆</span>"
                    html += f"<td style='font-weight:bold; background-color:rgba(0,200,83,0.05);'>{display_text}</td>"
                else:
                    html += f"<td>{display_text}</td>"
            html += "</tr>"
            
        html += "</tbody></table>"
        st.write(html, unsafe_allow_html=True)
