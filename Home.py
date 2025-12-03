"""
HamrLab Backtest Platform main entry.
Main page: Dashboard style layout with Password Protection & Market Signals.
"""

import streamlit as st
import os
import datetime
import pandas as pd # 記得 import pandas 來處理數據

# 1. 頁面設定 (必須放在第一行)
st.set_page_config(
    page_title="倉鼠回測平台 | 會員專屬",
    page_icon="🐹",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ------------------------------------------------------
# ✅ 正式內容開始
# ------------------------------------------------------

# 2. 側邊欄：品牌與外部連結
with st.sidebar:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=120)
    else:
        st.title("🐹") 
        
    st.title("倉鼠實驗室")
    st.caption("v1.2.0 Beta | 白銀會員限定")
    
    st.divider()
    
    if st.button("🚪 登出系統"):
        st.session_state["password_correct"] = False
        st.rerun()

    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@HamrLab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")
    st.divider()
    st.info("💡 **提示**\n本平台僅供策略研究與回測驗證，不代表投資建議。")

# 3. 主畫面：歡迎語
st.title("🚀 量化戰情室")

# 數據更新狀態
data_status = "檢查中..."
last_update = "N/A"

try:
    data_dir = "data"
    if os.path.exists(data_dir):
        files = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith(".csv")]
        if files:
            latest_file = max(files, key=os.path.getmtime)
            timestamp = os.path.getmtime(latest_file)
            last_update = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
            data_status = "✅ 系統數據正常"
        else:
            data_status = "⚠️ 無數據文件"
    else:
        data_status = "❌ 找不到數據資料夾"
except Exception as e:
    data_status = "⚠️ 狀態檢測異常"

st.caption(f"{data_status} | 📅 最後更新：{last_update}")

st.markdown("""
歡迎來到 **倉鼠回測平台**！這裡是鼠叔為白銀會員打造的專屬軍火庫。
下方儀表板顯示主要指數的 **200日均線 (牛熊分界)** 狀態，幫助您快速判斷市場水位。
""")

st.divider()

# ==========================================
# 📊 新增功能：市場即時儀表板 (戰情室核心)
# ==========================================
st.markdown("### 🚥 市場多空訊號 (最新收盤)")

def get_signal_status(symbol_csv, window=200):
    """讀取 CSV 並判斷目前是多頭還是空頭"""
    csv_path = os.path.join("data", symbol_csv)
    
    if not os.path.exists(csv_path):
        return None, None, None, "無資料"

    try:
        df = pd.read_csv(csv_path)
        # 兼容 Close 或 Adj Close
        col_price = "Adj Close" if "Adj Close" in df.columns else "Close"
        
        # 簡單清理並計算
        df = df.tail(300).copy() # 只取最後300筆提升效能
        df[col_price] = pd.to_numeric(df[col_price], errors='coerce')
        df["MA_200"] = df[col_price].rolling(window=window).mean()
        
        last_row = df.iloc[-1]
        price = last_row[col_price]
        ma = last_row["MA_200"]
        
        if pd.isna(ma):
            return price, None, "資料不足", "off"
            
        # 判斷邏輯：站上均線為多頭(綠燈)，跌破為空頭(紅燈)
        if price > ma:
            status = "🟢 多頭 (持有)"
            delta_color = "normal"  # Streamlit 預設 normal 是綠色 (Good)
        else:
            status = "🔴 空頭 (空手)"
            delta_color = "inverse" # Streamlit 預設 inverse 是紅色 (Bad)
            
        return price, ma, status, delta_color
        
    except Exception as e:
        return None, None, None, "讀取錯誤"

# 建立 3 個欄位顯示儀表板
m1, m2, m3 = st.columns(3)

# 1. 顯示 QQQ 狀態
with m1:
    # 這裡會去讀取 data/QQQ.csv
    price, ma, status, color = get_signal_status("QQQ.csv")
    if price:
        st.metric(
            label="🇺🇸 QQQ 納斯達克",
            value=f"${price:.2f}",
            delta=status,
            delta_color=color if color == "normal" else "inverse"
        )
        if ma: st.caption(f"200MA: ${ma:.2f}")
    else:
        st.info("尚無 QQQ 數據")

# 2. 顯示 0050 狀態
with m2:
    # 這裡會去讀取 data/0050.TW.csv (請確認您的檔名是否正確，或是 006208.csv)
    price, ma, status, color = get_signal_status("0050.TW.csv") 
    
    if price:
        st.metric(
            label="🇹🇼 0050 台灣五十",
            value=f"{price:.2f}",
            delta=status,
            delta_color=color if color == "normal" else "inverse"
        )
        if ma: st.caption(f"200MA: {ma:.2f}")
    else:
        st.info("尚無 0050 數據")

# 3. 預留位置 / 比特幣 / 其他
with m3:
    # 示範：如果有比特幣資料可讀取 BTC-USD.csv，目前先放開發中提示
    st.container(border=True).markdown("""
    **🚧 更多訊號開發中**
    
    比特幣 (BTC) 與 總體經濟指標
    即將上線...
    """)

st.divider()

# 4. 策略定義 (資料結構)
strategies = [
    {
        "name": "QQQ LRS 動態槓桿 (美股)",
        "icon": "🦅",
        "description": "鎖定美股科技巨頭。以 QQQ 200日均線為訊號，動態切換 QLD (2倍) 或 TQQQ (3倍) 槓桿 ETF，捕捉 Nasdaq 長期成長趨勢。",
        "tags": ["美股", "Nasdaq", "動態槓桿"],
        "page_path": "pages/1_QQQLRS.py",
        "btn_label": "進入 QQQ 回測"
    },
    {
        "name": "0050 LRS 動態槓桿 (台股)",
        "icon": "🇹🇼",
        "description": "進階的資金控管策略。以 0050/006208 為訊號，動態調整正2槓桿 ETF 的曝險比例，追求比大盤更高的報酬風險比。",
        "tags": ["台股", "0050", "波段操作"],
        "page_path": "pages/2_0050LRS.py",
        "btn_label": "進入 0050 回測"
    },
]

# 5. 策略展示區
st.subheader("🛠️ 選擇你的實驗策略")

cols = st.columns(2)

for index, strategy in enumerate(strategies):
    col = cols[index % 2]
    
    with col:
        with st.container(border=True):
            st.markdown(f"### {strategy['icon']} {strategy['name']}")
            st.markdown(" ".join([f"`{tag}`" for tag in strategy['tags']]))
            st.write(strategy['description'])
            st.write("") 
            st.page_link(
                strategy['page_path'], 
                label=strategy['btn_label'], 
                icon="👉", 
                use_container_width=True
            )

# 6. 頁尾
st.markdown("---")
st.caption("🚧 更多策略正在開發中 (MACD 動能、RSI 逆勢交易...)，敬請期待！")
