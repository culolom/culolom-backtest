import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import sys

# ===============================================================
# 0. 設定與美化參數定義
# ===============================================================
st.set_page_config(
    page_title="Hamr Lab | 50正2乖離雷達",
    page_icon="📉",
    layout="wide",
)

# 定義現代化配色方案
COLORS = {
    'main_gap': '#0052cc',    # 深藍色強調乖離率
    'price_line': '#B0B8C3',  # 淺灰色處理股價，使其退居次要
    'pos2_arb': '#DE350B',    # 深紅色 - 套利/危險
    'pos1_warn': '#FF991F',   # 橙色 - 警戒
    'neg1_buy': '#00875A',    # 綠色 - 定投/安全
    'neg2_bottom': '#00B8D9', # 青藍色 - 抄底/機會
    'grid': '#F4F5F7',        # 極淡的格線顏色
    'bg': '#FFFFFF'           # 純白背景
}

# 自定義 CSS 用於美化卡片 (Inject Custom CSS)
st.markdown("""
<style>
    .metric-card {
        background-color: #FFFFFF;
        border: 1px solid #E3E6E9;
        border-radius: 8px;
        padding: 15px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        transition: all 0.2s ease-in-out;
    }
    .metric-card:hover {
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        transform: translateY(-2px);
    }
    .metric-title {
        color: #6B778C;
        font-size: 0.9rem;
        font-weight: 600;
        margin-bottom: 5px;
        display: flex;
        align-items: center;
    }
    .metric-value {
        color: #172B4D;
        font-size: 1.5rem;
        font-weight: 700;
        margin: 0;
    }
    /* 移除 Streamlit 預設圖表邊距 */
    .js-plotly-plot .plotly .modebar {
        top: 0px !important;
    }
</style>
""", unsafe_allow_html=True)

# 🔒 驗證模塊 (保留原樣)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except ImportError:
    pass 

# ------------------------------------------------------
# 側邊欄
# ------------------------------------------------------
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 💡 策略核心")
    st.info("利用 200日均線乖離率，尋找市場極度恐慌與貪婪的時刻。")

st.title("📉 50正2 乖離率位階雷達")
st.markdown("追蹤價格與年線的距離，量化進出場的機會與風險。")

# ===============================================================
# 1. 數據處理
# ===============================================================
data_dir = "data"
TARGET_MAP = {
    "00631L 元大台灣50正2": "00631L.TW.csv",
    "00663L 國泰台灣加權正2": "00663L.TW.csv",
    "00675L 富邦台灣加權正2": "00675L.TW.csv",
    "00685L 群益台灣加權正2": "00685L.TW.csv"
}

available_options = [name for name, f in TARGET_MAP.items() if os.path.exists(os.path.join(data_dir, f))]

if not available_options:
    st.error("❌ 找不到數據檔案，請確認 data 目錄。")
    st.stop()

with st.container(border=True):
    c1, c2 = st.columns([3, 1])
    with c1:
        selected_option = st.selectbox("🎯 選擇分析標的", available_options)
        selected_file = TARGET_MAP[selected_option]
    with c2:
        sma_window = st.number_input("均線週期 (SMA)", value=200, step=10)

file_path = os.path.join(data_dir, selected_file)

