# -*- coding: utf-8 -*-
"""
Weather Fetcher Module (2-Hour Resolution)
Handles batch weather API data retrieval and structures hourly data into 2-hour ride windows.
"""
import math
import requests

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates distance between two points in km using Haversine formula."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

WMO_CODES = {
    0: ("Clear sky", "☀️"),
    1: ("Mainly clear", "🌤️"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Fog", "🌫️"),
    48: ("Depositing rime fog", "🌫️"),
    51: ("Light drizzle", "🌦️"),
    53: ("Moderate drizzle", "🌦️"),
    55: ("Dense drizzle", "🌧️"),
    56: ("Light freezing drizzle", "🌨️"),
    57: ("Dense freezing drizzle", "🌨️"),
    61: ("Light rain", "🌦️"),
    63: ("Moderate rain", "🌧️"),
    65: ("Heavy rain", "🌧️"),
    66: ("Light freezing rain", "🌨️"),
    67: ("Heavy freezing rain", "🌨️"),
    71: ("Light snowfall", "🌨️"),
    73: ("Moderate snowfall", "🌨️"),
    75: ("Heavy snowfall", "❄️"),
    77: ("Snow grains", "❄️"),
    80: ("Light rain showers", "🌦️"),
    81: ("Moderate rain showers", "🌧️"),
    82: ("Violent rain showers", "⛈️"),
    85: ("Light snow showers", "🌨️"),
    86: ("Heavy snow showers", "❄️"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Thunderstorm with slight hail", "⛈️"),
    99: ("Thunderstorm with heavy hail", "⛈️")
}

TIME_WINDOWS = [
    ("08:00-10:00", 8),
    ("10:00-12:00", 10),
    ("12:00-14:00", 12),
    ("14:00-16:00", 14),
    ("16:00-18:00", 16),
    ("18:00-20:00", 18),
    ("20:00-22:00", 20)
]

def fetch_weather(regions: list) -> list:
    """Fetches raw weather forecast data for all regions in a single batch request."""
    lats = ",".join(str(r['lat']) for r in regions)
    lons = ",".join(str(r['lon']) for r in regions)
    
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lats}&longitude={lons}"
        "&past_days=7"
        "&forecast_days=4"
        "&hourly=precipitation,temperature_2m,relative_humidity_2m,snowfall,cloud_cover,weather_code"
        "&daily=weather_code"
        "&timezone=America/Vancouver"
    )
    
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    
    data = response.json()
    return data if isinstance(data, list) else [data]

def get_daily_history(times: list, precip: list, temp: list, humidity: list, 
                      snow: list, daily_codes: list, history_start_h: int = 0) -> list:
    """Aggregates the past 7 days of hourly weather into daily summaries."""
    past_days = []
    for d_idx in range(7):
        start_h = history_start_h + d_idx * 24
        end_h = history_start_h + (d_idx + 1) * 24
        
        day_date = times[start_h].split('T')[0]
        code_idx = d_idx + 1 if history_start_h == 24 else d_idx
        w_desc, w_emoji = WMO_CODES.get(daily_codes[code_idx], ("Unknown", "❓"))
        
        past_days.append({
            "date": day_date,
            "precipitation": sum(precip[start_h:end_h]),
            "snowfall": sum(snow[start_h:end_h]),
            "temp_max": max(temp[start_h:end_h]),
            "temp_min": min(temp[start_h:end_h]),
            "temp_mean": sum(temp[start_h:end_h]) / 24.0,
            "humidity_mean": sum(humidity[start_h:end_h]) / 24.0,
            "weather_emoji": w_emoji,
            "weather_desc": w_desc
        })
    return past_days

