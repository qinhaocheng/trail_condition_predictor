# -*- coding: utf-8 -*-
"""
Report Generator Module (2-Hour Resolution)
Handles Jinja2 HTML rendering for the trail conditions briefing dashboard.
"""
import os
import sys
import datetime
from jinja2 import Template

def generate_html_report(regions_predictions: dict, warnings: list, 
                         gemini_active: bool, template_path: str = "templates/briefing_template.html",
                         vancouver_now = None) -> str:
    """Reads HTML template file and renders it with 2-hour window predictions."""
    with open(template_path, 'r', encoding='utf-8') as f:
        html_template_str = f.read()
        
    if vancouver_now is None:
        vancouver_now = datetime.datetime.now()
        
    is_after_8pm = vancouver_now.hour >= 20
    real_generation_date = vancouver_now.strftime("%B %d, %Y")
    
    briefing_dt = vancouver_now
    if is_after_8pm:
        briefing_dt = vancouver_now + datetime.timedelta(days=1)
        
    current_date = briefing_dt.strftime("%B %d, %Y")
    today_label = "Today"
    
    day_2_name = (briefing_dt + datetime.timedelta(days=2)).strftime("%A")
    day_3_name = (briefing_dt + datetime.timedelta(days=3)).strftime("%A")
    
    forecast_days = 3
    active_region = "Vancouver & Squamish"
    if regions_predictions:
        first_region = next(iter(regions_predictions.values()))
        forecast_days = len(first_region['daily_forecast'])
        active_region = first_region.get('region', 'Vancouver & Squamish').title()

    # Pre-calculate worst conditions for Next Days Outlook and assign labels
    SOIL_SEVERITY = {
        'muddy': 5,
        'wet': 4,
        'dusty': 3,
        'damp': 2,
        'dry': 1,
        'good': 0,
        'n/a': -1,
        'na': -1
    }
    RR_SEVERITY = {
        'dangerous': 3,
        'slick': 2,
        'dry': 1,
        'n/a': 0,
        'na': 0,
        'passed': 0
    }
    
    for region_data in regions_predictions.values():
        for day in region_data.get('daily_forecast', []):
            d_idx = day.get('day_index', 0)
            if d_idx == 0:
                day['label'] = "Today"
            elif d_idx == 1:
                day['label'] = "Tomorrow"
            else:
                day['label'] = (briefing_dt + datetime.timedelta(days=d_idx)).strftime("%A")
                    
            # Group windows by time of day slot
            morning_wins = [w for w in day['windows'] if w.get('window_index') in [0, 1]]
            afternoon_wins = [w for w in day['windows'] if w.get('window_index') in [2, 3, 4]]
            evening_wins = [w for w in day['windows'] if w.get('window_index') in [5, 6]]

            def get_worst(wins, key, severity_dict, default):
                vals = [w[key] for w in wins if w[key].lower().strip() not in ['n/a', 'na', 'passed']]
                if not vals:
                    return default
                return max(vals, key=lambda v: severity_dict.get(v.lower().strip(), 0))
                
            def get_common_emoji(wins):
                emojis = [w['weather_emoji'] for w in wins if w.get('weather_emoji')]
                if not emojis:
                    return "☀️"
                from collections import Counter
                return Counter(emojis).most_common(1)[0][0]
            
            # Morning (8 AM - 12 PM)
            day['morning_soil'] = get_worst(morning_wins, 'condition', SOIL_SEVERITY, 'N/A')
            day['morning_rr'] = get_worst(morning_wins, 'roots_rocks', RR_SEVERITY, 'N/A')
            day['morning_emoji'] = get_common_emoji(morning_wins)
            
            # Afternoon (12 PM - 6 PM)
            day['afternoon_soil'] = get_worst(afternoon_wins, 'condition', SOIL_SEVERITY, 'N/A')
            day['afternoon_rr'] = get_worst(afternoon_wins, 'roots_rocks', RR_SEVERITY, 'N/A')
            day['afternoon_emoji'] = get_common_emoji(afternoon_wins)
            
            # Evening (6 PM - 10 PM)
            day['evening_soil'] = get_worst(evening_wins, 'condition', SOIL_SEVERITY, 'N/A')
            day['evening_rr'] = get_worst(evening_wins, 'roots_rocks', RR_SEVERITY, 'N/A')
            day['evening_emoji'] = get_common_emoji(evening_wins)
        
    t = Template(html_template_str)
    return t.render(
        current_date=current_date, today_label=today_label,
        real_generation_date=real_generation_date,
        day_2_name=day_2_name, day_3_name=day_3_name,
        regions=regions_predictions, warnings=warnings, gemini_active=gemini_active,
        forecast_days=forecast_days, active_region=active_region
    )