try:
    # 資料讀取與計算
    df = pd.read_csv(file_path)
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)
    price_col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
    df['Price'] = pd.to_numeric(df[price_col], errors='coerce')
    df = df.dropna(subset=['Price']).sort_index()

    # 核心指標計算
    df['SMA'] = df['Price'].rolling(window=sma_window).mean()
    df['Gap'] = (df['Price'] - df['SMA']) / df['SMA']
    df_clean = df.dropna(subset=['SMA', 'Gap']).copy()

    # 標準差位階計算
    gap_mean = df_clean['Gap'].mean()
    gap_std = df_clean['Gap'].std()
    
    s_pos2 = gap_mean + 2 * gap_std
    s_pos1 = gap_mean + gap_std
    s_neg1 = gap_mean - gap_std
    s_neg2 = gap_mean - 2 * gap_std

    # ===============================================================
    # 2. 美化後的 Plotly 圖表
    # ===============================================================
    st.divider()
    
    fig_main = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 收盤價 (次要軸，顏色淡化)
    fig_main.add_trace(go.Scatter(
        x=df_clean.index, y=df_clean['Price'], 
        name="收盤價 (右軸)",
        line=dict(color=COLORS['price_line'], width=1), 
        opacity=0.5, # 降低透明度
        hoverinfo='y'
    ), secondary_y=True)

    # 乖離率 (主要軸，顏色強調)
    fig_main.add_trace(go.Scatter(
        x=df_clean.index, y=df_clean['Gap'], 
        name="指標乖離率 (左軸)", 
        line=dict(color=COLORS['main_gap'], width=2),
        fill='tozeroy', # 填充至中線，增加視覺份量
        fillcolor='rgba(0, 82, 204, 0.05)' # 極淡的藍色填充
    ), secondary_y=False)

    # 輔助線繪製函數
    def add_ref_line(fig, y_val, label, color, dash_type="dash"):
        fig.add_hline(
            y=y_val, 
            line=dict(color=color, width=1.5, dash=dash_type),
            annotation_text=f"<b>{label}</b>", # 加粗標籤
            annotation_position="top right",
            annotation_font=dict(color=color, size=11),
            secondary_y=False
        )

    add_ref_line(fig_main, s_pos2, "🔥 套利 (+2σ)", COLORS['pos2_arb'], "longdashdot")
    add_ref_line(fig_main, s_pos1, "⚡ 警戒 (+1σ)", COLORS['pos1_warn'])
    add_ref_line(fig_main, s_neg1, "💰 定投 (-1σ)", COLORS['neg1_buy'])
    add_ref_line(fig_main, s_neg2, "💎 抄底 (-2σ)", COLORS['neg2_bottom'], "longdashdot")

    # 圖表佈局優化
    fig_main.update_layout(
        title=dict(text=f"<b>{selected_option} 歷史乖離率操作位階圖</b>", font=dict(size=20)),
        height=550,
        hovermode="x unified",
        template="plotly_white",
        plot_bgcolor='rgba(0,0,0,0)', # 透明背景
        paper_bgcolor='rgba(0,0,0,0)',
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, # 圖例移到右上方
            bgcolor='rgba(255,255,255,0.8)'
        ),
        margin=dict(l=20, r=20, t=80, b=20), # 調整邊距
    )

    # 座標軸優化
    fig_main.update_yaxes(
        title_text="乖離率 (%)", 
        tickformat=".0%", 
        showgrid=True, gridcolor=COLORS['grid'], gridwidth=1, zeroline=True, zerolinecolor='#E3E6E9',
        secondary_y=False
    )
    fig_main.update_yaxes(
        title_text="收盤價", 
        showgrid=False, # 不顯示右軸格線，避免混亂
        secondary_y=True
    )
    fig_main.update_xaxes(showgrid=False) # 不顯示 X 軸垂直格線

    st.plotly_chart(fig_main, use_container_width=True)

    # ===============================================================
    # 3. 美化後的價格參考卡片 (使用自定義 HTML/CSS)
    # ===============================================================
    st.write("") # 增加一點間距

    # 輔助函數：生成 HTML 卡片
    def create_card(title, value, icon, border_color):
        return f"""
        <div class="metric-card" style="border-left: 4px solid {border_color};">
            <div class="metric-title"><span>{icon}</span>&nbsp;{title}</div>
            <p class="metric-value">{value}</p>
        </div>
        """

    with st.expander("📌 查看今日對應價格參考 (點擊展開/收合)", expanded=True):
        curr_p = df_clean['Price'].iloc[-1]
        curr_sma = df_clean['SMA'].iloc[-1]
        
        # 計算今日對應價格
        price_neg1 = curr_sma * (1 + s_neg1)
        price_neg2 = curr_sma * (1 + s_neg2)
        price_pos1 = curr_sma * (1 + s_pos1)
        price_pos2 = curr_sma * (1 + s_pos2)

        # 使用 HTML 渲染美化卡片
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(create_card("今日收盤價", f"{curr_p:.2f}", "🏁", COLORS['main_gap']), unsafe_allow_html=True)
        with c2:
             # 這裡示範顯示 200SMA，你也可以改成警戒價或套利價
            st.markdown(create_card("200日均線", f"{curr_sma:.2f}", "〰️", COLORS['price_line']), unsafe_allow_html=True)
        with c3:
            st.markdown(create_card("定投價 (-1σ)", f"{price_neg1:.2f}", "💰", COLORS['neg1_buy']), unsafe_allow_html=True)
        with c4:
            st.markdown(create_card("抄底價 (-2σ)", f"{price_neg2:.2f}", "💎", COLORS['neg2_bottom']), unsafe_allow_html=True)
        
        # 額外增加一行顯示高位價格 (選擇性)
        st.write("") # 間距
        c5, c6, c7, c8 = st.columns(4)
        with c7:
             st.markdown(create_card("警戒價 (+1σ)", f"{price_pos1:.2f}", "⚡", COLORS['pos1_warn']), unsafe_allow_html=True)
        with c8:
             st.markdown(create_card("套利價 (+2σ)", f"{price_pos2:.2f}", "🔥", COLORS['pos2_arb']), unsafe_allow_html=True)


except Exception as e:
    st.error(f"❌ 分析發生錯誤：{e}")
    # 在開發時可以取消下面這行的註解來查看詳細錯誤
    # st.exception(e)
