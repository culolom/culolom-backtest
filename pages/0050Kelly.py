import os
import sys
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ======================================================
# 1. ⚙️ Streamlit 頁面最優先設定
# ======================================================
st.set_page_config(
    page_title="0050 凱利公式戰情室",
    layout="wide"
)

# ======================================================
# 2. 🔒 驗證守門員
# ======================================================
# 讓 pages 資料夾能讀到根目錄的 auth.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import auth
    if not auth.check_password():
        st.stop()
except ImportError:
    pass

# ======================================================
# 3. 🏠 側邊欄與快速連結
# ======================================================
with st.sidebar:
    st.page_link("https://hamr-lab.com/warroom/", label="回到戰情室", icon="🏠")
    st.divider()
    st.markdown("### 🔗 快速連結")
    st.page_link("https://hamr-lab.com/", label="回到官網首頁", icon="🏠")
    st.page_link("https://www.youtube.com/@hamr-lab", label="YouTube 頻道", icon="📺")
    st.page_link("https://hamr-lab.com/contact", label="問題回報 / 許願", icon="📝")


# ======================================================
# 4. 🧮 函數區
# ======================================================
def calc_kelly_stats(returns: pd.Series, rf_rate: float) -> dict:
    """
    根據一組日報酬資料，計算：
    - 樣本天數
    - 年化報酬率
    - 年化波動率
    - Full Kelly
    - Half Kelly

    凱利公式：
    Full Kelly = (μ - rf) / σ²
    """

    returns = returns.dropna()

    if len(returns) < 30:
        return {
            "days": len(returns),
            "mu": np.nan,
            "sigma": np.nan,
            "full_kelly": np.nan,
            "half_kelly": np.nan,
        }

    mu = returns.mean() * 252
    sigma = returns.std() * np.sqrt(252)

    if sigma > 0:
        full_kelly = (mu - rf_rate) / (sigma ** 2)
    else:
        full_kelly = np.nan

    half_kelly = full_kelly * 0.5 if not np.isnan(full_kelly) else np.nan

    return {
        "days": len(returns),
        "mu": mu,
        "sigma": sigma,
        "full_kelly": full_kelly,
        "half_kelly": half_kelly,
    }


def format_percent(value):
    if pd.isna(value):
        return "資料不足"
    return f"{value:.2%}"


def format_multiple(value):
    if pd.isna(value):
        return "資料不足"
    return f"{value:.2f} 倍"


# ======================================================
# 5. 📊 主網頁 UI 標題
# ======================================================
st.title("📊 0050 凱利公式動態戰情室")

st.caption(
    "用長期報酬率、波動率、資金成本，估算 0050 在不同市場狀態下的凱利槓桿。"
)

# ======================================================
# 6. 讓使用者設定參數
# ======================================================
col_in1, col_in2 = st.columns(2)

with col_in1:
    sma_window = st.number_input(
        "設定狀態均線天數（判斷目前多空燈號）",
        min_value=5,
        max_value=240,
        value=200,
        step=5
    )

with col_in2:
    rf_rate_input = st.number_input(
        "無風險利率 / 資金成本 (%)",
        min_value=0.0,
        max_value=15.0,
        value=3.0,
        step=0.1
    )

rf_rate = rf_rate_input / 100

# ======================================================
# 7. 自動讀取 0050 資料
# ======================================================
df = pd.DataFrame()

possible_paths = [
    "data/0050.TW.csv",
    "data/0050.csv",
    "0050.TW.csv",
    "0050.csv"
]

for path in possible_paths:
    if os.path.exists(path):
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
        break

if df.empty:
    st.error("⚠️ 找不到 0050 的 CSV 檔案，請確認檔案是否放在 data/0050.TW.csv 或同層目錄。")
    st.stop()

# ======================================================
# 8. 資料清理與基礎計算
# ======================================================
df = df.dropna(subset=["Close"]).copy()

df["Daily_Return"] = np.log(df["Close"] / df["Close"].shift(1))
df["SMA"] = df["Close"].rolling(sma_window).mean()

# 用「昨天是否站上 SMA」來判斷今天報酬
# 這樣避免偷看未來
df["Above_SMA"] = df["Close"].shift(1) > df["SMA"].shift(1)
df["Below_SMA"] = df["Close"].shift(1) <= df["SMA"].shift(1)

all_returns = df["Daily_Return"].dropna()
above_returns = df.loc[df["Above_SMA"], "Daily_Return"].dropna()
below_returns = df.loc[df["Below_SMA"], "Daily_Return"].dropna()

# ======================================================
# 9. 計算三種凱利
# ======================================================
all_stats = calc_kelly_stats(all_returns, rf_rate)
above_stats = calc_kelly_stats(above_returns, rf_rate)
below_stats = calc_kelly_stats(below_returns, rf_rate)

