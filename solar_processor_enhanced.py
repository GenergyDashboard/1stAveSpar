#!/usr/bin/env python3
"""
Enhanced Solar Data Processor with TOU and Financial Analysis
Processes hourly solar generation data with Time-of-Use classification and financial calculations

CORRECTED VERSION - Based on Book2.xlsx
High-demand season (June-Aug) shifts peak/standard times 1 hour EARLIER compared to Low-demand season
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import openpyxl

# ============================================================================
# TOU Configuration - CORRECTED FROM Book2.xlsx
# ============================================================================

# TOU Time Periods (Based on Book2.xlsx with proper seasonal differences)
# High-demand season (June-Aug) shifts peak/standard times 1 hour EARLIER compared to Low-demand
# Weekday pattern: High-demand starts morning peak at 6am (vs 7am), evening peak at 5pm (vs 6pm)
TOU_SCHEDULE = {
    'high_season': {  # June, July, August (Winter)
        'weekday': {  # Monday-Friday
            'peak': [(6, 8), (17, 20)],      # 06:00-08:00, 17:00-20:00 (hours 6,7 and 17,18,19)
            'standard': [(8, 17), (20, 22)],  # 08:00-17:00, 20:00-22:00 (hours 8-16 and 20,21)
            'off_peak': [(0, 6), (22, 24)]    # 00:00-06:00, 22:00-24:00 (hours 0-5 and 22,23)
        },
        'saturday': {
            'peak': [],
            'standard': [(7, 12), (17, 19)],  # 07:00-12:00, 17:00-19:00 (hours 7-11 and 17,18)
            'off_peak': [(0, 7), (12, 17), (19, 24)]  # Rest of the day
        },
        'sunday': {
            'peak': [],
            'standard': [(17, 19)],           # 17:00-19:00 (hours 17,18) - 2-hour standard period
            'off_peak': [(0, 17), (19, 24)]   # Rest of the day
        }
    },
    'low_season': {  # All other months
        'weekday': {  # Monday-Friday
            'peak': [(7, 9), (18, 21)],      # 07:00-09:00, 18:00-21:00 (hours 7,8 and 18,19,20)
            'standard': [(6, 7), (9, 18), (21, 22)],  # 06:00-07:00, 09:00-18:00, 21:00-22:00 (hours 6, 9-17, 21)
            'off_peak': [(0, 6), (22, 24)]    # 00:00-06:00, 22:00-24:00 (hours 0-5 and 22,23)
        },
        'saturday': {
            'peak': [],
            'standard': [(7, 12), (18, 20)],  # 07:00-12:00, 18:00-20:00 (hours 7-11 and 18,19)
            'off_peak': [(0, 7), (12, 18), (20, 24)]  # Rest of the day
        },
        'sunday': {
            'peak': [],
            'standard': [(18, 20)],           # 18:00-20:00 (hours 18,19) - 2-hour standard period
            'off_peak': [(0, 18), (20, 24)]   # Rest of the day
        }
    }
}

# High season months (winter in South Africa)
HIGH_SEASON_MONTHS = [6, 7, 8]

# TOU Rates (from uploaded image - effective dates)
# Format: {effective_date: {high_season: {peak, standard, off_peak}, low_season: {...}}}
TOU_RATES = [
    {
        'effective_date': '2023-07-01',
        'high_season': {'peak': 9.69, 'standard': 2.79, 'off_peak': 2.02},
        'low_season': {'peak': 4.21, 'standard': 2.64, 'off_peak': 2.00}
    },
    {
        'effective_date': '2024-07-01',
        'high_season': {'peak': 9.69, 'standard': 2.79, 'off_peak': 2.02},
        'low_season': {'peak': 4.21, 'standard': 2.64, 'off_peak': 2.00}
    },
    {
        'effective_date': '2025-07-01',
        'high_season': {'peak': 17.15, 'standard': 4.94, 'off_peak': 3.57},
        'low_season': {'peak': 7.46, 'standard': 4.67, 'off_peak': 3.55}
    },
    # Add more as rates change
]

def get_tou_rate(date, period_type, season_type='high'):
    """Get the TOU rate for a specific date and period"""
    # Find the applicable rate period
    applicable_rate = TOU_RATES[0]  # Default to first
    
    for rate in TOU_RATES:
        rate_date = datetime.strptime(rate['effective_date'], '%Y-%m-%d').date()
        if date >= rate_date:
            applicable_rate = rate
    
    # Return the rate for the specified season and period
    season_rates = applicable_rate[f'{season_type}_season']
    return season_rates.get(period_type, 0)

def classify_tou_period(dt):
    """
    Classify a datetime into TOU period (peak, standard, off_peak)
    
    Args:
        dt: datetime object
        
    Returns:
        tuple: (period_type, season_type) e.g. ('peak', 'high')
    """
    hour = dt.hour
    month = dt.month
    weekday = dt.weekday()  # 0=Monday, 6=Sunday
    
    # Determine season
    season = 'high' if month in HIGH_SEASON_MONTHS else 'low'
    
    # Determine day type - CORRECTED to differentiate Saturday and Sunday
    if weekday == 6:  # Sunday
        day_type = 'sunday'
    elif weekday == 5:  # Saturday
        day_type = 'saturday'
    else:  # Monday-Friday
        day_type = 'weekday'
    
    # Get schedule for this season and day type
    schedule = TOU_SCHEDULE[f'{season}_season'][day_type]
    
    # Classify hour
    for period_type in ['peak', 'standard', 'off_peak']:
        time_ranges = schedule[period_type]
        for start_hour, end_hour in time_ranges:
            if start_hour <= hour < end_hour:
                return (period_type, season)
    
    # Default to off_peak if not found (shouldn't happen)
    return ('off_peak', season)

# ============================================================================
# Data Processing Functions
# ============================================================================

def process_hourly_data(hourly_data, date):
    """
    Process hourly data to extract actual Load, Grid, and calculate TOU breakdown
    
    Args:
        hourly_data: List of hourly records
        date: Date string (YYYY-MM-DD)
        
    Returns:
        dict: Enhanced hourly data with TOU classification and financial calculations
    """
    date_obj = datetime.strptime(date, '%Y-%m-%d').date()
    
    # Initialize totals
    totals = {
        'actual_load_kwh': 0,
        'actual_grid_kwh': 0,
        'tou_breakdown': {
            'peak_kwh': 0,
            'standard_kwh': 0,
            'off_peak_kwh': 0
        },
        'financial': {
            'total_savings_zar': 0,
            'peak_savings_zar': 0,
            'standard_savings_zar': 0,
            'off_peak_savings_zar': 0
        }
    }
    
    enhanced_hourly = []
    
    for record in hourly_data:
        # Parse time
        time_str = record.get('time', '00:00')
        try:
            hour = int(time_str.split(':')[0])
            minute = int(time_str.split(':')[1])
            dt = datetime.combine(date_obj, datetime.min.time().replace(hour=hour, minute=minute))
        except:
            continue
        
        # Extract values (already in kW from scraper)
        generation_kw = record.get('generation_kw', 0)
        grid_kw = record.get('grid_kw', 0)  # Negative when drawing from grid
        load_kw = record.get('load_kw', 0)
        
        # Classify TOU period
        period_type, season_type = classify_tou_period(dt)
        
        # Get rate
        rate = get_tou_rate(date_obj, period_type, season_type)
        
        # Calculate savings (generation * rate)
        # This is how much you would have paid if you drew this from grid
        savings_zar = generation_kw * rate
        
        # Add to totals
        totals['actual_load_kwh'] += load_kw
        totals['actual_grid_kwh'] += abs(grid_kw)  # Absolute value for total drawn
        totals['tou_breakdown'][f'{period_type}_kwh'] += generation_kw
        totals['financial'][f'{period_type}_savings_zar'] += savings_zar
        totals['financial']['total_savings_zar'] += savings_zar
        
        # Enhance record
        enhanced_record = {
            **record,
            'tou_period': period_type,
            'tou_season': season_type,
            'tou_rate': rate,
            'savings_zar': round(savings_zar, 2)
        }
        enhanced_hourly.append(enhanced_record)
    
    return enhanced_hourly, totals

def aggregate_monthly_data(daily_records):
    """
    Aggregate daily records into monthly summaries with TOU and financial data
    
    Args:
        daily_records: List of daily record dictionaries
        
    Returns:
        dict: Monthly summaries keyed by 'YYYY-MM'
    """
    monthly_summaries = {}
    
    for record in daily_records:
        date = record['date']
        month_key = date[:7]  # 'YYYY-MM'
        
        if month_key not in monthly_summaries:
            monthly_summaries[month_key] = {
                'total_generation_kwh': 0,
                'actual_load_kwh': 0,
                'actual_grid_kwh': 0,
                'days_with_data': 0,
                'tou_breakdown': {
                    'peak_kwh': 0,
                    'standard_kwh': 0,
                    'off_peak_kwh': 0
                },
                'financial': {
                    'total_savings_zar': 0,
                    'peak_savings_zar': 0,
                    'standard_savings_zar': 0,
                    'off_peak_savings_zar': 0
                }
            }
        
        month_data = monthly_summaries[month_key]
        month_data['total_generation_kwh'] += record.get('generation_kwh', 0)
        month_data['actual_load_kwh'] += record.get('actual_load_kwh', 0)
        month_data['actual_grid_kwh'] += record.get('actual_grid_kwh', 0)
        month_data['days_with_data'] += 1
        
        # TOU breakdown
        if 'tou_breakdown' in record:
            for period in ['peak', 'standard', 'off_peak']:
                month_data['tou_breakdown'][f'{period}_kwh'] += record['tou_breakdown'].get(f'{period}_kwh', 0)
        
        # Financial
        if 'financial' in record:
            for key in ['total_savings_zar', 'peak_savings_zar', 'standard_savings_zar', 'off_peak_savings_zar']:
                month_data['financial'][key] += record['financial'].get(key, 0)
    
    # Round financial values
    for month_key in monthly_summaries:
        for key in monthly_summaries[month_key]['financial']:
            monthly_summaries[month_key]['financial'][key] = round(monthly_summaries[month_key]['financial'][key], 2)
    
    return monthly_summaries

def calculate_lifetime_summary(daily_records):
    """
    Calculate lifetime summary with TOU and financial data
    
    Args:
        daily_records: List of daily record dictionaries
        
    Returns:
        dict: Lifetime summary statistics
    """
    summary = {
        'total_generation_kwh': 0,
        'actual_load_kwh': 0,
        'actual_grid_kwh': 0,
        'days_active': len(daily_records),
        'tou_breakdown': {
            'peak_kwh': 0,
            'standard_kwh': 0,
            'off_peak_kwh': 0
        },
        'financial': {
            'total_savings_zar': 0,
            'peak_savings_zar': 0,
            'standard_savings_zar': 0,
            'off_peak_savings_zar': 0,
            'by_year': {},
            'by_month': {}
        }
    }
    
    for record in daily_records:
        summary['total_generation_kwh'] += record.get('generation_kwh', 0)
        summary['actual_load_kwh'] += record.get('actual_load_kwh', 0)
        summary['actual_grid_kwh'] += record.get('actual_grid_kwh', 0)
        
        # TOU breakdown
        if 'tou_breakdown' in record:
            for period in ['peak', 'standard', 'off_peak']:
                summary['tou_breakdown'][f'{period}_kwh'] += record['tou_breakdown'].get(f'{period}_kwh', 0)
        
        # Financial by year
        year = record['date'][:4]
        if year not in summary['financial']['by_year']:
            summary['financial']['by_year'][year] = 0
        
        # Financial by month
        month_key = record['date'][:7]
        if month_key not in summary['financial']['by_month']:
            summary['financial']['by_month'][month_key] = 0
        
        if 'financial' in record:
            daily_savings = record['financial'].get('total_savings_zar', 0)
            
            summary['financial']['total_savings_zar'] += daily_savings
            summary['financial']['by_year'][year] += daily_savings
            summary['financial']['by_month'][month_key] += daily_savings
            
            for key in ['peak_savings_zar', 'standard_savings_zar', 'off_peak_savings_zar']:
                summary['financial'][key] += record['financial'].get(key, 0)
    
    # Round financial values
    summary['financial']['total_savings_zar'] = round(summary['financial']['total_savings_zar'], 2)
    for key in ['peak_savings_zar', 'standard_savings_zar', 'off_peak_savings_zar']:
        summary['financial'][key] = round(summary['financial'][key], 2)
    
    for year in summary['financial']['by_year']:
        summary['financial']['by_year'][year] = round(summary['financial']['by_year'][year], 2)
    
    for month in summary['financial']['by_month']:
        summary['financial']['by_month'][month] = round(summary['financial']['by_month'][month], 2)
    
    return summary

# ============================================================================
# Main Processing Pipeline
# ============================================================================

def enhance_dashboard_data(input_file, output_file=None):
    """
    Enhance existing dashboard data with TOU and financial calculations
    
    Args:
        input_file: Path to dashboard_data.json
        output_file: Path to output file (defaults to input_file)
    """
    if output_file is None:
        output_file = input_file
    
    # Load existing data
    with open(input_file, 'r') as f:
        data = json.load(f)
    
    print(f"Processing {len(data.get('daily_records', []))} daily records...")
    
    # Process each daily record
    enhanced_daily_records = []
    for record in data.get('daily_records', []):
        date = record['date']
        hourly_data = record.get('hourly_data', [])
        
        # Process hourly data
        enhanced_hourly, totals = process_hourly_data(hourly_data, date)
        
        # Update record
        enhanced_record = {
            **record,
            'actual_load_kwh': round(totals['actual_load_kwh'], 2),
            'actual_grid_kwh': round(totals['actual_grid_kwh'], 2),
            'tou_breakdown': {
                'peak_kwh': round(totals['tou_breakdown']['peak_kwh'], 2),
                'standard_kwh': round(totals['tou_breakdown']['standard_kwh'], 2),
                'off_peak_kwh': round(totals['tou_breakdown']['off_peak_kwh'], 2)
            },
            'financial': totals['financial'],
            'hourly_data': enhanced_hourly
        }
        
        enhanced_daily_records.append(enhanced_record)
        print(f"  {date}: Gen={record.get('generation_kwh', 0):.1f} kWh, Savings=R{totals['financial']['total_savings_zar']:.2f}")
    
    # Calculate monthly summaries
    print("\nAggregating monthly summaries...")
    monthly_summaries = aggregate_monthly_data(enhanced_daily_records)
    
    for month_key, month_data in sorted(monthly_summaries.items()):
        print(f"  {month_key}: Gen={month_data['total_generation_kwh']:.1f} kWh, Savings=R{month_data['financial']['total_savings_zar']:.2f}")
    
    # Calculate lifetime summary
    print("\nCalculating lifetime summary...")
    lifetime_summary = calculate_lifetime_summary(enhanced_daily_records)
    print(f"  Total Savings: R{lifetime_summary['financial']['total_savings_zar']:,.2f}")
    print(f"  Peak: R{lifetime_summary['financial']['peak_savings_zar']:,.2f}")
    print(f"  Standard: R{lifetime_summary['financial']['standard_savings_zar']:,.2f}")
    print(f"  Off-Peak: R{lifetime_summary['financial']['off_peak_savings_zar']:,.2f}")
    
    # Update data structure
    data['daily_records'] = enhanced_daily_records
    data['monthly_summaries'] = monthly_summaries
    data['lifetime_summary'] = lifetime_summary
    data['tou_rates'] = TOU_RATES
    
    # Update top-level summaries (today, yesterday, month, lifetime) for dashboard compatibility
    from datetime import date as date_class
    today_str = date_class.today().strftime('%Y-%m-%d')
    yesterday_str = (date_class.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    current_month = date_class.today().strftime('%Y-%m')
    
    # Find today's record
    today_record = next((r for r in enhanced_daily_records if r['date'] == today_str), None)
    yesterday_record = next((r for r in enhanced_daily_records if r['date'] == yesterday_str), None)
    
    if today_record:
        data['today'] = {
            'date': today_str,
            'generation_kwh': today_record['generation_kwh'],
            'expected_kwh': today_record.get('expected_kwh', 0),
            'performance_percent': today_record.get('performance_percent', 0),
            'avg_power_kw': today_record.get('avg_power_kw', 0),
            'peak_power_kw': today_record.get('peak_power_kw', 0),
            'env_impact': today_record.get('env_impact', {})
        }
    
    if yesterday_record:
        data['yesterday'] = {
            'date': yesterday_str,
            'generation_kwh': yesterday_record['generation_kwh'],
            'env_impact': yesterday_record.get('env_impact', {})
        }
    
    # Update current month summary
    if current_month in monthly_summaries:
        month_data = monthly_summaries[current_month]
        data['month'] = {
            'generation_kwh': month_data['total_generation_kwh'],
            'expected_kwh': month_data.get('expected_kwh', 0),
            'performance_percent': month_data.get('performance_percent', 0),
            'month_name': datetime.strptime(current_month, '%Y-%m').strftime('%B %Y'),
            'env_impact': month_data.get('env_impact', {})
        }
    
    # Update lifetime summary
    data['lifetime'] = {
        'total_generation_kwh': lifetime_summary['total_generation_kwh'],
        'total_generation_mwh': lifetime_summary['total_generation_kwh'] / 1000,
        'env_impact': lifetime_summary.get('env_impact', {})
    }
    
    # Save enhanced data
    print(f"\nSaving enhanced data to {output_file}...")
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    print("✓ Processing complete!")
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Daily records processed: {len(enhanced_daily_records)}")
    print(f"Monthly summaries: {len(monthly_summaries)}")
    print(f"Total lifetime generation: {lifetime_summary['total_generation_kwh']:,.1f} kWh")
    print(f"Total lifetime savings: R{lifetime_summary['financial']['total_savings_zar']:,.2f}")
    print(f"{'='*80}")

if __name__ == '__main__':
    # Auto-detect dashboard_data.json location
    if len(sys.argv) >= 2:
        input_file = sys.argv[1]
    else:
        # Try common locations
        possible_locations = [
            'dashboard_data.json',
            '../dashboard_data.json',
            '../../dashboard_data.json',
            './data/dashboard_data.json',
        ]
        
        input_file = None
        for location in possible_locations:
            if os.path.exists(location):
                input_file = location
                print(f"Found dashboard_data.json at: {location}")
                break
        
        if input_file is None:
            print("Error: Could not find dashboard_data.json")
            print("\nUsage: python3 solar_processor_enhanced.py <path_to_dashboard_data.json>")
            print("\nOr place this script in the same directory as dashboard_data.json")
            sys.exit(1)
    
    if not os.path.exists(input_file):
        print(f"Error: File not found: {input_file}")
        sys.exit(1)
    
    enhance_dashboard_data(input_file)
