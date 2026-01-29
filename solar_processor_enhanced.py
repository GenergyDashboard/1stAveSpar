#!/usr/bin/env python3
"""
Solar Data Processor - Enhanced with TOU and Financial Calculations
Updates dashboard_data.json with Time-of-Use breakdown and correct financial savings

CRITICAL: Uses correct savings formula:
- Savings = (Generation × TOU_rate) - (Generation × PPA_rate)
- NOT just Generation × TOU_rate
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Constants
TOU_RATES = {
    'peak': 4.68,       # Eskom peak rate (ZAR/kWh)
    'standard': 3.38,   # Eskom standard rate
    'off_peak': 2.07    # Eskom off-peak rate
}

PPA_RATE = 1.50  # Solar PPA rate (ZAR/kWh)


def get_tou_period(date_str, hour, minute=0):
    """
    Determine TOU period for a given datetime
    
    Args:
        date_str: Date in format "YYYY-MM-DD"
        hour: Hour (0-23)
        minute: Minute (0-59)
    
    Returns:
        str: 'peak', 'standard', or 'off_peak'
    """
    date = datetime.strptime(date_str, '%Y-%m-%d')
    day_of_week = date.weekday()  # 0 = Monday, 6 = Sunday
    month = date.month
    
    # Weekend check (Saturday=5, Sunday=6)
    is_weekend = day_of_week >= 5
    
    # Summer: September (9) to April (4)
    is_summer = month >= 9 or month <= 4
    
    # Decimal hour for easier comparison
    decimal_hour = hour + (minute / 60)
    
    # Weekends: All Off-Peak
    if is_weekend:
        return 'off_peak'
    
    # Weekdays
    if is_summer:
        # Summer (Sept - April) - Weekdays
        if (7 <= decimal_hour < 10) or (18 <= decimal_hour < 20):
            return 'peak'
        elif (6 <= decimal_hour < 7) or (10 <= decimal_hour < 18) or (20 <= decimal_hour < 22):
            return 'standard'
        else:
            return 'off_peak'
    else:
        # Winter (May - Aug) - Weekdays
        if (6 <= decimal_hour < 9) or (17 <= decimal_hour < 19):
            return 'peak'
        elif (9 <= decimal_hour < 17) or (19 <= decimal_hour < 22):
            return 'standard'
        else:
            return 'off_peak'


def calculate_tou_breakdown(hourly_data, date_str):
    """
    Calculate TOU breakdown from hourly generation data
    
    Args:
        hourly_data: List of hourly generation records
        date_str: Date string for TOU period determination
    
    Returns:
        dict: TOU breakdown with peak/standard/off_peak kWh
    """
    tou_breakdown = {
        'peak_kwh': 0.0,
        'standard_kwh': 0.0,
        'off_peak_kwh': 0.0
    }
    
    for entry in hourly_data:
        time_str = entry.get('time', '00:00:00')
        hour = int(time_str.split(':')[0])
        minute = int(time_str.split(':')[1]) if ':' in time_str else 0
        
        generation_kw = entry.get('generation_kw', 0)
        
        # Convert kW to kWh for the interval
        # If hourly data: multiply by 1 hour
        # If 5-minute data: multiply by 1/12 hour
        # Determine interval length from data structure
        interval_hours = 1.0  # Default to hourly
        
        # Check if we have 5-minute intervals (more than 20 entries suggests 5-min data)
        if len(hourly_data) > 20:
            interval_hours = 1/12  # 5 minutes = 1/12 hour
        
        generation_kwh = generation_kw * interval_hours
        
        # Determine TOU period
        tou_period = get_tou_period(date_str, hour, minute)
        
        # Add to appropriate bucket
        tou_breakdown[f'{tou_period}_kwh'] += generation_kwh
    
    return tou_breakdown


def calculate_financial_savings(tou_breakdown):
    """
    Calculate financial savings using correct formula:
    Savings = (Utility Cost - PPA Cost)
    
    Args:
        tou_breakdown: Dict with peak_kwh, standard_kwh, off_peak_kwh
    
    Returns:
        dict: Financial breakdown with utility, PPA, and savings for each period
    """
    peak_kwh = tou_breakdown.get('peak_kwh', 0)
    standard_kwh = tou_breakdown.get('standard_kwh', 0)
    off_peak_kwh = tou_breakdown.get('off_peak_kwh', 0)
    
    # Utility cost (what you would pay Eskom)
    utility_peak = peak_kwh * TOU_RATES['peak']
    utility_standard = standard_kwh * TOU_RATES['standard']
    utility_off_peak = off_peak_kwh * TOU_RATES['off_peak']
    utility_total = utility_peak + utility_standard + utility_off_peak
    
    # PPA cost (what you pay for solar)
    ppa_peak = peak_kwh * PPA_RATE
    ppa_standard = standard_kwh * PPA_RATE
    ppa_off_peak = off_peak_kwh * PPA_RATE
    ppa_total = ppa_peak + ppa_standard + ppa_off_peak
    
    # Actual savings (utility - ppa)
    savings_peak = utility_peak - ppa_peak
    savings_standard = utility_standard - ppa_standard
    savings_off_peak = utility_off_peak - ppa_off_peak
    savings_total = utility_total - ppa_total
    
    return {
        'utility': {
            'peak_zar': round(utility_peak, 2),
            'standard_zar': round(utility_standard, 2),
            'off_peak_zar': round(utility_off_peak, 2),
            'total_zar': round(utility_total, 2)
        },
        'ppa': {
            'peak_zar': round(ppa_peak, 2),
            'standard_zar': round(ppa_standard, 2),
            'off_peak_zar': round(ppa_off_peak, 2),
            'total_zar': round(ppa_total, 2)
        },
        'savings': {
            'peak_savings_zar': round(savings_peak, 2),
            'standard_savings_zar': round(savings_standard, 2),
            'off_peak_savings_zar': round(savings_off_peak, 2),
            'total_savings_zar': round(savings_total, 2)
        },
        # Backward compatibility (deprecated - use savings.* instead)
        'peak_savings_zar': round(savings_peak, 2),
        'standard_savings_zar': round(savings_standard, 2),
        'off_peak_savings_zar': round(savings_off_peak, 2),
        'total_savings_zar': round(savings_total, 2)
    }


def process_daily_record(record):
    """
    Process a single daily record to add TOU and financial data
    
    Args:
        record: Daily record dict
    
    Returns:
        dict: Updated record with tou_breakdown and financial data
    """
    if not record.get('hourly_data'):
        return record
    
    date_str = record.get('date', '')
    hourly_data = record['hourly_data']
    
    # Calculate TOU breakdown
    tou_breakdown = calculate_tou_breakdown(hourly_data, date_str)
    
    # Calculate financial savings
    financial = calculate_financial_savings(tou_breakdown)
    
    # Update record
    record['tou_breakdown'] = tou_breakdown
    record['financial'] = financial
    
    return record


def aggregate_monthly_data(daily_records, year_month):
    """
    Aggregate daily records into monthly summary
    
    Args:
        daily_records: List of daily records
        year_month: String like "2026-01"
    
    Returns:
        dict: Monthly summary with totals
    """
    # Filter records for this month
    month_records = [r for r in daily_records if r['date'].startswith(year_month)]
    
    if not month_records:
        return None
    
    # Aggregate TOU
    total_tou = {
        'peak_kwh': 0.0,
        'standard_kwh': 0.0,
        'off_peak_kwh': 0.0
    }
    
    for record in month_records:
        if 'tou_breakdown' in record:
            tou = record['tou_breakdown']
            total_tou['peak_kwh'] += tou.get('peak_kwh', 0)
            total_tou['standard_kwh'] += tou.get('standard_kwh', 0)
            total_tou['off_peak_kwh'] += tou.get('off_peak_kwh', 0)
    
    # Calculate financial for month
    financial = calculate_financial_savings(total_tou)
    
    return {
        'tou_breakdown': total_tou,
        'financial': financial
    }


def aggregate_lifetime_data(daily_records):
    """
    Aggregate all daily records into lifetime summary
    
    Args:
        daily_records: List of all daily records
    
    Returns:
        dict: Lifetime summary with totals
    """
    # Aggregate TOU
    total_tou = {
        'peak_kwh': 0.0,
        'standard_kwh': 0.0,
        'off_peak_kwh': 0.0
    }
    
    for record in daily_records:
        if 'tou_breakdown' in record:
            tou = record['tou_breakdown']
            total_tou['peak_kwh'] += tou.get('peak_kwh', 0)
            total_tou['standard_kwh'] += tou.get('standard_kwh', 0)
            total_tou['off_peak_kwh'] += tou.get('off_peak_kwh', 0)
    
    # Calculate financial for lifetime
    financial = calculate_financial_savings(total_tou)
    
    return {
        'tou_breakdown': total_tou,
        'financial': financial
    }


def process_dashboard_data(input_file):
    """
    Process dashboard_data.json to add TOU and financial calculations
    
    Args:
        input_file: Path to dashboard_data.json
    """
    print(f"📊 Processing: {input_file}")
    
    # Load data
    with open(input_file, 'r') as f:
        data = json.load(f)
    
    if 'daily_records' not in data:
        print("❌ No daily_records found in data")
        return
    
    print(f"✓ Found {len(data['daily_records'])} daily records")
    
    # Process each daily record
    for i, record in enumerate(data['daily_records']):
        data['daily_records'][i] = process_daily_record(record)
    
    print("✓ Processed all daily records")
    
    # Update monthly summaries
    if 'monthly_summaries' not in data:
        data['monthly_summaries'] = {}
    
    # Get unique year-months
    year_months = set()
    for record in data['daily_records']:
        date_str = record.get('date', '')
        if date_str:
            year_months.add(date_str[:7])  # "2026-01"
    
    for year_month in sorted(year_months):
        monthly_data = aggregate_monthly_data(data['daily_records'], year_month)
        if monthly_data:
            if year_month not in data['monthly_summaries']:
                data['monthly_summaries'][year_month] = {}
            data['monthly_summaries'][year_month].update(monthly_data)
    
    print(f"✓ Updated {len(year_months)} monthly summaries")
    
    # Update lifetime summary
    if 'lifetime_summary' not in data:
        data['lifetime_summary'] = {}
    
    lifetime_data = aggregate_lifetime_data(data['daily_records'])
    data['lifetime_summary'].update(lifetime_data)
    
    print("✓ Updated lifetime summary")
    
    # Save back to file
    with open(input_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"✅ Saved updated data to: {input_file}")
    
    # Print summary
    if 'lifetime_summary' in data and 'financial' in data['lifetime_summary']:
        fin = data['lifetime_summary']['financial']
        print("\n📊 Lifetime Financial Summary:")
        print(f"   Utility Cost: R {fin['utility']['total_zar']:,.2f}")
        print(f"   PPA Cost: R {fin['ppa']['total_zar']:,.2f}")
        print(f"   Total Savings: R {fin['savings']['total_savings_zar']:,.2f}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 solar_processor_enhanced.py <dashboard_data.json>")
        print("\nExample:")
        print("  python3 solar_processor_enhanced.py dashboard_data.json")
        print("  python3 solar_processor_enhanced.py data/dashboard_data.json")
        sys.exit(1)
    
    input_file = sys.argv[1]
    
    if not Path(input_file).exists():
        print(f"❌ File not found: {input_file}")
        sys.exit(1)
    
    try:
        process_dashboard_data(input_file)
        print("\n✅ Processing complete!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
