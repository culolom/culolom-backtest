###############################################################
# pages/2_Momentum_Backtest.py — 雙動能 + 凱利公式 + 現況診斷
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

# ------------------------------------------------------
# 1. 基本設定
# ------------------------------------------------------
font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="雙動能凱利決策", page_icon="⚖️", layout="wide")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except ImportError: pass

with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")

# ------------------------------------------------------
# 主標題
# ------------------------------------------------------
st.markdown("<h1 style='margin-bottom:0.5em;'>⚖️ 雙動能凱利決策 (Kelly Criterion)</h1>", unsafe_allow_html=True)
st.markdown("""
    <b>策略邏輯 (Markov Chain + Kelly)：</b><br>
    1. <b>狀態定義</b>：鎖定 <b>年線多頭 (12月漲)</b>，並區分 <b>短期順勢 (M月漲)</b> 與 <b>短期回檔 (M月跌)</b>。<br>
    2. <b>資金管理</b>：利用 <b>凱利公式</b> 計算最佳下注比例。<br>
    3. <b>現況診斷</b>：系統自動判斷 <b>目前最新狀態</b>，並給出歷史勝率與建議倉位。
""", unsafe_allow_html=True)

# ------------------------------------------------------
# 2. 資料讀取
# ------------------------------------------------------
DATA_DIR = Path("data")

def get_all_csv_files():
    if not DATA_DIR.exists(): os.makedirs(DATA_DIR); return []
    return sorted([f.stem for f in DATA_DIR.glob("*.csv")])

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    if "Adj Close" in df.columns: df["Price"] = df["Adj Close"]
    elif "Close" in df.columns: df["Price"] = df["Close"]
    return df[["Price"]]

# ------------------------------------------------------
# 3. UI 輸入區
# ------------------------------------------------------
csv_files = get_all_csv_files()
if not csv_files: st.error("⚠️ Data 資料夾內沒有 CSV 檔案。"); st.stop()

col1, col2 = st.columns(2)
with col1:
    target_symbol = st.selectbox("選擇回測標的", csv_files, index=0)
with col2:
    st.info("🔒 **主要趨勢 (N)**：固定鎖定為 **12 個月** (年線多頭確認)")
    fixed_n = 12
    default_short = [1, 3] 
    selected_m = st.multiselect("設定短期濾網月數 (M)", [1, 2, 3, 4, 5, 6, 9], default=default_short)

