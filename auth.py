import streamlit as st

def check_password():
    """
    驗證密碼是否正確。
    如果 session_state 中已經標記為 True，則直接通過。
    否則顯示輸入框與說明文字。
    """
    
    def password_entered():
        """檢查輸入的密碼是否與 secrets 匹配"""
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # 不留明文密碼
        else:
            st.session_state["password_correct"] = False

    # 1. 如果已經驗證過，直接回傳 True，什麼都不用顯示
    if st.session_state.get("password_correct", False):
        return True

    # ----------------------------------------------------
    # 2. 尚未驗證，顯示說明文字與輸入框 (這裡是你要加回來的內容)
    # ----------------------------------------------------
    st.title("🔒 倉鼠量化戰情室 - 會員登入")
    
    st.markdown("""
    本平台僅開放 **YT 白銀小倉鼠** 以上會員使用。
    
    請輸入您在 **[YouTube 會員專屬社群貼文](https://www.youtube.com/@HamrLab/community)** 中取得的 **本月通行密碼**。
    """)

    st.text_input(
        "請輸入通行密碼 (Password)",
        type="password",
        on_change=password_entered,
        key="password"
    )

    # 加入尚未加入會員的提示連結
    st.info("👋 若您尚未加入會員，請點選以下連結支持鼠叔：")
    st.markdown("[👉 **點此加入 YouTube 白銀小倉鼠會員**](https://www.youtube.com/channel/UCNDZDodxfoQorKD2gnLFd4Q/join)")

    # 3. 錯誤提示 (若密碼輸入錯誤時顯示)
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("😕 密碼錯誤，請確認大小寫，或前往 YT 社群貼文查看最新密碼。")

    return False
