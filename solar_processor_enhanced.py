#!/usr/bin/env python3
"""
Solar Data Processor - Enhanced with TOU and Financial Calculations
Updates dashboard_data.json with Time-of-Use breakdown and correct financial savings

CRITICAL: Uses correct savings formula:
- Savings = (Generation × TOU_rate) - (Generation × PPA_rate)
- NOT just Generation × TOU_rate

2026 TOU Rates (Season-Dependent):
- High Season (Sept-April): Peak R8.21, Standard R2.36, Off-Peak R1.71
- Low Season (May-Aug): Peak R3.57, Standard R2.23, Off-Peak R1.70
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Constants - 2026 TOU Rates
TOU_RATES_2026 = {
    'high_season': {  # Summer: September - April
        'peak': 8.21,
        'standard': 2.36,
        'off_peak': 1.71
    },
    'low_season': {   # Winter: May - August
        'peak': 3.57,
        'standard': 2.23,
        'off_peak': 1.70
    }
}

PPA_RATE = 1.50  # Solar PPA rate (ZAR/kWh)


def get_season(date_str):
    """
    Determine if a date is in high-demand or low-demand season
    High-demand = Winter (June-Aug) when heating demand is high
    Low-demand = Rest of year (Jan-May, Sep-Dec)
    
    Args:
        date_str: Date in format "YYYY-MM-DD"
    
    Returns:
        str: 'high_season' or 'low_season'
    """
    date = datetime.strptime(date_str, '%Y-%m-%d')
    month = date.month
    
    # High-demand Season (Winter): June (6), July (7), August (8)
    # Low-demand Season (Rest): Jan-May (1-5), Sep-Dec (9-12)
    if 6 <= month <= 8:
        return 'high_season'  # High-demand (winter)
    else:
        return 'low_season'   # Low-demand (rest of year)


def get_tou_rates(date_str):
    """
    Get TOU rates for a specific date
    
    Args:
        date_str: Date in format "YYYY-MM-DD"
    
    Returns:
        dict: {peak, standard, off_peak} rates
    """
    season = get_season(date_str)
    return TOU_RATES_2026[season]


def get_weighted_average_rates():
    """
    Calculate weighted average rates for lifetime calculations
    9 months low-demand, 3 months high-demand
    
    Returns:
        dict: {peak, standard, off_peak} weighted average rates
    """
    return {
        'peak': (TOU_RATES_2026['low_season']['peak'] * 9 + TOU_RATES_2026['high_season']['peak'] * 3) / 12,
        'standard': (TOU_RATES_2026['low_season']['standard'] * 9 + TOU_RATES_2026['high_season']['standard'] * 3) / 12,
        'off_peak': (TOU_RATES_2026['low_season']['off_peak'] * 9 + TOU_RATES_2026['high_season']['off_peak'] * 3) / 12
    }


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
        # FIX: Peak is 7-9am (not 7-10am) and 6-8pm
        if (7 <= decimal_hour < 9) or (18 <= decimal_hour < 20):
            return 'peak'
        elif (6 <= decimal_hour < 7) or (9 <= decimal_hour < 18) or (20 <= decimal_hour < 22):
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


def calculate_financial_savings(tou_breakdown, date_str=None):
    """
    Calculate financial savings using correct formula:
    Savings = (Utility Cost - PPA Cost)
    
    Args:
        tou_breakdown: Dict with peak_kwh, standard_kwh, off_peak_kwh
        date_str: Date string for seasonal rate determination (optional)
    
    Returns:
        dict: Financial breakdown with utility, PPA, and savings for each period
    """
    peak_kwh = tou_breakdown.get('peak_kwh', 0)
    standard_kwh = tou_breakdown.get('standard_kwh', 0)
    off_peak_kwh = tou_breakdown.get('off_peak_kwh', 0)
    
    # Get appropriate rates (seasonal or weighted average)
    if date_str:
        rates = get_tou_rates(date_str)
    else:
        rates = get_weighted_average_rates()
    
    # Utility cost (what you would pay Eskom)
    utility_peak = peak_kwh * rates['peak']
    utility_standard = standard_kwh * rates['standard']
    utility_off_peak = off_peak_kwh * rates['off_peak']
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
    
    # Calculate financial savings with seasonal rates
    financial = calculate_financial_savings(tou_breakdown, date_str)
    
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
    
    # Calculate financial for month using first day of month for seasonal rate
    month_date = year_month + '-01'
    financial = calculate_financial_savings(total_tou, month_date)
    
    return {
        'tou_breakdown': total_tou,
        'financial': financial
    }


def calculate_expected_tou_for_month(year_month, monthly_predictions_base, system_data):
    """
    Calculate expected TOU breakdown for a month based on PVSyst predictions
    
    Args:
        year_month: String like "2026-01"
        monthly_predictions_base: PVSyst monthly averages
        system_data: System configuration including commissioning date and degradation
    
    Returns:
        dict: Expected TOU breakdown and financial savings
    """
    if not monthly_predictions_base:
        return None
    
    year, month_num = year_month.split('-')
    month_key = month_num  # "01", "02", etc.
    
    if month_key not in monthly_predictions_base:
        return None
    
    # Get monthly average daily generation
    avg_daily_kwh = monthly_predictions_base[month_key].get('avg_daily_kwh', 0)
    
    # Apply degradation if system data available
    if system_data and 'commissioning_date' in system_data:
        commissioning_date = datetime.fromisoformat(system_data['commissioning_date'].split('T')[0])
        target_date = datetime(int(year), int(month_num), 15)  # Mid-month
        days_active = (target_date - commissioning_date).days
        years_active = days_active / 365.25
        
        degradation_year_1 = system_data.get('degradation_year_1', 0.02)
        degradation_subsequent = system_data.get('degradation_subsequent_years', 0.005)
        
        if years_active < 1:
            degradation_percent = degradation_year_1 * years_active
        else:
            degradation_percent = degradation_year_1 + (degradation_subsequent * (years_active - 1))
        
        degradation_factor = 1 - degradation_percent
        avg_daily_kwh *= degradation_factor
    
    # Get hourly pattern (normalized)
    hourly_pattern = monthly_predictions_base[month_key].get('hourly_avg_kw', [0] * 24)
    total_daily = sum(hourly_pattern)
    
    if total_daily > 0:
        # Normalize to sum to 1.0
        hourly_pattern = [h / total_daily for h in hourly_pattern]
    else:
        # Fallback to uniform distribution
        hourly_pattern = [1/24] * 24
    
    # Scale to actual daily generation
    hourly_kwh = [h * avg_daily_kwh for h in hourly_pattern]
    
    # Classify each hour by TOU period (using mid-month date)
    mid_month_date = f"{year}-{month_num}-15"
    
    expected_tou = {
        'peak_kwh': 0.0,
        'standard_kwh': 0.0,
        'off_peak_kwh': 0.0
    }
    
    for hour in range(24):
        kwh = hourly_kwh[hour]
        period = get_tou_period(mid_month_date, hour)
        expected_tou[f'{period}_kwh'] += kwh
    
    # Multiply by days in month
    if int(month_num) == 12:
        next_month_date = datetime(int(year) + 1, 1, 1)
    else:
        next_month_date = datetime(int(year), int(month_num) + 1, 1)
    
    this_month_date = datetime(int(year), int(month_num), 1)
    days_in_month = (next_month_date - this_month_date).days
    
    for key in expected_tou:
        expected_tou[key] = round(expected_tou[key] * days_in_month, 2)
    
    # Calculate expected financial savings
    month_date = year_month + '-01'
    financial_expected = calculate_financial_savings(expected_tou, month_date)
    
    return {
        'tou_breakdown_expected': expected_tou,
        'financial_expected': financial_expected
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
    
    # Calculate financial for lifetime using weighted average rates
    financial = calculate_financial_savings(total_tou, None)
    
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
            
            # Add expected TOU breakdown if predictions available
            if 'monthly_predictions_base' in data:
                expected_data = calculate_expected_tou_for_month(
                    year_month, 
                    data['monthly_predictions_base'],
                    data.get('system', {})
                )
                if expected_data:
                    data['monthly_summaries'][year_month].update(expected_data)
    
    print(f"✓ Updated {len(year_months)} monthly summaries (with expected TOU)")
    
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
        tou = data['lifetime_summary'].get('tou_breakdown', {})
        
        # Calculate TOU total
        tou_total = tou.get('peak_kwh', 0) + tou.get('standard_kwh', 0) + tou.get('off_peak_kwh', 0)
        lifetime_gen = data['lifetime_summary'].get('total_generation_kwh', 0)
        
        print("\n📊 Lifetime Summary:")
        print(f"   Total Generation: {lifetime_gen:,.1f} kWh")
        print(f"   TOU Breakdown Total: {tou_total:,.1f} kWh")
        print(f"     - Peak: {tou.get('peak_kwh', 0):,.1f} kWh")
        print(f"     - Standard: {tou.get('standard_kwh', 0):,.1f} kWh")
        print(f"     - Off-Peak: {tou.get('off_peak_kwh', 0):,.1f} kWh")
        
        # Validate totals match
        diff = abs(lifetime_gen - tou_total)
        if diff > 1:
            print(f"\n   ⚠️  WARNING: TOU total doesn't match lifetime generation!")
            print(f"   Difference: {diff:,.1f} kWh")
        else:
            print(f"\n   ✅ TOU total matches lifetime generation")
        
        print("\n📊 Financial Summary:")
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
