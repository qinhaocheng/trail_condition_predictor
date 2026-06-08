# -*- coding: utf-8 -*-
"""
Daily Trail Conditions Predictor - Main Orchestrator (2-Hour Resolution)
Orchestrates weather query, condition evaluations (Gemini / Fallback), and email delivery.
"""
import os
import sys
import argparse
import datetime
from config_loader import load_config, load_secrets_to_env
from weather_fetcher import fetch_weather, process_region_weather
from evaluator import merge_predictions
from gemini_client import run_gemini_evaluation
from email_sender import generate_html_report, send_email_report

def parse_arguments() -> argparse.Namespace:
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(description="Daily Trail Conditions Predictor")
    parser.add_argument("--dry-run", action="store_true", help="Generate HTML report locally but do not send email")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config.yaml file")
    parser.add_argument("--no-gemini", action="store_true", help="Disable Gemini API calls and enforce fallback heuristics")
    parser.add_argument("--region", default="north shore", choices=["north shore", "squamish"], help="Select active region group (north shore or squamish)")
    return parser.parse_args()

def evaluate_warnings(regions_predictions: dict) -> list:
    """Scans Today's 2-hour window predictions for muddy conditions or heavy rain alerts."""
    warnings = []
    for name, data in regions_predictions.items():
        today_forecast = data['daily_forecast'][0]
        
        # Identify specific windows matching warning criteria, ignoring passed hours
        muddy_windows = [w['time_window'] for w in today_forecast['windows'] if w['condition'] == 'muddy' and not w.get('is_passed')]
        heavy_rain_windows = [w['time_window'] for w in today_forecast['windows'] if w['precipitation'] >= 3.0 and not w.get('is_passed')]
        
        if muddy_windows:
            warnings.append(f"Avoid riding {name} today. Muddy trail conditions predicted during: {', '.join(muddy_windows)}.")
        elif heavy_rain_windows:
            warnings.append(f"Heavy rain alert for {name} today during: {', '.join(heavy_rain_windows)}. Riding conditions will be highly degraded.")
    return warnings

def run_pipeline(args: argparse.Namespace) -> None:
    """Runs the core data pipeline from weather query to briefing export."""
    load_secrets_to_env()
    config = load_config(args.config)
    
    # Filter zones to keep only the selected active region
    active_region = args.region.lower().strip()
    config['regions'] = [r for r in config['regions'] if r.get('region', '').lower().strip() == active_region]
    print(f"Active region selected: {active_region.upper()}. Active zones: {[r['name'] for r in config['regions']]}")
    
    api_key = None if args.no_gemini else (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    gemini_enabled = bool(api_key)
    
    print(f"Querying Open-Meteo weather data for {len(config['regions'])} regions...")
    raw_weather = fetch_weather(config['regions'])
    
    # Store raw weather data locally
    try:
        import json
        with open("output/raw_weather_data.json", 'w', encoding='utf-8') as f:
            json.dump(raw_weather, f, indent=2)
        print("Raw weather data stored to output/raw_weather_data.json.")
    except Exception as e:
        print(f"Warning: Failed to save raw weather data: {e}", file=sys.stderr)
        
    processed_regions = {
        r['name']: process_region_weather(r, w) for r, w in zip(config['regions'], raw_weather)
    }

    gemini_data = None
    gemini_active = False
    
    if gemini_enabled:
        try:
            model_name = config['gemini_settings'].get('model', 'gemini-2.5-flash')
            print(f"Calling Gemini ({model_name}) API for condition evaluations...")
            gemini_data = run_gemini_evaluation(processed_regions, config, api_key, dry_run=args.dry_run)
            gemini_active = True
            print(f"Gemini ({model_name}) evaluation successful!")
        except Exception as e:
            print(f"Warning: Gemini API call failed: {e}. Falling back to heuristics.", file=sys.stderr)
            
    regions_predictions = merge_predictions(processed_regions, gemini_data, config)
    warnings = evaluate_warnings(regions_predictions)
    
    offset = -25200
    if raw_weather and isinstance(raw_weather, list) and len(raw_weather) > 0:
        offset = raw_weather[0].get('utc_offset_seconds', -25200)
    from datetime import timezone, timedelta
    utc_now = datetime.datetime.now(timezone.utc)
    vancouver_now = utc_now + timedelta(seconds=offset)
    
    html_content = generate_html_report(regions_predictions, warnings, gemini_active, vancouver_now=vancouver_now)
    
    if args.dry_run:
        with open("output/email_preview.html", 'w', encoding='utf-8') as f:
            f.write(html_content)
        print("Dry-run active. HTML saved to output/email_preview.html.")
        print(f"Warnings generated: {warnings}")
        return
        
    try:
        send_email_report(html_content, regions_predictions, warnings, config)
        print("Email successfully sent!")
    except Exception as e:
        print(f"Error sending email: {e}. Saving copy to output/email_preview.html.", file=sys.stderr)
        with open("output/email_preview.html", 'w', encoding='utf-8') as f:
            f.write(html_content)
        sys.exit(1)

def main() -> None:
    """Entry point."""
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    args = parse_arguments()
    try:
        run_pipeline(args)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
