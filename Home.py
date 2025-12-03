"""
HamrLab Backtest Platform main entry.
Main page: Dashboard style layout with Password Protection.
"""

import streamlit as st
import os
import datetime

# ======================================================
# 1. 頁面設定 (必須放在第一行)
# ======================================================
st.set_page_config(
    page_title="倉鼠回測平台 | 會員專屬",
    page_icon="🐹",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ======================================================
# 2. 全域 UI / CSS 設定
# ======================================================
def inject_custom_css():
    st.markdown(
        """
        <style>
        /* 整體背景與字型 */
        .stApp {
            background: radial-gradient(circle at top left, #e0f2fe 0, #f5f5ff 35%, #f9fafb 70%);
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, -system-ui, sans-serif;
        }

        /* 主要內容容器 */
        .main-container {
            padding-top: 0.5rem;
        }

        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 3rem;
            max-width: 1100px;
        }

        /* Sidebar 樣式 */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #020617 0%, #0b1120 40%, #020617 100%);
            border-right: 1px solid rgba(148, 163, 184, 0.4);
        }

        /* Sidebar 內文字 */
        section[data-testid="stSidebar"] * {
            color: #e5e7eb !important;
        }

        section[data-testid="stSidebar"] .css-1d391kg {
            padding-top: 1.5rem;
        }

        /* Sidebar logo 圓形 + 光暈 */
        .hamr-logo img {
            border-radius: 999px;
            box-shadow: 0 0 0 3px rgba(148, 163, 184, 0.3),
                        0 18px 45px rgba(15, 23, 42, 0.8);
        }

        /* KPI Cards */
        .kpi-row {
            margin-top: 0.75rem;
            margin-bottom: 1.5rem;
        }

        .kpi-card {
            background: rgba(255, 255, 255, 0.9);
            border-radius: 16px;
            padding: 12px 18px;
            border: 1px solid rgba(148, 163, 184, 0.35);
            box-shadow: 0 12px 30px rgba(15, 23, 42, 0.05);
        }

        .kpi-label {
            font-size: 0.8rem;
            color: #6b7280;
            margin-bottom: 2px;
        }

        .kpi-value {
            font-size: 1.1rem;
            font-weight: 600;
            color: #111827;
        }

        .kpi-sub {
            font-size: 0.75rem;
            color: #9ca3af;
        }

        /* 策略卡片 */
        .strategy-card {
            background: rgba(255, 255, 255, 0.9);
            border-radius: 20px;
            padding: 18px 20px 14px 20px;
            border: 1px solid rgba(148, 163, 184, 0.4);
            box-shadow: 0 18px 45px rgba(15, 23, 42, 0.06);
            transition: all 0.18s ease-out;
        }

        .strategy-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 22px 55px rgba(15, 23, 42, 0.12);
            border-color: rgba(59, 130, 246, 0.7);
        }

        .strategy-title {
            font-size: 1.1rem;
            font-weight: 650;
            margin-bottom: 6px;
            color: #0f172a;
        }

        .strategy-desc {
            font-size: 0.9rem;
            color: #4b5563;
            line-height: 1.5;
            margin-top: 6px;
            margin-bottom: 10px;
        }

        /* Tag 樣式 (chips) */
        .tag-row {
            margin-top: 2px;
            margin-bottom: 4px;
        }

        .tag-chip {
            display: inline-flex;
            align-items: center;
            padding: 2px 9px;
            margin-right: 6px;
            margin-bottom: 3px;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 500;
            border: 1px solid rgba(148, 163, 184, 0.5);
            background: rgba(248, 250, 252, 0.95);
        }

        .tag-chip--green {
            border-color: rgba(16, 185, 129, 0.4);
            background: rgba(209, 250, 229, 0.9);
            color: #047857;
        }

        .tag-chip--blue {
            border-color: rgba(59, 130, 246, 0.45);
            background: rgba(219, 234, 254, 0.94);
            color: #1d4ed8;
        }

        .tag-chip--purple {
            border-color: rgba(168, 85, 247, 0.45);
            background: rgba(237, 233, 254, 0.94);
            color: #6d28d9;
        }

        /* 讓 page_link 看起來像滿版按鈕 */
        .stLinkButton {
            width: 100%;
        }

        .stLinkButton > button {
            width: 100% !important;
            border-radius: 999px !important;
            font-weight: 600 !important;
            font-size: 0.9rem !important;
            padding-top: 0.5rem !important;
            padding-bottom: 0.5rem !important;
        }

        /* 顯示在 caption 上方的狀態條 */
        .status-pill {
            display: inline-flex;
            align-items: center;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 500;
            background: rgba(16, 185, 129, 0.12);
            color: #047857;
            border: 1px solid rgba(16, 185, 129, 0.24);
            margin-bottom: 4px;
        }

        .status-dot {
            width: 7px;
            height: 7px;
            border-radius: 999px;
            background-color: #22c55e;
            margin-right: 6px;
        }

        /* 標題區塊 */
        .hero-lead {
            font-size: 0.95rem;
            color: #4b5563;
            margin-top: 0.25rem;
            margin-bottom: 0.2rem;
        }

        .hero-sub {
            font-size: 0.86rem;
            color: #6b7280;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_custom_css()



# ======================================================
# 4. 側邊欄：品牌與外部連結
# ======================================================
with st.sidebar:
    # Logo
    col_logo = st.container()
    with col_logo:
        if os.path.exists("logo.png"):
            st.markdown('<div class="hamr-logo">', unsafe_allow_html=True)
            st.image("logo.png", width=120)
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown("### 🐹")

    st.title("倉鼠實驗室")
    st.caption("v1.1.0 Beta｜白銀會員限定")

    st.divider()

    if st.button("🚪 登出系統"):
        st.session_state["password_correct"] = False
        st.rerun()

    st.divider()
    st.markdown("#### 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@HamrLab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")

    st.divider()
    st.info("本平台僅供策略研究與回測驗證，不構成任何投資建議。請自行評估風險。")

# ======================================================
# 5. 主畫面：Hero 區塊 + KPI Cards
# ======================================================

# 5-1 檢查數據狀態
data_status = "系統狀態未知"
last_update = "N/A"

try:
    data_dir = "data"
    if os.path.exists(data_dir):
        files = [
            os.path.join(data_dir, f)
            for f in os.listdir(data_dir)
            if f.endswith(".csv")
        ]
        if files:
            latest_file = max(files, key=os.path.getmtime)
            timestamp = os.path.getmtime(latest_file)
            last_update = datetime.datetime.fromtimestamp(timestamp).strftime(
                "%Y-%m-%d"
            )
            data_status = "系統數據正常"
        else:
            data_status = "目前找不到 CSV 數據檔"
    else:
        data_status = "尚未建立 data 資料夾"
except Exception:
    data_status = "狀態檢測異常"

# 5-2 Hero Title
st.markdown("### 🚀 倉鼠回測平台：你的量化策略沙盒")
st.markdown(
    """
<div class="hero-lead">
不需要寫程式，只要輸入參數，就能快速回測你的交易想法。
</div>
<div class="hero-sub">
適合白銀會員用來練習 <b>LRS 動態槓桿、資金控管、風險回撤</b> 等進階觀念。
</div>
""",
    unsafe_allow_html=True,
)

# 5-3 KPI Cards
st.markdown("<div class='kpi-row'>", unsafe_allow_html=True)
kpi_cols = st.columns(3)

num_strategies = 2  # 目前策略數量，如未來增加可改成 len(strategies)
today_str = datetime.datetime.now().strftime("%Y-%m-%d")

with kpi_cols[0]:
    st.markdown(
        """
        <div class="kpi-card">
            <div class="kpi-label">目前可用策略數</div>
            <div class="kpi-value">2 個策略</div>
            <div class="kpi-sub">QQQ LRS、TW 0050 LRS</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with kpi_cols[1]:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">數據狀態</div>
            <div class="kpi-value">{data_status}</div>
            <div class="kpi-sub">最後更新日期：{last_update}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with kpi_cols[2]:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">今日實驗日</div>
            <div class="kpi-value">{today_str}</div>
            <div class="kpi-sub">建議：先從單一策略開始熟悉，再逐步加上槓桿。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("</div>", unsafe_allow_html=True)

st.markdown("---")

# ======================================================
# 6. 策略定義 (資料結構)
# ======================================================
strategies = [
    {
        "name": "QQQ LRS 動態槓桿 (美股)",
        "icon": "🦅",
        "description": "鎖定美股科技巨頭。以 QQQ 的 200 日均線為訊號，動態切換 QLD (2 倍) 或 TQQQ (3 倍) 槓桿 ETF，追求在控制回撤的前提下放大長期報酬。",
        "tags": ["美股", "Nasdaq", "動態槓桿"],
        "page_path": "pages/1_QQQLRS.py",
        "btn_label": "👉 進入 QQQ 回測",
    },
    {
        "name": "TW 0050 LRS 動態槓桿 (台股)",
        "icon": "🇹🇼",
        "description": "以 0050 / 006208 為基準指標，透過 200 日均線動態調整正 2 槓桿 ETF 曝險比例，在台股大盤中追求更佳的報酬風險比。",
        "tags": ["台股", "0050", "波段操作"],
        "page_path": "pages/2_0050LRS.py",
        "btn_label": "👉 進入 0050 回測",
    },
]

# ======================================================
# 7. 策略展示區 (卡片式佈局)
# ======================================================
st.markdown("#### 🧪 選擇你的實驗策略")

cols = st.columns(2)

for index, strategy in enumerate(strategies):
    col = cols[index % 2]
    with col:
        st.markdown('<div class="strategy-card">', unsafe_allow_html=True)
        st.markdown(
            f'<div class="strategy-title">{strategy["icon"]} {strategy["name"]}</div>',
            unsafe_allow_html=True,
        )

        # Tag chips
        tag_html_parts = []
        for i, tag in enumerate(strategy["tags"]):
            if i == 0:
                cls = "tag-chip tag-chip--green"
            elif i == 1:
                cls = "tag-chip tag-chip--blue"
            else:
                cls = "tag-chip tag-chip--purple"
            tag_html_parts.append(f'<span class="{cls}">{tag}</span>')
        tags_html = " ".join(tag_html_parts)

        st.markdown(f'<div class="tag-row">{tags_html}</div>', unsafe_allow_html=True)

        st.markdown(
            f'<div class="strategy-desc">{strategy["description"]}</div>',
            unsafe_allow_html=True,
        )

        # page_link 作為主要 CTA
        st.page_link(
            strategy["page_path"],
            label=strategy["btn_label"],
            icon="",
            use_container_width=True,
        )

        st.markdown("</div>", unsafe_allow_html=True)

# ======================================================
# 8. 預告區塊
# ======================================================
st.markdown("---")
st.caption("🚧 更多策略（MACD 動能、RSI 逆勢交易、進階資金管理）開發中，之後會陸續開放給白銀會員測試。")
