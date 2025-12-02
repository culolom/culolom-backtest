"""
HamrLab Backtest Platform main entry.
Main page: Dashboard style layout for strategies.
"""

import streamlit as st
import os
import datetime

# 1. 頁面設定
st.set_page_config(
    page_title="倉鼠回測平台 | 會員專屬",
    page_icon="🐹",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. 側邊欄：品牌與外部連結
with st.sidebar:
    # 檢查並顯示 Logo
    if os.path.exists("logo.png"):
        st.image("logo.png", width=120)
    else:
        st.title("🐹") 
        
    st.title("倉鼠實驗室")
    st.caption("v1.1.0 Beta | 白銀會員限定")
    
    st.divider()
    
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")
    
    st.divider()
    st.info("💡 **提示**\n本平台僅供策略研究與回測驗證，不代表投資建議。")

# 3. 主畫面：歡迎語 (Hero Section)
st.title("🚀 量化戰情室")

# 動態檢查數據更新時間
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
不需要寫程式，直接點擊下方策略卡片，輸入參數即可驗證你的交易想法。
""")

st.divider()

# 4. 策略定義 (資料結構)
# ✅ 修正重點：根據您的截圖，更新策略對應的檔案路徑與描述
strategies = [
    {
        "name": "QQQ LRS 動態槓桿 (美股)",
        "icon": "🦅",  # 換成老鷹代表美股
        "description": "鎖定美股科技巨頭。以 QQQ 200日均線為訊號，動態切換 QLD (2倍) 或 TQQQ (3倍) 槓桿 ETF，捕捉 Nasdaq 長期成長趨勢。",
        "tags": ["美股", "Nasdaq", "動態槓桿"],
        "page_path": "pages/1_QQQLRS.py",  # ✅ 對應截圖中的新檔名
        "btn_label": "進入 QQQ 回測"
    },
    {
        "name": "0050 LRS 動態槓桿 (台股)",
        "icon": "📚", # 換成台灣國旗
        "description": "進階的資金控管策略。以 0050/006208 為訊號，動態調整正2槓桿 ETF 的曝險比例，追求比大盤更高的報酬風險比。",
        "tags": ["台股", "0050", "波段操作"],
        "page_path": "pages/2_0050LRS.py",   # ✅ 對應截圖中的既有檔名
        "btn_label": "進入 0050 回測"
    },
]

# 5. 策略展示區 (卡片式佈局)
st.subheader("🛠️ 選擇你的實驗策略")

cols = st.columns(2)

for index, strategy in enumerate(strategies):
    col = cols[index % 2]
    
    with col:
        with st.container(border=True):
            st.markdown(f"### {strategy['icon']} {strategy['name']}")
            
            st.markdown(
                " ".join([f"`{tag}`" for tag in strategy['tags']])
            )
            
            st.write(strategy['description'])
            st.write("") 
            
            st.page_link(
                strategy['page_path'], 
                label=strategy['btn_label'], 
                icon="👉", 
                use_container_width=True
            )

# 6. 未來展望 / 預告區塊
st.markdown("---")
st.caption("🚧 更多策略正在開發中 (布林通道 雙動能、GTAA...)，敬請期待！")