def get_today_so_far_weather(times: list, precip: list, temp: list, hourly_codes: list, now_idx: int, forecast_start_h: int = 168) -> dict:
    """Calculates weather metrics for today so far (midnight to now)."""
    num_hours = now_idx - forecast_start_h
    if num_hours <= 0:
        return None
    today_precip = sum(precip[forecast_start_h:now_idx])
    today_temp = sum(temp[forecast_start_h:now_idx]) / float(num_hours)
    from collections import Counter
    codes_so_far = hourly_codes[forecast_start_h:now_idx]
    most_common_code = Counter(codes_so_far).most_common(1)[0][0] if codes_so_far else 0
    w_desc, w_emoji = WMO_CODES.get(most_common_code, ("Clear sky", "☀️"))
    return {
        "date": times[forecast_start_h].split('T')[0],
        "precipitation": today_precip,
        "temp_mean": today_temp,
        "weather_emoji": w_emoji,
        "weather_desc": w_desc,
        "is_today_so_far": True,
        "hours_count": num_hours
    }

def create_2h_windows(d_idx: int, date_str: str, times: list, precip: list, temp: list, 
                      humidity: list, snow: list, cloud: list, hourly_codes: list, now_idx: int, forecast_start_h: int = 168) -> list:
    """Creates seven 2-hour windows between 8 AM and 10 PM for a specific forecast day."""
    day_start_h = forecast_start_h + d_idx * 24  # Forecast starts at forecast_start_h
    windows = []
    
    for w_idx, (label, start_hour) in enumerate(TIME_WINDOWS):
        h_idx = day_start_h + start_hour
        is_passed = (d_idx == 0 and h_idx + 2 <= now_idx)
        if is_passed:
            continue
            
        w_precip = sum(precip[h_idx:h_idx+2])
        w_snow = sum(snow[h_idx:h_idx+2])
        w_temp_mean = sum(temp[h_idx:h_idx+2]) / 2.0
        w_humidity_mean = sum(humidity[h_idx:h_idx+2]) / 2.0
        w_cloud_mean = sum(cloud[h_idx:h_idx+2]) / 2.0
        
        # Determine weather code from the first hour of window
        w_code = hourly_codes[h_idx]
        w_desc, w_emoji = WMO_CODES.get(w_code, ("Unknown", "❓"))
        
        windows.append({
            "window_index": w_idx,
            "time_window": label,
            "date": date_str,
            "precipitation": w_precip,
            "snowfall": w_snow,
            "temp_mean": w_temp_mean,
            "humidity_mean": w_humidity_mean,
            "cloud_cover_mean": w_cloud_mean,
            "weather_desc": w_desc,
            "weather_emoji": w_emoji,
            "weather_code": w_code,
            "is_passed": is_passed
        })
    return windows

