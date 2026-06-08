# -*- coding: utf-8 -*-
"""
Evaluator Module (2-Hour Resolution)
Performs hourly soil moisture simulations and handles Gemini evaluations.
"""
import json
import sys
import requests
from datetime import datetime
from zone_config import TRAIL_CONFIGS, GLOBAL_CONFIG
from physics_engine import TrailConditionAnalyzer
from typing import List, Dict, Tuple


def calculate_hourly_saturation(hourly_raw: dict, config: dict) -> list:
    """Calculates the accumulated decayed rain/snow saturation over 240 hours."""
    precip = hourly_raw['precipitation']
    temp = hourly_raw['temperature_2m']
    humidity = hourly_raw['relative_humidity_2m']
    snow = hourly_raw['snowfall']
    cloud = hourly_raw['cloud_cover']
    
    rules = config['evaluation_rules']
    evap = rules['evaporation_tuning']
    base_decay = rules['hourly_base_decay']
    
    s_list = [0.0] * 240
    for h in range(240):
        prev_s = s_list[h-1] if h > 0 else 0.0
        
        # Evaporation adjustments based on weather metrics
        t_adj = 0.0
        if temp[h] > evap['high_temp_threshold']:
            t_adj = min(0.02, (temp[h] - evap['high_temp_threshold']) * 0.001)
        elif temp[h] < evap['low_temp_threshold']:
            t_adj = -min(0.01, (evap['low_temp_threshold'] - temp[h]) * 0.0015)
            
        h_adj = 0.0
        if humidity[h] > evap['high_humidity_threshold']:
            h_adj = min(0.015, (humidity[h] - evap['high_humidity_threshold']) * 0.0007)
        elif humidity[h] < evap['low_humidity_threshold']:
            h_adj = -min(0.01, (evap['low_humidity_threshold'] - humidity[h]) * 0.0004)
            
        c_adj = 0.0
        if cloud[h] > evap['overcast_threshold']:
            c_adj = min(0.01, (cloud[h] - evap['overcast_threshold']) * 0.0005)
        elif cloud[h] < evap['sunny_threshold']:
            c_adj = -min(0.01, (evap['sunny_threshold'] - cloud[h]) * 0.0005)
            
        lambda_h = max(0.85, min(0.995, base_decay - t_adj + h_adj + c_adj))
        moisture = precip[h] + (snow[h] * 2.0)
        s_list[h] = prev_s * lambda_h + moisture
        
    return s_list

def evaluate_window(w_idx: int, day_start_h: int, s_list: list, 
                    data: dict, config: dict) -> dict:
    """Evaluates the trail condition and weather for a single 2-hour window."""
    w_info = data['forecast_windows'][day_start_h][w_idx]
    
    start_time_str = f"{w_info['date']}T{w_info['time_window'].split('-')[0]}"
    try:
        start_h = data['hourly_raw']['time'].index(start_time_str)
    except ValueError:
        start_h = int(w_info['time_window'].split('-')[0].split(':')[0]) + 168 + day_start_h * 24

    
    sat = sum(s_list[start_h:start_h+2]) / 2.0
    rain = w_info['precipitation']
    rules = config['evaluation_rules']
    overrides = rules['window_overrides']
    
    score = (sat * rules['past_rain_weight'] + rain * rules['forecast_rain_weight']) * data['drainage_index']
    
    cond = "dry"
    for thresh in config['condition_thresholds']:
        max_val = float('inf') if thresh['max_score'] == '.inf' else float(thresh['max_score'])
        if score <= max_val:
            cond = thresh['condition']
            break
            
    # Window active rainfall overrides
    if rain >= overrides['muddy_threshold']:
        cond = "muddy"
    elif rain >= overrides['wet_threshold'] and cond in ["dusty", "dry", "good", "damp"]:
        cond = "wet"
    elif rain >= overrides['damp_threshold'] and cond in ["dusty", "dry", "good"]:
        cond = "damp"
        
    # Evaluate roots and rocks condition
    rr_rules = config['evaluation_rules']['roots_rocks_rules']
    if rain >= rr_rules['dangerous_rain_threshold'] or cond == 'muddy':
        rr_cond = 'dangerous'
    elif rain >= rr_rules['slick_rain_threshold'] or cond == 'wet' or w_info['humidity_mean'] >= rr_rules['slick_humidity_threshold']:
        rr_cond = 'slick'
    else:
        rr_cond = 'dry'
        
    return {
        "time_window": w_info['time_window'], "condition": cond, "roots_rocks": rr_cond,
        "weather_desc": w_info['weather_desc'], "weather_emoji": w_info['weather_emoji'],
        "temp": w_info['temp_mean'], "precipitation": rain, "score": score, "saturation": sat,
        "is_passed": w_info.get('is_passed', False)
    }

