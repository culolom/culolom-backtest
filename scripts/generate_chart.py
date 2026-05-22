import os
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

def calculate_period_returns():
    # 1. 檔案與路徑設定
    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(current_dir)
    data_dir = os.path.join(base_dir, 'data')
    
    # 目標比較的五檔 ETF
    symbols = ['0050.TW', '00631L.TW', '00675L.TW', '00663L.TW', '00685L.TW']
    
    # 儲存所有 ETF 的完整收盤價資料，用來畫 5 年走勢圖
    close_trends = {}
    
    # 儲存各期間報酬率結果
    period_performance = {}

    # 2. 依序讀取與計算每檔 ETF
    for sym in symbols:
        csv_path = os.path.join(data_dir, f"{sym}.csv")
        if not os.path.exists(csv_path):
            print(f"警告：找不到 {sym}.csv，跳過此檔案。")
            continue
            
        df = pd.read_csv(csv_path)
        df.columns = df.columns.str.strip()
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        df.sort_index(inplace=True)
        
        # 取得最新一筆資料的日期與價格
        latest_date = df.index[-1]
        latest_price = df['Close'].iloc[-1]
        
        # 儲存收盤價供後續畫圖使用
        close_trends[sym] = df['Close']
        
        # 3. 定義各區間的基準日期 (精準回推)
        intervals = {
            '近一週': latest_date - pd.Timedelta(weeks=1),
            '近一月': latest_date - pd.DateOffset(months=1),
            '近三月': latest_date - pd.DateOffset(months=3),
            '今年以來': datetime(latest_date.year, 1, 1),
            '近六月': latest_date - pd.DateOffset(months=6),
            '近一年': latest_date - pd.DateOffset(years=1),
            '近兩年': latest_date - pd.DateOffset(years=2),
            '近三年': latest_date - pd.DateOffset(years=3),
            '近五年': latest_date - pd.DateOffset(years=5)
        }
        
        sym_returns = {}
        # 4. 計算每個區間的報酬率
        for period_name, target_date in intervals.items():
            # 尋找最接近目標日期的實際交易日資料 (asof)
            try:
                # asof 會回傳該日期或該日期前最近的資料索引
                available_date = df.index[df.index.get_indexer([target_date], method='asof')[0]]
                base_price = df.loc[available_date, 'Close']
                
                # 若取出來的基推價格為多個，取第一個值
                if isinstance(base_price, pd.Series):
                    base_price = base_price.iloc[0]
                    
                ret = ((latest_price / base_price) - 1) * 100
                sym_returns[period_name] = round(ret, 2)
            except Exception as e:
                sym_returns[period_name] = "N/A" # 資料歷史不夠長時顯示 N/A
                
        period_performance[sym.replace('.TW', '')] = sym_returns

    # 建立期間比較表 DataFrame
    df_perf = pd.DataFrame(period_performance)
    
    # 5. 處理 5 年走勢對比資料 (將基準日歸一化為 100% 或從 0% 開始累積)
    df_trends = pd.DataFrame(close_trends)
    # 取最後一筆日期往前推 5 年的所有資料
    five_years_ago = df_trends.index[-1] - pd.DateOffset(years=5)
    df_trends_5y = df_trends.loc[five_years_ago:]
    
    # 計算 5 年累積報酬率走勢 (每一格除以該欄位的第一個有效價格)
    df_cum_returns = (df_trends_5y / df_trends_5y.bfill().iloc[0] - 1) * 100
    df_cum_returns = df_cum_returns.round(2)
    
    latest_date_str = df_trends.index[-1].strftime('%Y-%m-%d')
    
    # 6. 使用 Plotly 繪製 5 年累積走勢比較圖
    fig = go.Figure()
    # 經典配色
    colors = {
        '0050.TW': '#7f8c8d',    # 灰色基準
        '00631L.TW': '#e74c3c',  # 元大正2-紅色
        '00675L.TW': '#3498db',  # 富邦正2-藍色
        '00663L.TW': '#2ecc71',  # 國泰正2-綠色
        '00685L.TW': '#f1c40f'   # 群益正2-黃色
    }
    
    for col in df_cum_returns.columns:
        display_name = col.replace('.TW', '')
        fig.add_trace(go.Scatter(
            x=df_cum_returns.index,
            y=df_cum_returns[col],
            mode='lines',
            name=display_name,
            line=dict(width=2, color=colors.get(col, '#000000')),
            hovertemplate='%{x}<br><b>' + display_name + '</b>: %{y}%',
        ))
        
    fig.update_layout(
        title=f"0050 與四大正2 ETF 近五年累積報酬率走勢對比 (至 {latest_date_str})",
        xaxis_title="日期",
        yaxis_title="累積報酬率 (%)",
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=70, b=20),
        height=480
    )

    # 7. 建立 WordPress 橫向比較網頁表格 HTML
    # 欄位順序：期間 | 0050 | 00631L | 00675L | 00663L | 00685L
    columns_order = ['0050', '00631L', '00675L', '00663L', '00685L']
    periods_order = ['近一週', '近一月', '近三月', '今年以來', '近六月', '近一年', '近兩年', '近三年', '近五年']
    
    table_html = f"""
    <div style="overflow-x:auto; margin-top: 30px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
        <table style="width:100%; border-collapse: collapse; text-align: center; background: #ffffff; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border-radius: 8px; overflow: hidden; min-width: 600px;">
            <thead>
                <tr style="background-color: #2c3e50; color: #ffffff; font-size: 15px;">
                    <th style="padding: 14px; text-align: left; font-weight: 600;">期間 / 績效</th>
    """
    for col in columns_order:
        table_html += f'<th style="padding: 14px; font-weight: 600;">{col}</th>'
    table_html += "</tr></thead><tbody>"
    
    for period in periods_order:
        table_html += f'<tr style="border-bottom: 1px solid #f1f2f6; font-size: 14px;">'
        table_html += f'<td style="padding: 12px; text-align: left; font-weight: 600; background-color: #fcfcfc; color: #34495e;">{period}</td>'
        
        for col in columns_order:
            val = df_perf.loc[period, col]
            if val == "N/A":
                table_html += f'<td style="padding: 12px; color: #95a5a6;">-</td>'
            else:
                # 根據正負號決定紅綠顏色
                color_style = "color: #d63031; font-weight: 600;" if val >= 0 else "color: #2ed573; font-weight: 600;"
                table_html += f'<td style="padding: 12px; {color_style}">{val:+.2f}%</td>'
        table_html += '</tr>'
        
    table_html += """
            </tbody>
        </table>
    </div>
    """

    # 8. 整合輸出 HTML 網頁
    chart_html = fig.to_html(include_plotlyjs='cdn', full_html=False)
    
    full_page_html = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>0050正2績效比較表</title>
        <style>
            body {{ margin: 0; padding: 10px; background-color: #ffffff; }}
            .report-container {{ max-width: 1000px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <div class="report-container">
            {table_html}
            <div style="margin-top: 25px;">
                {chart_html}
            </div>
        </div>
    </body>
    </html>
    """

    # 輸出至根目錄下的 dist/index.html
    os.makedirs(os.path.join(base_dir, 'dist'), exist_ok=True)
    output_path = os.path.join(base_dir, 'dist', 'index.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_page_html)
        
    print(f"成功更新期間績效對比報告：{output_path}")

if __name__ == '__main__':
    calculate_period_returns()
