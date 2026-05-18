#!/usr/bin/env python3
"""
Solar Data Processor - Enhanced with TOU and Financial Calculations
Updates dashboard_data.json with Time-of-Use breakdown and correct financial savings

CORRECTED VERSION v2 - Fixed interval detection bug

CRITICAL BUG FIX (v2):
  The previous version assumed hourly_data with >20 entries was 5-minute data
  and divided generation by 12. This was WRONG - Spar's hourly_data is ALWAYS
  hourly (each entry already aggregates a full hour, see the 'intervals' field).
  A day simply has more entries when data coverage is good (22-24h) vs gappy (16h).
  This caused 112 of 173 days to have their TOU/financial figures divided by 12.

  FIX: interval length is now detected from the data itself - if every entry
  has a unique hour, the data is hourly (interval = 1.0h). Only genuinely
  sub-hourly data (repeated hours) uses a fractional interval.

CRITICAL: Uses correct savings formula:
- Savings = (Generation × TOU_rate) - (Generation × PPA_rate)
- NOT just Generation × TOU_rate

2026 TOU Rates (Season-Dependent):
- High Season (winter, Jun-Aug): Peak R8.21, Standard R2.36, Off-Peak R1.71
- Low Season (rest of year):     Peak R3.57, Standard R2.23, Off-Peak R1.70
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Constants - 2026 TOU Rates
TOU_RATES_2026 = {
    'high_season': {  # Winter: June - August (high demand)
        'peak': 8.21,
        'standard': 2.36,
        'off_peak': 1.71
    },
    'low_season': {   # Rest of year: Jan-May, Sep-Dec (low demand)
        'peak': 3.57,
        'standard': 2.23,
        'off_peak': 1.70
    }
}

PPA_RATE = 1.50  # Solar PPA rate (ZAR/kWh)


def get_season(date_str):
    """
    Determine if a date is in high-demand or low-demand season.
    High-demand = Winter (June-Aug). Low-demand = rest of year.

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
    Get TOU rates for a specific date.

    Args:
        date_str: Date in format "YYYY-MM-DD"

    Returns:
        dict: {peak, standard, off_peak} rates
    """
    season = get_season(date_str)
    return TOU_RATES_2026[season]


def get_weighted_average_rates():
    """
    Calculate weighted average rates for lifetime calculations.
    9 months low-demand, 3 months high-demand.

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
    Determine TOU period for a given datetime - based on official Eskom schedule.

    NOTE: season boundary here is aligned with get_season() above:
    high-demand = Jun-Aug, low-demand = the rest of the year.

    Args:
        date_str: Date in format "YYYY-MM-DD"
        hour: Hour (0-23)
        minute: Minute (0-59, ignored for TOU classification)

    Returns:
        str: 'peak', 'standard', or 'off_peak'
    """
    date = datetime.strptime(date_str, '%Y-%m-%d')
    day_of_week = date.weekday()  # 0 = Monday, 6 = Sunday
    month = date.month

    # Day classification
    is_saturday = (day_of_week == 5)
    is_sunday = (day_of_week == 6)
    is_weekday = not is_saturday and not is_sunday

    # Season: high-demand (Jun-Aug), low-demand (rest)
    # Aligned with get_season() - previously this line disagreed on May.
    is_low_demand = not (6 <= month <= 8)

    h = hour  # TOU periods use integer hour only

    if is_weekday:
        if is_low_demand:
            # LOW-DEMAND SEASON - Weekdays (Mon-Fri)
            # Peak: 7-9am (hour 7,8), 6-9pm (hour 18,19,20)
            if (7 <= h <= 8) or (18 <= h <= 20):
                return 'peak'
            # Standard: 6am, 9am-6pm (hour 9-17), 9pm (hour 21)
            elif h == 6 or (9 <= h <= 17) or h == 21:
                return 'standard'
            # Off-Peak: midnight-6am (hour 0-5), 10pm-midnight (hour 22-23)
            else:
                return 'off_peak'
        else:
            # HIGH-DEMAND SEASON - Weekdays (Mon-Fri)
            # Peak: 6-8am (hour 6,7), 5-8pm (hour 17,18,19)
            if (6 <= h <= 7) or (17 <= h <= 19):
                return 'peak'
            # Standard: 8am-5pm (hour 8-16), 8-10pm (hour 20-21)
            elif (8 <= h <= 16) or (20 <= h <= 21):
                return 'standard'
            # Off-Peak: midnight-6am (hour 0-5), 10pm-midnight (hour 22-23)
            else:
                return 'off_peak'

    elif is_saturday:
        if is_low_demand:
            # LOW-DEMAND SEASON - Saturday
            if (7 <= h <= 11) or (18 <= h <= 19):
                return 'standard'
            else:
                return 'off_peak'
        else:
            # HIGH-DEMAND SEASON - Saturday
            if (7 <= h <= 11) or (17 <= h <= 18):
                return 'standard'
            else:
                return 'off_peak'

    else:  # Sunday
        if is_low_demand:
            # LOW-DEMAND SEASON - Sunday
            if 18 <= h <= 19:
                return 'standard'
            else:
                return 'off_peak'
        else:
            # HIGH-DEMAND SEASON - Sunday
            if 17 <= h <= 18:
                return 'standard'
            else:
                return 'off_peak'


def detect_interval_hours(hourly_data):
    """
    Determine the length (in hours) each entry in hourly_data represents.

    FIXED LOGIC (v2):
      The old code assumed >20 entries meant 5-minute data. That was wrong -
      a full day of HOURLY data legitimately has 22-24 entries.

      Correct approach: look at the actual timestamps.
      - If every entry has a unique hour  -> data is hourly       -> 1.0h
      - If hours repeat (multiple entries within the same hour)
        -> sub-hourly -> 1 / (entries per hour)

    Args:
        hourly_data: list of entries each with a 'time' field "HH:MM"

    Returns:
        float: interval length in hours (1.0 for hourly data)
    """
    if not hourly_data:
        return 1.0

    hours = []
    for entry in hourly_data:
        time_str = entry.get('time', '00:00')
        try:
            hours.append(int(time_str.split(':')[0]))
        except (ValueError, IndexError):
            hours.append(0)

    unique_hours = len(set(hours))
    total_entries = len(hours)

    # If every entry sits in its own hour, the data is hourly.
    if unique_hours == total_entries:
        return 1.0

    # Otherwise it is sub-hourly: figure out how many readings per hour.
    # (e.g. 12 readings/hour -> 5-minute data -> interval 1/12)
    entries_per_hour = round(total_entries / unique_hours)
    if entries_per_hour <= 1:
        return 1.0
    return 1.0 / entries_per_hour


def calculate_tou_breakdown(hourly_data, date_str):
    """
    Calculate TOU breakdown from hourly generation data.

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

    # Detect interval ONCE per day from the actual data (the v2 fix).
    interval_hours = detect_interval_hours(hourly_data)

    for entry in hourly_data:
        time_str = entry.get('time', '00:00:00')
        hour = int(time_str.split(':')[0])
        minute = int(time_str.split(':')[1]) if ':' in time_str else 0

        generation_kw = entry.get('generation_kw', 0)

        # kW averaged over the interval -> kWh for that interval
        generation_kwh = generation_kw * interval_hours

        # Determine TOU period and accumulate
        tou_period = get_tou_period(date_str, hour, minute)
        tou_breakdown[f'{tou_period}_kwh'] += generation_kwh

    return tou_breakdown


