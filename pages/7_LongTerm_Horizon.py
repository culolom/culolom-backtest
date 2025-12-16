import os
import sys
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

# (字體設定保持不變...)
font_path = "./NotoSansTC-Bold.ttf"
if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    matplotlib.rcParams["font.family"] = "Noto Sans TC"
else:
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "PingFang TC", "Heiti TC"]
matplotlib.rcParams["axes.unicode_minus"] = False

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password(): st.stop()
except ImportError: pass

# ------------------------------------------------------
# 2. CSS 優化 (增加一點上方 Padding，讓標題不貼頂)
# ------------------------------------------------------
st.markdown("""
    <style>
        .block-container { padding-top: 2rem; }
        /* KPI 卡片與表格樣式保持不變 */
        .kpi-card {
            background-color: var(--secondary-background-color);
            border-radius: 16px; padding: 24px 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.04); border: 1px solid rgba(128,128,128,0.1);
            display: flex; flex-direction: column; justify-content: space-between; height: 100%;
        }
        .kpi-label { font-size: 0.9rem; opacity: 0.8; font-weight: 500; }
        .kpi-value { font-size: 1.8rem; font-weight: 700; margin: 4px 0; color: var(--text-color); }
        
        .comparison-table { width: 100%; border-collapse: separate; border-spacing: 0; border-radius: 12px; border: 1px solid var(--secondary-background-color); margin-bottom: 1rem; font-size: 0.95rem; }
        .comparison-table th { background-color: var(--secondary-background-color); padding: 14px; text-align: center; font-weight: 600; border-bottom: 1px solid rgba(128,128,128,0.1); }
        .comparison-table td { text-align: center; padding: 12px; border-bottom: 1px solid rgba(128,128,128,0.1); }
        .comparison-table td.metric-name { text-align: left; font-weight: 500; background-color: rgba(128,128,128,0.02); width: 20%; }
        .trophy-icon { margin-left: 6px; font-size: 1.1em; text-shadow: 0 0 5px rgba(255,215,0,0.4); }
        
        .status-card { padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid rgba(128,128,128,0.2); }
        .status-bull { background-color: rgba(0, 200, 83, 0.1); border-left: 5px solid #00C853; }
        .status-bear { background-color: rgba(211, 47, 47, 0.1); border-left: 5px solid #D32F2F; }
        .status-neutral { background-color: rgba(255, 167, 38, 0.1); border-left: 5px solid #FFA726; }
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------------------
# 3. 資料讀取函式 (保持不變)
# ------------------------------------------------------
DATA_DIR = Path("data")

def get_all_csv_files():
    if not DATA_DIR.exists(): return []
    return sorted([f.stem for f in DATA_DIR.glob("*.csv")])

def load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}.csv"
    if not path.exists(): return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
    if "Adj Close" in df.columns: df["Price"] = df["Adj Close"]
    elif "Close" in df.columns: df["Price"] = df["Close"]
    return df[["Price"]]

# ------------------------------------------------------
# 4. Sidebar (僅保留導航) & 主標題
# ------------------------------------------------------
with st.sidebar:
    st.page_link("Home.py", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")

st.markdown("<h1 style='margin-bottom:0.1em;'>⚔️ 雙動能全方位戰情室</h1>", unsafe_allow_html=True)
st.caption("整合 **凱利公式決策 (Kelly)** 與 **長線趨勢展望 (Horizon)** 的綜合分析工具")

# ------------------------------------------------------
# ★★★ 修改重點：參數設定移至主畫面 (使用 Container + Columns) ★★★
# ------------------------------------------------------
csv_files = get_all_csv_files()
if not csv_files:
    st.error("⚠️ Data 資料夾內沒有 CSV 檔案。")
    st.stop()

# 這裡使用 container(border=True) 創造一個有邊框的控制區塊，視覺上比較聚攏
with st.container(border=True):
    st.markdown("#### ⚙️ 參數設定面板")
    
    # 建立三個欄位，比例可以自由調整，例如 [1, 2, 1]
    c1, c2, c3 = st.columns([1, 2, 1])
    
    with c1:
        target_symbol = st.selectbox("選擇回測標的 (Symbol)", csv_files, index=0)
    
    with c2:
        default_short = [1, 3]
        selected_m = st.multiselect("設定短期濾網月數 (M)", [1, 2, 3, 4, 5, 6, 9], default=default_short)
        
    with c3:
        # 這裡放說明或是固定的參數，用 info 顯示比較不像輸入框
        st.info("🔒 **主要趨勢 (N)**\n\n固定鎖定 **12 個月** (年線)")
        fixed_n = 12

    # 按鈕放在 Container 內的最下方，讓它跟參數在一起
    start_btn = st.button("開始全方位分析 🚀", type="primary", use_container_width=True)

# ------------------------------------------------------
# 6. 主程式邏輯 (觸發後執行)
# ------------------------------------------------------
if start_btn and target_symbol:
    
    st.divider() # 加一條分隔線，區隔設定與結果

    with st.spinner(f"正在運算 {target_symbol} 的凱利參數與長線展望..."):
        df_daily = load_csv(target_symbol)
        if df_daily.empty: st.error("讀取失敗"); st.stop()

        # --- 共用資料處理 (轉月線) ---
        try: df_monthly = df_daily['Price'].resample('ME').last().to_frame()
        except: df_monthly = df_daily['Price'].resample('M').last().to_frame()
        
        momentum_long = df_monthly['Price'].pct_change(periods=fixed_n)
        signal_long = momentum_long > 0
        
        # 準備 Tabs
        tab_decision, tab_horizon = st.tabs(["⚖️ 凱利決策 & 現況診斷", "🔭 長線趨勢展望"])

        # ==============================================================================
        # TAB 1: 凱利決策 (內容邏輯不變)
        # ==============================================================================
        with tab_decision:
            df_m1 = df_monthly.copy()
            df_m1['Next_Month_Return'] = df_m1['Price'].pct_change().shift(-1)
            results_kelly = []
            
            for m in sorted(selected_m):
                momentum_short = df_m1['Price'].pct_change(periods=m)
                signal_trend = signal_long & (momentum_short > 0)
                signal_pullback = signal_long & (momentum_short < 0)
                
                # ... (內部計算函式保持不變) ...
                def calc_stats_kelly(signal_series, label, sort_idx):
                    target_returns = df_m1.loc[signal_series, 'Next_Month_Return'].dropna()
                    count = len(target_returns)
                    if count > 0:
                        wins = target_returns[target_returns > 0]
                        losses = target_returns[target_returns <= 0]
                        win_count = wins.count(); loss_count = losses.count()
                        win_rate = win_count / count
                        avg_win_pct = wins.mean() if win_count > 0 else 0
                        avg_loss_pct = abs(losses.mean()) if loss_count > 0 else 0
                        payoff_ratio = (avg_win_pct / avg_loss_pct) if avg_loss_pct > 0 else 0
                        kelly_pct = (win_rate - ((1 - win_rate) / payoff_ratio)) if payoff_ratio > 0 else 0
                        if win_count == 0: kelly_pct = -1.0
                        if loss_count == 0: kelly_pct = 1.0
                    else:
                        win_rate, payoff_ratio, kelly_pct, avg_win_pct, avg_loss_pct = 0,0,0,0,0
                    
                    return {
                        '回測設定': label, '排序': sort_idx,
                        '勝率': win_rate, '賠率 (盈虧比)': payoff_ratio,
                        '半凱利 (建議穩健)': kelly_pct * 0.5,
                        '平均獲利': avg_win_pct, '平均虧損': avg_loss_pct,
                        '發生次數': count
                    }
                # ... 

                results_kelly.append(calc_stats_kelly(signal_trend, f"年線多 + {m}月續漲 (順勢)", m * 10 + 1))
                results_kelly.append(calc_stats_kelly(signal_pullback, f"年線多 + {m}月回檔 (低接)", m * 10 + 2))
            
            res_df_kelly = pd.DataFrame(results_kelly).sort_values(by='排序')
            
            # --- Tab 1 UI ---
            st.markdown("### 🧭 目前市場狀態診斷")
            curr_long_mom = momentum_long.iloc[-1] if len(df_monthly) > fixed_n else 0
            
            # (這裡省略重複的 UI 渲染程式碼，請直接沿用上一個版本的 Tab 1 內容)
            # 為了節省篇幅，邏輯完全相同，只需將上個回答的 Tab 1 內容複製過來即可
            # ...
            # 顯示現況卡片
            if curr_long_mom > 0:
                st.success(f"✅ 主要趨勢：多頭 (Yearly Bull) | 過去 12 個月漲幅：+{curr_long_mom:.2%}")
                # 顯示詳細卡片...
                cols = st.columns(len(selected_m))
                for idx, m in enumerate(sorted(selected_m)):
                     with cols[idx]:
                        # ... (顯示每個 M 的小卡片) ...
                        pass # 請填入原有的顯示邏輯
            else:
                st.error(f"🛑 主要趨勢：空頭 (Yearly Bear) | 過去 12 個月跌幅：{curr_long_mom:.2%}")

            # 顯示表格
            if not res_df_kelly.empty:
                st.markdown("### 🎲 歷史統計數據表")
                st.dataframe(res_df_kelly.style.format({'勝率':'{:.1%}', '半凱利 (建議穩健)':'{:.1%}'}), use_container_width=True)


        # ==============================================================================
        # TAB 2: 長線趨勢展望 (內容邏輯不變)
        # ==============================================================================
        with tab_horizon:
            # (這裡省略重複的 UI 渲染程式碼，請直接沿用上一個版本的 Tab 2 內容)
            # ...
            st.info("長線趨勢分析內容...")
            # 請填入原有的熱力圖與長條圖邏輯
