import pandas as pd
import json
from datetime import datetime, timedelta
import calendar
import os
import glob

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
    
    # Load historical data
    history_file = 'data/generation_history.json'
    if os.path.exists(history_file):
        with open(history_file, 'r') as f:
            history = json.load(f)
    else:
        history = {
            'daily_records': [],
            'monthly_total': 0,
            'total_generation': 0,
            'current_month': datetime.now().strftime('%Y-%m')
        }
    
    # Check if new month
    current_month = datetime.now().strftime('%Y-%m')
    if history['current_month'] != current_month:
        history['monthly_total'] = 0
        history['current_month'] = current_month
    
    # Update totals
    today_date = datetime.now().strftime('%Y-%m-%d')
    
    existing_record = None
    for record in history['daily_records']:
        if record['date'] == today_date:
            existing_record = record
            break
    
    if existing_record:
        old_generation = existing_record['generation_kwh']
        existing_record['generation_kwh'] = today_generation
        existing_record['updated_at'] = datetime.now().isoformat()
        
        history['monthly_total'] += (today_generation - old_generation)
        history['total_generation'] += (today_generation - old_generation)
    else:
        history['daily_records'].append({
            'date': today_date,
            'generation_kwh': today_generation,
            'updated_at': datetime.now().isoformat()
        })
        history['monthly_total'] += today_generation
        history['total_generation'] += today_generation
    
    # Keep only last 365 days
    history['daily_records'] = sorted(history['daily_records'], key=lambda x: x['date'])[-365:]
    
    # Get predicted values from config
    expected_daily_kwh = config['predicted_generation']['daily_kwh']
    
    # Get monthly target based on current month
    current_month_name = datetime.now().strftime('%B').lower()
    monthly_targets = config['predicted_generation']['monthly_targets']
    expected_monthly_kwh = monthly_targets.get(current_month_name, config['predicted_generation']['monthly_kwh'])
    
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
    
    env_impact_today = calculate_env_impact(today_generation)
    env_impact_monthly = calculate_env_impact(history['monthly_total'])
    env_impact_lifetime = calculate_env_impact(history['total_generation'])
    
    # Calculate days in current month
    days_in_month = (datetime.now().replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    days_in_current_month = days_in_month.day
    
    # Get current year for leap year calculation
    current_year = datetime.now().year
    
    # Calculate environmental impacts with correct time periods (accounting for leap years)
    env_impact_today = calculate_env_impact(today_generation, days=1, year=current_year)
    env_impact_monthly = calculate_env_impact(history['monthly_total'], days=days_in_current_month, year=current_year)
    env_impact_lifetime = calculate_env_impact(history['total_generation'], days=len(history['daily_records']), year=current_year)
    
    # Create dashboard data
    dashboard_data = {
        'last_updated': datetime.now().isoformat(),
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
            'month_name': datetime.now().strftime('%B %Y'),
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
            'plant_name': config['system']['plant_name']
        },
        'recent_days': history['daily_records'][-30:]
    }
    
    # Save files
    with open(history_file, 'w') as f:
        json.dump(history, f, indent=2)
    
    with open('data/dashboard_data.json', 'w') as f:
        json.dump(dashboard_data, f, indent=2)
    
    # Save detailed data
    chart_data = df[['time', 'pv_kw', 'grid_kw', 'load_kw']].to_dict('records')
    with open('data/today_detailed.json', 'w') as f:
        json.dump(chart_data, f, indent=2)
    
    print("✅ Data processing completed!")
    print(f"  - Today: {today_generation:.2f} kWh ({daily_performance:.1f}% of expected)")
    print(f"  - This Month: {history['monthly_total']:.2f} kWh")
    print(f"  - Total: {history['total_generation']:.2f} kWh")
    print(f"  - CO₂ Offset: {env_impact_lifetime['co2_offset_tons']:.2f} tons")

if __name__ == "__main__":
    process_solar_data()
