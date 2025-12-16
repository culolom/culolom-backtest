###############################################################
# pages/2_Momentum_Backtest.py — 雙動能 + 凱利公式 (Kelly Criterion)
###############################################################

import os
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.font_manager as fm
import plotly.graph_objects as go
from pathlib import Path
import sys

# ... (字型與基本設定、Sidebar 保持不變，直接複製原本的即可) ...
# 為了節省篇幅，這邊省略前面的 setup，直接進入核心邏輯修改處

# ===============================================================
#  請將以下內容完全覆蓋原本的 "主程式邏輯" 到結尾
# ===============================================================

###############################################################
# 5. 主程式邏輯 (新增凱利公式計算)
###############################################################

# ... (前面的 Setup 程式碼請保留) ...
# 若您需要完整複製，請確保上方 import 和 sidebar 設定都有保留
# 以下是從 if st.button("開始回測 🚀")... 開始的邏輯

if st.button("開始回測 🚀") and target_symbol:
    
    with st.spinner(f"正在計算凱利公式與期望值: {target_symbol} ..."):
        df_daily = load_csv(target_symbol)
        
        if df_daily.empty:
            st.error(f"讀取 {target_symbol} 失敗")
            st.stop()

        start_date = df_daily.index.min().strftime('%Y-%m-%d')
        end_date = df_daily.index.max().strftime('%Y-%m-%d')
        total_years = (df_daily.index.max() - df_daily.index.min()).days / 365.25

        try:
            df_monthly = df_daily['Price'].resample('ME').last().to_frame()
        except Exception:
            df_monthly = df_daily['Price'].resample('M').last().to_frame()
            
        df_monthly['Next_Month_Return'] = df_monthly['Price'].pct_change().shift(-1)
        
        results = []
        
        momentum_long = df_monthly['Price'].pct_change(periods=fixed_n)
        signal_long = momentum_long > 0
        
        for m in sorted(selected_m):
            momentum_short = df_monthly['Price'].pct_change(periods=m)
            signal_trend = signal_long & (momentum_short > 0)
            signal_pullback = signal_long & (momentum_short < 0)
            
            # --- 核心運算升級：計算盈虧比與凱利值 ---
            def calc_stats_kelly(signal_series, label, sort_idx):
                # 取出該狀態下，下個月的所有報酬率
                target_returns = df_monthly.loc[signal_series, 'Next_Month_Return'].dropna()
                count = len(target_returns)
                
                if count > 0:
                    # 1. 基礎統計
                    wins = target_returns[target_returns > 0]
                    losses = target_returns[target_returns <= 0]
                    
                    win_count = wins.count()
                    loss_count = losses.count()
                    
                    win_rate = win_count / count
                    avg_ret = target_returns.mean()
                    
                    # 2. 凱利公式參數 (Kelly Inputs)
                    # 平均獲利 (Avg Win)
                    avg_win_pct = wins.mean() if win_count > 0 else 0
                    # 平均虧損 (Avg Loss) - 取絕對值
                    avg_loss_pct = abs(losses.mean()) if loss_count > 0 else 0
                    
                    # 賠率 (Odds / Profit Factor) = 平均獲利 / 平均虧損
                    if avg_loss_pct > 0:
                        payoff_ratio = avg_win_pct / avg_loss_pct
                    else:
                        payoff_ratio = 0 # 避免除以零 (或視為無限大)

                    # 3. 計算凱利值 (Kelly Fraction)
                    # 公式: f = p - (q / b)
                    # p = win_rate, q = 1 - win_rate, b = payoff_ratio
                    if payoff_ratio > 0:
                        kelly_pct = win_rate - ((1 - win_rate) / payoff_ratio)
                    else:
                        kelly_pct = 0 # 無法計算時歸零
                    
                    # 極端值保護 (例如全虧或全贏)
                    if win_count == 0: kelly_pct = -1.0 # 絕對不賭
                    if loss_count == 0: kelly_pct = 1.0 # 全押 (理論值)

                    med_ret = target_returns.median()
                    max_ret = target_returns.max()
                    min_ret = target_returns.min()
                else:
                    win_rate, avg_ret, med_ret, max_ret, min_ret = 0, 0, 0, 0, 0
                    avg_win_pct, avg_loss_pct, payoff_ratio, kelly_pct = 0, 0, 0, 0
                
                return {
                    '回測設定': label,
                    '排序': sort_idx, 
                    '短期M': m,
                    '類型': '順勢' if '續漲' in label else '拉回',
                    '發生次數': count,              # 次數 (信賴度)
                    '勝率': win_rate,             # P
                    '賠率 (盈虧比)': payoff_ratio,  # b
                    '凱利值 (建議倉位)': kelly_pct,  # f
                    '平均獲利': avg_win_pct,
                    '平均虧損': avg_loss_pct,
                    '平均報酬': avg_ret,
                    '最大跌幅': min_ret
                }

            results.append(calc_stats_kelly(signal_trend, f"年線多 + {m}月續漲 (順勢)", m * 10 + 1))
            results.append(calc_stats_kelly(signal_pullback, f"年線多 + {m}月回檔 (低接)", m * 10 + 2))
            
        res_df = pd.DataFrame(results).sort_values(by='排序')
        
        # Base Rate
        base_returns = df_monthly['Next_Month_Return'].dropna()
        if not base_returns.empty:
            base_win_rate = base_returns[base_returns > 0].count() / len(base_returns)
        else:
            base_win_rate = 0

    # -----------------------------------------------------
    # 6. 顯示結果
    # -----------------------------------------------------

    st.success(f"📅 **回測區間**：{start_date} ~ {end_date} (共 {total_years:.1f} 年)")
    
    # --- KPI 卡片 ---
    # 這裡我們改找「凱利值」最高的策略，因為那代表「期望獲利能力最強」
    best_strategy = res_df.loc[res_df['凱利值 (建議倉位)'].idxmax()] if not res_df.empty else None
    
    col_kpi = st.columns(4)
    
    def simple_card(label, value, sub_value=""):
        return f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div style="font-size:0.8em; opacity:0.7; margin-top:4px">{sub_value}</div>
        </div>
        """

    with col_kpi[0]:
        st.markdown(simple_card("總交易月數", f"{len(df_monthly):,} 月"), unsafe_allow_html=True)
    with col_kpi[1]:
        st.markdown(simple_card("基準月勝率", f"{base_win_rate:.1%}"), unsafe_allow_html=True)
    with col_kpi[2]:
        if best_strategy is not None:
            st.markdown(simple_card("🔥 最佳凱利策略", f"{best_strategy['回測設定']}"), unsafe_allow_html=True)
    with col_kpi[3]:
        if best_strategy is not None:
            # 顯示半凱利比較安全
            k_val = best_strategy['凱利值 (建議倉位)']
            st.markdown(simple_card("建議下注比例", f"{k_val:.1%}", " (理論全凱利值)"), unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 30px'></div>", unsafe_allow_html=True)

    # --- 表格 (核心重點) ---
    if not res_df.empty:
        st.markdown("<h3>🎲 凱利公式詳細分析 (Kelly Criterion Analysis)</h3>", unsafe_allow_html=True)
        
        st.info("""
        **指標說明：**
        * **發生次數**：樣本數。次數太少 (如 < 10)，凱利值的參考價值極低。
        * **賠率 (盈虧比)**：平均賺 1 元的同時，會賠掉多少元。大於 1 代表賺多賠少。
        * **凱利值 (Kelly %)**：數學上計算出的「最佳資金運用比例」。若為負值，代表期望值為負，**絕對不該進場**。
        """)

        # 定義顯示欄位
        metrics_map = {
            "發生次數":      {"fmt": lambda x: f"{int(x):,}", "high_is_good": True},
            "勝率":          {"fmt": lambda x: f"{x:.2%}",   "high_is_good": True},
            "賠率 (盈虧比)":  {"fmt": lambda x: f"{x:.2f}",   "high_is_good": True},
            "平均獲利":      {"fmt": lambda x: f"<span style='color:#00CC96'>+{x:.2%}</span>", "high_is_good": True},
            "平均虧損":      {"fmt": lambda x: f"<span style='color:#EF553B'>-{x:.2%}</span>", "high_is_good": False}, # 數值越小(越接近0)越好，但這裡是絕對值
            "凱利值 (建議倉位)": {"fmt": lambda x: f"{x:.2%}",   "high_is_good": True},
        }

        html = '<table class="comparison-table"><thead><tr><th style="text-align:left; padding-left:16px;">指標</th>'
        
        # 1. 產生表頭
        for name in res_df['回測設定']:
            if "回檔" in name:
                html += f"<th style='color:#E65100; background-color:rgba(255,167,38,0.1)'>{name}</th>"
            else:
                html += f"<th style='color:#1B5E20; background-color:rgba(102,187,106,0.1)'>{name}</th>"
        html += "</tr></thead><tbody>"

        # 2. 產生內容
        for metric, config in metrics_map.items():
            html += f"<tr><td class='metric-name' style='padding-left:16px;'>{metric}</td>"
            
            vals = res_df[metric].values
            
            # 找出最佳值 (用於頒獎)
            if metric == "平均虧損": # 虧損要看誰比較小
                 best_val = min(vals)
            else:
                 best_val = max(vals)
            
            for i, val in enumerate(vals):
                display_text = config["fmt"](val)
                count = res_df['發生次數'].iloc[i]
                
                # --- 特殊邏輯 ---
                
                # 1. 凱利值特別顯示
                if metric == "凱利值 (建議倉位)":
                    if val > 0.5: # 凱利值 > 50% 
                        display_text = f"<span style='color:#00C853; font-weight:900; font-size:1.1em'>{display_text}</span>"
                    elif val > 0:
                        display_text = f"<span style='color:#00C853; font-weight:bold'>{display_text}</span>"
                    else:
                        display_text = f"<span style='color:#D32F2F; font-weight:bold'>不建議 ({display_text})</span>"
                
                # 2. 次數過少警示
                if count < 10 and metric == "凱利值 (建議倉位)":
                     display_text += " <span style='font-size:0.8em; color:gray'>(樣本不足)</span>"

                # 3. 冠軍邏輯
                is_winner = (val == best_val) and (metric != "發生次數") and (metric != "平均獲利") and (metric != "平均虧損")
                
                # 凱利值如果是負的，就算最大也不能給獎盃
                if metric == "凱利值 (建議倉位)" and val <= 0:
                    is_winner = False

                if is_winner:
                    display_text += " <span class='trophy-icon'>🏆</span>"
                    html += f"<td style='font-weight:bold; background-color:rgba(0,200,83,0.05);'>{display_text}</td>"
                else:
                    html += f"<td>{display_text}</td>"
            html += "</tr>"
            
        html += "</tbody></table>"
        st.write(html, unsafe_allow_html=True)
