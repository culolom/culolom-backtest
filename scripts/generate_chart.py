import os
import pandas as pd
import plotly.graph_objects as go

def calculate_and_generate_report():
    # 1. 自動定位路徑：取得目前腳本所在位置，並推算專案根目錄與 data 資料夾
    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(current_dir)  # 專案根目錄
    data_dir = os.path.join(base_dir, 'data')
    
    # 定義 0050.TW.csv 的絕對路徑
    csv_path = os.path.join(data_dir, '0050.TW.csv')
    
    if not os.path.exists(csv_path):
        print(f"錯誤：找不到 CSV 檔案，請確認路徑是否存在: {csv_path}")
        return

    # 2. 讀取資料與資料清洗
    df_0050 = pd.read_csv(csv_path)
    
    # 確保欄位名稱正確（處理大小寫或前後空格）
    df_0050.columns = df_0050.columns.str.strip()
    
    # 將 Date 轉為日期格式並設為索引
    df_0050['Date'] = pd.to_datetime(df_0050['Date'])
    df_0050.set_index('Date', inplace=True)
    df_0050.sort_index(inplace=True)

    # 3. 計算 4 種 0050正2 策略累積報酬率
    # 備註：以下為示範邏輯，您可以自由替換成您個人開發的真實回測公式
    df_results = pd.DataFrame(index=df_0050.index)
    
    # 基準：0050 買入持有報酬率 (%)
    df_results['基準 (0050買入持有)'] = (df_0050['Close'] / df_0050['Close'].iloc[0] - 1) * 100
    
    # 策略 1：簡單正2槓桿模擬 (0050報酬率的 2 倍)
    df_results['策略一：定期定額正2'] = df_results['基準 (0050買入持有)'] * 2.0
    
    # 策略 2：均線突破加碼策略
    df_results['策略二：均線不破正2'] = df_results['基準 (0050買入持有)'] * 2.2 + 5.5
    
    # 策略 3：KD低檔區間動態調整
    df_results['策略三：KD低檔加碼正2'] = df_results['基準 (0050買入持有)'] * 1.8 - 3.2
    
    # 策略 4：強勢動能追蹤策略
    df_results['策略四：動能追蹤正2'] = df_results['基準 (0050買入持有)'] * 2.5 - 12.0
    
    # 四捨五入到小數點後兩位
    df_results = df_results.round(2)
    latest_date = df_results.index[-1].strftime('%Y-%m-%d')

    # 4. 使用 Plotly 建立前端互動式走勢圖
    fig = go.Figure()
    colors = ['#7f8c8d', '#2ecc71', '#3498db', '#9b59b6', '#e74c3c']

    for i, col in enumerate(df_results.columns):
        fig.add_trace(go.Scatter(
            x=df_results.index, 
            y=df_results[col], 
            mode='lines', 
            name=col,
            line=dict(width=2, color=colors[i]),
            hovertemplate='%{x}<br>%{text}: %{y}%',
            text=[col] * len(df_results)
        ))

    fig.update_layout(
        title=f"0050 正2 四種操作策略累積報酬率比較 (最後更新: {latest_date})",
        xaxis_title="日期",
        yaxis_title="累積報酬率 (%)",
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=70, b=20),
        height=450
    )

    # 5. 建立響應式 HTML 數據表格
    latest_data = df_results.iloc[-1]
    table_html = f"""
    <div style="overflow-x:auto; margin-top: 25px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
        <table style="width:100%; border-collapse: collapse; text-align: left; background: #ffffff; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border-radius: 8px; overflow: hidden;">
            <thead>
                <tr style="background-color: #2c3e50; color: #ffffff;">
                    <th style="padding: 14px 16px; font-weight: 600;">策略模型名稱</th>
                    <th style="padding: 14px 16px; font-weight: 600; text-align: right;">最新累積報酬率 (至 {latest_date})</th>
                </tr>
            </thead>
            <tbody>
    """
    for idx, val in latest_data.items():
        # 根據正負報酬自動切換顏色 (正紅、負綠)
        color_style = "color: #d63031; font-weight: 700;" if val >= 0 else "color: #2ed573; font-weight: 700;"
        table_html += f"""
                <tr style="border-bottom: 1px solid #f1f2f6; background-color: #ffffff;">
                    <td style="padding: 14px 16px; color: #2f3542;">{idx}</td>
                    <td style="padding: 14px 16px; text-align: right; {color_style}">{val:+.2f}%</td>
                </tr>
        """
    table_html += """
            </tbody>
        </table>
    </div>
    """

    # 6. 整合圖表與表格，組裝成完整 HTML 網頁
    chart_html = fig.to_html(include_plotlyjs='cdn', full_html=False)
    
    full_page_html = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>0050正2策略回測績效比較表</title>
        <style>
            body {{ 
                margin: 0; 
                padding: 15px; 
                background-color: #f8f9fa;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }}
            .container {{
                max-width: 1000px;
                margin: 0 auto;
                background: #ffffff;
                padding: 20px;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            }}
        </style>
    </head>
    <body>
        <div class="container">
            {chart_html}
            {table_html}
        </div>
    </body>
    </html>
    """

    # 7. 輸出 HTML 到根目錄的 dist 資料夾下
    dist_dir = os.path.join(base_dir, 'dist')
    os.makedirs(dist_dir, exist_ok=True)
    
    output_path = os.path.join(dist_dir, 'index.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_page_html)
        
    print(f"成功！報告網頁已生成至: {output_path}")

if __name__ == '__main__':
    calculate_and_generate_report()
