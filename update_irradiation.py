#!/usr/bin/env python3
"""
Fetch current irradiation data from Open-Meteo API and update predictions file
Runs daily to keep irradiation data current
"""

import json
import requests
from datetime import datetime, timedelta

# Configuration
LATITUDE = -33.974268385473856
LONGITUDE = 25.612268537267603
FORECAST_API = "https://api.open-meteo.com/v1/forecast"
PREDICTIONS_FILE = "predictions_2025_2044.min.json"

def fetch_irradiation_forecast(days=16):
    """
    Fetch irradiation forecast from Open-Meteo API
    Returns dict of date -> [24 hourly values]
    """
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": "direct_radiation",
        "timezone": "Africa/Johannesburg",
        "forecast_days": days
    }
    
    print(f"📡 Fetching irradiation forecast for next {days} days...")
    response = requests.get(FORECAST_API, params=params, timeout=30)
    
    if response.status_code != 200:
        raise Exception(f"API error: {response.status_code}")
    
    data = response.json()
    
    # Parse response
    daily_irradiation = {}
    timestamps = data["hourly"]["time"]
    direct_radiation = data["hourly"]["direct_radiation"]
    
    for timestamp, radiation in zip(timestamps, direct_radiation):
        date = timestamp.split("T")[0]
        hour = int(timestamp.split("T")[1].split(":")[0])
        
        if date not in daily_irradiation:
            daily_irradiation[date] = [0] * 24
        
        daily_irradiation[date][hour] = int(radiation) if radiation is not None else 0
    
    print(f"✓ Fetched {len(daily_irradiation)} days of irradiation data")
    return daily_irradiation

def update_predictions_file(predictions_file, new_irradiation):
    """
    Update predictions file with fresh irradiation data
    """
    print(f"\n📂 Loading {predictions_file}...")
    
    with open(predictions_file, 'r') as f:
        predictions = json.load(f)
    
    total_days = len(predictions.get('daily_predictions', {}))
    updated_count = 0
    
    print(f"✓ Loaded predictions for {total_days} days")
    print(f"\n🔄 Updating irradiation data...")
    
    for date_str, irradiation_hourly in new_irradiation.items():
        if 'daily_predictions' in predictions and date_str in predictions['daily_predictions']:
            predictions['daily_predictions'][date_str]['irradiation_wm2'] = irradiation_hourly
            updated_count += 1
    
    # Update or create metadata
    if 'metadata' not in predictions:
        predictions['metadata'] = {}
    
    predictions['metadata']['irradiation_last_updated'] = datetime.now().isoformat()
    predictions['metadata']['irradiation_dates_updated'] = list(new_irradiation.keys())
    
    # Save
    print(f"\n💾 Saving updated predictions...")
    with open(predictions_file, 'w') as f:
        json.dump(predictions, f, separators=(',', ':'))
    
    print(f"✓ Updated {updated_count} days with fresh irradiation data")
    
    # Show sample
    sample_date = list(new_irradiation.keys())[0] if new_irradiation else None
    if sample_date and sample_date in predictions['daily_predictions']:
        sample = predictions['daily_predictions'][sample_date]
        peak_irr = max(sample['irradiation_wm2'])
        print(f"\nSample ({sample_date}): Peak irradiation = {peak_irr} W/m²")

def main():
    print("="*70)
    print("UPDATING IRRADIATION DATA FROM OPEN-METEO API")
    print("="*70)
    
    try:
        # Fetch fresh irradiation data (16 days forecast)
        irradiation = fetch_irradiation_forecast(days=16)
        
        # Update predictions file
        update_predictions_file(PREDICTIONS_FILE, irradiation)
        
        print("\n" + "="*70)
        print("✅ IRRADIATION UPDATE COMPLETE")
        print("="*70)
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\n⚠️  Using existing irradiation data from predictions file")
        return 1

if __name__ == '__main__':
    import sys
    sys.exit(main())