def calculate_financial_savings(tou_breakdown, date_str=None):
    """
    Calculate financial savings: Savings = Utility Cost - PPA Cost.

    Args:
        tou_breakdown: Dict with peak_kwh, standard_kwh, off_peak_kwh
        date_str: Date string for seasonal rate determination (optional)

    Returns:
        dict: Financial breakdown with utility, PPA, and savings for each period
    """
    peak_kwh = tou_breakdown.get('peak_kwh', 0)
    standard_kwh = tou_breakdown.get('standard_kwh', 0)
    off_peak_kwh = tou_breakdown.get('off_peak_kwh', 0)

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
    Process a single daily record to add TOU and financial data.

    Args:
        record: Daily record dict

    Returns:
        dict: Updated record with tou_breakdown and financial data
    """
    if not record.get('hourly_data'):
        return record

    date_str = record.get('date', '')
    hourly_data = record['hourly_data']

    tou_breakdown = calculate_tou_breakdown(hourly_data, date_str)
    financial = calculate_financial_savings(tou_breakdown, date_str)

    record['tou_breakdown'] = tou_breakdown
    record['financial'] = financial

    return record


def aggregate_monthly_data(daily_records, year_month):
    """
    Aggregate daily records into monthly summary.

    Args:
        daily_records: List of daily records
        year_month: String like "2026-01"

    Returns:
        dict: Monthly summary with totals
    """
    month_records = [r for r in daily_records if r['date'].startswith(year_month)]

    if not month_records:
        return None

    total_tou = {
        'peak_kwh': 0.0,
        'standard_kwh': 0.0,
        'off_peak_kwh': 0.0
    }
    total_generation_kwh = 0.0
    actual_load_kwh = 0.0
    actual_grid_kwh = 0.0
    days_with_data = 0

    for record in month_records:
        if 'tou_breakdown' in record:
            tou = record['tou_breakdown']
            total_tou['peak_kwh'] += tou.get('peak_kwh', 0)
            total_tou['standard_kwh'] += tou.get('standard_kwh', 0)
            total_tou['off_peak_kwh'] += tou.get('off_peak_kwh', 0)
        total_generation_kwh += record.get('generation_kwh', 0)
        actual_load_kwh += record.get('actual_load_kwh', 0)
        actual_grid_kwh += record.get('actual_grid_kwh', 0)
        days_with_data += 1

    month_date = year_month + '-01'
    financial = calculate_financial_savings(total_tou, month_date)

    return {
        'tou_breakdown': total_tou,
        'financial': financial,
        'total_generation_kwh': round(total_generation_kwh, 2),
        'actual_load_kwh': round(actual_load_kwh, 2),
        'actual_grid_kwh': round(actual_grid_kwh, 2),
        'days_with_data': days_with_data
    }


def calculate_expected_tou_for_month(year_month, monthly_predictions_base, system_data):
    """
    Calculate expected TOU breakdown for a month based on PVSyst predictions.

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
    month_key = month_num

    if month_key not in monthly_predictions_base:
        return None

    avg_daily_kwh = monthly_predictions_base[month_key].get('avg_daily_kwh', 0)

    if system_data and 'commissioning_date' in system_data:
        commissioning_date = datetime.fromisoformat(system_data['commissioning_date'].split('T')[0])
        target_date = datetime(int(year), int(month_num), 15)
        days_active = (target_date - commissioning_date).days
        years_active = days_active / 365.25

        degradation_year_1 = system_data.get('degradation_year_1', 0.02)
        degradation_subsequent = system_data.get('degradation_subsequent_years', 0.005)

        if years_active < 1:
            degradation_percent = degradation_year_1 * max(0, years_active)
        else:
            degradation_percent = degradation_year_1 + (degradation_subsequent * (years_active - 1))

        degradation_factor = 1 - degradation_percent
        avg_daily_kwh *= degradation_factor

    hourly_pattern = monthly_predictions_base[month_key].get('hourly_avg_kw', [0] * 24)
    total_daily = sum(hourly_pattern)

    if total_daily > 0:
        hourly_pattern = [h / total_daily for h in hourly_pattern]
    else:
        hourly_pattern = [1 / 24] * 24

    hourly_kwh = [h * avg_daily_kwh for h in hourly_pattern]

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

    if int(month_num) == 12:
        next_month_date = datetime(int(year) + 1, 1, 1)
    else:
        next_month_date = datetime(int(year), int(month_num) + 1, 1)

    this_month_date = datetime(int(year), int(month_num), 1)
    days_in_month = (next_month_date - this_month_date).days

    for key in expected_tou:
        expected_tou[key] = round(expected_tou[key] * days_in_month, 2)

    month_date = year_month + '-01'
    financial_expected = calculate_financial_savings(expected_tou, month_date)

    return {
        'tou_breakdown_expected': expected_tou,
        'financial_expected': financial_expected
    }


