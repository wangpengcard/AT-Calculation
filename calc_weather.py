import os
import requests
import json
import pandas as pd
from datetime import datetime, timedelta

# 从 GitHub Actions 的环境变量读取配置
LAT = os.getenv("LAT")
LON = os.getenv("LON")
YEARS = os.getenv("YEARS").split(',') 
API_KEY = os.getenv("OWM_API_KEY")

def get_weather_data(lat, lon, date):
    url = f"https://api.openweathermap.org/data/3.0/onecall/day_summary?lat={lat}&lon={lon}&date={date}&tz=+08:00&appid={API_KEY}&units=metric"
    try:
        response = requests.get(url, timeout=10)
        return response.json() if response.status_code == 200 else None
    except:
        return None

results = {}

for year in YEARS:
    raw_daily_list = []
    # 【修改】固定 X 轴范围：4月1日 到 9月30日
    start_date = datetime.strptime(f"{year}-04-01", "%Y-%m-%d")
    end_date = datetime.strptime(f"{year}-09-30", "%Y-%m-%d")
    
    print(f"正在获取 {year} 年天气数据 (04-01 至 09-30)...")
    
    current_date = start_date
    monthly_rain = {}

    # 第一阶段：获取原始每日增量数据
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        data = get_weather_data(LAT, LON, date_str)
        
        if data:
            t = data['temperature']
            # 取 6 个时间点的平均值作为日均温
            temps = [t['min'], t['max'], t['afternoon'], t['night'], t['evening'], t['morning']]
            avg_t = sum(temps) / 6
            
            # 1. 活动积温原始增量 (日均温 >= 10)
            act_inc = avg_t if avg_t >= 10 else 0.0
            
            # 2. 有效积温原始增量 (减去基准温10度，上限30度)
            eff_inc = sum([max(0, min(temp, 30) - 10) for temp in temps]) / 6
            
            # 3. 基础降雨量累计
            month_key = current_date.strftime("%Y-%m")
            rain = data.get('precipitation', {}).get('total', 0)
            monthly_rain[month_key] = monthly_rain.get(month_key, 0) + rain
            
            raw_daily_list.append({
                "date": current_date,
                "month_key": month_key,
                "act_inc": act_inc,
                "eff_inc": eff_inc
            })
            
        current_date += timedelta(days=1)
    
    # 第二阶段：滑动判定、累计值计算及月度统计
    if raw_daily_list:
        df = pd.DataFrame(raw_daily_list)
        year_results = {
            "dates": [d.strftime("%m-%d") for d in df['date']], # 简短日期格式
            "active_accum": [],
            "effective_accum": [],
            "monthly_active": {},   # 新增：月度活动积温柱状图数据
            "monthly_effective": {}, # 新增：月度有效积温柱状图数据
            "monthly_rain": {k: int(round(v, 0)) for k, v in monthly_rain.items()}
        }
        
        # 配置独立处理规则
        configs = [
            {'prefix': 'act', 'threshold': 10.0, 'res_key': 'active_accum', 'mon_key': 'monthly_active'},
            {'prefix': 'eff', 'threshold': 0.0, 'res_key': 'effective_accum', 'mon_key': 'monthly_effective'}
        ]
        
        for cfg in configs:
            inc_col = f"{cfg['prefix']}_inc"
            vals = df[inc_col].values
            dts = df['date'].values
            threshold = cfg['threshold']
            
            # 5日滑动判定逻辑
            start_dt, end_dt = None, None
            # 起始判定
            for i in range(len(vals) - 4):
                if all(v >= threshold and v > 0 for v in vals[i : i + 5]):
                    start_dt = dts[i]
                    break
            # 终止判定
            for i in range(len(vals) - 1, 3, -1):
                if all(v >= threshold and v > 0 for v in vals[i - 4 : i + 1]):
                    end_dt = dts[i]
                    break
            
            # 执行累加与月度聚合
            current_accum = 0.0
            accum_series = []
            monthly_totals = {}
            
            for j in range(len(df)):
                this_dt = dts[j]
                this_val = vals[j]
                this_month = df.iloc[j]['month_key']
                
                # 初始化月度字典键
                if this_month not in monthly_totals:
                    monthly_totals[this_month] = 0.0

                if start_dt and end_dt and start_dt <= this_dt <= end_dt:
                    current_accum += this_val
                    monthly_totals[this_month] += this_val # 记录月度有效增量
                elif end_dt and this_dt > end_dt:
                    pass # 超过生长期不再累加，保持最大值
                else:
                    current_accum = 0.0 # 未进入生长期归零
                
                accum_series.append(round(current_accum, 2))
            
            year_results[cfg['res_key']] = accum_series
            year_results[cfg['mon_key']] = {k: round(v, 1) for k, v in monthly_totals.items()}
            
        results[year] = year_results

# 第三阶段：保存结果
with open("data.json", "w") as f:
    json.dump(results, f)

print(f"✅ 计算完成：4月-9月 积温与降雨数据已生成。")
