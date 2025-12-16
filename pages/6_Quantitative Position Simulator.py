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
st.set_page_config(page_title="量化槓桿模擬器", page_icon="🎚️", layout="wide")

# 字體設定
font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

# 權限驗證
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except ImportError: pass

# ------------------------------------------------------
# 2. CSS 樣式
# ------------------------------------------------------
st.markdown("""
    <style>
        .block-container { padding-top: 2rem; }
        .kpi-card {
            background-color: var(--secondary-background-color);
            border-radius: 16px; padding: 24px 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.04); border: 1px solid rgba(128,128,128,0.1);
            display: flex; flex-direction: column; justify-content: space-between; height: 100%;
        }
        .comparison-table { width: 100%; border-collapse: separate; border-spacing: 0; border-radius: 12px; border: 1px solid var(--secondary-background-color); margin-bottom: 1rem; font-size: 0.95rem; }
        .comparison-table th { background-color: var(--secondary-background-color); padding: 14px; text-align: center; font-weight: 600; border-bottom: 1px solid rgba(128,128,128,0.1); }
        .comparison-table td { text-align: center; padding: 12px; border-bottom: 1px solid rgba(128,128,128,0.1); }
        .comparison-table td.metric-name { text-align: left; font-weight: 500; background-color: rgba(128,128,128,0.02); width: 25%; }
        .trophy-icon { margin-left: 6px; font-size: 1.1em; text-shadow: 0 0 5px rgba(255,215,0,0.4); }
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------------------
# 3. 資料讀取函式
# ------------------------------------------------------
DATA_DIR = Path("data")

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    if "Adj Close" in df.columns: df["Price"] = df["Adj Close"]
    elif "Close" in df.columns: df["Price"] = df["Close"]
    return df[["Price"]]

# ------------------------------------------------------
# 4. Sidebar & 頂部控制面板
# ------------------------------------------------------
with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")

st.markdown("<h1 style='margin-bottom:0.1em;'>🎚️ 量化槓桿模擬器 (Continuous Kelly)</h1>", unsafe_allow_html=True)
st.caption("基於 **歷史波動率** 與 **BIL 無風險利率** 計算最佳槓桿倍數")

# ★★★ 控制面板 ★★★
with st.container(border=True):
    st.markdown("#### ⚙️ 模擬參數設定")
    
    c1, c2, c3 = st.columns([1, 2, 1])
    
    with c1:
        watch_list = ["QQQ", "SPY", "0050.TW", "VT", "VTI", "GLD"]
        target_symbol = st.selectbox("選擇標的 (Symbol)", watch_list, index=0)
    
    with c2:
        default_short = [1, 3]
        selected_m = st.multiselect("短期濾網 (M)", [1, 2, 3, 4, 5, 6, 9], default=default_short)
        
    with c3:
        # ★★★ 自動讀取 BIL ★★★
        df_bil = load_csv("BIL")
        rf_rate = 0.04 # 預設值
        
        if not df_bil.empty:
            # 轉月線並計算近一年報酬
            try: df_bil_m = df_bil['Price'].resample('ME').last().to_frame()
            except: df_bil_m = df_bil['Price'].resample('M').last().to_frame()
            
            # 取得最新一筆的「年變動率」
            if len(df_bil_m) > 12:
                rf_rate = df_bil_m['Price'].pct_change(periods=12).iloc[-1]
                st.success(f"📊 **無風險利率 (BIL)**\n\n**{rf_rate:.2%}** (自動偵測)")
            else:
                st.warning("⚠️ BIL 資料不足一年，使用預設 4%")
        else:
            st.error("❌ 未找到 BIL.csv，使用預設 4%")
            
        fixed_n = 12

    start_btn = st.button("計算最佳槓桿倍數 🚀", type="primary", use_container_width=True)

# ------------------------------------------------------
# 5. 主程式
# ------------------------------------------------------
if start_btn and target_symbol:
    
    st.divider() 

    with st.spinner(f"正在分析 {target_symbol} 的波動率，並對照 BIL 利率 ({rf_rate:.2%})..."):
        # 1. 讀取標的
        df_daily = load_csv(target_symbol)
        if df_daily.empty: st.error(f"找不到 {target_symbol}.csv"); st.stop()

        # 2. 轉月線
        try: df_monthly = df_daily['Price'].resample('ME').last().to_frame()
        except: df_monthly = df_daily['Price'].resample('M').last().to_frame()
        
        momentum_long = df_monthly['Price'].pct_change(periods=fixed_n)
        signal_long = momentum_long > 0
        
        tab_lev, tab_horizon = st.tabs(["🎚️ 最佳槓桿決策", "🔭 長線機率展望"])

        # ==============================================================================
        # TAB 1: 最佳槓桿決策 (股市版凱利)
        # ==============================================================================
        with tab_lev:
            df_m1 = df_monthly.copy()
            df_m1['Next_Month_Return'] = df_m1['Price'].pct_change().shift(-1)
            
            results_kelly = []
            
            for m in sorted(selected_m):
                momentum_short = df_m1['Price'].pct_change(periods=m)
                signal_trend = signal_long & (momentum_short > 0)
                signal_pullback = signal_long & (momentum_short < 0)
                
                def calc_leverage_kelly(signal_series, label, sort_idx):
                    target_returns = df_m1.loc[signal_series, 'Next_Month_Return'].dropna()
                    count = len(target_returns)
                    
                    if count > 5:
                        # 1. 年化報酬 (Arithmetic Mean)
                        avg_monthly_ret = target_returns.mean()
                        ann_ret = avg_monthly_ret * 12 
                        
                        # 2. 年化波動率 (Std Dev)
                        std_monthly = target_returns.std()
                        ann_vol = std_monthly * np.sqrt(12)
                        
                        # 3. 連續凱利公式: f = (u - r) / sigma^2
                        # 注意：這裡使用「目前的 BIL 利率」作為 r，來評估「現在」該開多少槓桿
                        variance = ann_vol ** 2
                        
                        if variance > 0:
                            # 核心公式
                            optimal_leverage = (ann_ret - rf_rate) / variance
                        else:
                            optimal_leverage = 0
                            
                        # 安全邊際：半凱利
                        suggested_leverage = optimal_leverage * 0.5
                        win_rate = (target_returns > 0).sum() / count
                    else:
                        ann_ret, ann_vol, optimal_leverage, suggested_leverage, win_rate = 0,0,0,0,0
                    
                    return {
                        '回測設定': label, '排序': sort_idx, '短期M': m,
                        '類型': '順勢' if '續漲' in label else '拉回',
                        '樣本數': count,
                        '年化報酬': ann_ret, '年化波動': ann_vol,
                        '理論最佳槓桿': optimal_leverage,
                        '建議槓桿 (半凱利)': suggested_leverage
                    }

                results_kelly.append(calc_leverage_kelly(signal_trend, f"年線多 + {m}月續漲 (順勢)", m * 10 + 1))
                results_kelly.append(calc_leverage_kelly(signal_pullback, f"年線多 + {m}月回檔 (低接)", m * 10 + 2))
            
            res_df = pd.DataFrame(results_kelly).sort_values(by='排序')
            
            # --- UI: 現況建議 ---
            st.markdown("### 🧭 目前市場狀態與槓桿建議")
            curr_long_mom = momentum_long.iloc[-1] if len(df_monthly) > fixed_n else 0
            
            if curr_long_mom > 0:
                st.success(f"✅ 主要趨勢：多頭 | 過去12月漲幅: +{curr_long_mom:.2%} | **資金成本(Rf): {rf_rate:.2%}**")
                
                status_cols = st.columns(len(selected_m))
                for idx, m in enumerate(sorted(selected_m)):
                    with status_cols[idx]:
                        if len(df_monthly) > m:
                            curr_short_mom = df_monthly['Price'].pct_change(periods=m).iloc[-1]
                            
                            if curr_short_mom > 0:
                                curr_type, icon = "順勢", "🚀"
                                curr_label = f"年線多 + {m}月續漲 (順勢)"
                            else:
                                curr_type, icon = "拉回", "🛡️"
                                curr_label = f"年線多 + {m}月回檔 (低接)"
                            
                            match = res_df[res_df['回測設定'] == curr_label]
                            
                            if not match.empty:
                                data = match.iloc[0]
                                lev = data['建議槓桿 (半凱利)']
                                
                                # 顏色邏輯
                                lev_color = "#2962FF"
                                if lev <= 0: lev_str = "建議空手 (0x)"; lev_color="#D32F2F"
                                elif lev < 1: lev_str = f"降低曝險 ({lev:.2f}x)"; lev_color="#FF9800"
                                else: lev_str = f"{lev:.2f} 倍"; 
                                
                                st.markdown(f"""
                                <div style='border:1px solid #ddd; border-radius:8px; padding:15px; background-color:var(--secondary-background-color); height:100%'>
                                    <div style='font-size:0.9em; opacity:0.8'>短期濾網 ({m}個月)</div>
                                    <div style='font-size:1.3em; font-weight:bold; margin:5px 0'>{icon} {curr_type}</div>
                                    <hr style='margin:5px 0'>
                                    <div style='font-size:0.85em; color:#666'>年化報酬: <b>{data['年化報酬']:.1%}</b></div>
                                    <div style='font-size:0.85em; color:#666'>年化波動: <b>{data['年化波動']:.1%}</b></div>
                                    <div style='margin-top:10px; padding-top:8px; border-top:1px dashed #ccc'>
                                        <span style='font-size:0.85em'>建議槓桿 (半凱利):</span><br>
                                        <span style='font-size:1.6em; font-weight:900; color:{lev_color}'>{lev_str}</span>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
            else:
                st.error("🛑 主要趨勢：空頭 (Yearly Bear)。建議槓桿：0x (空手)。")

            st.markdown("<br>", unsafe_allow_html=True)

            # --- 表格 ---
            if not res_df.empty:
                st.markdown("<h3>📊 歷史數據詳細分析表</h3>", unsafe_allow_html=True)
                metrics_map = {
                    "年化報酬":      {"fmt": lambda x: f"{x:.2%}"},
                    "年化波動":      {"fmt": lambda x: f"{x:.2%}"},
                    "理論最佳槓桿":   {"fmt": lambda x: f"{x:.2f} x"},
                    "建議槓桿 (半凱利)": {"fmt": lambda x: f"{x:.2f} x"},
                }

                html = '<table class="comparison-table"><thead><tr><th style="text-align:left; padding-left:16px;">指標</th>'
                for name in res_df['回測設定']:
                    style = "color:#E65100; background-color:rgba(255,167,38,0.1)" if "回檔" in name else "color:#1B5E20; background-color:rgba(102,187,106,0.1)"
                    html += f"<th style='{style}'>{name}</th>"
                html += "</tr></thead><tbody>"

                for metric, config in metrics_map.items():
                    html += f"<tr><td class='metric-name' style='padding-left:16px;'>{metric}</td>"
                    vals = res_df[metric].values
                    for val in vals:
                        display_text = config["fmt"](val)
                        if "槓桿" in metric:
                            if val > 1.5: display_text = f"<span style='color:#2962FF; font-weight:900'>{display_text}</span>"
                            elif val <= 0: display_text = f"<span style='color:#D32F2F; font-weight:bold'>0x</span>"
                        html += f"<td>{display_text}</td>"
                    html += "</tr>"
                html += "</tbody></table>"
                
                st.info(f"""
                **💡 槓桿計算說明**
                * **資金成本 (Risk-Free Rate)**：目前採用 **BIL** 過去12個月報酬率 **{rf_rate:.2%}**。
                * **意義**：當無風險利率上升 (如升息循環)，資金成本變貴，系統算出的最佳槓桿倍數會自動下降，提示您降低風險。
                """)

        # ==============================================================================
        # TAB 2: 長線機率展望 (維持原樣，補回完整代碼以防空白)
        # ==============================================================================
        with tab_horizon:
            df_m2 = df_monthly.copy()
            horizons = [1, 3, 6, 12]
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
                            avg_ret = rets.mean()
                            row_data[f'{h}個月'] = avg_ret
                            row_data[f'報酬_{h}M'] = avg_ret
                            row_data[f'勝率_{h}M'] = (rets > 0).sum() / len(rets)
                            if h == 1: valid_count = len(rets)
                        else:
                            row_data[f'{h}個月'] = np.nan
                            row_data[f'報酬_{h}M'] = np.nan
                            row_data[f'勝率_{h}M'] = np.nan
                    row_data['發生次數'] = valid_count
                    if valid_count > 0: results_horizon.append(row_data)

            res_df_hz = pd.DataFrame(results_horizon)

            if not res_df_hz.empty:
                st.markdown("### 💠 全局視野：熱力圖 (Heatmap)")
                heatmap_ret = res_df_hz.set_index('策略')[['1個月', '3個月', '6個月', '12個月']]
                fig_ret = px.imshow(
                    heatmap_ret, labels=dict(x="持有期間", y="策略設定", color="平均報酬"),
                    x=['1個月', '3個月', '6個月', '12個月'], y=heatmap_ret.index,
                    text_auto='.2%', color_continuous_scale='Blues', aspect="auto"
                )
                fig_ret.update_layout(height=150 + (len(res_df_hz) * 35), xaxis_side="top")
                st.plotly_chart(fig_ret, use_container_width=True)

                st.divider()
                st.markdown("### 📊 績效排行 (Rankings)")
                t1, t2, t3, t4 = st.tabs(["1個月展望", "3個月展望", "6個月展望", "12個月展望"])
                
                def plot_horizon_bar(horizon_month, container):
                    col_name = f'報酬_{horizon_month}M'
                    sorted_df = res_df_hz.sort_values(by=col_name, ascending=False)
                    fig = px.bar(
                        sorted_df, x='策略', y=col_name, color='類型', text_auto='.1%',
                        title=f"持有 {horizon_month} 個月後的平均報酬排序",
                        color_discrete_map={'順勢': '#2962FF', '拉回': '#FF9100'}
                    )
                    fig.update_layout(yaxis_tickformat='.1%', height=450)
                    container.plotly_chart(fig, use_container_width=True)

                with t1: plot_horizon_bar(1, t1)
                with t2: plot_horizon_bar(3, t2)
                with t3: plot_horizon_bar(6, t3)
                with t4: plot_horizon_bar(12, t4)
