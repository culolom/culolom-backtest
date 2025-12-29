import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import sys

# ===============================================================
# 0. 頁面設定與視覺美化 (CSS 注入)
# ===============================================================
st.set_page_config(
    page_title="Hamr Lab | 50正2乖離雷達",
    page_icon="📈",
    layout="wide",
)

# 定義配色方案
COLORS = {
    'main_gap': '#0052cc',    # 深藍色 - 指標主線
    'price_line': '#B0B8C3',  # 淺灰色 - 收盤價
    'pos2_arb': '#DE350B',    # 深紅色 - 套利線 (+2σ)
    'pos1_warn': '#FF991F',   # 橙色 - 警戒線 (+1σ)
    'neg1_buy': '#00875A',    # 綠色 - 定投線 (-1σ)
    'neg2_bottom': '#00B8D9', # 青藍色 - 抄底線 (-2σ)
    'grid': '#F4F5F7',        # 極淡格線
}

# 自定義 CSS 美化卡片
st.markdown("""
<style>
    .metric-card {
        background-color: #FFFFFF;
        border: 1px solid #E3E6E9;
        border-radius: 10px;
        padding: 15px 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        margin-bottom: 10px;
    }
    .metric-card:hover {
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        transform: translateY(-2px);
    }
    .metric-title {
        color: #6B778C;
        font-size: 0.85rem;
        font-weight: 700;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-value {
        color: #172B4D;
        font-size: 1.6rem;
        font-weight: 800;
        margin: 0;
    }
    .metric-sub {
        font-size: 0.9rem;
        font-weight: 600;
        color: #6B778C;
        margin-left: 5px;
    }
</style>
""", unsafe_allow_html=True)

# 🔒 驗證模塊
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import auth 
    if not auth.check_password():
        st.stop()
except ImportError:
    pass 

# ------------------------------------------------------
# 側邊欄 Sidebar
# ------------------------------------------------------
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.info("💡 指標原理：計算價格與 200SMA 的乖離率，並透過歷史標準差定義恐慌買點與過熱賣點。")

st.title("🚀 50正2 乖離率位階雷達")

# ===============================================================
# 1. 數據讀取與運算
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
    st.error("❌ 找不到數據檔案。")
    st.stop()

with st.container(border=True):
    c1, c2 = st.columns([3, 1])
    with c1:
        selected_option = st.selectbox("🎯 選擇分析標的", available_options)
        selected_file = TARGET_MAP[selected_option]
    with c2:
        sma_window = st.number_input("基準均線週期 (SMA)", value=200, step=10)

file_path = os.path.join(data_dir, selected_file)

