# -*- coding: utf-8 -*-
"""
Gemini Client Module
Handles Gemini API integration, prompt generation, payload compression, and request timing.
"""
import json
import sys
import requests
import time
from datetime import datetime
from evaluator import find_now_hour_index

def format_single_region_for_llm(name: str, data: dict, hist_days: int = 7, fore_days: int = 3) -> dict:
    """Formats a single region's weather data into a clean structure for the LLM."""
    hist_key = f"past_{hist_days}_days_daily"
    fore_key = f"forecast_{fore_days}_days_hourly"
    
    hourly = data['hourly_raw']
    now_idx = find_now_hour_index(hourly)
    
    today_so_far = {
        "precipitation_mm": hourly['precipitation'][168:now_idx],
        "temperature_2m_c": hourly['temperature_2m'][168:now_idx],
        "relative_humidity_2m_percent": hourly['relative_humidity_2m'][168:now_idx],
        "cloud_cover_percent": hourly['cloud_cover'][168:now_idx],
        "weather_code": hourly['weather_code'][168:now_idx]
    }
    
    fore_hours = fore_days * 24
    end_fore_idx = min(len(hourly['precipitation']), now_idx + fore_hours)
    
    return {
        "name": name,
        "drainage_index": data['drainage_index'],
        "description": data['description'],
        hist_key: data['past_days'][-hist_days:],
        "today_so_far_hourly": today_so_far,
        fore_key: {
            "precipitation_mm": hourly['precipitation'][now_idx:end_fore_idx],
            "temperature_2m_c": hourly['temperature_2m'][now_idx:end_fore_idx],
            "relative_humidity_2m_percent": hourly['relative_humidity_2m'][now_idx:end_fore_idx],
            "cloud_cover_percent": hourly['cloud_cover'][now_idx:end_fore_idx],
            "weather_code": hourly['weather_code'][now_idx:end_fore_idx]
        }
    }

def compress_region_for_llm(region_data: dict, hist_days: int = 7, fore_days: int = 3) -> str:
    """
    Translates format_single_region_for_llm output into a dense text prompt representation.
    """
    output = []
    
    name = region_data['name']
    desc = region_data.get('description', 'No description')
    
    output.append(f"========== {name.upper()} ==========")
    output.append(f"Terrain Profile: {desc}")

    output.append(f"【Historical Daily Summary (Past {hist_days} Days)】")
    hist_key = f"past_{hist_days}_days_daily"
    past_days = region_data.get(hist_key, [])
    
    if not past_days:
        output.append("- No daily history available.")
    else:
        for day in past_days:
            date = day.get('time', 'Unknown')
            t_max = day.get('temperature_2m_max', 'N/A')
            p_sum = day.get('precipitation_sum', 0.0)
            output.append(f"- Date: {date} | Max Temp: {t_max}°C | Total Precip: {p_sum}mm")

    output.append("\n【Micro Recent Weather (Today So Far)】")
    today = region_data.get('today_so_far_hourly', {})
    t_precip = today.get('precipitation_mm', [])
    t_temp = today.get('temperature_2m_c', [])
    t_hum = today.get('relative_humidity_2m_percent', [])
    
    if not t_precip:
        output.append("- No data recorded for today yet.")
    else:
        total_hours_today = len(t_precip)
        for i in range(total_hours_today):
            p, t, h = t_precip[i], t_temp[i], t_hum[i]
            label = "[CURRENT HOUR / NOW]" if i == total_hours_today - 1 else f"[-{total_hours_today - 1 - i}h]"
            output.append(f"{label}: Temp {t}°C, Precip {p}mm, Hum {h}%")

    output.append(f"\n【Future Forecast (Next {fore_days} Days, 2-Hour Windows)】")
    fore_key = f"forecast_{fore_days}_days_hourly"
    forecast = region_data.get(fore_key, {})
    f_precip = forecast.get('precipitation_mm', [])
    f_temp = forecast.get('temperature_2m_c', [])
    f_hum = forecast.get('relative_humidity_2m_percent', [])
    
    if not f_precip:
        output.append("- No forecast data available.")
    else:
        for i in range(0, len(f_precip), 2):
            chunk_p = f_precip[i:i+2]
            chunk_t = f_temp[i:i+2]
            chunk_hum = f_hum[i:i+2]
            
            tot_p = round(sum(chunk_p), 1)
            max_t = max(chunk_t) if chunk_t else 'N/A'
            avg_h = int(sum(chunk_hum)/len(chunk_hum)) if chunk_hum else 0
            
            rain_tag = " ⚠️(ACTIVE RAIN)" if tot_p > 0.1 else ""
            output.append(f"[+ {i}h to + {i+2}h from NOW]: Max Temp {max_t}°C, Total Precip {tot_p}mm, Avg Hum {avg_h}%{rain_tag}")
            
    output.append("\n")
    return "\n".join(output)

