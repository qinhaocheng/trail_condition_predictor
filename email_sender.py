# -*- coding: utf-8 -*-
"""
Email Sender Module (2-Hour Resolution)
Handles Jinja2 HTML rendering and SMTP mail transmission.
"""
import os
import sys
import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Template

def generate_html_report(regions_predictions: dict, warnings: list, 
                         gemini_active: bool, template_path: str = "templates/email_template.html",
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
                    
            def get_worst(wins, key, severity_dict, default):
                vals = [w[key] for w in wins if w[key].lower().strip() not in ['n/a', 'na', 'passed']]
                if not vals:
                    return default
                return max(vals, key=lambda v: severity_dict.get(v.lower().strip(), 0))
                
            # Morning: windows 0 and 1
            day['morning_soil'] = get_worst(day['windows'][:2], 'condition', SOIL_SEVERITY, 'N/A')
            day['morning_rr'] = get_worst(day['windows'][:2], 'roots_rocks', RR_SEVERITY, 'N/A')
            
            # Afternoon: windows 2, 3, and 4
            day['afternoon_soil'] = get_worst(day['windows'][2:5], 'condition', SOIL_SEVERITY, 'N/A')
            day['afternoon_rr'] = get_worst(day['windows'][2:5], 'roots_rocks', RR_SEVERITY, 'N/A')
            
            # Evening: windows 5 and 6
            day['evening_soil'] = get_worst(day['windows'][5:], 'condition', SOIL_SEVERITY, 'N/A')
            day['evening_rr'] = get_worst(day['windows'][5:], 'roots_rocks', RR_SEVERITY, 'N/A')
        
    t = Template(html_template_str)
    return t.render(
        current_date=current_date, today_label=today_label,
        real_generation_date=real_generation_date,
        day_2_name=day_2_name, day_3_name=day_3_name,
        regions=regions_predictions, warnings=warnings, gemini_active=gemini_active,
        forecast_days=forecast_days, active_region=active_region
    )

def build_text_fallback(regions_predictions: dict, warnings: list) -> str:
    """Generates a plain-text representation of today's 2-hour windows."""
    current_date = datetime.datetime.now().strftime("%B %d, %Y")
    lines = [f"Daily Trail Condition Forecast Briefing - {current_date}", "==================================================", ""]
    
    if warnings:
        lines.append("Alerts:")
        for w in warnings:
            lines.append(f" - {w}")
        lines.append("")
        
    for name, data in regions_predictions.items():
        lines.append(f"{name}:")
        today_forecast = data['daily_forecast'][0]
        lines.append(f"  Today's Analysis: {today_forecast['reasoning']}")
        for win in today_forecast['windows']:
            lines.append(f"    {win['time_window']}: {win['condition'].upper()} ({win['weather_desc']} {win['weather_emoji']}, {win['temp']:.1f}°C)")
        lines.append("")
    return "\n".join(lines)

def send_email_report(html_content: str, regions_predictions: dict, 
                      warnings: list, config: dict) -> None:
    """Delivers 2-hour email briefing to recipients via SMTP."""
    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_port = os.environ.get("SMTP_PORT")
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    recipient_emails = os.environ.get("RECIPIENT_EMAILS")
    
    if not all([smtp_server, smtp_port, smtp_user, smtp_password, recipient_emails]):
        raise ValueError("SMTP variables are not fully configured in the environment.")
        
    recipients = [r.strip() for r in recipient_emails.split(",") if r.strip()]
    current_date = datetime.datetime.now().strftime("%B %d, %Y")
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{config['email_settings']['subject_prefix']} - {current_date}"
    msg["From"] = f"{config['email_settings']['sender_name']} <{smtp_user}>"
    msg["To"] = ", ".join(recipients)
    
    msg.attach(MIMEText(build_text_fallback(regions_predictions, warnings), "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))
    
    port = int(smtp_port)
    server = smtplib.SMTP_SSL(smtp_server, port) if port == 465 else smtplib.SMTP(smtp_server, port)
    if port == 587:
        server.starttls()
        
    server.login(smtp_user, smtp_password)
    server.sendmail(smtp_user, recipients, msg.as_string())
    server.quit()