def process_region_weather(region: dict, weather_data: dict) -> dict:
    """Aggregates raw weather data into history days and 2-hour forecast windows."""
    hourly = weather_data['hourly']
    daily = weather_data['daily']
    
    times = hourly['time']
    precip = hourly['precipitation']
    temp = hourly['temperature_2m']
    humidity = hourly['relative_humidity_2m']
    snow = hourly.get('snowfall', [0.0] * len(times))
    cloud = hourly.get('cloud_cover', [0.0] * len(times))
    hourly_codes = hourly.get('weather_code', [0] * len(times))
    
    # Calculate now_idx
    offset = weather_data.get('utc_offset_seconds', -25200)
    from datetime import datetime, timezone, timedelta
    utc_now = datetime.now(timezone.utc)
    vancouver_now = utc_now + timedelta(seconds=offset)
    
    is_after_8pm = vancouver_now.hour >= 20
    if is_after_8pm:
        history_start_h = 24
        forecast_start_h = 192
        vancouver_now = (vancouver_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        history_start_h = 0
        forecast_start_h = 168
        
    now_str = vancouver_now.strftime("%Y-%m-%dT%H:00")
        
    try:
        now_idx = times.index(now_str)
    except ValueError:
        now_idx = forecast_start_h
        
    past_days = get_daily_history(times, precip, temp, humidity, snow, daily['weather_code'], history_start_h)
    
    forecast_days_metadata = []
    forecast_windows = []
    
    forecast_days_limit = 3
    for i in range(forecast_days_limit):
        date_str = times[forecast_start_h + i * 24].split('T')[0]
        forecast_days_metadata.append({"day_index": i, "date": date_str})
        
        day_windows = create_2h_windows(
            i, date_str, times, precip, temp, humidity, snow, cloud, hourly_codes, now_idx, forecast_start_h
        )
        forecast_windows.append(day_windows)
        
    station_lat = weather_data.get('latitude', region['lat'])
    station_lon = weather_data.get('longitude', region['lon'])
    distance_km = calculate_distance(region['lat'], region['lon'], station_lat, station_lon)
    
    hourly_raw_dict = {
        "time": times,
        "precipitation": precip,
        "temperature_2m": temp,
        "relative_humidity_2m": humidity,
        "snowfall": snow,
        "cloud_cover": cloud,
        "weather_code": hourly_codes,
        "utc_offset_seconds": offset
    }
    
    today_so_far = get_today_so_far_weather(times, precip, temp, hourly_codes, now_idx, forecast_start_h)
    log_aggregated_weather(region['name'], past_days, forecast_days_metadata, forecast_windows, hourly_raw_dict, forecast_start_h)
        
    return {
        "name": region['name'],
        "region": region.get('region', 'north shore'),
        "drainage_index": region['drainage_index'],
        "description": region['description'],
        "maps_link": region['maps_link'],
        "past_days": past_days,
        "today_so_far": today_so_far,
        "forecast_days_meta": forecast_days_metadata,
        "forecast_windows": forecast_windows,  # List of lists (4 days, each 7 windows)
        "hourly_raw": hourly_raw_dict,
        "station_lat": station_lat,
        "station_lon": station_lon,
        "distance_to_station_km": distance_km
    }

def log_aggregated_weather(region_name: str, past_days: list, forecast_days_metadata: list, forecast_windows: list, hourly_raw: dict, forecast_start_h: int = 168) -> None:
    """Logs detailed aggregated weather data for a region."""
    from datetime import datetime, timezone, timedelta
    print(f"\n[Weather Process] Region: {region_name}")
    print("  Recent 7x24 hours history:")
    for day in past_days:
        print(f"    - {day['date']}: Rain: {day['precipitation']:.1f}mm, Temp Mean: {day['temp_mean']:.1f}°C, Weather: {day['weather_desc']} {day['weather_emoji']}")
    
    # Calculate today so far
    times = hourly_raw.get('time', [])
    offset = hourly_raw.get('utc_offset_seconds', -25200)
    utc_now = datetime.now(timezone.utc)
    vancouver_now = utc_now + timedelta(seconds=offset)
    
    is_after_8pm = vancouver_now.hour >= 20
    if is_after_8pm:
        vancouver_now = (vancouver_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    now_str = vancouver_now.strftime("%Y-%m-%dT%H:00")
    try:
        now_idx = times.index(now_str)
    except ValueError:
        now_idx = forecast_start_h
        
    num_hours = now_idx - forecast_start_h
    if num_hours > 0:
        today_precip = sum(hourly_raw['precipitation'][forecast_start_h:now_idx])
        today_temp = sum(hourly_raw['temperature_2m'][forecast_start_h:now_idx]) / float(num_hours)
        print(f"    - Today So Far (midnight to now, {num_hours} hours): Rain: {today_precip:.1f}mm, Temp Mean: {today_temp:.1f}°C")
    else:
        print("    - Today So Far (midnight to now): 0 hours elapsed yet.")

    print("  Next 3 Days Forecast Windows:")
    for d_idx, day_windows in enumerate(forecast_windows):
        day_date = forecast_days_metadata[d_idx]["date"]
        active_windows = [w for w in day_windows if not w.get('is_passed')]
        if active_windows:
            day_precip = sum(w['precipitation'] for w in active_windows)
            day_temp_avg = sum(w['temp_mean'] for w in active_windows) / len(active_windows)
            desc = f"Total Window Precip (remaining): {day_precip:.1f}mm" if d_idx == 0 else f"Total Window Precip: {day_precip:.1f}mm"
            print(f"    - Day {d_idx} ({day_date}): {desc}, Temp Mean: {day_temp_avg:.1f}°C")
        else:
            print(f"    - Day {d_idx} ({day_date}): No remaining forecast windows today.")