def run_gemini_evaluation_for_region(name: str, data: dict, config: dict, api_key: str, dry_run: bool = False) -> dict:
    """Calls Gemini 2.5 Pro to calculate 2-hour window predictions for a single region."""
    hist_days = 7
    fore_days = 3
    
    hourly = data['hourly_raw']
    now_idx = find_now_hour_index(hourly)
    now_hour = (now_idx - 168) % 24
    now_hour_str = f"{now_hour:02d}:00"
    print(f"    - Today so far (hours 168 to {now_idx}, midnight to {now_hour_str}) sent as history; forecast starts at hour {now_idx}")
    
    llm_payload = compress_region_for_llm(format_single_region_for_llm(name, data, hist_days, fore_days), hist_days, fore_days)
    print(f"    - Sending payload to Gemini: {len(json.dumps(llm_payload))} chars")
    
    prompt = f"""
You are an expert trail builder and mountain biking condition analyst in vancouver north shore and sea to sky area.
Analyze weather data for the mountain biking region '{name}' and predict trail conditions (soil), roots/rocks traction, and ride-time weather for seven 2-hour windows (08:00 to 22:00) over the next {fore_days} days.

The history payload includes:
1. The past {hist_days} days of daily weather records (`past_{hist_days}_days_daily`).
2. Today's hourly weather history from midnight to the current hour {now_hour_str} (`today_so_far_hourly`).

The forecast payload (`forecast_{fore_days}_days_hourly`) starts precisely from the current hour ({now_hour_str}) onwards.

CRITICAL: Your predictions for Today (day_index 0) MUST start from the current hour ({now_hour_str}) onwards. Only return prediction windows that start at or after {now_hour_str} for Today (do not return windows that start before {now_hour_str}). For subsequent days, return all seven 2-hour windows.

Allowed Trail Conditions: 'dusty', 'dry', 'good', 'damp', 'wet', 'muddy'.
Allowed Roots/Rocks Traction States: 'dry', 'slick', 'dangerous'.

CRITICAL:
1. ANCHOR TO REAL-TIME: Evaluate current surface dampness based strictly on the "[CURRENT HOUR / NOW]" row.
2. USE THE PROVIDED INDEX: Rely on the `Drainage Index` provided for each region. Higher index means the soil recovers to 'dry' faster. 
3. TEMPORAL CONTINUITY: Conditions in window [+2h to +4h] depend on the state in window [+0h to +2h]. If it stops raining, rocks/roots dry quickly, but soil (especially low drainage index) takes hours or days to recover.
4. ZERO HALLUCINATION: Only use the exact mm of precipitation provided. Do not guess weather.
5. Active rain during a 2-hour window overrides both soil and roots/rocks conditions. If rain in a window is >2mm, override soil to 'muddy'; >0.5mm to 'wet'; >0.1mm to 'damp'. If rain in a window is >1mm, override roots and rocks to 'dangerous'; >0.1mm (or if soil is 'wet' or humidity >=80%), override to 'slick'.

Provide a daily 'reasoning' string explaining how weather history (including today so-far) affect dry-out speeds and conditions.

Here is the weather data for '{name}':
{llm_payload}
Return a raw JSON object matching this schema:
{{
  "name": "{name}",
  "daily_forecast": [
    {{
      "day_index": 0, "date": "YYYY-MM-DD",
      "reasoning": "1-2 sentence daily explanation of why this day behaves like this.",
      "windows": [
        {{ "time_window": "08:00-10:00", "condition": "good", "roots_rocks": "dry", "weather_desc": "Sunny", "weather_emoji": "☀️" }},
        ... (7 windows total)
      ]
    }},
    ... ({fore_days} days total)
  ]
}}
Do not include any markdown styling. Output raw JSON only.
"""
    model_name = config['gemini_settings'].get('dry_run_model' if dry_run else 'model', 'gemini-2.5-flash')
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": config['gemini_settings']['temperature']}
    }
    for attempt in range(3):
        try:
            start_time = time.time()
            response = requests.post(url, headers=headers, json=body, timeout=120)
            response.raise_for_status()
            duration = time.time() - start_time
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}]       [Gemini API Debug] Request for {name} took {duration:.2f} seconds.")
            
            text = response.json()['candidates'][0]['content']['parts'][0]['text']
            parsed = json.loads(text.strip())
            if not isinstance(parsed, dict) or "daily_forecast" not in parsed:
                raise ValueError("Response missing 'daily_forecast' key or is not a valid dictionary.")
            return parsed
        except Exception as e:
            print(f"      [Gemini API] Attempt {attempt + 1} failed for {name}: {e}.", file=sys.stderr)
            if attempt == 2:
                raise e

def run_gemini_evaluation(processed_regions: dict, config: dict, api_key: str, dry_run: bool = False) -> dict:
    """Orchestrates Gemini 2.5 Pro evaluations for each region sequentially."""
    results = {"regions": []}
    model_name = config['gemini_settings'].get('dry_run_model' if dry_run else 'model', 'gemini-2.5-flash')
    for name, data in processed_regions.items():
        print(f"  Evaluating region with Gemini ({model_name}): {name}...")
        try:
            region_res = run_gemini_evaluation_for_region(name, data, config, api_key, dry_run=dry_run)
            if region_res:
                results["regions"].append(region_res)
        except Exception as e:
            print(f"  Warning: Gemini API call failed for {name}: {e}", file=sys.stderr)
    return results