def aggregate_lifetime_data(daily_records):
    """
    Aggregate all daily records into lifetime summary.

    Args:
        daily_records: List of all daily records

    Returns:
        dict: Lifetime summary with totals
    """
    total_tou = {
        'peak_kwh': 0.0,
        'standard_kwh': 0.0,
        'off_peak_kwh': 0.0
    }
    total_generation_kwh = 0.0
    actual_load_kwh = 0.0
    actual_grid_kwh = 0.0
    days_active = 0

    for record in daily_records:
        if 'tou_breakdown' in record:
            tou = record['tou_breakdown']
            total_tou['peak_kwh'] += tou.get('peak_kwh', 0)
            total_tou['standard_kwh'] += tou.get('standard_kwh', 0)
            total_tou['off_peak_kwh'] += tou.get('off_peak_kwh', 0)
        total_generation_kwh += record.get('generation_kwh', 0)
        actual_load_kwh += record.get('actual_load_kwh', 0)
        actual_grid_kwh += record.get('actual_grid_kwh', 0)
        days_active += 1

    # Lifetime uses weighted average rates (date_str=None)
    financial = calculate_financial_savings(total_tou, None)

    return {
        'tou_breakdown': total_tou,
        'financial': financial,
        'total_generation_kwh': round(total_generation_kwh, 2),
        'actual_load_kwh': round(actual_load_kwh, 2),
        'actual_grid_kwh': round(actual_grid_kwh, 2),
        'days_active': days_active
    }