def generate_day_reasoning(day_idx: int, day_rain: float, day_sat: float, 
                           drainage: float, name: str) -> str:
    """Generates daily verbal reasoning based on daily moisture status."""
    reasons = []
    if day_rain > 12.0:
        reasons.append(f"Heavy rainfall ({day_rain:.1f} mm) today will lead to muddy, water-saturated trails.")
    elif day_rain > 4.0:
        reasons.append(f"Steady rainfall today ({day_rain:.1f} mm) will keep the trails wet and slick.")
    elif day_rain > 1.0:
        reasons.append(f"Light rain today ({day_rain:.1f} mm) will introduce dampness.")
        
    if not reasons:
        if day_sat > 10.0:
            reasons.append(f"Trails remain wet and saturated from previous rainfall.")
        elif day_sat > 3.0:
            reasons.append(f"Trails retain a nice damp tackiness from past moisture.")
        else:
            reasons.append("Dry soils and sunny/clear skies will lead to fast, rolling trails.")
            
    if drainage > 1.2:
        reasons.append("Slow drainage in this clay-heavy terrain will slow down dry-out speeds.")
    elif drainage < 0.8:
        reasons.append("Excellent sandy granite slabs will accelerate drying times.")
        
    return " ".join(reasons)

def evaluate_day_fallback(d_idx: int, date_str: str, s_list: list, 
                          data: dict, config: dict) -> dict:
    """Aggregates all 2-hour window predictions and builds reasoning for a single day."""
    num_windows = len(data['forecast_windows'][d_idx])
    windows = [evaluate_window(w, d_idx, s_list, data, config) for w in range(num_windows)]
    
    # Calculate day aggregates
    day_start_h = 168 + d_idx * 24
    day_rain = sum(data['hourly_raw']['precipitation'][day_start_h:day_start_h+24])
    day_sat = sum(s_list[day_start_h+8:day_start_h+22]) / 14.0
    
    reasoning = generate_day_reasoning(
        d_idx, day_rain, day_sat, data['drainage_index'], data['name']
    )
    
    return {
        "day_index": d_idx,
        "date": date_str,
        "reasoning": reasoning,
        "windows": windows
    }

def run_formula_simulation(region_data: dict) -> Tuple[List[str], List[str], List[float], List[float], List[float]]:
    """Runs the TrailConditionAnalyzer hour-by-hour for all 240 hours."""
    name = region_data['name']
    trail_config = TRAIL_CONFIGS.get(name, TRAIL_CONFIGS["Mount Fromme"])
    hourly = region_data['hourly_raw']
    hourly_list = []
    for i in range(len(hourly['time'])):
        hourly_list.append({
            "time": hourly['time'][i],
            "temp": hourly['temperature_2m'][i],
            "humidity": hourly['relative_humidity_2m'][i],
            "cloud": hourly['cloud_cover'][i],
            "precip": hourly['precipitation'][i]
        })
        
    swi_labels = []
    rsi_labels = []
    swi_scores = []
    rsi_scores = []
    di_scores = []
    
    for h in range(len(hourly_list)):
        analyzer = TrailConditionAnalyzer(hourly_list[:h+1], trail_config)
        swi_val, rsi_val, swi_label, rsi_label = analyzer.calculate()
        
        swi_labels.append(swi_label)
        rsi_labels.append(rsi_label)
        swi_scores.append(swi_val)
        rsi_scores.append(rsi_val)
        di_scores.append(round(analyzer.di, 1))
        
    return swi_labels, rsi_labels, swi_scores, rsi_scores, di_scores

