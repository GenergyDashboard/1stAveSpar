#!/usr/bin/env python3
"""
Migration script to populate daily_records in dashboard_data.json
Reads raw XLS files from data/daily/ directory and extracts Load/Grid/PV data
"""

import json
import os
import xlrd
from datetime import datetime
from pathlib import Path

def parse_xls_file(filepath):
    """
    Parse a raw XLS file and extract hourly data
    Aggregates 5-minute interval data into hourly buckets
    
    Returns:
        dict with date, generation_kwh, and hourly_data
    """
    try:
        wb = xlrd.open_workbook(filepath)
        sheet = wb.sheet_by_index(0)
        
        # Find header row (should be around row 28)
        header_row = None
        for i in range(min(35, sheet.nrows)):
            row_values = sheet.row_values(i)
            row_str = ' '.join(str(v) for v in row_values).upper()
            if 'PV(W)' in row_str and 'GRID(W)' in row_str and 'LOAD(W)' in row_str:
                header_row = i
                break
        
        if header_row is None:
            print(f"  ⚠️  Could not find header row in {filepath}")
            return None
        
        print(f"  Found header at row {header_row}")
        
        # Extract date from filename
        # Format can be: YYYY-MM-DD.xls or timestamp_solar_export_latest.xls
        filename = os.path.basename(filepath)
        
        # Try to extract date from filename
        if filename.startswith('20') and len(filename.split('-')) == 3:
            # Format: 2026-01-14.xls
            date_str = filename.replace('.xls', '')
        else:
            # For solar_export_latest.xls or other formats, try to find date in first few rows
            date_str = None
            for i in range(min(5, sheet.nrows)):
                row = sheet.row_values(i)
                row_text = ' '.join(str(v) for v in row)
                # Look for date pattern like "14/01/2026"
                if '/' in row_text and any(str(y) in row_text for y in range(2020, 2030)):
                    # Try to parse Plant_14/01/2026Chart format
                    try:
                        parts = row_text.split('_')
                        if len(parts) > 1:
                            date_part = parts[1].split('Chart')[0]  # "14/01/2026"
                            day, month, year = date_part.split('/')
                            date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                            break
                    except:
                        pass
            
            if not date_str:
                # Fallback to today's date
                from datetime import date
                date_str = date.today().strftime('%Y-%m-%d')
                print(f"  ⚠️  Could not extract date from filename, using today: {date_str}")
        
        # Parse 5-minute interval data and aggregate to hourly
        hourly_buckets = {}  # hour: {pv_sum, grid_sum, load_sum, count}
        
        for i in range(header_row + 1, sheet.nrows):
            try:
                row = sheet.row_values(i)
                
                # Extract values (columns: Number, Time, State, PV(W), Grid(W), Load(W))
                if len(row) < 6:
                    continue
                
                time_str = str(row[1]) if len(row) > 1 else ""
                pv_w = float(row[3]) if len(row) > 3 and row[3] != '' else 0
                grid_w = float(row[4]) if len(row) > 4 and row[4] != '' else 0
                load_w = float(row[5]) if len(row) > 5 and row[5] != '' else 0
                
                # Extract hour from time (HH:MM:SS)
                try:
                    hour = int(time_str.split(':')[0])
                except:
                    continue
                
                # Initialize hourly bucket
                if hour not in hourly_buckets:
                    hourly_buckets[hour] = {
                        'pv_sum': 0,
                        'grid_sum': 0,
                        'load_sum': 0,
                        'count': 0
                    }
                
                # Add to hourly bucket (W * 5 minutes / 60 = Wh for this interval)
                # Then sum all intervals in the hour to get total Wh
                interval_hours = 5 / 60  # 5 minutes = 1/12 hour
                hourly_buckets[hour]['pv_sum'] += pv_w * interval_hours
                hourly_buckets[hour]['grid_sum'] += grid_w * interval_hours
                hourly_buckets[hour]['load_sum'] += load_w * interval_hours
                hourly_buckets[hour]['count'] += 1
                
            except (ValueError, IndexError) as e:
                # Skip invalid rows
                continue
        
        if not hourly_buckets:
            print(f"  ⚠️  No data extracted from {filepath}")
            return None
        
        # Create hourly records
        hourly_data = []
        total_generation = 0
        
        for hour in sorted(hourly_buckets.keys()):
            bucket = hourly_buckets[hour]
            
            # Convert Wh to kWh
            pv_kwh = bucket['pv_sum'] / 1000
            grid_kwh = bucket['grid_sum'] / 1000
            load_kwh = bucket['load_sum'] / 1000
            
            hour_record = {
                'time': f"{hour:02d}:00",
                'generation_kw': round(pv_kwh, 3),  # Total energy in this hour
                'grid_kw': round(grid_kwh, 3),
                'load_kw': round(load_kwh, 3),
                'intervals': bucket['count']  # For debugging
            }
            
            hourly_data.append(hour_record)
            total_generation += pv_kwh
        
        return {
            'date': date_str,
            'generation_kwh': round(total_generation, 2),
            'hourly_data': hourly_data
        }
        
    except Exception as e:
        print(f"  ✗ Error parsing {filepath}: {e}")
        return None