def process_dashboard_data(input_file):
    """
    Process dashboard_data.json to add TOU and financial calculations.

    Args:
        input_file: Path to dashboard_data.json
    """
    print(f"Processing: {input_file}")

    with open(input_file, 'r') as f:
        data = json.load(f)

    if 'daily_records' not in data:
        print("ERROR: No daily_records found in data")
        return

    print(f"Found {len(data['daily_records'])} daily records")

    # Process each daily record
    for i, record in enumerate(data['daily_records']):
        data['daily_records'][i] = process_daily_record(record)

    print("Processed all daily records")

    # Update monthly summaries
    if 'monthly_summaries' not in data:
        data['monthly_summaries'] = {}

    year_months = set()
    for record in data['daily_records']:
        date_str = record.get('date', '')
        if date_str:
            year_months.add(date_str[:7])

    for year_month in sorted(year_months):
        monthly_data = aggregate_monthly_data(data['daily_records'], year_month)
        if monthly_data:
            if year_month not in data['monthly_summaries']:
                data['monthly_summaries'][year_month] = {}
            data['monthly_summaries'][year_month].update(monthly_data)

            if 'monthly_predictions_base' in data:
                expected_data = calculate_expected_tou_for_month(
                    year_month,
                    data['monthly_predictions_base'],
                    data.get('system', {})
                )
                if expected_data:
                    data['monthly_summaries'][year_month].update(expected_data)

    print(f"Updated {len(year_months)} monthly summaries (with expected TOU)")

    # Update lifetime summary
    if 'lifetime_summary' not in data:
        data['lifetime_summary'] = {}

    lifetime_data = aggregate_lifetime_data(data['daily_records'])
    data['lifetime_summary'].update(lifetime_data)

    print("Updated lifetime summary")

    # Save back to file
    with open(input_file, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Saved updated data to: {input_file}")

    # Print summary
    if 'lifetime_summary' in data and 'financial' in data['lifetime_summary']:
        fin = data['lifetime_summary']['financial']
        tou = data['lifetime_summary'].get('tou_breakdown', {})

        tou_total = tou.get('peak_kwh', 0) + tou.get('standard_kwh', 0) + tou.get('off_peak_kwh', 0)
        lifetime_gen = data['lifetime_summary'].get('total_generation_kwh', 0)

        print("\nLifetime Summary:")
        print(f"   Total Generation: {lifetime_gen:,.1f} kWh")
        print(f"   TOU Breakdown Total: {tou_total:,.1f} kWh")
        print(f"     - Peak: {tou.get('peak_kwh', 0):,.1f} kWh")
        print(f"     - Standard: {tou.get('standard_kwh', 0):,.1f} kWh")
        print(f"     - Off-Peak: {tou.get('off_peak_kwh', 0):,.1f} kWh")

        diff = abs(lifetime_gen - tou_total)
        if diff > 1:
            print(f"\n   WARNING: TOU total doesn't match lifetime generation!")
            print(f"   Difference: {diff:,.1f} kWh")
        else:
            print(f"\n   OK: TOU total matches lifetime generation")

        print("\nFinancial Summary:")
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
        print(f"ERROR: File not found: {input_file}")
        sys.exit(1)

    try:
        process_dashboard_data(input_file)
        print("\nProcessing complete!")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