# ------------------------------------------------------
# 4. CSS
# ------------------------------------------------------
st.markdown("""
    <style>
        .kpi-card {
            background-color: var(--secondary-background-color);
            border-radius: 16px; padding: 24px 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.04); border: 1px solid rgba(128,128,128,0.1);
            display: flex; flex-direction: column; justify-content: space-between; height: 100%;
        }
        .comparison-table { width: 100%; border-collapse: separate; border-spacing: 0; border-radius: 12px; border: 1px solid var(--secondary-background-color); margin-bottom: 1rem; font-size: 0.95rem; }
        .comparison-table th { background-color: var(--secondary-background-color); padding: 14px; text-align: center; font-weight: 600; border-bottom: 1px solid rgba(128,128,128,0.1); }
        .comparison-table td { text-align: center; padding: 12px; border-bottom: 1px solid rgba(128,128,128,0.1); }
        .comparison-table td.metric-name { text-align: left; font-weight: 500; background-color: rgba(128,128,128,0.02); width: 20%; }
        .trophy-icon { margin-left: 6px; font-size: 1.1em; text-shadow: 0 0 5px rgba(255,215,0,0.4); }
        
        /* 現況診斷卡片樣式 */
        .status-card {
            padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid rgba(128,128,128,0.2);
        }
        .status-bull { background-color: rgba(0, 200, 83, 0.1); border-left: 5px solid #00C853; }
        .status-bear { background-color: rgba(211, 47, 47, 0.1); border-left: 5px solid #D32F2F; }
        .status-neutral { background-color: rgba(255, 167, 38, 0.1); border-left: 5px solid #FFA726; }
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------------------
# 5. 主程式邏輯
# ------------------------------------------------------
if st.button("開始回測 & 診斷現況 🚀") and target_symbol:
    
    with st.spinner(f"正在計算凱利公式與現況分析: {target_symbol} ..."):
        df_daily = load_csv(target_symbol)
        if df_daily.empty: st.error("讀取失敗"); st.stop()

        # 時間區間
        start_date = df_daily.index.min().strftime('%Y-%m-%d')
        end_date = df_daily.index.max().strftime('%Y-%m-%d')
        total_years = (df_daily.index.max() - df_daily.index.min()).days / 365.25

        # 轉月線
        try: df_monthly = df_daily['Price'].resample('ME').last().to_frame()
        except: df_monthly = df_daily['Price'].resample('M').last().to_frame()
            
        df_monthly['Next_Month_Return'] = df_monthly['Price'].pct_change().shift(-1)
        
        results = []
        
        # 主要趨勢訊號
        momentum_long = df_monthly['Price'].pct_change(periods=fixed_n)
        signal_long = momentum_long > 0
        
        for m in sorted(selected_m):
            momentum_short = df_monthly['Price'].pct_change(periods=m)
            
            # 定義兩種狀態
            signal_trend = signal_long & (momentum_short > 0)
            signal_pullback = signal_long & (momentum_short < 0)
            
            # 統計函式
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
                    
                    payoff_ratio = (avg_win_pct / avg_loss_pct) if avg_loss_pct > 0 else 0
                    
                    # Kelly
                    kelly_pct = (win_rate - ((1 - win_rate) / payoff_ratio)) if payoff_ratio > 0 else 0
                    if win_count == 0: kelly_pct = -1.0
                    if loss_count == 0: kelly_pct = 1.0
                    
                    half_kelly_pct = kelly_pct * 0.5
                    max_ret = target_returns.max()
                    min_ret = target_returns.min()
                else:
                    win_rate, avg_ret, max_ret, min_ret, payoff_ratio, kelly_pct, half_kelly_pct = 0,0,0,0,0,0,0
                    avg_win_pct, avg_loss_pct = 0, 0
                
                return {
                    '回測設定': label, '排序': sort_idx, '短期M': m,
                    '類型': '順勢' if '續漲' in label else '拉回',
                    '發生次數': count, '勝率': win_rate, '賠率 (盈虧比)': payoff_ratio,
                    '凱利值 (理論全倉)': kelly_pct, '半凱利 (建議穩健)': half_kelly_pct,
                    '平均獲利': avg_win_pct, '平均虧損': avg_loss_pct, '平均報酬': avg_ret
                }

            results.append(calc_stats_kelly(signal_trend, f"年線多 + {m}月續漲 (順勢)", m * 10 + 1))
            results.append(calc_stats_kelly(signal_pullback, f"年線多 + {m}月回檔 (低接)", m * 10 + 2))
            
        res_df = pd.DataFrame(results).sort_values(by='排序')
        
        # Base Rate
        base_returns = df_monthly['Next_Month_Return'].dropna()
        base_win_rate = (base_returns > 0).sum() / len(base_returns) if not base_returns.empty else 0

    # ==============================================================================
    # ★★★ 新增區塊：目前市場狀態診斷 (Current Status) ★★★
    # ==============================================================================
    
    st.markdown("## 🧭 目前市場狀態診斷 (Current Status)")
    
    # 取得最新一筆資料
    last_date = df_monthly.index[-1]
    current_price = df_monthly['Price'].iloc[-1]
    
    # 計算目前的 12 個月趨勢 (最新一筆)
    # 注意：這裡要確定最後一筆是否為月底，如果不是月底，pct_change 結果可能會有偏差
    # 但為了簡化，直接取 df_monthly 的最後一筆與 12 個月前的比較
    if len(df_monthly) > fixed_n:
        curr_long_mom = df_monthly['Price'].pct_change(periods=fixed_n).iloc[-1]
    else:
        curr_long_mom = 0
        
    st.info(f"📅 **數據更新日期**：{last_date.strftime('%Y-%m-%d')} | **最新收盤價**：{current_price:,.2f}")

    # 1. 判斷長線 (年線)
    if curr_long_mom > 0:
        st.markdown(
            f"""<div class='status-card status-bull'>
                <h3 style='margin:0; color:#1B5E20'>✅ 主要趨勢：多頭 (Yearly Bull)</h3>
                <p style='margin:5px 0 0 0'>過去 12 個月漲幅：<b>+{curr_long_mom:.2%}</b>。符合進場大前提，請參考下方短期策略建議。</p>
            </div>""", unsafe_allow_html=True
        )
        
        st.markdown("### 🔍 根據歷史數據，您目前的選擇與預期回報：")
        
        # 2. 針對使用者選擇的 M，判斷目前是「順勢」還是「拉回」
        # 使用 st.columns 排列卡片
        status_cols = st.columns(len(selected_m))
        
        for idx, m in enumerate(sorted(selected_m)):
            with status_cols[idx]:
                if len(df_monthly) > m:
                    curr_short_mom = df_monthly['Price'].pct_change(periods=m).iloc[-1]
                    
                    # 決定狀態類型
                    if curr_short_mom > 0:
                        curr_type = "順勢"
                        curr_label = f"年線多 + {m}月續漲 (順勢)"
                        icon = "🚀"
                        css_class = "status-bull" # 綠色
                        mom_color = "green"
                    else:
                        curr_type = "拉回"
                        curr_label = f"年線多 + {m}月回檔 (低接)"
                        icon = "🛡️"
                        css_class = "status-neutral" # 橘色/黃色
                        mom_color = "orange"
                    
                    # 從 res_df 撈出對應的歷史數據
                    match = res_df[res_df['回測設定'] == curr_label]
                    
                    if not match.empty:
                        data = match.iloc[0]
                        # 顯示小卡片
                        st.markdown(f"""
                        <div style='border:1px solid #ddd; border-radius:8px; padding:15px; background-color:var(--secondary-background-color)'>
                            <div style='font-size:0.9em; opacity:0.8'>短期濾網 ({m}個月)</div>
                            <div style='font-size:1.3em; font-weight:bold; margin:5px 0'>{icon} {curr_type}</div>
                            <div style='color:{mom_color}; font-weight:bold; font-size:0.9em; margin-bottom:10px'>
                                近{m}月漲幅: {curr_short_mom:+.2%}
                            </div>
                            <hr style='margin:5px 0'>
                            <div style='font-size:0.85em'>歷史預測 (下個月)：</div>
                            <div style='display:flex; justify-content:space-between; margin-top:5px'>
                                <span>勝率:</span> <b>{data['勝率']:.1%}</b>
                            </div>
                            <div style='display:flex; justify-content:space-between'>
                                <span>盈虧比:</span> <b>{data['賠率 (盈虧比)']:.2f}</b>
                            </div>
                            <div style='margin-top:8px; padding-top:8px; border-top:1px dashed #ccc'>
                                <span style='font-size:0.9em'>建議倉位 (半凱利):</span><br>
                                <span style='font-size:1.4em; font-weight:900; color:#2962FF'>{data['半凱利 (建議穩健)']:.1%}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.warning(f"無 {m} 個月歷史數據")
                else:
                    st.warning("資料不足")

    else:
        # 長線空頭
        st.markdown(
            f"""<div class='status-card status-bear'>
                <h3 style='margin:0; color:#B71C1C'>🛑 主要趨勢：空頭 (Yearly Bear)</h3>
                <p style='margin:5px 0 0 0'>過去 12 個月跌幅：<b>{curr_long_mom:.2%}</b>。<br>
                <b>系統建議：</b>目前失去長期上漲動能，歷史期望值通常較差。建議 <b>空手</b>、<b>減碼</b> 或 <b>轉入防禦性資產</b>。
                </p>
            </div>""", unsafe_allow_html=True
        )

    st.divider()

    # -----------------------------------------------------
    # 6. 詳細回測結果 (KPI + 表格) - 保持不變
    # -----------------------------------------------------
    best_strategy = res_df.loc[res_df['半凱利 (建議穩健)'].idxmax()] if not res_df.empty else None
    
    col_kpi = st.columns(4)
    def simple_card(label, value, sub_value=""):
        return f"""<div class="kpi-card"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div><div style="font-size:0.8em;opacity:0.7">{sub_value}</div></div>"""

    with col_kpi[0]: st.markdown(simple_card("總交易月數", f"{len(df_monthly):,} 月"), unsafe_allow_html=True)
    with col_kpi[1]: st.markdown(simple_card("基準月勝率", f"{base_win_rate:.1%}"), unsafe_allow_html=True)
    with col_kpi[2]:
        if best_strategy is not None: st.markdown(simple_card("🔥 最佳策略", f"{best_strategy['回測設定']}"), unsafe_allow_html=True)
    with col_kpi[3]:
        if best_strategy is not None: 
            hk = best_strategy['半凱利 (建議穩健)']
            st.markdown(simple_card("最佳半凱利", f"{hk:.1%}", "(穩健倉位建議)"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if not res_df.empty:
        st.markdown("<h3>🎲 策略回測詳細數據表</h3>", unsafe_allow_html=True)
        st.info("""
        **指標說明：**
        * **凱利值**：:green[**綠色**] 為正期望值可進場，:red[**紅色**] 為負期望值應避開。
        * **半凱利**：實戰建議採用半凱利，以降低波動風險。
        """)

        metrics_map = {
            "發生次數":      {"fmt": lambda x: f"{int(x):,}", "high_is_good": True},
            "勝率":          {"fmt": lambda x: f"{x:.2%}",   "high_is_good": True},
            "賠率 (盈虧比)":  {"fmt": lambda x: f"{x:.2f}",   "high_is_good": True},
            "平均獲利":      {"fmt": lambda x: f"<span style='color:#00CC96'>+{x:.2%}</span>", "high_is_good": True},
            "平均虧損":      {"fmt": lambda x: f"<span style='color:#EF553B'>-{x:.2%}</span>", "high_is_good": False},
            "半凱利 (建議穩健)": {"fmt": lambda x: f"{x:.2%}",   "high_is_good": True},
        }

        html = '<table class="comparison-table"><thead><tr><th style="text-align:left; padding-left:16px;">指標</th>'
        
        for name in res_df['回測設定']:
            if "回檔" in name: html += f"<th style='color:#E65100; background-color:rgba(255,167,38,0.1)'>{name}</th>"
            else: html += f"<th style='color:#1B5E20; background-color:rgba(102,187,106,0.1)'>{name}</th>"
        html += "</tr></thead><tbody>"

        for metric, config in metrics_map.items():
            html += f"<tr><td class='metric-name' style='padding-left:16px;'>{metric}</td>"
            vals = res_df[metric].values
            best_val = min(vals) if metric == "平均虧損" else max(vals)
            
            for i, val in enumerate(vals):
                display_text = config["fmt"](val)
                if "凱利" in metric:
                    if val > 0: display_text = f"<span style='color:#00C853; font-weight:900'>{display_text}</span>"
                    else: display_text = f"<span style='color:#D32F2F; font-weight:bold'>避開</span>"
                
                is_winner = (val == best_val) and (metric != "發生次數") and (metric != "平均獲利") and (metric != "平均虧損")
                if "凱利" in metric and val <= 0: is_winner = False

                if is_winner:
                    display_text += " <span class='trophy-icon'>🏆</span>"
                    html += f"<td style='font-weight:bold; background-color:rgba(0,200,83,0.05);'>{display_text}</td>"
                else: html += f"<td>{display_text}</td>"
            html += "</tr>"
        html += "</tbody></table>"
        st.write(html, unsafe_allow_html=True)