def migrate_data(dashboard_json_path, xls_directory='data/daily'):
    """
    Migrate data from raw XLS files to dashboard_data.json
    """
    print("=" * 80)
    print("MIGRATION: Populating daily_records from raw XLS files")
    print("=" * 80)
    
    # Load dashboard_data.json
    print(f"\nLoading {dashboard_json_path}...")
    with open(dashboard_json_path, 'r') as f:
        dashboard_data = json.load(f)
    
    print(f"✓ Loaded dashboard data")
    
    # Find all XLS files
    xls_pattern = os.path.join(xls_directory, '*.xls')
    xls_files = sorted(Path(xls_directory).glob('*.xls'))
    
    if not xls_files:
        print(f"\n✗ No XLS files found in {xls_directory}/")
        print(f"\nPlease ensure your raw scraped XLS files are in: {xls_directory}/")
        print(f"Expected format: YYYY-MM-DD.xls")
        return False
    
    print(f"\nFound {len(xls_files)} XLS files in {xls_directory}/")
    
    # Get today's date for smart updating
    from datetime import date
    today = date.today().strftime('%Y-%m-%d')
    
    # Build a map of existing daily records for efficient updates
    existing_records = {rec['date']: rec for rec in dashboard_data.get('daily_records', [])}
    
    # Parse each XLS file
    daily_records_map = existing_records.copy()  # Start with existing records
    success_count = 0
    error_count = 0
    updated_count = 0
    
    for xls_file in xls_files:
        print(f"\nProcessing: {xls_file.name}")
        record = parse_xls_file(str(xls_file))
        
        if record:
            record_date = record['date']
            
            # Check if this record already exists and if it's changed
            if record_date in daily_records_map:
                old_gen = daily_records_map[record_date].get('generation_kwh', 0)
                new_gen = record['generation_kwh']
                
                # Always update today's record, and update others if generation changed significantly
                if record_date == today or abs(old_gen - new_gen) > 1.0:
                    daily_records_map[record_date] = record
                    updated_count += 1
                    if record_date == today:
                        print(f"  🔄 UPDATED (today): {record_date}: {new_gen} kWh, {len(record['hourly_data'])} hours")
                    else:
                        print(f"  🔄 Updated: {record_date}: {old_gen:.1f} → {new_gen} kWh")
                else:
                    print(f"  ✓ Unchanged: {record_date}: {old_gen:.1f} kWh")
            else:
                # New record
                daily_records_map[record_date] = record
                print(f"  ✓ NEW: {record_date}: {record['generation_kwh']} kWh, {len(record['hourly_data'])} hours")
            
            success_count += 1
        else:
            error_count += 1
    
    # Convert map back to sorted list
    daily_records = sorted(daily_records_map.values(), key=lambda x: x['date'])
    
    print("\n" + "=" * 80)
    print("MIGRATION SUMMARY")
    print("=" * 80)
    print(f"XLS files processed: {len(xls_files)}")
    print(f"Successfully parsed: {success_count}")
    print(f"Updated records: {updated_count}")
    print(f"Errors: {error_count}")
    
    if not daily_records:
        print("\n✗ No daily records created!")
        return False
    
    # Sort by date
    daily_records = sorted(daily_records, key=lambda x: x['date'])
    
    # Update dashboard_data
    print(f"\nUpdating dashboard_data.json...")
    dashboard_data['daily_records'] = daily_records
    
    # Backup original
    backup_path = dashboard_json_path.replace('.json', '.backup.json')
    print(f"Creating backup: {backup_path}")
    with open(backup_path, 'w') as f:
        json.dump(dashboard_data, f, indent=2)
    
    # Save updated file
    print(f"Saving updated dashboard_data.json...")
    with open(dashboard_json_path, 'w') as f:
        json.dump(dashboard_data, f, indent=2)
    
    print("\n✓ Migration complete!")
    print(f"\nDaily records: {len(daily_records)}")
    print(f"Date range: {daily_records[0]['date']} to {daily_records[-1]['date']}")
    
    # Show sample
    if daily_records:
        sample = daily_records[0]
        print(f"\nSample record ({sample['date']}):")
        print(f"  Generation: {sample['generation_kwh']} kWh")
        print(f"  Hourly data points: {len(sample['hourly_data'])}")
        if sample['hourly_data']:
            print(f"  Sample hour: {sample['hourly_data'][0]}")
    
    print("\n" + "=" * 80)
    print("NEXT STEP: Run the enhanced processor")
    print("=" * 80)
    print(f"\npython3 solar_processor_enhanced.py {dashboard_json_path}")
    print("\n")
    
    return True

if __name__ == '__main__':
    import sys
    
    # Get paths from command line or use defaults
    dashboard_path = sys.argv[1] if len(sys.argv) > 1 else 'dashboard_data.json'
    xls_dir = sys.argv[2] if len(sys.argv) > 2 else 'data/daily'
    
    # Check if files exist
    if not os.path.exists(dashboard_path):
        print(f"✗ Error: {dashboard_path} not found!")
        print("\nUsage: python3 migrate_data.py <dashboard_data.json> [xls_directory]")
        print("\nExample:")
        print("  python3 migrate_data.py ./dashboard_data.json ./data/daily")
        sys.exit(1)
    
    if not os.path.exists(xls_dir):
        print(f"✗ Error: XLS directory not found: {xls_dir}")
        print(f"\nPlease ensure your raw XLS files are in: {xls_dir}/")
        sys.exit(1)
    
    # Run migration
    success = migrate_data(dashboard_path, xls_dir)
    
    if success:
        print("✓ Ready for Phase 1 processing!")
        sys.exit(0)
    else:
        print("✗ Migration failed")
        sys.exit(1)
