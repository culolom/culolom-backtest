import os
import sys
import datetime as dt
from dateutil.relativedelta import relativedelta
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
st.set_page_config(page_title="動態凱利倉位模擬器", page_icon="🎚️", layout="wide")

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
        
        .status-card { padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid rgba(128,128,128,0.2); }
        .status-bull { background-color: rgba(0, 200, 83, 0.1); border-left: 5px solid #00C853; }
        .status-bear { background-color: rgba(211, 47, 47, 0.1); border-left: 5px solid #D32F2F; }

        .comparison-table { width: 100%; border-collapse: separate; border-spacing: 0; border-radius: 12px; border: 1px solid var(--secondary-background-color); margin-bottom: 1rem; font-size: 0.95rem; }
        .comparison-table th { background-color: var(--secondary-background-color); padding: 14px; text-align: center; font-weight: 600; border-bottom: 1px solid rgba(128,128,128,0.1); }
        .comparison-table td { text-align: center; padding: 12px; border-bottom: 1px solid rgba(128,128,128,0.1); }
        .comparison-table td.metric-name { text-align: left; font-weight: 500; background-color: rgba(128,128,128,0.02); width: 25%; }
        
        div[data-testid="stMetric"] {
            background-color: #f8f9fa; padding: 10px; border-radius: 8px; border: 1px solid #eee;
        }
        div.stButton > button { border-radius: 8px; font-weight: bold; width: 100%; }
        
        /* 日期選擇區塊樣式 */
        .date-selector-label { font-size: 0.9rem; font-weight: 600; margin-bottom: 5px; }
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------------------
# 3. 資料讀取函式
# ------------------------------------------------------
DATA_DIR = Path("data")

@st.cache_data(ttl=3600) # 加入快取避免重複讀取
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

st.markdown("<h1 style='margin-bottom:0.1em;'>🎚️ 動態凱利倉位模擬器</h1>", unsafe_allow_html=True)
st.caption("混合策略：**歷史預期報酬 ($\mu$)** vs **現況波動率 ($\sigma_{current}$)**")

# ★★★ 控制面板區塊 ★★★
with st.container(border=True):
    st.markdown("#### ⚙️ 模擬參數設定")
    
    # 上半部：標的與利率
    c1, c2 = st.columns([1, 1.5])
    
    with c1:
        watch_list = ["QQQ", "SPY", "0050.TW", "VT", "VTI", "GLD"]
        target_symbol = st.selectbox("選擇標的 (Symbol)", watch_list, index=0)
        
        # 預先讀取資料以取得日期範圍
        df_raw = load_csv(target_symbol)
        if not df_raw.empty:
            min_date = df_raw.index.min().date()
            max_date = df_raw.index.max().date()
        else:
            min_date = dt.date(2000, 1, 1)
            max_date = dt.date.today()

    with c2:
        rf_symbol = "預設 4%"
        rf_rate = 0.04
        candidates = ["BIL", "SHV", "SGOV"]
        for sym in candidates:
            df_rf = load_csv(sym)
            if not df_rf.empty:
                try: df_rf_m = df_rf['Price'].resample('ME').last().to_frame()
                except: df_rf_m = df_rf['Price'].resample('M').last().to_frame()
                if len(df_rf_m) > 12:
                    rf_rate = df_rf_m['Price'].pct_change(periods=12).iloc[-1]
                    rf_symbol = sym
                    break
        
        st.info(f"**市場參數**：無風險利率 `{rf_rate:.2%}` ({rf_symbol}) | 主要趨勢 `12個月` | 短期濾網 `1,3,6,9個月`")
        fixed_n = 12
        selected_m = [1, 3, 6, 9]

    # 下半部：時間區間選擇 (新增功能)
    st.markdown("---")
    st.markdown("<div class='date-selector-label'>📅 選擇回測時間區間</div>", unsafe_allow_html=True)
    
    # 使用 session_state 來管理日期，以便按鈕可以更新它
    if 'start_d' not in st.session_state: st.session_state.start_d = min_date
    if 'end_d' not in st.session_state: st.session_state.end_d = max_date
    
    # 確保切換股票時，日期不會卡在舊的範圍外 (重置邏輯)
    if st.session_state.end_d > max_date: st.session_state.end_d = max_date
    if st.session_state.start_d < min_date: st.session_state.start_d = min_date

    # 快速選單按鈕
    b_col1, b_col2, b_col3, b_col4, b_col5 = st.columns(5)
    
    def set_date_range(years=None, all_data=False):
        st.session_state.end_d = max_date
        if all_data:
            st.session_state.start_d = min_date
        else:
            new_start = max_date - relativedelta(years=years)
            st.session_state.start_d = max(new_start, min_date) # 確保不超出最早日期

    if b_col1.button("1 年"): set_date_range(years=1)
    if b_col2.button("3 年"): set_date_range(years=3)
    if b_col3.button("5 年"): set_date_range(years=5)
    if b_col4.button("10 年"): set_date_range(years=10)
    if b_col5.button("全部"): set_date_range(all_data=True)

    # 日期選擇器 (與 Session State 連動)
    # 這裡我們使用 columns 來讓它置中或調整寬度
    d_col1, d_col2 = st.columns([3, 1])
    with d_col1:
        date_range = st.date_input(
            "自訂範圍",
            value=(st.session_state.start_d, st.session_state.end_d),
            min_value=min_date,
            max_value=max_date,
            label_visibility="collapsed"
        )
    
    with d_col2:
        start_btn = st.button("開始分析 🚀", type="primary")

# ------------------------------------------------------
# 5. 主程式執行邏輯
# ------------------------------------------------------
if start_btn and target_symbol:
    
    st.divider() 

    # 處理日期輸入
    if isinstance(date_range, tuple):
        if len(date_range) == 2:
            req_start, req_end = date_range
        elif len(date_range) == 1:
            req_start = date_range[0]
            req_end = max_date
        else:
            req_start, req_end = min_date, max_date
    else:
        req_start, req_end = min_date, max_date

    with st.spinner(f"正在計算區間 {req_start} ~ {req_end} 的動態凱利模型..."):
        # 1. 讀取標的 (已在上面讀過，但這裡要過濾)
        if df_raw.empty: st.error(f"找不到 {target_symbol}.csv"); st.stop()
        
        # ★★★ 關鍵：根據選擇的時間進行切片 ★★★
        # 注意：為了讓「起始日」的年線動能計算正確，我們需要「往前多抓一年」的資料
        # 否則切片後的第一天會因為沒有前12個月資料而變成 NaN
        buffer_start = req_start - relativedelta(months=13)
        df_daily = df_raw.loc[buffer_start : req_end].copy()
        
        # 2. 轉月線 (歷史回測用)
        try: df_monthly = df_daily['Price'].resample('ME').last().to_frame()
        except: df_monthly = df_daily['Price'].resample('M').last().to_frame()
        
        # 3. 計算「現況」波動率 (使用選定區間內 最後 21 個交易日)
        # 如果使用者選的結束時間是 2020年，這裡就會用 2020年當時的波動率，達成「時光機」回測效果
        recent_daily_returns = df_daily['Price'].pct_change().tail(21)
        current_daily_std = recent_daily_returns.std()
        current_ann_vol = current_daily_std * np.sqrt(252)
        
        # 4. 計算「近12個月」的現況指標 (基於選定區間的最後一天)
        if len(df_daily) > 252:
            curr_12m_ret = (df_daily['Price'].iloc[-1] / df_daily['Price'].iloc[-252]) - 1
            last_12m_daily_rets = df_daily['Price'].pct_change().tail(252)
            curr_12m_vol = last_12m_daily_rets.std() * np.sqrt(252)
        else:
            curr_12m_ret = 0
            curr_12m_vol = 0
            
        var_12m = curr_12m_vol ** 2
        if var_12m > 0:
            kelly_12m_full = (curr_12m_ret - rf_rate) / var_12m
        else:
            kelly_12m_full = 0
        kelly_12m_half = kelly_12m_full * 0.5

        # -----------------------------------------------
        # 顯示區塊 A: 現況基準 (顯示使用者選擇的區間)
        # -----------------------------------------------
        # 重新校正顯示用的開始時間 (因為前面多抓了 buffer)
        display_start = max(req_start, df_monthly.index[0].date())
        data_years = (req_end - display_start).days / 365.25
        
        st.caption(f"📅 分析區間：{display_start} ~ {req_end} (共 {data_years:.1f} 年)")

        st.markdown(f"### 📊 區間期末基準 (Benchmark @ {req_end})")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("近12月報酬", f"{curr_12m_ret:.2%}", help="區間結束時的過去一年漲跌幅")
        m2.metric("近12月波動", f"{curr_12m_vol:.2%}", help="區間結束時的年化標準差")
        m3.metric("無風險利率", f"{rf_rate:.2%}", help=f"來自 {rf_symbol}")
        m4.metric("全凱利 (現況)", f"{kelly_12m_full:.2f} x", help="理論最大值")
        m5.metric("半凱利 (建議)", f"{kelly_12m_half:.2f} x", help="安全邊際建議值")
        
        st.divider()

        # -----------------------------------------------
        # 繼續原本的邏輯
        # -----------------------------------------------
        # 注意：計算動能時，我們會基於 df_monthly (已包含 buffer)
        momentum_long = df_monthly['Price'].pct_change(periods=fixed_n)
        signal_long = momentum_long > 0
        
        # 但統計「歷史期望值」時，我們應該只統計「使用者選擇區間內」的數據？
        # 凱利公式的精神是利用「長期的歷史機率」來決定「當下的注碼」。
        # 因此，通常 u (歷史報酬) 會用「所有可用歷史」來算會比較準，
        # 但為了符合您「回測」的需求 (例如假裝我在 2020)，我們應該只使用截至 req_end 為止的數據。
        # 程式碼上方已經做了 df_daily = df_raw.loc[... : req_end]，所以 df_monthly 也是截止到 req_end 的。
        # 這意味著：所有的歷史統計 u，都是基於「那一天之前」的數據，完全符合 Backtest 不看未來數據的原則！
        
        tab_lev, tab_horizon = st.tabs(["🎚️ 動態槓桿決策", "🔭 長線機率展望"])

        # ==============================================================================
        # TAB 1: 最佳槓桿決策 (混合制)
        # ==============================================================================
        with tab_lev:
            df_m1 = df_monthly.copy()
            df_m1['Next_Month_Return'] = df_m1['Price'].pct_change().shift(-1)
            
            results_kelly = []
            
            for m in sorted(selected_m):
                momentum_short = df_m1['Price'].pct_change(periods=m)
                signal_trend = signal_long & (momentum_short > 0)
                signal_pullback = signal_long & (momentum_short < 0)
                
                def calc_leverage_stats(signal_series, label, sort_idx):
                    # 這裡的 target_returns 已經被限制在 req_end 之前了
                    target_returns = df_m1.loc[signal_series, 'Next_Month_Return'].dropna()
                    count = len(target_returns)
                    
                    if count > 5:
                        avg_monthly_ret = target_returns.mean()
                        ann_ret = avg_monthly_ret * 12 
                    else:
                        ann_ret = 0
                    
                    # 混合公式
                    variance_current = current_ann_vol ** 2
                    
                    if variance_current > 0:
                        optimal_lev = (ann_ret - rf_rate) / variance_current
                    else:
                        optimal_lev = 0
                    
                    return {
                        '回測設定': label, '排序': sort_idx,
                        '歷史年化報酬(預期)': ann_ret, 
                        '現況年化波動': current_ann_vol,
                        '凱利 (全倉)': optimal_lev,
                        '半凱利 (建議)': optimal_lev * 0.5
                    }

                results_kelly.append(calc_leverage_stats(signal_trend, f"年線多 + {m}月續漲 (順勢)", m * 10 + 1))
                results_kelly.append(calc_leverage_stats(signal_pullback, f"年線多 + {m}月回檔 (低接)", m * 10 + 2))
            
            res_df = pd.DataFrame(results_kelly).sort_values(by='排序')
            
            # 計算該區間「最後一天」的動能狀態
            curr_long_mom = momentum_long.iloc[-1] if len(df_monthly) > fixed_n else 0
            current_suggestions = []
            details_for_cards = [] 
            
            if curr_long_mom > 0:
                for m in selected_m:
                    if len(df_monthly) > m:
                        curr_short_mom = df_monthly['Price'].pct_change(periods=m).iloc[-1]
                        
                        if curr_short_mom > 0:
                            curr_type, icon = "順勢", "🚀"
                            target_label = f"年線多 + {m}月續漲 (順勢)"
                        else:
                            curr_type, icon = "拉回", "🛡️"
                            target_label = f"年線多 + {m}月回檔 (低接)"
                        
                        match = res_df[res_df['回測設定'] == target_label]
                        if not match.empty:
                            hist_u = match.iloc[0]['歷史年化報酬(預期)']
                            half_kelly_lev = match.iloc[0]['半凱利 (建議)']
                            
                            current_suggestions.append(half_kelly_lev)
                            details_for_cards.append({
                                'm': m, 'type': curr_type, 'icon': icon,
                                'u': hist_u, 'lev': half_kelly_lev
                            })

            if current_suggestions:
                avg_leverage = sum(current_suggestions) / len(current_suggestions)
            else:
                avg_leverage = 0 

            # UI 顯示
            st.markdown(f"### 🚀 區間期末綜合建議 (Action @ {req_end})")
            
            if curr_long_mom > 0:
                col_action, col_info = st.columns([1, 2])
                
                with col_action:
                    st.markdown(f"""
                    <div class='action-card'>
                        <div class='action-title'>🔥 綜合建議槓桿</div>
                        <div class='action-value'>{avg_leverage:.2f} 倍</div>
                        <div class='action-sub'>現況波動率: {current_ann_vol:.1%}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with col_info:
                    st.info(f"""
                    **📊 模擬情境說明**
                    
                    假設時間停留在 **{req_end}**：
                    * 當時的年線趨勢為 **多頭**。
                    * 當時的市場波動率為 **{current_ann_vol:.1%}**。
                    * 根據截至當時的歷史數據，系統建議開 **{avg_leverage:.2f} 倍** 槓桿。
                    """)
            else:
                st.error(f"🛑 在 {req_end} 時，主要趨勢為空頭 (Yearly Bear)。建議：0x (空手)。")

            st.divider()

            st.markdown("### 🔍 各週期詳細訊號")
            if curr_long_mom > 0 and details_for_cards:
                cols = st.columns(4)
                for idx, item in enumerate(details_for_cards):
                    with cols[idx]:
                        lev = item['lev']
                        color = "#2962FF" if lev >= 1 else "#FF9800"
                        st.markdown(f"""
                        <div style='border:1px solid #ddd; border-radius:8px; padding:15px; background-color:var(--secondary-background-color); height:100%'>
                            <div style='font-size:0.9em; opacity:0.8'>短期濾網 ({item['m']}個月)</div>
                            <div style='font-size:1.3em; font-weight:bold; margin:5px 0'>{item['icon']} {item['type']}</div>
                            <div style='font-size:0.85em; color:#555'>歷史期望報酬: {item['u']:.1%}</div>
                            <hr style='margin:5px 0'>
                            <div style='margin-top:8px;'>
                                <span style='font-size:0.8em'>建議:</span><br>
                                <span style='font-size:1.4em; font-weight:900; color:{color}'>{lev:.2f}x</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            if not res_df.empty:
                st.markdown("<h3>📚 動態凱利計算總表</h3>", unsafe_allow_html=True)
                metrics_map = {
                    "歷史年化報酬(預期)": {"fmt": lambda x: f"{x:.2%}"},
                    "現況年化波動":      {"fmt": lambda x: f"{x:.2%}"},
                    "凱利 (全倉)":       {"fmt": lambda x: f"{x:.2f} x"},
                    "半凱利 (建議)":     {"fmt": lambda x: f"{x:.2f} x"},
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
                        if "凱利" in metric:
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