def evaluate_window_new(w_idx: int, day_start_h: int, swi_labels: list, rsi_labels: list,
                        swi_scores: list, rsi_scores: list, di_scores: list, data: dict, config: dict) -> dict:
    """Evaluates the trail condition and weather for a single 2-hour window using simulated values."""
    w_info = data['forecast_windows'][day_start_h][w_idx]
    
    start_time_str = f"{w_info['date']}T{w_info['time_window'].split('-')[0]}"
    try:
        start_h = data['hourly_raw']['time'].index(start_time_str)
    except ValueError:
        start_h = int(w_info['time_window'].split('-')[0].split(':')[0]) + 168 + day_start_h * 24
    target_idx = min(len(swi_labels) - 1, start_h + 1)
    
    cond = swi_labels[target_idx]
    rr_cond = rsi_labels[target_idx]
    score = swi_scores[target_idx]
    sat = swi_scores[target_idx]
    rsi_val = rsi_scores[target_idx]
    di_val = di_scores[target_idx]
    rain = w_info['precipitation']
    
    # Log the calculated SWI, RSI, and DI scores
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}]       - Window {w_info['date']} {w_info['time_window']}: SWI={score:.1f}, RSI={rsi_val:.1f}, DI={di_val:.1f} -> Soil={cond}, Roots/Rocks={rr_cond}")
    
    return {
        "time_window": w_info['time_window'], "condition": cond, "roots_rocks": rr_cond,
        "weather_desc": w_info['weather_desc'], "weather_emoji": w_info['weather_emoji'],
        "temp": w_info['temp_mean'], "precipitation": rain, "score": score, "saturation": sat, "swi_score": score, "rsi_score": rsi_val, "di_score": di_val,
        "is_passed": w_info.get('is_passed', False)
    }

def evaluate_day_fallback_new(d_idx: int, date_str: str, swi_labels: list, rsi_labels: list,
                              swi_scores: list, rsi_scores: list, di_scores: list, data: dict, config: dict) -> dict:
    """Aggregates all 2-hour window predictions and builds reasoning for a single day using simulated values."""
    num_windows = len(data['forecast_windows'][d_idx])
    windows = [evaluate_window_new(w, d_idx, swi_labels, rsi_labels, swi_scores, rsi_scores, di_scores, data, config) for w in range(num_windows)]
    
    day_start_h = 168 + d_idx * 24
    day_rain = sum(data['hourly_raw']['precipitation'][day_start_h:day_start_h+24])
    day_sat = sum(swi_scores[day_start_h+8:day_start_h+22]) / 14.0
    
    reasoning = generate_day_reasoning(
        d_idx, day_rain, day_sat, data['drainage_index'], data['name']
    )
    
    return {
        "day_index": d_idx,
        "date": date_str,
        "reasoning": reasoning,
        "windows": windows
    }

def run_fallback_heuristic(region_data: dict, config: dict) -> list:
    """Generates predictions for all 3 days (each with 7 windows) using new formula simulation."""
    swi_labels, rsi_labels, swi_scores, rsi_scores, di_scores = run_formula_simulation(region_data)
    results = []
    for d_idx, meta in enumerate(region_data['forecast_days_meta']):
        results.append(evaluate_day_fallback_new(d_idx, meta['date'], swi_labels, rsi_labels, swi_scores, rsi_scores, di_scores, region_data, config))
    return results

