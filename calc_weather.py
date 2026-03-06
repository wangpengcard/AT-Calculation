import os
import requests
import json
from datetime import datetime, timedelta

# 从 GitHub Actions 的环境变量读取配置
LAT = os.getenv("LAT")
LON = os.getenv("LON")
YEARS = os.getenv("YEARS", "2024").split(',')
API_KEY = os.getenv("OWM_API_KEY")

def get_weather_data(lat, lon, date):
    # 修正了 lat 后的下划线错误
    url = f"https://api.openweathermap.org/data/3.0/onecall/day_summary?lat={lat}&lon={lon}&date={date}&tz=+08:00&appid={API_KEY}&units=metric"
    try:
        response = requests.get(url)
        return response.json() if response.status_code == 200 else None
    except Exception:
        return None

def find_growth_period_limits(daily_data):
    """
    五日滑动平均法逻辑：
    起始日：第一次连续5天 >= 10℃ 窗口中的第一天
    终止日：最后一次连续5天 >= 10℃ 窗口中的最后一天
    """
    start_limit = None
    end_limit = None
    n = len(daily_data)
    
    # 1. 寻找起始日 (从前往后)
    for i in range(n - 4):
        window = [daily_data[j]['avg_t'] for j in range(i, i + 5)]
        if all(t >= 10 for t in window):
            start_limit = daily_data[i]['date']
            break

    # 2. 寻找终止日 (从后往前)
    for i in range(n - 1, 3, -1):
        window = [daily_data[j]['avg_t'] for j in range(i - 4, i + 1)]
        if all(t >= 10 for t in window):
            end_limit = daily_data[i]['date']
            break
            
    return start_limit, end_limit

results = {}

for year in YEARS:
    print(f"--- 正在处理 {year} 年数据 ---")
    full_season_data = []
    # 预取范围：3月1日 - 11月30日
    current_date = datetime.strptime(f"{year}-03-01", "%Y-%m-%d")
    end_fetch_date = datetime.strptime(f"{year}-11-30", "%Y-%m-%d")
    
    # 第一步：数据采集
    while current_date <= end_fetch_date:
        date_str = current_date.strftime("%Y-%m-%d")
        data = get_weather_data(LAT, LON, date_str)
        if data:
            t = data['temperature']
            # 6点采样均温逻辑
            temps_list = [t['min'], t['max'], t['afternoon'], t['night'], t['evening'], t['morning']]
            avg_t = sum(temps_list) / 6
            full_season_data.append({
                "date": current_date,
                "avg_t": avg_t,
                "rain": data.get('precipitation', {}).get('total', 0)
            })
        current_date += timedelta(days=1)

    # 第二步：判定生长期界限
    start_limit, end_limit = find_growth_period_limits(full_season_data)
    
    # 第三步：计算积温
    year_data = {"dates": [], "active_accum": [], "effective_accum": [], "monthly_rain": {}, "info": {}}
    active_sum = 0
    effective_sum = 0
    
    # 存储判定结果供前端展示
    year_data["info"] = {
        "start_date": start_limit.strftime("%Y-%m-%d") if start_limit else "未达标",
        "end_date": end_limit.strftime("%Y-%m-%d") if end_limit else "未达标"
    }

    n = len(full_season_data)
    for i in range(n):
        item = full_season_data[i]
        date_obj = item["date"]
        avg_t = item["avg_t"]
        
        # 判定：是否在 10°C 确定的生长期区间内
        in_season = (start_limit and end_limit and start_limit <= date_obj <= end_limit)
        
        if in_season:
            # 1. 活动积温：区间内且日均温 >= 10
            if avg_t >= 10:
                active_sum += avg_t
            
            # 2. 有效积温：区间内且当日开始连续5天 > 0
            is_eff_valid = False
            if i <= n - 5:
                window_0 = [full_season_data[j]['avg_t'] for j in range(i, i + 5)]
                if all(t > 0 for t in window_0):
                    is_eff_valid = True
            
            if is_eff_valid:
                effective_sum += max(0, avg_t)
        
        # 无论是否在生长期，都记录日期和降雨量，但在生长期外积温增量为 0
        month_key = date_obj.strftime("%Y-%m")
        year_data["monthly_rain"][month_key] = year_data["monthly_rain"].get(month_key, 0) + item["rain"]
        year_data["dates"].append(date_obj.strftime("%Y-%m-%d"))
        year_data["active_accum"].append(round(active_sum, 2))
        year_data["effective_accum"].append(round(effective_sum, 2))
    
    results[year] = year_data

# 写入文件
with open("data.json", "w") as f:
    json.dump(results, f)

print(f"成功导出！{year}年有效生长期：{year_data['info']['start_date']} 至 {year_data['info']['end_date']}")
