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
    # 固定 X 轴范围：3月1日 到 10月31日
    start_date = datetime.strptime(f"{year}-03-01", "%Y-%m-%d")
    end_date = datetime.strptime(f"{year}-10-31", "%Y-%m-%d")
    
    print(f"正在获取 {year} 年天气数据 (03-01 至 10-31)...")
    
    current_date = start_date
    monthly_rain = {}

    # 第一阶段：获取原始每日增量
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        data = get_weather_data(LAT, LON, date_str)
        
        if data:
            t = data['temperature']
            temps = [t['min'], t['max'], t['afternoon'], t['night'], t['evening'], t['morning']]
            avg_t = sum(temps) / 6
            
            # 1. 活动积温增量：日均温 >= 10 计入
            act_inc = avg_t if avg_t >= 10 else 0.0
            
            # 2. 有效积温增量：每点减10，锁定在 0-20 度区间
            eff_inc = sum([max(0, min(temp, 30) - 10) for temp in temps]) / 6
            
            # 3. 降雨量统计
            month_key = current_date.strftime("%Y-%m")
            rain = data.get('precipitation', {}).get('total', 0)
            monthly_rain[month_key] = monthly_rain.get(month_key, 0) + rain
            
            raw_daily_list.append({
                "date": current_date,
                "act_inc": act_inc,
                "eff_inc": eff_inc
            })
            
        current_date += timedelta(days=1)
    
    # 第二阶段：5日滑动判定及累加
    if raw_daily_list:
        df = pd.DataFrame(raw_daily_list)
        year_results = {
            "dates": [d.strftime("%Y-%m-%d") for d in df['date']],
            "active_accum": [],
            "effective_accum": [],
            "monthly_rain": monthly_rain
        }
        
        # 独立处理 act (阈值10) 和 eff (阈值0)
        configs = [
            {'prefix': 'act', 'threshold': 10.0},
            {'prefix': 'eff', 'threshold': 0.0}
        ]
        
        for cfg in configs:
            prefix = cfg['prefix']
            threshold = cfg['threshold']
            
            inc_col = f"{prefix}_inc"
            vals = df[inc_col].values
            dts = df['date'].values
            
            # 判定起始日 (连续5天满足阈值)
            start_dt = None
            for i in range(len(vals) - 4):
                if all(v > 0 and v >= threshold for v in vals[i : i + 5]):
                    start_dt = dts[i]
                    break
            
            # 判定终止日 (最后一次连续5天满足阈值)
            end_dt = None
            for i in range(len(vals) - 1, 3, -1):
                if all(v > 0 and v >= threshold for v in vals[i - 4 : i + 1]):
                    end_dt = dts[i]
                    break
            
            # 执行累加
            current_accum = 0.0
            accum_series = []
            for j in range(len(df)):
                this_dt = dts[j]
                if start_dt and end_dt and start_dt <= this_dt <= end_dt:
                    current_accum += vals[j]
                elif end_dt and this_dt > end_dt:
                    pass # 冻结数值
                else:
                    current_accum = 0.0 # 起始前归零
                
                accum_series.append(round(current_accum, 2))
            
            res_key = "active_accum" if prefix == 'act' else "effective_accum"
            year_results[res_key] = accum_series
        year_results["monthly_rain"] = {k: int(round(v, 0)) for k, v in monthly_rain.items()}    
        results[year] = year_results

# 第三阶段：保存结果
with open("data.json", "w") as f:
    json.dump(results, f)

print("✅ 修改完成：活动积温(>=10)与有效积温(>0)已按独立滑动规则累加。")