def calculate_saturation_list(region_data: dict, config: dict) -> list:
    """Wrapper to compute hourly saturation sequence."""
    swi_labels, rsi_labels, swi_scores, rsi_scores, di_scores = run_formula_simulation(region_data)
    return swi_scores

def find_now_hour_index(hourly_raw: dict) -> int:
    """Finds the index of the current hour in Vancouver timezone in the times list."""
    from datetime import datetime, timezone, timedelta
    times = hourly_raw.get('time', [])
    offset = hourly_raw.get('utc_offset_seconds', -25200)
    utc_now = datetime.now(timezone.utc)
    vancouver_now = utc_now + timedelta(seconds=offset)
    
    is_after_8pm = vancouver_now.hour >= 20
    if is_after_8pm:
        vancouver_now = (vancouver_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        
    now_str = vancouver_now.strftime("%Y-%m-%dT%H:00")
        
    try:
        return times.index(now_str)
    except ValueError:
        return 192 if is_after_8pm else 168 # Fallback


def merge_predictions(processed_regions: dict, gemini_data: dict, config: dict) -> dict:
    """Merges Gemini JSON predictions with the processed weather records."""
    result = {}
    for name, data in processed_regions.items():
        daily_preds = run_fallback_heuristic(data, config)
        print(f"  Computed fallback heuristics for {name}: {len(daily_preds)} forecast days.")
        if gemini_data:
            analyzer = TrailConditionAnalyzer([],  TRAIL_CONFIGS.get(name, TRAIL_CONFIGS["Mount Fromme"]))
            llm_r = next((r for r in gemini_data.get('regions', []) if r.get('name', '').lower() == name.lower()), None)
            if llm_r:
                print(f"  Merging Gemini predictions for {name}...")
                for fd in daily_preds:
                    llm_d = next((ld for ld in llm_r.get('daily_forecast', []) if ld.get('day_index') == fd['day_index']), None)
                    if llm_d:
                        fd['reasoning'] = llm_d.get('reasoning', fd['reasoning'])
                        for fp in fd['windows']:
                            llm_w = next((lw for lw in llm_d.get('windows', []) if lw.get('time_window') == fp['time_window']), None)
                            if llm_w:
                                cond = llm_w.get('condition', '').lower().strip()
                                rr = llm_w.get('roots_rocks', '').lower().strip()
                                if cond in ["dusty", "dry", "good", "damp", "wet", "muddy"] and rr in ["dry", "slick", "dangerous"]:
                                    merge_cond, merged_rr = analyzer.merging_scores_and_ai_labels(cond, rr, fp['swi_score'], fp['rsi_score'], fp['di_score'])
                                    fp['condition'] = merge_cond
                                    fp['roots_rocks'] = merged_rr
                                fp['weather_desc'] = llm_w.get('weather_desc', fp['weather_desc'])
                                fp['weather_emoji'] = llm_w.get('weather_emoji', fp['weather_emoji'])
                                
        result[name] = {
            "name": name, "region": data.get('region', 'north shore'), "drainage_index": data['drainage_index'], "description": data['description'], "maps_link": data['maps_link'],
            "past_days_daily": data['past_days'],
            "today_so_far": data.get('today_so_far'),
            "station_info": {
                "latitude": data.get('station_lat', 0.0),
                "longitude": data.get('station_lon', 0.0),
                "distance_km": data.get('distance_to_station_km', 0.0)
            },
            "past_days_summary": {
                "total_rain": sum(d['precipitation'] for d in data['past_days']),
                "total_snow": sum(d['snowfall'] for d in data['past_days']),
                "mean_temp": sum(d['temp_mean'] for d in data['past_days']) / max(1.0, float(len(data['past_days']))),
                "mean_humidity": sum(d['humidity_mean'] for d in data['past_days']) / max(1.0, float(len(data['past_days'])))
            },
            "daily_forecast": daily_preds
        }
    return result