try:
    df = pd.read_csv(file_path)
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)
    price_col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
    df['Price'] = pd.to_numeric(df[price_col], errors='coerce')
    df = df.dropna(subset=['Price']).sort_index()

    df['SMA'] = df['Price'].rolling(window=sma_window).mean()
    df['Gap'] = (df['Price'] - df['SMA']) / df['SMA']
    df_clean = df.dropna(subset=['SMA', 'Gap']).copy()

    gap_mean, gap_std = df_clean['Gap'].mean(), df_clean['Gap'].std()
    s_pos2, s_pos1 = gap_mean + 2 * gap_std, gap_mean + gap_std
    s_neg1, s_neg2 = gap_mean - gap_std, gap_mean - 2 * gap_std

    # ===============================================================
    # 2. 全歷史圖表
    # ===============================================================
    st.divider()
    fig_main = make_subplots(specs=[[{"secondary_y": True}]])
    fig_main.add_trace(go.Scatter(x=df_clean.index, y=df_clean['Gap'], name="指標乖離率", line=dict(color=COLORS['main_gap'], width=2), fill='tozeroy', fillcolor='rgba(0, 82, 204, 0.03)'), secondary_y=False)
    fig_main.add_trace(go.Scatter(x=df_clean.index, y=df_clean['Price'], name="收盤價", line=dict(color=COLORS['price_line'], width=1), opacity=0.4), secondary_y=True)

    def add_ref_line(fig, y_val, label, color):
        fig.add_hline(y=y_val, line=dict(color=color, width=1.2, dash="dash"), annotation_text=f"<b>{label}</b>", annotation_position="top right", annotation_font=dict(color=color, size=11), secondary_y=False)

    add_ref_line(fig_main, s_pos2, f"套利 +2σ ({s_pos2*100:.1f}%)", COLORS['pos2_arb'])
    add_ref_line(fig_main, s_pos1, f"警戒 +1σ ({s_pos1*100:.1f}%)", COLORS['pos1_warn'])
    add_ref_line(fig_main, s_neg1, f"定投 -1σ ({s_neg1*100:.1f}%)", COLORS['neg1_buy'])
    add_ref_line(fig_main, s_neg2, f"抄底 -2σ ({s_neg2*100:.1f}%)", COLORS['neg2_bottom'])

    fig_main.update_layout(title=dict(text=f"<b>{selected_option} 歷史乖離率與操作位階</b>", font=dict(size=18)), height=600, hovermode="x unified", template="plotly_white", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig_main.update_yaxes(title_text="乖離率 (%)", tickformat=".1%", secondary_y=False, showgrid=True, gridcolor=COLORS['grid'])
    st.plotly_chart(fig_main, use_container_width=True)

    # ===============================================================
    # 3. 數據參考資訊卡片 (更新百分比標註)
    # ===============================================================
    def create_card(title, value, icon, border_color, sub_text=""):
        sub_html = f'<span class="metric-sub">{sub_text}</span>' if sub_text else ""
        return f"""
        <div class="metric-card" style="border-left: 5px solid {border_color};">
            <div class="metric-title"><span>{icon}</span>&nbsp;{title}</div>
            <p class="metric-value">{value}{sub_html}</p>
        </div>
        """

    with st.expander("📌 查看今日對應價格與當前位階參考", expanded=True):
        curr_p, curr_sma, curr_gap = df_clean['Price'].iloc[-1], df_clean['SMA'].iloc[-1], df_clean['Gap'].iloc[-1]
        
        # 換算價格
        p_pos2, p_pos1 = curr_sma * (1 + s_pos2), curr_sma * (1 + s_pos1)
        p_neg1, p_neg2 = curr_sma * (1 + s_neg1), curr_sma * (1 + s_neg2)

        # 第一排：現況
        r1_c1, r1_c2, r1_c3 = st.columns(3)
        with r1_c1: st.markdown(create_card("今日收盤價", f"{curr_p:.2f}", "🏁", COLORS['main_gap']), unsafe_allow_html=True)
        with r1_c2: st.markdown(create_card("200日均線", f"{curr_sma:.2f}", "〰️", COLORS['price_line']), unsafe_allow_html=True)
        with r1_c3: st.markdown(create_card("當前乖離率", f"{curr_gap*100:.2f}%", "📊", "#172B4D"), unsafe_allow_html=True)

        st.write("") 

        # 第二排：操作建議價格 (加入百分比標註)
        r2_c1, r2_c2, r2_c3, r2_c4 = st.columns(4)
        with r2_c1: 
            st.markdown(create_card("抄底價 (-2σ)", f"{p_neg2:.2f}", "💎", COLORS['neg2_bottom'], f"({s_neg2*100:.1f}%)"), unsafe_allow_html=True)
        with r2_c2: 
            st.markdown(create_card("定投價 (-1σ)", f"{p_neg1:.2f}", "💰", COLORS['neg1_buy'], f"({s_neg1*100:.1f}%)"), unsafe_allow_html=True)
        with r2_c3: 
            st.markdown(create_card("警戒價 (+1σ)", f"{p_pos1:.2f}", "⚡", COLORS['pos1_warn'], f"({s_pos1*100:.1f}%)"), unsafe_allow_html=True)
        with r2_c4: 
            st.markdown(create_card("套利價 (+2σ)", f"{p_pos2:.2f}", "🔥", COLORS['pos2_arb'], f"({s_pos2*100:.1f}%)"), unsafe_allow_html=True)

except Exception as e:
    st.error(f"❌ 分析發生錯誤：{e}")
