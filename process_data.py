import pandas as pd
import json
from datetime import datetime, timedelta, timezone
import calendar
import os
import glob
import requests

# South African timezone (SAST = UTC+2)
SAST = timezone(timedelta(hours=2))

def get_sast_now():
    """Get current time in South African timezone"""
    return datetime.now(SAST)

def load_config():
    """Load configuration file"""
    with open('config.json', 'r') as f:
        return json.load(f)

def convert_to_number(value):
    """Convert text values to numbers"""
    if pd.isna(value) or value == '':
        return 0
    try:
        return float(str(value).replace(' ', '').replace(',', ''))
    except:
        return 0

def fetch_irradiation_data(date):
    """Fetch hourly irradiation data from open-meteo API"""
    try:
        base_url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": -33.97422273793887,
            "longitude": 25.61212584301634,
            "start_date": date,
            "end_date": date,
            "hourly": "direct_radiation"
        }
        
        response = requests.get(base_url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            timestamps = data["hourly"]["time"]
            direct_radiation = data["hourly"]["direct_radiation"]
            
            # Convert API timestamps to SAST (South Africa Standard Time)
            # User reported: irradiation shows 1 hour early, so adding 1 hour offset
            # If still incorrect after testing, try TIMEZONE_OFFSET_HOURS = 2 (full UTC+2)
            TIMEZONE_OFFSET_HOURS = 1  # Adjust to 2 if irradiation still appears early
            
            hourly_data = {}
            for timestamp, radiation in zip(timestamps, direct_radiation):
                # Parse timestamp and apply timezone offset
                utc_time = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M')
                local_time = utc_time + timedelta(hours=TIMEZONE_OFFSET_HOURS)
                hour = local_time.hour
                
                hourly_data[hour] = radiation if radiation is not None else 0
            
            print(f"  ✓ Fetched irradiation data for {date}")
            return hourly_data
        else:
            print(f"  ⚠️ Failed to fetch irradiation data: Status {response.status_code}")
            return {}
    except Exception as e:
        print(f"  ⚠️ Error fetching irradiation data: {e}")
        return {}

def calculate_system_degradation(config):
    """Calculate current system degradation factor based on age"""
    try:
        commissioning_date = datetime.strptime(config['system']['commissioning_date'], '%Y-%m-%d')
        # Use SAST time for consistency
        days_active = (get_sast_now().replace(tzinfo=None) - commissioning_date).days
        years_active = days_active / 365.25
        
        if years_active < 1:
            # First year: 1% degradation prorated
            degradation = config['system']['degradation']['year_1'] * years_active
        else:
            # After first year: 1% + 0.5% per additional year
            first_year_deg = config['system']['degradation']['year_1']
            subsequent_years = years_active - 1
            subsequent_deg = config['system']['degradation']['subsequent_years'] * subsequent_years
            degradation = first_year_deg + subsequent_deg
        
        degradation_factor = 1 - degradation
        print(f"  System age: {years_active:.2f} years, Degradation factor: {degradation_factor:.4f}")
        return degradation_factor
    except Exception as e:
        print(f"  ⚠️ Could not calculate degradation: {e}")
        return 1.0  # No degradation if error

def load_pvsyst_predictions():
    """Load daily hourly predictions from PVSyst data file (2025-2044 with Load, Grid, PV)"""
    try:
        # Try minified file first (smaller, faster)
        predictions_file = 'predictions_2025_2044.min.json'
        if os.path.exists(predictions_file):
            with open(predictions_file, 'r') as f:
                data = json.load(f)
            print(f"  ✓ Loaded predictions for {len(data['daily_predictions'])} days ({data.get('years', ['?'])[0]}-{data.get('years', ['?'])[-1]})")
            return data['daily_predictions']
        
        # Fallback to full file
        predictions_file = 'predictions_2025_2044.json'
        if os.path.exists(predictions_file):
            with open(predictions_file, 'r') as f:
                data = json.load(f)
            print(f"  ✓ Loaded predictions for {len(data['daily_predictions'])} days ({data.get('years', ['?'])[0]}-{data.get('years', ['?'])[-1]})")
            return data['daily_predictions']
        
        # Fallback to old filename
        predictions_file = 'pvsyst_predictions_2025.json'
        if os.path.exists(predictions_file):
            with open(predictions_file, 'r') as f:
                data = json.load(f)
            
            daily_preds = data.get('daily_predictions', data)
            
            # Detect format by checking first entry
            if daily_preds:
                first_key = list(daily_preds.keys())[0]
                first_value = daily_preds[first_key]
                
                if isinstance(first_value, dict) and 'pv_kw' in first_value:
                    print(f"  ✓ Loaded predictions for {len(daily_preds)} days (new format with Load/Grid)")
                else:
                    print(f"  ✓ Loaded predictions for {len(daily_preds)} days (legacy format)")
            
            return daily_preds
        
        print(f"  ⚠️ PVSyst predictions file not found, using config defaults")
        return None
        
    except Exception as e:
        print(f"  ⚠️ Error loading PVSyst predictions: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_hourly_predictions_for_date(date_str, pvsyst_data, config, degradation_factor=None):
    """Get hourly predictions for a specific date
    Returns dict with pv_kw, load_kw, grid_kw (if available)
    """
    # Try to get actual data for this date
    if pvsyst_data and date_str in pvsyst_data:
        data = pvsyst_data[date_str]
        
        # Check if it's the new format (dict with pv_kw, load_kw, grid_kw)
        if isinstance(data, dict) and 'pv_kw' in data:
            print(f"  ✓ Using predictions data for {date_str} (includes Load/Grid)")
            return {
                'pv_kw': data['pv_kw'],
                'load_kw': data.get('load_kw', [0]*24),
                'grid_kw': data.get('grid_kw', [0]*24)
            }
        # Old format (just PV array)
        elif isinstance(data, list):
            predictions = [p * (degradation_factor or 1.0) for p in data]
            print(f"  ✓ Using PVSyst data for {date_str} (legacy format)")
            return {
                'pv_kw': predictions,
                'load_kw': [0]*24,
                'grid_kw': [0]*24
            }
    
    # If not found, use the same month/day from 2025 as the pattern
    # Extract month and day from date_str (YYYY-MM-DD)
    parts = date_str.split('-')
    if len(parts) == 3:
        pattern_date = f"2025-{parts[1]}-{parts[2]}"
        if pvsyst_data and pattern_date in pvsyst_data:
            data = pvsyst_data[pattern_date]
            print(f"  ✓ Using 2025 pattern ({pattern_date}) for {date_str}")
            
            # Check format
            if isinstance(data, dict) and 'pv_kw' in data:
                predictions = data['pv_kw']
                load_predictions = data.get('load_kw', [0]*24)
                grid_predictions = data.get('grid_kw', [0]*24)
            else:
                predictions = data
                load_predictions = [0]*24
                grid_predictions = [0]*24
        else:
            # Final fallback to config average values
            predictions = config.get('hourly_predictions', {}).get('year_1_kwh', [0] * 24)
            load_predictions = [0]*24
            grid_predictions = [0]*24
            print(f"  ⚠️ Using config defaults for {date_str} (no pattern data)")
    else:
        # Fallback to config average values
        predictions = config.get('hourly_predictions', {}).get('year_1_kwh', [0] * 24)
        load_predictions = [0]*24
        grid_predictions = [0]*24
        print(f"  ⚠️ Using config defaults for {date_str} (invalid date format)")
    
    # Apply degradation if needed (for old format or pattern-based predictions)
    if degradation_factor:
        degraded_predictions = [pred * degradation_factor for pred in predictions]
    else:
        degraded_predictions = predictions
        
    return {
        'pv_kw': degraded_predictions,
        'load_kw': load_predictions,
        'grid_kw': grid_predictions
    }

def process_solar_data():
    """Process the downloaded solar data and calculate all metrics"""
    
    config = load_config()
    
    # Find the latest export file
    latest_file = 'data/solar_export_latest.xls'
    
    if not os.path.exists(latest_file):
        print("No data file found!")
        return
    
    print(f"Processing {latest_file}...")
    
    # Read the Excel file, skipping to row 29 (0-indexed = 28)
    df = pd.read_excel(latest_file, header=28, engine='xlrd')
    
    # Select and rename columns
    df = df.rename(columns={
        'Time': 'time',
        'PV(W)': 'pv_w',
        'Grid(W)': 'grid_w',
        'Load(W)': 'load_w'
    })
    
    # Keep only relevant columns
    df = df[['time', 'pv_w', 'grid_w', 'load_w']].copy()
    
    # Convert all values from text to numbers
    df['pv_w'] = df['pv_w'].apply(convert_to_number)
    df['grid_w'] = df['grid_w'].apply(convert_to_number)
    df['load_w'] = df['load_w'].apply(convert_to_number)
    
    # Remove rows where time is empty
    df = df[df['time'].notna()].copy()
    
    # Convert watts to kilowatts
    df['pv_kw'] = df['pv_w'] / 1000
    df['grid_kw'] = df['grid_w'] / 1000
    df['load_kw'] = df['load_w'] / 1000
    
    # Calculate generation (5-minute intervals)
    df['generation_kwh'] = df['pv_kw'] * (5/60)
    
    # Calculate daily totals
    today_generation = df['generation_kwh'].sum()
    today_pv_avg = df['pv_kw'].mean()
    today_pv_max = df['pv_kw'].max()
    
    print(f"Today's Generation: {today_generation:.2f} kWh")
    
    # Fetch today's irradiation data EARLY (needed for daily records)
    today_date = get_sast_now().strftime('%Y-%m-%d')
    print("Fetching irradiation data...")
    irradiation_data = fetch_irradiation_data(today_date)
    
    # Calculate daily irradiation total (Wh/m²)
    daily_irradiation_total = sum(irradiation_data.values())
    print(f"  Daily irradiation total: {daily_irradiation_total:.0f} Wh/m²")
    
    # Load historical data
    history_file = 'data/generation_history.json'
    if os.path.exists(history_file):
        with open(history_file, 'r') as f:
            history = json.load(f)
    else:
        history = {
            'daily_records': [],
            'hourly_records': {},  # Store last 7 days of hourly data
            'monthly_total': 0,
            'total_generation': 0,
            'current_month': get_sast_now().strftime('%Y-%m')
        }
    
    # Check if new month (use SAST time)
    current_month = get_sast_now().strftime('%Y-%m')
    if history['current_month'] != current_month:
        history['monthly_total'] = 0
        history['current_month'] = current_month
    
    # Find and update today's record
    existing_record = None
    for record in history['daily_records']:
        if record['date'] == today_date:
            existing_record = record
            break
    
    if existing_record:
        old_generation = existing_record['generation_kwh']
        existing_record['generation_kwh'] = today_generation
        existing_record['irradiation_wh_m2'] = daily_irradiation_total
        existing_record['updated_at'] = get_sast_now().isoformat()
        
        history['monthly_total'] += (today_generation - old_generation)
        history['total_generation'] += (today_generation - old_generation)
    else:
        history['daily_records'].append({
            'date': today_date,
            'generation_kwh': today_generation,
            'irradiation_wh_m2': daily_irradiation_total,
            'updated_at': get_sast_now().isoformat()
        })
        history['monthly_total'] += today_generation
        history['total_generation'] += today_generation
    
    # Keep only last 365 days
    history['daily_records'] = sorted(history['daily_records'], key=lambda x: x['date'])[-365:]
    
    # Load PVSyst predictions and calculate degradation
    pvsyst_predictions = load_pvsyst_predictions()
    degradation_factor = calculate_system_degradation(config)
    
    # Calculate BASE monthly predictions FIRST (without year-specific degradation)
    # These are reusable for any year - just apply the year's degradation factor
    print("  Calculating base monthly predictions (2025 pattern)...")
    monthly_predictions_base = {}
    
    for month_num in range(1, 13):
        days_in_month = calendar.monthrange(2025, month_num)[1]
        month_expected_raw = 0  # Without degradation
        
        for day in range(1, days_in_month + 1):
            date_str = f"2025-{month_num:02d}-{day:02d}"
            if pvsyst_predictions and date_str in pvsyst_predictions:
                # Sum raw PVSyst data WITHOUT degradation
                data = pvsyst_predictions[date_str]
                # Handle new format (dict with pv_kw) or old format (array)
                if isinstance(data, dict) and 'pv_kw' in data:
                    month_expected_raw += sum(data['pv_kw'])
                elif isinstance(data, list):
                    month_expected_raw += sum(data)
                else:
                    print(f"  ⚠️ Unexpected data format for {date_str}")
        
        month_key = f"{month_num:02d}"  # Just "01", "02", etc. - works for any year
        monthly_predictions_base[month_key] = {
            'month_name': calendar.month_name[month_num],
            'base_kwh': round(month_expected_raw, 2),  # Raw PVSyst prediction
            'avg_daily_kwh': round(month_expected_raw / days_in_month, 2),  # Average daily for this month
            'days': days_in_month
        }
    
    annual_base = sum(m['base_kwh'] for m in monthly_predictions_base.values())
    print(f"  ✓ Calculated base predictions for 12 months (annual base: {annual_base:.2f} kWh)")
    
    # Calculate expected values from actual PVSyst predictions OR monthly averages
    sast_now = get_sast_now()
    year = sast_now.year
    month = sast_now.month
    today_month_key = f"{month:02d}"
    
    # Get today's expected using monthly average with degradation
    if today_month_key in monthly_predictions_base:
        expected_daily_kwh = monthly_predictions_base[today_month_key]['avg_daily_kwh'] * degradation_factor
        print(f"  ✓ Using monthly average for today's expected: {expected_daily_kwh:.2f} kWh")
    else:
        # Fallback if no prediction data
        today_hourly_predictions_data = get_hourly_predictions_for_date(today_date, pvsyst_predictions, config, degradation_factor)
        expected_daily_kwh = sum(today_hourly_predictions_data['pv_kw'])
        print(f"  ⚠️ Using hourly fallback for today's expected: {expected_daily_kwh:.2f} kWh")
    
    # Calculate monthly expected by using monthly base prediction with degradation
    days_in_month_calc = calendar.monthrange(year, month)[1]
    
    if today_month_key in monthly_predictions_base:
        expected_monthly_kwh = monthly_predictions_base[today_month_key]['base_kwh'] * degradation_factor
        print(f"  ✓ Using monthly base for expected: {expected_monthly_kwh:.2f} kWh")
    else:
        # Fallback: sum daily predictions
        expected_monthly_kwh = 0
        for day in range(1, days_in_month_calc + 1):
            date_str = f"{year}-{month:02d}-{day:02d}"
            day_predictions_data = get_hourly_predictions_for_date(date_str, pvsyst_predictions, config, degradation_factor)
            expected_monthly_kwh += sum(day_predictions_data['pv_kw'])
        print(f"  ⚠️ Using daily sum fallback for monthly expected: {expected_monthly_kwh:.2f} kWh")
    
    # Calculate performance ratios
    daily_performance = (today_generation / expected_daily_kwh * 100) if expected_daily_kwh > 0 else 0
    monthly_performance = (history['monthly_total'] / expected_monthly_kwh * 100) if expected_monthly_kwh > 0 else 0
    
    # Environmental impact calculations
    def calculate_env_impact(generation_kwh):
        """Calculate environmental impact based on generation"""
        factors = config['environmental_factors']
        co2_offset = generation_kwh * factors['co2_per_kwh']
        
        return {
            'co2_offset_tons': co2_offset / 1000,
            'trees_equivalent': generation_kwh / factors['trees_per_kwh'],
            'households_offset': generation_kwh / factors['households_kwh_per_year'],
            'km_driven_offset': co2_offset / factors['co2_per_km_driven'],
            'km_flown_offset': co2_offset / factors['co2_per_km_flown'],
            'coal_saved_kg': co2_offset * factors['coal_per_kwh'],
            'water_saved_litres': generation_kwh * factors['water_per_kwh']
        }
    
    # Calculate environmental impacts
    env_impact_today = calculate_env_impact(today_generation)
    env_impact_monthly = calculate_env_impact(history['monthly_total'])
    env_impact_lifetime = calculate_env_impact(history['total_generation'])
    
    # Get yesterday's data from history (use SAST time)
    yesterday_date = (get_sast_now() - timedelta(days=1)).strftime('%Y-%m-%d')
    yesterday_record = next((r for r in history['daily_records'] if r['date'] == yesterday_date), None)
    
    if yesterday_record:
        yesterday_generation = yesterday_record['generation_kwh']
        env_impact_yesterday = calculate_env_impact(yesterday_generation)
    else:
        # Fallback if no yesterday data exists
        yesterday_generation = 0
        env_impact_yesterday = calculate_env_impact(0)
    
    # Calculate system degradation
    degradation_factor = calculate_system_degradation(config)
    
    # Load PVSyst daily predictions
    pvsyst_data = load_pvsyst_predictions()
    
    # Get hourly predictions for today (includes PV, Load, Grid)
    predictions_data = get_hourly_predictions_for_date(today_date, pvsyst_data, config, degradation_factor)
    
    # Prepare hourly data with PV generation, predicted values, irradiation, load, and grid
    hourly_data = []
    
    # Group PV data by hour
    df['hour'] = pd.to_datetime(df['time']).dt.hour
    hourly_pv = df.groupby('hour')['pv_kw'].mean().to_dict()
    
    for hour in range(24):
        hourly_data.append({
            'hour': hour,
            'time': f"{hour:02d}:00",
            'pv_kw': round(hourly_pv.get(hour, 0), 2),
            'predicted_kw': round(predictions_data['pv_kw'][hour], 2) if hour < len(predictions_data['pv_kw']) else 0,
            'predicted_load_kw': round(predictions_data['load_kw'][hour], 2) if hour < len(predictions_data['load_kw']) else 0,
            'predicted_grid_kw': round(predictions_data['grid_kw'][hour], 2) if hour < len(predictions_data['grid_kw']) else 0,
            'irradiation_wm2': irradiation_data.get(hour, 0)
        })
    
    # Store hourly data for last 7 days
    if 'hourly_records' not in history:
        history['hourly_records'] = {}
    
    history['hourly_records'][today_date] = hourly_data
    
    # Keep only last 7 days of hourly data
    all_dates = sorted(history['hourly_records'].keys())
    if len(all_dates) > 7:
        dates_to_remove = all_dates[:-7]
        for old_date in dates_to_remove:
            del history['hourly_records'][old_date]
    
    print(f"  ✓ Stored hourly data (keeping last 7 days, current: {len(history['hourly_records'])} days)")

    # Create dashboard data
    dashboard_data = {
        'last_updated': get_sast_now().isoformat(),
        'yesterday': {
            'date': yesterday_date,
            'generation_kwh': round(yesterday_generation, 2),
            'env_impact': {k: round(v, 2) for k, v in env_impact_yesterday.items()}
        },
        'today': {
            'date': today_date,
            'generation_kwh': round(today_generation, 2),
            'expected_kwh': round(expected_daily_kwh, 2),
            'performance_percent': round(daily_performance, 1),
            'avg_power_kw': round(today_pv_avg, 2),
            'peak_power_kw': round(today_pv_max, 2),
            'env_impact': {k: round(v, 2) for k, v in env_impact_today.items()}
        },
        'month': {
            'generation_kwh': round(history['monthly_total'], 2),
            'expected_kwh': round(expected_monthly_kwh, 2),
            'performance_percent': round(monthly_performance, 1),
            'month_name': get_sast_now().strftime('%B %Y'),
            'env_impact': {k: round(v, 2) for k, v in env_impact_monthly.items()}
        },
        'lifetime': {
            'total_generation_kwh': round(history['total_generation'], 2),
            'total_generation_mwh': round(history['total_generation'] / 1000, 2),
            'days_active': len(history['daily_records']),
            'env_impact': {k: round(v, 2) for k, v in env_impact_lifetime.items()}
        },
        'system': {
            'installed_capacity_kwp': config['system']['installed_capacity_kwp'],
            'plant_name': config['system']['plant_name'],
            'commissioning_date': config['system']['commissioning_date'],
            'degradation_year_1': config['system']['degradation']['year_1'],
            'degradation_subsequent_years': config['system']['degradation']['subsequent_years']
        },
        'monthly_predictions_base': monthly_predictions_base,
        'recent_days': history['daily_records'][-30:]
    }
    
    # Save files
    with open(history_file, 'w') as f:
        json.dump(history, f, indent=2)
    
    with open('data/dashboard_data.json', 'w') as f:
        json.dump(dashboard_data, f, indent=2)
    
    # Save today's detailed hourly data (with irradiation and predictions)
    with open('data/today_detailed.json', 'w') as f:
        json.dump(hourly_data, f, indent=2)
    
    print("✅ Data processing completed!")
    print(f"  - Today: {today_generation:.2f} kWh ({daily_performance:.1f}% of expected)")
    print(f"  - This Month: {history['monthly_total']:.2f} kWh")
    print(f"  - Total: {history['total_generation']:.2f} kWh")
    print(f"  - CO₂ Offset: {env_impact_lifetime['co2_offset_tons']:.2f} tons")

if __name__ == "__main__":
    process_solar_data()
