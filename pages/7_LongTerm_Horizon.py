import os
import sys
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path

# ------------------------------------------------------
# 1. 基本設定 & Page Config
# ------------------------------------------------------
st.set_page_config(page_title="雙動能全方位戰情室", page_icon="⚔️", layout="wide")

# 字體設定
font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

# 權限驗證 (若無 auth.py 則跳過)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except ImportError: pass

# ------------------------------------------------------
# 2. CSS 樣式優化
# ------------------------------------------------------
st.markdown("""
    <style>
        /* 調整上方留白，讓控制面板更緊湊 */
        .block-container { padding-top: 2rem; }
        
        /* KPI 卡片 */
        .kpi-card {
            background-color: var(--secondary-background-color);
            border-radius: 16px; padding: 24px 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.04); border: 1px solid rgba(128,128,128,0.1);
            display: flex; flex-direction: column; justify-content: space-between; height: 100%;
        }
        .kpi-label { font-size: 0.9rem; opacity: 0.8; font-weight: 500; }
        .kpi-value { font-size: 1.8rem; font-weight: 700; margin: 4px 0; color: var(--text-color); }
        .kpi-sub { font-size: 0.8em; opacity: 0.7; }
        
        /* 比較表格樣式 */
        .comparison-table { width: 100%; border-collapse: separate; border-spacing: 0; border-radius: 12px; border: 1px solid var(--secondary-background-color); margin-bottom: 1rem; font-size: 0.95rem; }
        .comparison-table th { background-color: var(--secondary-background-color); padding: 14px; text-align: center; font-weight: 600; border-bottom: 1px solid rgba(128,128,128,0.1); }
        .comparison-table td { text-align: center; padding: 12px; border-bottom: 1px solid rgba(128,128,128,0.1); }
        .comparison-table td.metric-name { text-align: left; font-weight: 500; background-color: rgba(128,128,128,0.02); width: 20%; }
        .trophy-icon { margin-left: 6px; font-size: 1.1em; text-shadow: 0 0 5px rgba(255,215,0,0.4); }
        
        /* 現況診斷卡片樣式 */
        .status-card { padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid rgba(128,128,128,0.2); }
        .status-bull { background-color: rgba(0, 200, 83, 0.1); border-left: 5px solid #00C853; }
        .status-bear { background-color: rgba(211, 47, 47, 0.1); border-left: 5px solid #D32F2F; }
        .status-neutral { background-color: rgba(255, 167, 38, 0.1); border-left: 5px solid #FFA726; }
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------------------
# 3. 資料讀取函式
# ------------------------------------------------------
DATA_DIR = Path("data")

def get_all_csv_files():
    if not DATA_DIR.exists(): return []
    return sorted([f.stem for f in DATA_DIR.glob("*.csv")])

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    # 兼容 Adj Close 與 Close
    if "Adj Close" in df.columns: df["Price"] = df["Adj Close"]
    elif "Close" in df.columns: df["Price"] = df["Close"]
    return df[["Price"]]

# ------------------------------------------------------
# 4. Sidebar (僅導航) & 頂部控制面板
# ------------------------------------------------------
with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")

st.markdown("<h1 style='margin-bottom:0.1em;'>⚔️ 雙動能全方位戰情室</h1>", unsafe_allow_html=True)
st.caption("整合 **凱利公式決策 (Kelly)** 與 **長線趨勢展望 (Horizon)** 的綜合分析工具")

# ★★★ 控制面板區塊 ★★★
csv_files = get_all_csv_files()
if not csv_files:
    st.error("⚠️ Data 資料夾內沒有 CSV 檔案。")
    st.stop()

with st.container(border=True):
    st.markdown("#### ⚙️ 參數設定面板")
    
    # 建立三欄佈局
    c1, c2, c3 = st.columns([1, 2, 1])
    
    with c1:
        target_symbol = st.selectbox("選擇回測標的 (Symbol)", csv_files, index=0)
    
    with c2:
        default_short = [1, 3]
        selected_m = st.multiselect("設定短期濾網月數 (M)", [1, 2, 3, 4, 5, 6, 9], default=default_short)
        
    with c3:
        st.info("🔒 **主要趨勢 (N)**\n\n固定鎖定 **12 個月** (年線)")
        fixed_n = 12

    # 按鈕
    start_btn = st.button("開始全方位分析 🚀", type="primary", use_container_width=True)

# ------------------------------------------------------
# 5. 主程式執行邏輯
# ------------------------------------------------------
if start_btn and target_symbol:
    
    st.divider()

    with st.spinner(f"正在運算 {target_symbol} 的數據模型..."):
        df_daily = load_csv(target_symbol)
        if df_daily.empty: st.error("讀取失敗"); st.stop()

        # 轉月線 (共用)
        try: df_monthly = df_daily['Price'].resample('ME').last().to_frame()
        except: df_monthly = df_daily['Price'].resample('M').last().to_frame()
        
        # 基礎訊號：長線趨勢 (N=12)
        momentum_long = df_monthly['Price'].pct_change(periods=fixed_n)
        signal_long = momentum_long > 0
        
        # 建立 Tabs
        tab_decision, tab_horizon = st.tabs(["⚖️ 凱利決策 & 現況診斷", "🔭 長線趨勢展望"])

        # ==============================================================================
        # TAB 1: 凱利決策 & 現況診斷
        # ==============================================================================
        with tab_decision:
            # 準備 Tab 1 資料 (Next Month Return)
            df_m1 = df_monthly.copy()
            df_m1['Next_Month_Return'] = df_m1['Price'].pct_change().shift(-1)
            
            results_kelly = []
            
            # 迴圈計算每個 M 的凱利值
            for m in sorted(selected_m):
                momentum_short = df_m1['Price'].pct_change(periods=m)
                
                # 順勢與拉回定義
                signal_trend = signal_long & (momentum_short > 0)
                signal_pullback = signal_long & (momentum_short < 0)
                
                # 內部函式：計算統計與凱利
                def calc_stats_kelly(signal_series, label, sort_idx):
                    target_returns = df_m1.loc[signal_series, 'Next_Month_Return'].dropna()
                    count = len(target_returns)
                    
                    if count > 0:
                        wins = target_returns[target_returns > 0]
                        losses = target_returns[target_returns <= 0]
                        
                        win_count = wins.count()
                        loss_count = losses.count()
                        win_rate = win_count / count
                        
                        avg_win_pct = wins.mean() if win_count > 0 else 0
                        avg_loss_pct = abs(losses.mean()) if loss_count > 0 else 0
                        
                        payoff_ratio = (avg_win_pct / avg_loss_pct) if avg_loss_pct > 0 else 0
                        
                        # Kelly Formula
                        kelly_pct = (win_rate - ((1 - win_rate) / payoff_ratio)) if payoff_ratio > 0 else 0
                        
                        # 邊界處理
                        if win_count == 0: kelly_pct = -1.0
                        if loss_count == 0: kelly_pct = 1.0
                        
                        half_kelly_pct = kelly_pct * 0.5
                    else:
                        win_rate, payoff_ratio, kelly_pct, half_kelly_pct = 0, 0, 0, 0
                        avg_win_pct, avg_loss_pct = 0, 0
                    
                    return {
                        '回測設定': label, '排序': sort_idx, '短期M': m,
                        '類型': '順勢' if '續漲' in label else '拉回',
                        '發生次數': count, '勝率': win_rate, '賠率 (盈虧比)': payoff_ratio,
                        '凱利值 (理論全倉)': kelly_pct, '半凱利 (建議穩健)': half_kelly_pct,
                        '平均獲利': avg_win_pct, '平均虧損': avg_loss_pct
                    }

                results_kelly.append(calc_stats_kelly(signal_trend, f"年線多 + {m}月續漲 (順勢)", m * 10 + 1))
                results_kelly.append(calc_stats_kelly(signal_pullback, f"年線多 + {m}月回檔 (低接)", m * 10 + 2))
            
            res_df_kelly = pd.DataFrame(results_kelly).sort_values(by='排序')
            
            # --- Tab 1 UI: 現況診斷 ---
            st.markdown("### 🧭 目前市場狀態診斷")
            
            last_date = df_monthly.index[-1]
            current_price = df_monthly['Price'].iloc[-1]
            # 取得最新一期的 N 月動能
            curr_long_mom = momentum_long.iloc[-1] if len(df_monthly) > fixed_n else 0
            
            st.info(f"📅 **數據更新日期**：{last_date.strftime('%Y-%m-%d')} | **最新收盤價**：{current_price:,.2f}")

            # 判斷大趨勢
            if curr_long_mom > 0:
                st.markdown(f"""<div class='status-card status-bull'>
                    <h3 style='margin:0; color:#1B5E20'>✅ 主要趨勢：多頭 (Yearly Bull)</h3>
                    <p style='margin:5px 0 0 0'>過去 12 個月漲幅：<b>+{curr_long_mom:.2%}</b>。符合進場大前提，請參考下方各週期的建議。</p>
                    </div>""", unsafe_allow_html=True)
                
                st.markdown("#### 🔍 各週期策略建議 (Actionable Insights)")
                
                # 動態產生欄位顯示小卡
                status_cols = st.columns(len(selected_m))
                
                for idx, m in enumerate(sorted(selected_m)):
                    with status_cols[idx]:
                        if len(df_monthly) > m:
                            # 取得最新一期的 M 月動能
                            curr_short_mom = df_monthly['Price'].pct_change(periods=m).iloc[-1]
                            
                            if curr_short_mom > 0:
                                curr_type = "順勢"
                                curr_label = f"年線多 + {m}月續漲 (順勢)"
                                icon, mom_color = "🚀", "green"
                            else:
                                curr_type = "拉回"
                                curr_label = f"年線多 + {m}月回檔 (低接)"
                                icon, mom_color = "🛡️", "orange"
                            
                            # 撈取對應的歷史數據
                            match = res_df_kelly[res_df_kelly['回測設定'] == curr_label]
                            
                            if not match.empty:
                                data = match.iloc[0]
                                st.markdown(f"""
                                <div style='border:1px solid #ddd; border-radius:8px; padding:15px; background-color:var(--secondary-background-color); height:100%'>
                                    <div style='font-size:0.9em; opacity:0.8'>短期濾網 ({m}個月)</div>
                                    <div style='font-size:1.3em; font-weight:bold; margin:5px 0'>{icon} {curr_type}</div>
                                    <div style='color:{mom_color}; font-weight:bold; font-size:0.9em; margin-bottom:10px'>近{m}月漲幅: {curr_short_mom:+.2%}</div>
                                    <hr style='margin:5px 0'>
                                    <div style='display:flex; justify-content:space-between; margin-top:5px; font-size:0.9em'><span>勝率:</span> <b>{data['勝率']:.1%}</b></div>
                                    <div style='display:flex; justify-content:space-between; font-size:0.9em'><span>盈虧比:</span> <b>{data['賠率 (盈虧比)']:.2f}</b></div>
                                    <div style='margin-top:10px; padding-top:8px; border-top:1px dashed #ccc'>
                                        <span style='font-size:0.85em'>建議倉位 (半凱利):</span><br>
                                        <span style='font-size:1.5em; font-weight:900; color:#2962FF'>{data['半凱利 (建議穩健)']:.1%}</span>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                            else:
                                st.warning("無歷史數據")
            else:
                # 空頭狀態
                st.markdown(f"""<div class='status-card status-bear'>
                    <h3 style='margin:0; color:#B71C1C'>🛑 主要趨勢：空頭 (Yearly Bear)</h3>
                    <p style='margin:5px 0 0 0'>過去 12 個月跌幅：<b>{curr_long_mom:.2%}</b>。<br>
                    <b>系統建議：</b>目前失去長期上漲動能，歷史期望值通常較差。建議 <b>空手</b>、<b>減碼</b> 或 <b>轉入防禦性資產</b>。
                    </p>
                    </div>""", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # --- Tab 1 UI: 詳細數據表 ---
            if not res_df_kelly.empty:
                st.markdown("<h3>🎲 策略歷史統計數據表</h3>", unsafe_allow_html=True)
                
                metrics_map = {
                    "發生次數":      {"fmt": lambda x: f"{int(x):,}", "high_is_good": True},
                    "勝率":          {"fmt": lambda x: f"{x:.2%}",    "high_is_good": True},
                    "賠率 (盈虧比)":  {"fmt": lambda x: f"{x:.2f}",    "high_is_good": True},
                    "平均獲利":      {"fmt": lambda x: f"<span style='color:#00CC96'>+{x:.2%}</span>", "high_is_good": True},
                    "平均虧損":      {"fmt": lambda x: f"<span style='color:#EF553B'>-{x:.2%}</span>", "high_is_good": False},
                    "半凱利 (建議穩健)": {"fmt": lambda x: f"{x:.2%}",    "high_is_good": True},
                }

                html = '<table class="comparison-table"><thead><tr><th style="text-align:left; padding-left:16px;">指標</th>'
                
                for name in res_df_kelly['回測設定']:
                    style = "color:#E65100; background-color:rgba(255,167,38,0.1)" if "回檔" in name else "color:#1B5E20; background-color:rgba(102,187,106,0.1)"
                    html += f"<th style='{style}'>{name}</th>"
                html += "</tr></thead><tbody>"

                for metric, config in metrics_map.items():
                    html += f"<tr><td class='metric-name' style='padding-left:16px;'>{metric}</td>"
                    vals = res_df_kelly[metric].values
                    
                    # 判斷最佳值
                    if metric == "平均虧損":
                         # 虧損越小(絕對值)越好，但因為是負值顯示，這裡取 min 代表虧最多，max 代表虧最少
                         # 為了簡單，假設數值是正的絕對值邏輯:
                         best_val = min(vals) 
                    else:
                         best_val = max(vals)
                    
                    for val in vals:
                        display_text = config["fmt"](val)
                        
                        # 凱利值顏色
                        if "凱利" in metric:
                            if val > 0: display_text = f"<span style='color:#00C853; font-weight:900'>{display_text}</span>"
                            else: display_text = f"<span style='color:#D32F2F; font-weight:bold'>避開</span>"
                        
                        # 冠軍獎盃邏輯
                        is_winner = (val == best_val) and (metric not in ["發生次數", "平均獲利", "平均虧損"])
                        if "凱利" in metric and val <= 0: is_winner = False
                        
                        if is_winner:
                            html += f"<td style='font-weight:bold; background-color:rgba(0,200,83,0.05);'>{display_text} <span class='trophy-icon'>🏆</span></td>"
                        else:
                            html += f"<td>{display_text}</td>"
                    html += "</tr>"
                html += "</tbody></table>"
                st.write(html, unsafe_allow_html=True)

        # ==============================================================================
        # TAB 2: 長線趨勢展望
        # ==============================================================================
        with tab_horizon:
            # 準備 Tab 2 資料 (Forward N Months)
            df_m2 = df_monthly.copy()
            horizons = [1, 3, 6, 12]
            
            # 建立未來回報欄位
            for h in horizons:
                df_m2[f'Fwd_{h}M'] = df_m2['Price'].shift(-h) / df_m2['Price'] - 1

            results_horizon = []
            
            for m in sorted(selected_m):
                momentum_short = df_m2['Price'].pct_change(periods=m)
                
                scenarios = {
                    f"年線多 + {m}月續漲 (順勢)": signal_long & (momentum_short > 0),
                    f"年線多 + {m}月回檔 (低接)": signal_long & (momentum_short < 0)
                }
                
                for label, signal in scenarios.items():
                    row_data = {'策略': label, '短期M': m, '類型': '順勢' if '續漲' in label else '拉回'}
                    valid_count = 0
                    
                    for h in horizons:
                        rets = df_m2.loc[signal, f'Fwd_{h}M'].dropna()
                        if len(rets) > 0:
                            win_rate = (rets > 0).sum() / len(rets)
                            avg_ret = rets.mean()
                            
                            row_data[f'{h}個月'] = avg_ret     # For Heatmap
                            row_data[f'報酬_{h}M'] = avg_ret  # For Bar Chart
                            row_data[f'勝率_{h}M'] = win_rate # For Table
                            if h == 1: valid_count = len(rets)
                        else:
                            row_data[f'{h}個月'] = np.nan
                            row_data[f'報酬_{h}M'] = np.nan
                            row_data[f'勝率_{h}M'] = np.nan
                            
                    row_data['發生次數'] = valid_count
                    if valid_count > 0:
                        results_horizon.append(row_data)

            res_df_hz = pd.DataFrame(results_horizon)

            if not res_df_hz.empty:
                st.markdown("### 💠 全局視野：熱力圖 (Heatmap)")
                st.caption("觀察訊號出現後，持有不同時間長度 (1~12個月) 的平均回報。:blue[**深藍色**] 代表回報越高。")
                
                # 準備熱力圖資料
                return_cols = ['1個月', '3個月', '6個月', '12個月']
                heatmap_ret = res_df_hz.set_index('策略')[return_cols]
                
                fig_ret = px.imshow(
                    heatmap_ret,
                    labels=dict(x="持有期間", y="策略設定", color="平均報酬"),
                    x=return_cols,
                    y=heatmap_ret.index,
                    text_auto='.2%', 
                    color_continuous_scale='Blues', 
                    aspect="auto"
                )
                fig_ret.update_layout(height=150 + (len(res_df_hz) * 35), xaxis_side="top")
                st.plotly_chart(fig_ret, use_container_width=True)

                st.divider()

                # 直條圖分析
                st.markdown("### 📊 績效排行 (Rankings)")
                t1, t2, t3, t4 = st.tabs(["1個月展望", "3個月展望", "6個月展望", "12個月展望"])
                
                def plot_horizon_bar(horizon_month, container):
                    col_name = f'報酬_{horizon_month}M'
                    # 排序
                    sorted_df = res_df_hz.sort_values(by=col_name, ascending=False)
                    
                    fig = px.bar(
                        sorted_df, 
                        x='策略', y=col_name, 
                        color='類型', 
                        text_auto='.1%',
                        title=f"持有 {horizon_month} 個月後的平均報酬排序",
                        color_discrete_map={'順勢': '#2962FF', '拉回': '#FF9100'}
                    )
                    fig.update_layout(yaxis_tickformat='.1%', height=450)
                    container.plotly_chart(fig, use_container_width=True)

                with t1: plot_horizon_bar(1, t1)
                with t2: plot_horizon_bar(3, t2)
                with t3: plot_horizon_bar(6, t3)
                with t4: plot_horizon_bar(12, t4)
                
                # 原始資料
                st.divider()
                with st.expander("📄 點擊查看詳細數據表格 (原始資料)"):
                    fmt_dict = {'發生次數': '{:.0f}'}
                    for col in res_df_hz.columns:
                        if '個月' in col or '勝率' in col or '報酬' in col:
                            fmt_dict[col] = '{:.2%}'
                    
                    st.dataframe(
                        res_df_hz.style.format(fmt_dict)
                        .background_gradient(subset=[f'勝率_{h}M' for h in horizons], cmap='Blues'),
                        use_container_width=True
                    )