# ======================================================
# 10. 全歷史凱利指標
# ======================================================
st.subheader("① 全歷史凱利")

col1, col2, col3, col4 = st.columns(4)

col1.metric("📌 無風險利率 / 資金成本", f"{rf_rate:.2%}")
col2.metric("📈 全歷史年化報酬率 μ", format_percent(all_stats["mu"]))
col3.metric("🔥 Full Kelly", format_multiple(all_stats["full_kelly"]))
col4.metric("🛡️ Half Kelly", format_multiple(all_stats["half_kelly"]))

st.caption(
    "全歷史凱利是用 0050 所有歷史日報酬計算，代表不分多空環境的長期平均結果。"
)

st.write("---")

# ======================================================
# 11. 均線狀態版凱利
# ======================================================
st.subheader(f"② {sma_window} 日均線狀態版凱利")

latest_price = df["Close"].iloc[-1]
latest_sma = df["SMA"].iloc[-1]

if pd.isna(latest_sma):
    st.warning(f"資料天數不足，暫時無法計算 {sma_window} 日均線。")
    st.stop()

if latest_price > latest_sma:
    st.success(
        f"🟢 目前 0050 價格 {latest_price:.2f} 在 {sma_window} 日均線 {latest_sma:.2f} 之上："
        "環境偏多，可觀察槓桿策略。"
    )
else:
    st.warning(
        f"🔴 目前 0050 價格 {latest_price:.2f} 在 {sma_window} 日均線 {latest_sma:.2f} 之下："
        "環境偏空，槓桿風險較高。"
    )

col_s1, col_s2, col_s3, col_s4 = st.columns(4)

col_s1.metric(
    f"站上 {sma_window}MA 年化報酬率",
    format_percent(above_stats["mu"])
)

col_s2.metric(
    f"站上 {sma_window}MA 年化波動率",
    format_percent(above_stats["sigma"])
)

col_s3.metric(
    f"站上 {sma_window}MA Full Kelly",
    format_multiple(above_stats["full_kelly"])
)

col_s4.metric(
    f"站上 {sma_window}MA Half Kelly",
    format_multiple(above_stats["half_kelly"])
)

st.caption(
    f"這裡統計的是：前一交易日站上 {sma_window}MA 後，隔日的報酬表現。"
)

# ======================================================
# 12. 狀態比較表
# ======================================================
st.subheader("③ 多空狀態比較表")

regime_table = pd.DataFrame({
    "狀態": [
        "全歷史",
        f"站上 {sma_window}MA",
        f"跌破 {sma_window}MA"
    ],
    "樣本天數": [
        all_stats["days"],
        above_stats["days"],
        below_stats["days"]
    ],
    "年化報酬率": [
        all_stats["mu"],
        above_stats["mu"],
        below_stats["mu"]
    ],
    "年化波動率": [
        all_stats["sigma"],
        above_stats["sigma"],
        below_stats["sigma"]
    ],
    "Full Kelly": [
        all_stats["full_kelly"],
        above_stats["full_kelly"],
        below_stats["full_kelly"]
    ],
    "Half Kelly": [
        all_stats["half_kelly"],
        above_stats["half_kelly"],
        below_stats["half_kelly"]
    ]
})

st.dataframe(
    regime_table.style.format({
        "年化報酬率": "{:.2%}",
        "年化波動率": "{:.2%}",
        "Full Kelly": "{:.2f} 倍",
        "Half Kelly": "{:.2f} 倍"
    }),
    use_container_width=True
)

st.info(
    f"""
    **💡 怎麼看這張表？**

    - **全歷史**：不管多空，直接用全部資料算。
    - **站上 {sma_window}MA**：只看偏多環境，通常波動較低，凱利槓桿可能較高。
    - **跌破 {sma_window}MA**：只看偏空環境，通常波動較高，凱利槓桿可能較低，甚至變成負數。

    這代表槓桿不是固定答案。

    更合理的做法是：

    > 市場健康時，提高曝險。  
    > 市場轉弱時，降低曝險。
    """
)

st.write("---")

# ======================================================
# 13. 選擇要畫哪一種凱利曲線
# ======================================================
st.subheader("④ 槓桿效能拋物線")

curve_mode = st.radio(
    "選擇要顯示哪一種市場狀態的凱利曲線",
    [
        "全歷史",
        f"站上 {sma_window}MA",
        f"跌破 {sma_window}MA"
    ],
    horizontal=True
)

if curve_mode == "全歷史":
    selected_stats = all_stats
elif curve_mode == f"站上 {sma_window}MA":
    selected_stats = above_stats
else:
    selected_stats = below_stats

selected_mu = selected_stats["mu"]
selected_sigma = selected_stats["sigma"]
selected_full_kelly = selected_stats["full_kelly"]
selected_half_kelly = selected_stats["half_kelly"]

