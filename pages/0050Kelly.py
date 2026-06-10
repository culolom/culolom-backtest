import os
import sys
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ======================================================
# 1. ⚙️ Streamlit 頁面最優先設定
# ======================================================
st.set_page_config(
    page_title="0050 / 台指期 動態曝險戰情室",
    layout="wide"
)

# ======================================================
# 2. 🔒 驗證守門員
# ======================================================
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
    根據日報酬計算：
    - 年化報酬率
    - 年化波動率
    - Full Kelly
    - Half Kelly
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


def format_money(value):
    if pd.isna(value):
        return "資料不足"
    return f"{value:,.0f} 元"


def clamp(value, lower, upper):
    return max(lower, min(value, upper))


def calc_futures_position(
    capital: float,
    target_exposure_multiple: float,
    current_exposure_multiple: float,
    futures_price: float,
    multiplier: int,
):
    """
    根據目標曝險計算期貨口數。

    capital：本金
    target_exposure_multiple：目標曝險倍數，例如 1.5 倍
    current_exposure_multiple：目前已有曝險，例如 1.0 倍
    futures_price：期貨點數
    multiplier：契約乘數
    """

    current_exposure = capital * current_exposure_multiple
    target_exposure = capital * target_exposure_multiple
    need_exposure = target_exposure - current_exposure

    contract_value = futures_price * multiplier

    if contract_value <= 0:
        contracts = 0
    else:
        contracts = need_exposure / contract_value

    return {
        "current_exposure": current_exposure,
        "target_exposure": target_exposure,
        "need_exposure": need_exposure,
        "contract_value": contract_value,
        "contracts": contracts,
        "rounded_contracts": int(round(contracts)),
        "floor_contracts": int(np.floor(contracts)),
        "ceil_contracts": int(np.ceil(contracts)),
    }


def calc_leveraged_etf_allocation(target_exposure_multiple: float, leveraged_multiple: float = 2.0):
    """
    用正2 ETF 做目標曝險換算。

    假設：
    正2 = 2 倍曝險
    現金 = 0 倍曝險

    目標曝險 = 正2比例 * 2

    所以：
    正2比例 = 目標曝險 / 2
    現金比例 = 1 - 正2比例
    """

    if leveraged_multiple <= 0:
        return np.nan, np.nan

    etf_weight = target_exposure_multiple / leveraged_multiple
    cash_weight = 1 - etf_weight

    return etf_weight, cash_weight


# ======================================================
# 5. 📊 主標題
# ======================================================
st.title("📊 0050 / 台指期 動態曝險戰情室")

st.caption(
    "用 0050 估計台股長期報酬與波動，再用均線狀態 + 凱利公式，轉換成台指期、小台、微台或正2的曝險建議。"
)

# ======================================================
# 6. 使用者參數
# ======================================================
st.subheader("① 參數設定")

col_in1, col_in2, col_in3 = st.columns(3)

