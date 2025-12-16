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
        
        /* 綜合建議卡片 */
        .action-card {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            border-left: 6px solid #2962FF;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .action-title { font-size: 1.1rem; font-weight: bold; color: #333; margin-bottom: 5px; }
        .action-value { font-size: 2.5rem; font-weight: 900; color: #2962FF; margin: 0; line-height: 1.2; }
        .action-sub { font-size: 0.9rem; color: #555; }
        
        /* 狀態卡片 */
        .status-card { padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid rgba(128,128,128,0.2); }
        .status-bull { background-color: rgba(0, 200, 83, 0.1); border-left: 5px solid #00C853; }
        .status-bear { background-color: rgba(211, 47, 47, 0.1); border-left: 5px solid #D32F2F; }

        /* 表格樣式 */
        .comparison-table { width: 100%; border-collapse: separate; border-spacing: 0; border-radius: 12px; border: 1px solid var(--secondary-background-color); margin-bottom: 1rem; font-size: 0.95rem; }
        .comparison-table th { background-color: var(--secondary-background-color); padding: 14px; text-align: center; font-weight: 600; border-bottom: 1px solid rgba(128,128,128,0.1); }
        .comparison-table td { text-align: center; padding: 12px; border-bottom: 1px solid rgba(128,128,128,0.1); }
        .comparison-table td.metric-name { text-align: left; font-weight: 500; background-color: rgba(128,128,128,0.02); width: 25%; }
        
        div.stButton > button { border-radius: 8px; font-weight: bold; }
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
# 4. Sidebar & 控制面板
# ------------------------------------------------------
with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")

st.markdown("<h1 style='margin-bottom:0.1em;'>🎚️ 量化槓桿模擬器 (Continuous Kelly)</h1>", unsafe_allow_html=True)
st.caption("基於 **歷史波動率** 與 **無風險利率 ($r$)** 計算最佳槓桿倍數")

with st.container(border=True):
    st.markdown("#### ⚙️ 模擬參數設定")
    c1, c2 = st.columns([1, 1.5])
    
    with c1:
        watch_list = ["QQQ", "SPY", "0050.TW", "VT", "VTI", "GLD"]
        target_symbol = st.selectbox("選擇標的 (Symbol)", watch_list, index=0)
        st.markdown("<br>", unsafe_allow_html=True)
        start_btn = st.button("開始分析 🚀", type="primary") 

    with c2:
        # 自動偵測 Risk Free Rate
        rf_symbol = "預設 4%"
        rf_rate = 0.04
        candidates = ["BIL", "SHV", "SGOV"]
        found_rf = False
        
        for sym in candidates:
            df_rf = load_csv(sym)
            if not df_rf.empty:
                try: df_rf_m = df_rf['Price'].resample('ME').last().to_frame()
                except: df_rf_m = df_rf['Price'].resample('M').last().to_frame()
                if len(df_rf_m) > 12:
                    rf_rate = df_rf_m['Price'].pct_change(periods=12).iloc[-1]
                    rf_symbol = sym
                    found_rf = True
                    break
        
        st.info(f"""
        **📊 市場參數偵測**
        * **無風險利率 ($r$)**: `{rf_rate:.2%}` (來源: {rf_symbol})
        * **主要趨勢 (N)**: `12 個月` (年線固定)
        * **短期濾網 (M)**: `1, 3, 6, 9 個月` (固定參數)
        """)
        
        fixed_n = 12
        selected_m = [1, 3, 6, 9]

# ------------------------------------------------------
# 5. 主程式執行邏輯
# ------------------------------------------------------
if start_btn and target_symbol:
    
    st.divider() 

    with st.spinner(f"正在運算多週期綜合決策模型..."):
        # 1. 讀取標的
        df_daily = load_csv(target_symbol)
        if df_daily.empty: st.error(f"找不到 {target_symbol}.csv"); st.stop()

        # 2. 轉月線
        try: df_monthly = df_daily['Price'].resample('ME').last().to_frame()
        except: df_monthly = df_daily['Price'].resample('M').last().to_frame()
        
        # ★★★ 新增：計算並顯示回測時間區間 ★★★
        start_date = df_monthly.index[0]
        end_date = df_monthly.index[-1]
        data_years = (end_date - start_date).days / 365.25
        current_price = df_monthly['Price'].iloc[-1]
        
        # 顯示資料狀態列
        st.info(f"""
        📅 **回測數據區間**：`{start_date.strftime('%Y-%m-%d')}` ~ `{end_date.strftime('%Y-%m-%d')}` (共 {data_years:.1f} 年) 
        💰 **最新收盤價**：`{current_price:,.2f}`
        """)

        # 檢查資料長度警示
        if data_years < 3:
            st.warning("⚠️ **注意：資料長度不足 3 年！** 部分長週期 (如 9個月濾網 + 12個月展望) 可能會因為樣本不足而無法顯示或出現空白。建議更新為更長歷史的 CSV 檔。")
        
        momentum_long = df_monthly['Price'].pct_change(periods=fixed_n)
        signal_long = momentum_long > 0
        
        tab_lev, tab_horizon = st.tabs(["🎚️ 最佳槓桿決策", "🔭 長線機率展望"])

        # ==============================================================================
        # TAB 1: 最佳槓桿決策
        # ==============================================================================
        with tab_lev:
            df_m1 = df_monthly.copy()
            df_m1['Next_Month_Return'] = df_m1['Price'].pct_change().shift(-1)
            
            results_kelly = []
            
            # 1. 先跑迴圈計算所有歷史數據 (建立查表資料庫)
            for m in sorted(selected_m):
                momentum_short = df_m1['Price'].pct_change(periods=m)
                signal_trend = signal_long & (momentum_short > 0)
                signal_pullback = signal_long & (momentum_short < 0)
                
                def calc_leverage_kelly(signal_series, label, sort_idx):
                    target_returns = df_m1.loc[signal_series, 'Next_Month_Return'].dropna()
                    count = len(target_returns)
                    
                    if count > 5:
                        avg_monthly_ret = target_returns.mean()
                        ann_ret = avg_monthly_ret * 12 
                        std_monthly = target_returns.std()
                        ann_vol = std_monthly * np.sqrt(12)
                        variance = ann_vol ** 2
                        
                        if variance > 0:
                            optimal_leverage = (ann_ret - rf_rate) / variance
                        else:
                            optimal_leverage = 0
                            
                        suggested_leverage = optimal_leverage * 0.5
                    else:
                        ann_ret, ann_vol, optimal_leverage, suggested_leverage = 0,0,0,0
                    
                    return {
                        '回測設定': label, '排序': sort_idx,
                        '年化報酬': ann_ret, '年化波動': ann_vol,
                        '理論最佳槓桿': optimal_leverage,
                        '建議槓桿 (半凱利)': suggested_leverage
                    }

                results_kelly.append(calc_leverage_kelly(signal_trend, f"年線多 + {m}月續漲 (順勢)", m * 10 + 1))
                results_kelly.append(calc_leverage_kelly(signal_pullback, f"年線多 + {m}月回檔 (低接)", m * 10 + 2))
            
            res_df = pd.DataFrame(results_kelly).sort_values(by='排序')
            
            # 2. ★★★ 計算「當下」的綜合建議 ★★★
            curr_long_mom = momentum_long.iloc[-1] if len(df_monthly) > fixed_n else 0
            
            current_suggestions = []
            
            if curr_long_mom > 0:
                for m in selected_m:
                    if len(df_monthly) > m:
                        curr_short_mom = df_monthly['Price'].pct_change(periods=m).iloc[-1]
                        if curr_short_mom > 0:
                            target_label = f"年線多 + {m}月續漲 (順勢)"
                        else:
                            target_label = f"年線多 + {m}月回檔 (低接)"
                        
                        match = res_df[res_df['回測設定'] == target_label]
                        if not match.empty:
                            lev = match.iloc[0]['建議槓桿 (半凱利)']
                            current_suggestions.append(lev)
            
            if current_suggestions:
                avg_leverage = sum(current_suggestions) / len(current_suggestions)
            else:
                avg_leverage = 0 
                
            # 3. 顯示綜合決策卡片
            st.markdown("### 🚀 當下綜合操作建議 (Current Action)")
            
            if curr_long_mom > 0:
                col_action, col_details = st.columns([1, 2])
                
                with col_action:
                    st.markdown(f"""
                    <div class='action-card'>
                        <div class='action-title'>🔥 綜合建議槓桿</div>
                        <div class='action-value'>{avg_leverage:.2f} 倍</div>
                        <div class='action-sub'>基於 4 個週期的平均權重</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with col_details:
                    exposure_pct = avg_leverage * 100
                    cash_pct = max(0, 100 - exposure_pct)
                    
                    if avg_leverage < 1:
                        advice = f"建議買入 **{exposure_pct:.0f}%** 的 {target_symbol}，保留 **{cash_pct:.0f}%** 現金 (或買美債)。"
                    elif 1 <= avg_leverage < 2:
                        advice = f"建議使用 **現金 + 2倍槓桿ETF** 組合。<br>例如：買入本金 **{(avg_leverage/2)*100:.0f}%** 的正2 ETF (如QLD/00631L)，保留其餘現金。"
                    else:
                        advice = f"建議積極操作，可考慮融資或高比例正2 ETF。"

                    st.info(f"""
                    **💡 執行策略 (空手資金 $10,000 為例)：**
                    {advice}
                    *此數值綜合考量了 {selected_m} 個月的長短週期信號，能平衡「順勢追價」與「拉回波動」的風險。*
                    """)
            else:
                st.error("🛑 目前主要趨勢為空頭 (Yearly Bear)。綜合建議：**0x (空手/防禦)**。")

            st.divider()

            # --- 下方顯示細節卡片 ---
            st.markdown("### 🔍 各週期詳細訊號")
            if curr_long_mom > 0:
                status_cols = st.columns(4)
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
                                lev_color = "#2962FF" if lev >= 1 else "#FF9800"
                                
                                st.markdown(f"""
                                <div style='border:1px solid #ddd; border-radius:8px; padding:15px; background-color:var(--secondary-background-color); height:100%'>
                                    <div style='font-size:0.9em; opacity:0.8'>短期濾網 ({m}個月)</div>
                                    <div style='font-size:1.3em; font-weight:bold; margin:5px 0'>{icon} {curr_type}</div>
                                    <div style='font-size:0.85em;'>年化波動: {data['年化波動']:.1%}</div>
                                    <hr style='margin:5px 0'>
                                    <div style='margin-top:8px;'>
                                        <span style='font-size:0.8em'>單獨建議:</span><br>
                                        <span style='font-size:1.4em; font-weight:900; color:{lev_color}'>{lev:.2f}x</span>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)

            # --- 歷史數據表 ---
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
                    vals = []
                    for name in res_df['回測設定']:
                        val = res_df.loc[res_df['回測設定'] == name, metric].values[0]
                        vals.append(val)
                    for val in vals:
                        display_text = config["fmt"](val)
                        if "槓桿" in metric:
                            if val > 1.5: display_text = f"<span style='color:#2962FF; font-weight:900'>{display_text}</span>"
                            elif val <= 0: display_text = f"<span style='color:#D32F2F; font-weight:bold'>0x</span>"
                        html += f"<td>{display_text}</td>"
                    html += "</tr>"
                html += "</tbody></table>"
                st.markdown(html, unsafe_allow_html=True)

        # ==============================================================================
        # TAB 2: 長線機率展望
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
                
                st.divider()
                with st.expander("📄 點擊查看詳細數據表格 (原始資料)"):
                    fmt_dict = {'發生次數': '{:.0f}'}
                    for col in res_df_hz.columns:
                        if '個月' in col or '勝率' in col or '報酬' in col:
                            fmt_dict[col] = '{:.2%}'
                    st.dataframe(res_df_hz.style.format(fmt_dict).background_gradient(subset=[f'勝率_{h}M' for h in horizons], cmap='Blues'), use_container_width=True)