if pd.isna(selected_mu) or pd.isna(selected_sigma) or selected_sigma <= 0:
    st.warning("這個狀態的資料不足，暫時無法繪製凱利曲線。")
    st.stop()

# X 軸：槓桿倍數
# 若凱利很高，圖表自動拉大；但至少顯示到 6 倍
x_max = max(6, selected_full_kelly * 1.5 if selected_full_kelly > 0 else 6)
x_max = min(x_max, 12)  # 避免圖表被極端值拉太誇張

betas = np.linspace(0, x_max, 300)

# 連續時間 CAGR 公式：
# g(β) = rf + β(μ - rf) - 0.5 * β² * σ²
cagr_values = rf_rate + betas * (selected_mu - rf_rate) - 0.5 * (betas ** 2) * (selected_sigma ** 2)

fig = go.Figure()

# 主曲線
fig.add_trace(
    go.Scatter(
        x=betas,
        y=cagr_values,
        mode="lines",
        name="預期長期 CAGR",
        line=dict(color="blue", width=3)
    )
)

# rf 點
fig.add_trace(
    go.Scatter(
        x=[0],
        y=[rf_rate],
        mode="markers+text",
        name="無風險利率",
        marker=dict(color="red", size=12),
        text=["rf"],
        textposition="bottom left"
    )
)

# 1X 原型資產
cagr_1x = rf_rate + 1 * (selected_mu - rf_rate) - 0.5 * (1 ** 2) * (selected_sigma ** 2)

fig.add_trace(
    go.Scatter(
        x=[1],
        y=[cagr_1x],
        mode="markers+text",
        name="1X 原型資產",
        marker=dict(color="green", size=12),
        text=["1X"],
        textposition="top center"
    )
)

# Full Kelly
if not pd.isna(selected_full_kelly) and selected_full_kelly >= 0:
    cagr_full = (
        rf_rate
        + selected_full_kelly * (selected_mu - rf_rate)
        - 0.5 * (selected_full_kelly ** 2) * (selected_sigma ** 2)
    )

    fig.add_trace(
        go.Scatter(
            x=[selected_full_kelly],
            y=[cagr_full],
            mode="markers+text",
            name="Full Kelly",
            marker=dict(color="orange", size=15, symbol="star"),
            text=["Full Kelly"],
            textposition="top center"
        )
    )

    fig.add_vrect(
        x0=0,
        x1=selected_full_kelly,
        fillcolor="lightgreen",
        opacity=0.2,
        layer="below",
        line_width=0
    )

    fig.add_vrect(
        x0=selected_full_kelly,
        x1=x_max,
        fillcolor="salmon",
        opacity=0.2,
        layer="below",
        line_width=0
    )

# Half Kelly
if not pd.isna(selected_half_kelly) and selected_half_kelly >= 0:
    cagr_half = (
        rf_rate
        + selected_half_kelly * (selected_mu - rf_rate)
        - 0.5 * (selected_half_kelly ** 2) * (selected_sigma ** 2)
    )

    fig.add_trace(
        go.Scatter(
            x=[selected_half_kelly],
            y=[cagr_half],
            mode="markers+text",
            name="Half Kelly",
            marker=dict(color="purple", size=12, symbol="diamond"),
            text=["Half Kelly"],
            textposition="top left"
        )
    )

fig.update_layout(
    title=(
        f"0050 槓桿效能拋物線｜{curve_mode}"
        f"｜年化波動率 {selected_sigma:.2%}"
    ),
    xaxis_title="每日調整槓桿倍數 Leverage Beta",
    yaxis_title="年化複合增長率 CAGR",
    template="plotly_white",
    height=520,
    yaxis=dict(tickformat=".1%"),
    hovermode="x unified"
)

st.plotly_chart(fig, use_container_width=True)

# ======================================================
# 14. 曲線解讀
# ======================================================
st.info(
    f"""
    **💡 曲線解讀說明**

    目前選擇狀態：**{curve_mode}**

    - 年化報酬率 μ：**{format_percent(selected_mu)}**
    - 年化波動率 σ：**{format_percent(selected_sigma)}**
    - Full Kelly：**{format_multiple(selected_full_kelly)}**
    - Half Kelly：**{format_multiple(selected_half_kelly)}**

    **Full Kelly** 是數學上讓長期複利最大化的位置。

    但實戰上我會更偏向看 **Half Kelly**。

    因為 Full Kelly 對估算誤差非常敏感。

    報酬率只要高估一點，或波動率低估一點，實際結果就可能差很多。
    """
)

st.warning(
    """
    **⚠️ 注意**

    這個工具不是叫你真的開到 Full Kelly。

    它比較像是「曝險上限參考儀表板」。

    真正實戰可以這樣看：

    - 站上長期均線：允許較高曝險
    - 跌破長期均線：降低曝險
    - Half Kelly：比 Full Kelly 更接近實戰參考
    - Full Kelly：偏理論上限，不建議直接照抄
    """
)
