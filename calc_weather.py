import os
import requests
import json
from datetime import datetime, timedelta

# 从 GitHub Actions 的环境变量读取配置
LAT = os.getenv("LAT")
LON = os.getenv("LON")
YEARS = os.getenv("YEARS").split(',')  # 支持多个年份，如 "2022,2023"
API_KEY = os.getenv("OWM_API_KEY")

def get_weather_data(lat, lon, date):
    url = f"https://api.openweathermap.org/data/3.0/onecall/day_summary?lat={lat}&lon={lon}&date={date}&tz=+08:00&appid={API_KEY}&units=metric"
    response = requests.get(url)
    return response.json() if response.status_code == 200 else None

results = {}

for year in YEARS:
    year_data = {"dates": [], "active_accum": [], "effective_accum": [], "monthly_rain": {}}
    active_sum = 0
    effective_sum = 0
    
    start_date = datetime.strptime(f"{year}-04-01", "%Y-%m-%d")
    end_date = datetime.strptime(f"{year}-09-30", "%Y-%m-%d")
    
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        data = get_weather_data(LAT, LON, date_str)
        
        if data:
            t = data['temperature']
            # 6点采样值
            temps = [t['min'], t['max'], t['afternoon'], t['night'], t['evening'], t['morning']]
            
            # 1. 活动积温计算
            avg_t = sum(temps) / 6
            active_sum += avg_t if avg_t >= 10 else 0
            
            # 2. 有效积温计算 (每点减10, 范围0-20, 因为上限30-10=20)
            daily_eff = sum([max(0, min(temp, 30) - 10) for temp in temps]) / 6
            effective_sum += daily_eff
            
            # 3. 降雨量按月累加
            month_key = current_date.strftime("%Y-%m")
            rain = data.get('precipitation', {}).get('total', 0)
            year_data["monthly_rain"][month_key] = year_data["monthly_rain"].get(month_key, 0) + rain
            
            year_data["dates"].append(date_str)
            year_data["active_accum"].append(round(active_sum, 2))
            year_data["effective_accum"].append(round(effective_sum, 2))
            
        current_date += timedelta(days=1)
    
    results[year] = year_data

# 将结果写入 JSON 供前端读取
with open("data.json", "w") as f:
    json.dump(results, f)