with col_in1:
    sma_window = st.number_input(
        "狀態均線天數",
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

with col_in3:
    max_target_exposure = st.number_input(
        "曝險上限倍數",
        min_value=0.0,
        max_value=5.0,
        value=2.0,
        step=0.1
    )

rf_rate = rf_rate_input / 100

# ======================================================
# 7. 讀取 0050 資料
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
# 8. 資料處理
# ======================================================
df = df.dropna(subset=["Close"]).copy()

df["Daily_Return"] = np.log(df["Close"] / df["Close"].shift(1))
df["SMA"] = df["Close"].rolling(sma_window).mean()

# 用昨天是否站上 SMA 來判斷今天報酬，避免偷看未來
df["Above_SMA"] = df["Close"].shift(1) > df["SMA"].shift(1)
df["Below_SMA"] = df["Close"].shift(1) <= df["SMA"].shift(1)

all_returns = df["Daily_Return"].dropna()
above_returns = df.loc[df["Above_SMA"], "Daily_Return"].dropna()
below_returns = df.loc[df["Below_SMA"], "Daily_Return"].dropna()

all_stats = calc_kelly_stats(all_returns, rf_rate)
above_stats = calc_kelly_stats(above_returns, rf_rate)
below_stats = calc_kelly_stats(below_returns, rf_rate)

latest_price = df["Close"].iloc[-1]
latest_sma = df["SMA"].iloc[-1]

if pd.isna(latest_sma):
    st.warning(f"資料天數不足，暫時無法計算 {sma_window} 日均線。")
    st.stop()

# ======================================================
# 9. 目前市場狀態
# ======================================================
st.subheader("② 目前市場狀態")

if latest_price > latest_sma:
    current_regime = f"站上 {sma_window}MA"
    current_stats = above_stats
    st.success(
        f"🟢 目前 0050 價格 {latest_price:.2f} 在 {sma_window} 日均線 {latest_sma:.2f} 之上："
        "市場偏多，允許較高曝險。"
    )
else:
    current_regime = f"跌破 {sma_window}MA"
    current_stats = below_stats
    st.warning(
        f"🔴 目前 0050 價格 {latest_price:.2f} 在 {sma_window} 日均線 {latest_sma:.2f} 之下："
        "市場偏空，應降低曝險。"
    )

col_m1, col_m2, col_m3, col_m4 = st.columns(4)

col_m1.metric("目前狀態", current_regime)
col_m2.metric("狀態年化報酬率 μ", format_percent(current_stats["mu"]))
col_m3.metric("狀態年化波動率 σ", format_percent(current_stats["sigma"]))
col_m4.metric("狀態 Half Kelly", format_multiple(current_stats["half_kelly"]))

st.caption(
    f"這裡使用「前一交易日是否站上 {sma_window}MA」來統計隔日報酬，避免偷看未來。"
)

# ======================================================
# 10. 多空狀態比較表
# ======================================================
st.subheader("③ 全歷史 vs 均線狀態比較")

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

# ======================================================
# 11. 曝險建議
# ======================================================
st.subheader("④ 動態曝險建議")

raw_full_kelly = current_stats["full_kelly"]
raw_half_kelly = current_stats["half_kelly"]

if pd.isna(raw_half_kelly):
    st.warning("目前狀態樣本不足，無法計算曝險建議。")
    st.stop()

# 實戰上不讓曝險小於 0，也不超過使用者設定上限
full_kelly_capped = clamp(raw_full_kelly, 0, max_target_exposure)
half_kelly_capped = clamp(raw_half_kelly, 0, max_target_exposure)

# 給三種模式
conservative_exposure = clamp(half_kelly_capped * 0.75, 0, max_target_exposure)
standard_exposure = half_kelly_capped
aggressive_exposure = clamp(half_kelly_capped * 1.25, 0, max_target_exposure)

exposure_col1, exposure_col2, exposure_col3, exposure_col4 = st.columns(4)

exposure_col1.metric(
    "理論 Full Kelly",
    format_multiple(raw_full_kelly)
)

exposure_col2.metric(
    "實戰 Half Kelly",
    format_multiple(raw_half_kelly)
)

exposure_col3.metric(
    "上限後 Half Kelly",
    format_multiple(half_kelly_capped)
)

exposure_col4.metric(
    "曝險上限",
    f"{max_target_exposure:.2f} 倍"
)

target_mode = st.radio(
    "選擇你的目標曝險模式",
    [
        "保守：Half Kelly × 0.75",
        "標準：Half Kelly",
        "積極：Half Kelly × 1.25",
        "自訂"
    ],
    horizontal=True
)

if target_mode == "保守：Half Kelly × 0.75":
    target_exposure = conservative_exposure
elif target_mode == "標準：Half Kelly":
    target_exposure = standard_exposure
elif target_mode == "積極：Half Kelly × 1.25":
    target_exposure = aggressive_exposure
else:
    target_exposure = st.number_input(
        "自訂目標曝險倍數",
        min_value=0.0,
        max_value=max_target_exposure,
        value=float(standard_exposure),
        step=0.1
    )

target_exposure = clamp(target_exposure, 0, max_target_exposure)

st.success(f"🎯 目前目標曝險：{target_exposure:.2f} 倍")

st.info(
    f"""
    **曝險解讀**

    - 0.00 倍：全部現金，不承擔台股價格曝險
    - 1.00 倍：等同 100% 持有 0050
    - 1.50 倍：等同 150% 台股曝險
    - 2.00 倍：等同 100% 持有正2，或用期貨做到 200% 曝險

    目前狀態是：**{current_regime}**

    所以這裡不是單純問「買不買」，而是問：

    > 現在台股環境，應該承擔多少曝險？
    """
)

# ======================================================
# 12. 期貨執行換算
# ======================================================
st.subheader("⑤ 期貨執行換算")

fut_col1, fut_col2, fut_col3 = st.columns(3)

with fut_col1:
    capital = st.number_input(
        "可承擔風險本金 / 策略本金",
        min_value=10000,
        max_value=100000000,
        value=1000000,
        step=10000
    )

with fut_col2:
    current_exposure_multiple = st.number_input(
        "目前已有曝險倍數",
        min_value=0.0,
        max_value=5.0,
        value=1.0,
        step=0.1
    )

with fut_col3:
    futures_price = st.number_input(
        "台指期目前點數",
        min_value=1000,
        max_value=50000,
        value=23000,
        step=100
    )

contract_type = st.radio(
    "選擇期貨商品",
    [
        "大台 TX：每點 200 元",
        "小台 MTX：每點 50 元",
        "微台 TMF：每點 10 元",
        "自訂乘數"
    ],
    horizontal=True
)

if contract_type == "大台 TX：每點 200 元":
    multiplier = 200
elif contract_type == "小台 MTX：每點 50 元":
    multiplier = 50
elif contract_type == "微台 TMF：每點 10 元":
    multiplier = 10
else:
    multiplier = st.number_input(
        "自訂期貨乘數，每點多少元",
        min_value=1,
        max_value=1000,
        value=50,
        step=1
    )

futures_result = calc_futures_position(
    capital=capital,
    target_exposure_multiple=target_exposure,
    current_exposure_multiple=current_exposure_multiple,
    futures_price=futures_price,
    multiplier=multiplier
)

f_col1, f_col2, f_col3, f_col4 = st.columns(4)

f_col1.metric("目前曝險金額", format_money(futures_result["current_exposure"]))
f_col2.metric("目標曝險金額", format_money(futures_result["target_exposure"]))
f_col3.metric("需增加 / 減少曝險", format_money(futures_result["need_exposure"]))
f_col4.metric("單口契約價值", format_money(futures_result["contract_value"]))

st.markdown("### 📌 建議期貨口數")

contracts = futures_result["contracts"]

if contracts > 0:
    st.success(
        f"""
        你需要 **增加多單曝險** 約 **{contracts:.2f} 口**。

        實務可參考：

        - 保守口數：{futures_result["floor_contracts"]} 口
        - 四捨五入口數：{futures_result["rounded_contracts"]} 口
        - 積極口數：{futures_result["ceil_contracts"]} 口
        """
    )
elif contracts < 0:
    st.warning(
        f"""
        你目前曝險高於目標，需要 **降低曝險** 約 **{abs(contracts):.2f} 口**。

        實務可參考：

        - 少減一點：{abs(futures_result["floor_contracts"])} 口
        - 四捨五入：{abs(futures_result["rounded_contracts"])} 口
        - 多減一點：{abs(futures_result["ceil_contracts"])} 口
        """
    )
else:
    st.info("目前曝險已接近目標，不需要調整期貨口數。")

st.caption(
    "提醒：這裡只計算名目曝險，不代表保證金需求。實際交易還要考慮保證金、維持率、滑價、轉倉、稅費與心理承受度。"
)

# ======================================================
# 13. 正2 ETF 替代方案
# ======================================================
st.subheader("⑥ 正2 ETF 替代方案")

leveraged_multiple = st.number_input(
    "槓桿 ETF 倍數",
    min_value=1.0,
    max_value=3.0,
    value=2.0,
    step=0.1
)

etf_weight, cash_weight = calc_leveraged_etf_allocation(
    target_exposure_multiple=target_exposure,
    leveraged_multiple=leveraged_multiple
)

if etf_weight <= 1:
    etf_money = capital * etf_weight
    cash_money = capital * cash_weight

    e_col1, e_col2, e_col3 = st.columns(3)

    e_col1.metric("正2 配置比例", f"{etf_weight:.1%}")
    e_col2.metric("現金配置比例", f"{cash_weight:.1%}")
    e_col3.metric("組合目標曝險", f"{target_exposure:.2f} 倍")

    st.success(
        f"""
        如果用 **{leveraged_multiple:.1f} 倍 ETF** 做替代：

        - 正2 金額：約 **{etf_money:,.0f} 元**
        - 現金金額：約 **{cash_money:,.0f} 元**

        這樣整體曝險約等於 **{target_exposure:.2f} 倍**。
        """
    )
else:
    st.warning(
        f"""
        目標曝險 **{target_exposure:.2f} 倍** 已經超過單純使用 {leveraged_multiple:.1f} 倍 ETF 可達成的範圍。

        單純 100% 持有正2，最高大約就是 **{leveraged_multiple:.1f} 倍曝險**。

        若要更高曝險，需要：

        - 搭配期貨
        - 搭配融資
        - 或降低目標曝險上限
        """
    )

# ======================================================
# 14. 槓桿效能曲線
# ======================================================
st.subheader("⑦ 槓桿效能拋物線")

curve_mode = st.radio(
    "選擇要顯示哪一種市場狀態",
    [
        "全歷史",
        f"站上 {sma_window}MA",
        f"跌破 {sma_window}MA",
        "目前狀態"
    ],
    horizontal=True
)

if curve_mode == "全歷史":
    selected_stats = all_stats
elif curve_mode == f"站上 {sma_window}MA":
    selected_stats = above_stats
elif curve_mode == f"跌破 {sma_window}MA":
    selected_stats = below_stats
else:
    selected_stats = current_stats

selected_mu = selected_stats["mu"]
selected_sigma = selected_stats["sigma"]
selected_full_kelly = selected_stats["full_kelly"]
selected_half_kelly = selected_stats["half_kelly"]

if pd.isna(selected_mu) or pd.isna(selected_sigma) or selected_sigma <= 0:
    st.warning("這個狀態的資料不足，暫時無法繪製凱利曲線。")
    st.stop()

x_max = max(6, selected_full_kelly * 1.5 if selected_full_kelly > 0 else 6)
x_max = min(x_max, 12)

betas = np.linspace(0, x_max, 300)

cagr_values = (
    rf_rate
    + betas * (selected_mu - rf_rate)
    - 0.5 * (betas ** 2) * (selected_sigma ** 2)
)

fig = go.Figure()

fig.add_trace(
    go.Scatter(
        x=betas,
        y=cagr_values,
        mode="lines",
        name="預期長期 CAGR",
        line=dict(color="blue", width=3)
    )
)

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

cagr_1x = (
    rf_rate
    + 1 * (selected_mu - rf_rate)
    - 0.5 * (1 ** 2) * (selected_sigma ** 2)
)

fig.add_trace(
    go.Scatter(
        x=[1],
        y=[cagr_1x],
        mode="markers+text",
        name="1X",
        marker=dict(color="green", size=12),
        text=["1X"],
        textposition="top center"
    )
)

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

fig.add_trace(
    go.Scatter(
        x=[target_exposure],
        y=[
            rf_rate
            + target_exposure * (selected_mu - rf_rate)
            - 0.5 * (target_exposure ** 2) * (selected_sigma ** 2)
        ],
        mode="markers+text",
        name="目前目標曝險",
        marker=dict(color="black", size=14, symbol="x"),
        text=["Target"],
        textposition="bottom center"
    )
)

fig.update_layout(
    title=(
        f"0050 槓桿效能拋物線｜{curve_mode}"
        f"｜年化波動率 {selected_sigma:.2%}"
    ),
    xaxis_title="曝險倍數 Leverage Beta",
    yaxis_title="年化複合增長率 CAGR",
    template="plotly_white",
    height=520,
    yaxis=dict(tickformat=".1%"),
    hovermode="x unified"
)

st.plotly_chart(fig, use_container_width=True)

# ======================================================
# 15. 最後說明
# ======================================================
st.info(
    f"""
    **核心邏輯**

    這個工具的定位不是「預測明天漲跌」。

    它比較像是：

    > 台股曝險調節器

    0050 負責提供長期統計資料。  
    均線負責判斷目前市場狀態。  
    凱利公式負責估算理論曝險。  
    半凱利負責轉成比較接近實戰的曝險。  
    期貨、正2、現金則是執行工具。

    目前狀態：**{current_regime}**

    目前目標曝險：**{target_exposure:.2f} 倍**
    """
)

st.warning(
    """
    **⚠️ 風險提醒**

    凱利公式對參數非常敏感。

    尤其是：

    - 報酬率 μ 只要高估
    - 波動率 σ 只要低估
    - 資金成本 rf 上升
    - 市場結構改變

    實際結果都會差很多。

    所以 Full Kelly 比較像理論上限。

    實戰更適合使用 Half Kelly，甚至再打折。

    期貨還要另外注意：

    - 保證金
    - 維持率
    - 轉倉成本
    - 滑價
    - 跳空
    - 心理壓力
    """
)
