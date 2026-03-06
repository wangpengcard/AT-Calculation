import os
import requests
import json
from datetime import datetime, timedelta

# 从 GitHub Actions 的环境变量读取配置
LAT = os.getenv("LAT")
LON = os.getenv("LON")
YEARS = os.getenv("YEARS").split(',')  # 支持多个年份，如 "2024,2025"
API_KEY = os.getenv("OWM_API_KEY")

def get_weather_data(lat, lon, date):
    url = f"https://api.openweathermap.org/data/3.0/onecall/day_summary?lat={lat}_&lon={lon}&date={date}&tz=+08:00&appid={API_KEY}&units=metric"
    try:
        response = requests.get(url)
        return response.json() if response.status_code == 200 else None
    except Exception:
        return None

def find_growth_period_limits(daily_data):
    """
    使用五日滑动平均法确定 10°C 的起始日和终止日
    daily_data: list of {'date': datetime, 'avg_t': float}
    """
    start_limit = None
    end_limit = None
    n = len(daily_data)
    
    # 1. 寻找起始日 (从前往后)
    for i in range(n - 4):
        window = [daily_data[j]['avg_t'] for j in range(i, i + 5)]
        if all(t >= 10 for t in window):
            # 找到这5天中第一个 >= 10°C 的日期
            for j in range(i, i + 5):
                if daily_data[j]['avg_t'] >= 10:
                    start_limit = daily_data[j]['date']
                    break
            break

    # 2. 寻找终止日 (从后往前)
    for i in range(n - 1, 3, -1):
        window = [daily_data[j]['avg_t'] for j in range(i - 4, i + 1)]
        if all(t >= 10 for t in window):
            # 找到这5天中最后一个 >= 10°C 的日期
            for j in range(i, i - 5, -1):
                if daily_data[j]['avg_t'] >= 10:
                    end_limit = daily_data[j]['date']
                    break
            break
            
    return start_limit, end_limit

results = {}

for year in YEARS:
    print(f"正在处理 {year} 年数据...")
    
    # 1. 预获取数据：范围扩大以覆盖可能的生长期（4月至10月）
    full_season_data = []
    current_date = datetime.strptime(f"{year}-04-01", "%Y-%m-%d")
    end_fetch_date = datetime.strptime(f"{year}-10-30", "%Y-%m-%d")
    
    while current_date <= end_fetch_date:
        date_str = current_date.strftime("%Y-%m-%d")
        data = get_weather_data(LAT, LON, date_str)
        if data:
            t = data['temperature']
            # 6点采样均温
            temps_list = [t['min'], t['max'], t['afternoon'], t['night'], t['evening'], t['morning']]
            avg_t = sum(temps_list) / 6
            full_season_data.append({
                "date": current_date,
                "avg_t": avg_t,
                "rain": data.get('precipitation', {}).get('total', 0)
            })
        current_date += timedelta(days=1)

    # 2. 判定 10°C 生长期界限
    start_limit, end_limit = find_growth_period_limits(full_season_data)
    
    # 3. 计算积温
    year_data = {"dates": [], "active_accum": [], "effective_accum": [], "monthly_rain": {}, "info": {}}
    active_sum = 0
    effective_sum = 0
    
    # 记录判定结果
    year_data["info"] = {
        "start_date": start_limit.strftime("%Y-%m-%d") if start_limit else "未达标",
        "end_date": end_limit.strftime("%Y-%m-%d") if end_limit else "未达标"
    }

    n = len(full_season_data)
    for i in range(n):
        item = full_season_data[i]
        date_obj = item["date"]
        avg_t = item["avg_t"]
        
        # 核心逻辑：必须在 10°C 判定的生长期内
        is_growing = (start_limit and end_limit and start_limit <= date_obj <= end_limit)
        
        if is_growing:
            # A. 活动积温：生长期内日均温 >= 10°C 累加
            if avg_t >= 10:
                active_sum += avg_t
            
            # B. 有效积温：生长期内，且从当日开始连续5天日均温 > 0°C
            is_eff_valid = False
            if i <= n - 5:
                window_0 = [full_season_data[j]['avg_t'] for j in range(i, i + 5)]
                if all(t > 0 for t in window_0):
                    is_eff_valid = True
            
            if is_eff_valid:
                # 累加 (日均温 - 0°C)，确保不加负数
                effective_sum += max(0, avg_t)
        
        # 降雨量统计（按月）
        month_key = date_obj.strftime("%Y-%m")
        year_data["monthly_rain"][month_key] = year_data["monthly_rain"].get(month_key, 0) + item["rain"]
        
        # 记录每日趋势
        year_data["dates"].append(date_obj.strftime("%Y-%m-%d"))
        year_data["active_accum"].append(round(active_sum, 2))
        year_data["effective_accum"].append(round(effective_sum, 2))
    
    results[year] = year_data

# 写入 JSON
with open("data.json", "w") as f:
    json.dump(results, f)

print("计算完成，数据已写入 data.json")
