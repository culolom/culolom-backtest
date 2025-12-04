"""
HamrLab Backtest Platform main entry.
Dashboard-style layout with Password Protection + Momentum Overview.
"""

import streamlit as st
import os
import datetime
import pandas as pd
import numpy as np

# 1. 頁面設定 (必須放在第一行)
st.set_page_config(
    page_title="倉鼠回測平台 | 會員專屬",
    page_icon="🐹",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------------------------------------------
# 🎨 全域主題色 (HamrLab 經典藍)
# ------------------------------------------------------
PRIMARY_COLOR = "#2563EB"   # 藍
ACCENT_COLOR = "#22C55E"    # 綠
BG_COLOR = "#F3F4F6"        # 淺灰
CARD_BG = "#FFFFFF"         # 白
TEXT_COLOR = "#111827"      # 深灰

def inject_global_css():
    """自訂 CSS，讓整體更像 SaaS 儀表板。"""
    st.markdown(
        f"""
        <style>
        /* 整體背景 & 內容寬度 */
        .stApp {{
            background-color: {BG_COLOR};
        }}
        .block-container {{
            padding-top: 1.5rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }}

        /* 標題顏色 */
        h1, h2, h3, h4, h5, h6 {{
            color: {TEXT_COLOR};
        }}

        /* 卡片容器統一樣式 */
        .hamr-card {{
            background-color: {CARD_BG};
            border-radius: 1rem;
            padding: 1.2rem 1.4rem;
            box-shadow: 0 10px 25px rgba(15, 23, 42, 0.08);
            border: 1px solid #E5E7EB;
        }}

        .hamr-card:hover {{
            box-shadow: 0 15px 35px rgba(15, 23, 42, 0.16);
            transform: translateY(-2px);
            transition: box-shadow 0.18s ease, transform 0.18s ease;
        }}

        /* 按鈕主題色 */
        .stButton>button {{
            background: linear-gradient(135deg, {PRIMARY_COLOR}, #1D4ED8);
            color: white;
            border-radius: 999px;
            border: none;
            padding: 0.5rem 1rem;
            font-weight: 600;
        }}
        .stButton>button:hover {{
            background: linear-gradient(135deg, #1D4ED8, {PRIMARY_COLOR});
        }}

        /* metrics 卡片微調 */
        [data-testid="stMetric"] {{
            background-color: {CARD_BG};
            padding: 0.6rem 0.8rem;
            border-radius: 0.75rem;
            border: 1px solid #E5E7EB;
        }}

        /* 熱力格：使用 emoji +對齊 */
        .momentum-cell {{
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            font-size: 0.9rem;
            text-align: center;
            padding: 0.2rem 0.4rem;
        }}
        .momentum-table th {{
            font-size: 0.85rem;
            padding: 0.3rem 0.4rem;
        }}
        .momentum-table td {{
            padding: 0.25rem 0.4rem;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )


# ------------------------------------------------------
# 資料檢查 & 公用函式
# ------------------------------------------------------
DATA_DIR = "data"

def scan_data_folder():
    """掃描 data 資料夾，回傳檔案列表與最近更新日期。"""
    data_status = "檢查中..."
    last_update = None
    files = []

    try:
        if os.path.exists(DATA_DIR):
            files = [
                os.path.join(DATA_DIR, f)
                for f in os.listdir(DATA_DIR)
                if f.endswith(".csv")
            ]
            if files:
                latest_file = max(files, key=os.path.getmtime)
                timestamp = os.path.getmtime(latest_file)
                last_update = datetime.datetime.fromtimestamp(timestamp)
                data_status = "✅ 系統數據正常"
            else:
                data_status = "⚠️ 無數據文件"
        else:
            data_status = "❌ 找不到 data 資料夾"
    except Exception:
        data_status = "⚠️ 狀態檢測異常"

    return data_status, last_update, files

def find_csv_for_symbol(symbol: str, files: list):
    """在 data/*.csv 中，找符合 symbol 的檔名（模糊搜尋）。"""
    symbol_lower = symbol.lower()
    for f in files:
        name = os.path.basename(f).lower()
        if symbol_lower in name:
            return f
    return None

def load_price_series(csv_path: str):
    """
    從 CSV 讀出價格序列：
    - 優先找 'Close' 欄位
    - 否則取數值欄位中最後一個當作價格
    """
    try:
        df = pd.read_csv(csv_path)
        # 嘗試把第一欄日期當 index
        df.iloc[:, 0] = pd.to_datetime(df.iloc[:, 0], errors="coerce")
        df = df.set_index(df.columns[0])
        df = df.sort_index()
        # 找價格欄位
        if "Close" in df.columns:
            price = df["Close"].astype(float)
        else:
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) == 0:
                return None
            price = df[numeric_cols[-1]].astype(float)
        return price.dropna()
    except Exception:
        return None

def calc_momentum(price: pd.Series, window_days: int):
    """計算 N 日報酬率（近似 1/3/6/12 月）。"""
    if price is None or len(price) <= window_days:
        return None
    latest = price.iloc[-1]
    past = price.iloc[-window_days]
    if past == 0 or pd.isna(latest) or pd.isna(past):
        return None
    return (latest / past) - 1.0

def momentum_to_cell(value: float):
    """把數值轉成帶 emoji 的文字（當簡易熱力圖）。"""
    if value is None:
        return "<span class='momentum-cell'>-</span>"
    pct = value * 100
    if pct <= 0:
        icon = "⬜"
    elif pct <= 5:
        icon = "🟨"
    elif pct <= 15:
        icon = "🟩"
    else:
        icon = "🟩🟩"
    return f"<span class='momentum-cell'>{icon}<br>{pct:.1f}%</span>"

# ------------------------------------------------------
# 🧭 Hero Section + 資料狀態
# ------------------------------------------------------
data_status, last_update, files = scan_data_folder()

st.title("🚀 倉鼠量化戰情室")

hero_left, hero_right = st.columns([2, 1])

with hero_left:
    st.markdown(
        f"""
        <div class="hamr-card">
            <h3>歡迎回到你的量化基地。</h3>
            <p style="margin-top:0.5rem; color:{TEXT_COLOR}; line-height:1.6;">
            在這裡，你不用寫一行程式碼，就能用
            <b style="color:{PRIMARY_COLOR};">LRS、動能評分、槓桿控管</b>
            來驗證任何交易想法。
            </p>
            <p style="margin-top:0.5rem; color:{TEXT_COLOR}; line-height:1.6;">
            今天的市場誰最強？哪一種策略最適合現在？<br>
            先看下面的 <b>市場摘要 + 動能儀表板</b>，再決定要開哪一套策略。
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

with hero_right:
    col_status, col_files = st.columns(2)
    col_status.metric("資料狀態", data_status.replace("✅ ", "").replace("⚠️ ", "").replace("❌ ", ""))
    col_files.metric("數據檔案數量", len(files))

    if last_update:
        st.metric("最後更新日期", last_update.strftime("%Y-%m-%d"))
    else:
        st.metric("最後更新日期", "N/A")

st.caption("🧪 你今天想做什麼？看市場方向、找強勢標的，還是直接開 LRS 回測？")

st.markdown("---")

# ------------------------------------------------------
# 📊 今日市場摘要（依據 SMA200 簡易判斷）
# ------------------------------------------------------
st.subheader("📌 今日市場摘要")

summary_cols = st.columns(4)

# 定義幾個常見指標／資產（可依你的 CSV 命名調整）
ASSET_CONFIG = [
    {"label": "美股科技", "symbol": "QQQ"},
    {"label": "美股大盤", "symbol": "VOO"},
    {"label": "台股大盤", "symbol": "0050"},
    {"label": "全球股市", "symbol": "VT"},
    {"label": "長天期債券", "symbol": "TLT"},
    {"label": "比特幣", "symbol": "BTC"},
]

def classify_trend(price: pd.Series):
    """用 200 日 + 價格位置簡易判斷趨勢。"""
    if price is None or len(price) < 200:
        return "資料不足", "⬜"
    ma200 = price.rolling(200).mean().iloc[-1]
    last = price.iloc[-1]
    if pd.isna(ma200) or pd.isna(last):
        return "資料不足", "⬜"
    diff = (last / ma200) - 1.0
    if diff > 0.05:
        return "多頭", "🟢"
    elif diff > 0:
        return "偏多", "🟡"
    elif diff > -0.05:
        return "偏空", "🟠"
    else:
        return "空頭", "🔴"

if not files:
    st.info("目前找不到任何 CSV 數據檔案，動能儀表板會先顯示占位內容。請在 data 資料夾放入價格歷史 CSV。")
else:
    for i, asset in enumerate(ASSET_CONFIG[:4]):  # 先顯示 4 個重點
        with summary_cols[i]:
            csv_path = find_csv_for_symbol(asset["symbol"], files)
            if csv_path is None:
                st.metric(asset["label"], "資料不存在", "⬜")
            else:
                price = load_price_series(csv_path)
                trend_text, trend_icon = classify_trend(price)
                st.metric(asset["label"], trend_text, trend_icon)

st.caption("註：以上為簡易 SMA200 趨勢判讀，只作為戰情室參考，不作為買賣訊號。")

st.markdown("---")

# ------------------------------------------------------
# 🔥 動能儀表板（1 / 3 / 6 / 12 月）
# ------------------------------------------------------
st.subheader("🔥 動能熱力儀表板（1 / 3 / 6 / 12 月報酬）")

if not files:
    st.info("目前沒有數據檔案，因此無法計算動能。請先在 data 資料夾放入 QQQ、0050 等標的的歷史價格 CSV。")
else:
    # 只顯示我們有檔案的標的
    TARGETS = ["QQQ", "VOO", "0050", "VT", "TLT", "BTC"]
    rows_html = ""
    has_any = False

    for sym in TARGETS:
        csv_path = find_csv_for_symbol(sym, files)
        if csv_path is None:
            continue

        price = load_price_series(csv_path)
        if price is None:
            continue

        has_any = True
        m1 = calc_momentum(price, 21)    # 約 1 個月 (21 交易日)
        m3 = calc_momentum(price, 63)    # 約 3 個月
        m6 = calc_momentum(price, 126)   # 約 6 個月
        m12 = calc_momentum(price, 252)  # 約 12 個月

        rows_html += f"""
        <tr>
            <td style="text-align:left; padding:0.25rem 0.4rem;">{sym}</td>
            <td>{momentum_to_cell(m1)}</td>
            <td>{momentum_to_cell(m3)}</td>
            <td>{momentum_to_cell(m6)}</td>
            <td>{momentum_to_cell(m12)}</td>
        </tr>
        """

    if not has_any:
        st.info("目前雖然找到 CSV 檔案，但無法解析價格欄位。請確認 CSV 有日期欄位與 Close 或數值價格欄位。")
    else:
        table_html = f"""
        <table class="momentum-table">
            <thead>
                <tr>
                    <th style="text-align:left;">標的</th>
                    <th>1M</th>
                    <th>3M</th>
                    <th>6M</th>
                    <th>12M</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
        """
        st.markdown(f"<div class='hamr-card'>{table_html}</div>", unsafe_allow_html=True)

st.caption("🟩 顏色越綠代表動能越強；⬜ 代表動能偏弱或報酬為負。")

st.markdown("---")

# ------------------------------------------------------
# 🛠️ 策略展示區 (卡片式佈局)
# ------------------------------------------------------
strategies = [
    {
        "name": "QQQ LRS 動態槓桿 (美股)",
        "icon": "🦅",
        "description": "鎖定美股科技巨頭。以 QQQ 200 日均線為訊號，動態切換 QLD / TQQQ 槓桿 ETF，追蹤 Nasdaq 長期成長趨勢，同時控制回撤。",
        "tags": ["美股", "Nasdaq", "動態槓桿"],
        "who": "適合願意承受波動、但又希望有風險控管機制的長線投資人。",
        "page_path": "pages/1_QQQLRS.py",
        "btn_label": "進入 QQQ LRS 回測"
    },
    {
        "name": "0050 LRS 動態槓桿 (台股)",
        "icon": "🇹🇼",
        "description": "以 0050 / 006208 為基準，搭配正二槓桿 ETF，在多頭時放大曝險、空頭時降低持股比重，追求優於大盤的報酬風險比。",
        "tags": ["台股", "0050", "波段操作"],
        "who": "適合熟悉台股、想用系統化方式控制正二風險的投資人。",
        "page_path": "pages/2_0050LRS.py",
        "btn_label": "進入 0050 LRS 回測"
    },
]

st.subheader("🛠️ 選擇你的實驗策略")

cols = st.columns(2)

for index, strategy in enumerate(strategies):
    col = cols[index % 2]
    with col:
        st.markdown("<div class='hamr-card'>", unsafe_allow_html=True)

        st.markdown(f"### {strategy['icon']} {strategy['name']}")
        st.markdown(" ".join([f"`{tag}`" for tag in strategy["tags"]]))
        st.write(strategy["description"])
        st.markdown(f"<span style='font-size:0.9rem; color:#4B5563;'>👉 {strategy['who']}</span>", unsafe_allow_html=True)
        st.write("")
        st.page_link(
            strategy["page_path"],
            label=strategy["btn_label"],
            icon="👉",
            use_container_width=True
        )

        st.markdown("</div>", unsafe_allow_html=True)

# 6. 未來展望 / 預告區塊
st.markdown("---")
st.caption("🚧 更多策略正在開發中（MACD 動能、RSI 逆勢策略、資金輪動雷達...），完成後會優先在這裡開給白銀會員。")
