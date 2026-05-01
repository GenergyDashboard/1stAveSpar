"""
generate_today_detailed.py

Reads the latest SolisCloud XLS export and generates today_detailed.json
for the main PV fleet dashboard to consume.

This bridges the 1st Ave Spar's SolisCloud data format with the standard
format expected by the Genergy overview dashboard.

Run after scraper.py in the workflow.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pandas as pd

SAST = timezone(timedelta(hours=2))
DATA_DIR = Path(__file__).parent / "data"
XLS_FILE = DATA_DIR / "solar_export_latest.xls"
OUTPUT_FILE = DATA_DIR / "today_detailed.json"
PREDICTIONS_FILE = Path(__file__).parent / "predictions_2025_2044.min.json"


def load_predictions():
    """Load predicted hourly kW from predictions file if available."""
    predicted = [0.0] * 24
    try:
        if PREDICTIONS_FILE.exists():
            with open(PREDICTIONS_FILE) as f:
                pdata = json.load(f)
            # Get current month's predictions
            now = datetime.now(SAST)
            month_key = str(now.month)
            # Try different possible structures
            if isinstance(pdata, dict):
                monthly = pdata.get("monthly_avg_hourly", pdata.get("monthly", {}))
                if month_key in monthly:
                    month_data = monthly[month_key]
                    if isinstance(month_data, list):
                        for entry in month_data:
                            if isinstance(entry, dict) and "hour" in entry:
                                predicted[entry["hour"]] = entry.get("pv_kw", 0)
                            elif isinstance(entry, (int, float)):
                                idx = month_data.index(entry)
                                if idx < 24:
                                    predicted[idx] = entry
    except Exception as e:
        print(f"  ⚠️  Could not load predictions: {e}")
    return predicted


def parse_xls(filepath):
    """Parse SolisCloud XLS export into hourly PV data."""
    df = pd.read_excel(filepath, header=None)

    # Find the header row (contains "Time" and "PV(W)")
    header_row = None
    for i in range(min(40, len(df))):
        row_vals = [str(v).strip() for v in df.iloc[i].tolist() if not pd.isna(v)]
        if any("Time" in v for v in row_vals) and any("PV" in v for v in row_vals):
            header_row = i
            break

    if header_row is None:
        print("❌ Could not find header row in XLS")
        return None

    # Find column indices
    headers = [str(v).strip() if not pd.isna(v) else "" for v in df.iloc[header_row].tolist()]
    time_col = next((i for i, h in enumerate(headers) if "Time" in h), 1)
    pv_col = next((i for i, h in enumerate(headers) if "PV" in h), 3)

    print(f"  📊 Header row: {header_row}, Time col: {time_col}, PV col: {pv_col}")

    # Parse 5-minute data into hourly buckets
    hourly_readings = {h: [] for h in range(24)}

    for i in range(header_row + 1, len(df)):
        time_val = df.iloc[i, time_col]
        pv_val = df.iloc[i, pv_col]

        if pd.isna(time_val) or pd.isna(pv_val):
            continue

        # Parse time - could be "HH:MM:SS" string or datetime
        try:
            time_str = str(time_val).strip()
            if ":" in time_str:
                parts = time_str.split(":")
                hour = int(parts[0])
            else:
                continue
        except (ValueError, IndexError):
            continue

        # Parse PV value (in Watts)
        try:
            pv_watts = float(str(pv_val).replace(",", ""))
            pv_kw = max(pv_watts / 1000.0, 0)  # Convert W to kW, no negatives
        except (ValueError, TypeError):
            continue

        if 0 <= hour <= 23:
            hourly_readings[hour].append(pv_kw)

    # Average each hour's readings to get kW (= kWh for 1 hour)
    hourly_pv = [0.0] * 24
    for h in range(24):
        readings = hourly_readings[h]
        if readings:
            hourly_pv[h] = round(sum(readings) / len(readings), 2)

    return hourly_pv


def fetch_irradiation(date_str):
    """Fetch irradiation from Open-Meteo for 1st Ave Spar location."""
    import requests
    import time as _time

    # 1st Avenue Spar coordinates (Gqeberha/Port Elizabeth)
    lat, lon = -33.9580, 25.5950

    for attempt in range(3):
        try:
            resp = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat, "longitude": lon,
                    "hourly": "shortwave_radiation",
                    "start_date": date_str, "end_date": date_str,
                },
                timeout=20,
            )
            resp.raise_for_status()
            irrad = resp.json().get("hourly", {}).get("shortwave_radiation", [])
            while len(irrad) < 24:
                irrad.append(0)
            utc_data = [round(v if v else 0, 1) for v in irrad[:24]]
            # Shift UTC → SAST (+1 hour)
            result = [0.0] * 24
            for h in range(24):
                sast_h = h + 1
                if 0 <= sast_h <= 23:
                    result[sast_h] = utc_data[h]
            if sum(result) > 1:
                return result
        except Exception as e:
            print(f"  ⚠️  Irradiation attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                _time.sleep(3)

    return [0.0] * 24


def main():
    print("📊 Generating today_detailed.json for 1st Avenue Spar")

    if not XLS_FILE.exists():
        print(f"❌ XLS not found: {XLS_FILE}")
        sys.exit(1)

    # Parse XLS
    hourly_pv = parse_xls(XLS_FILE)
    if hourly_pv is None:
        sys.exit(1)

    total = sum(hourly_pv)
    last_hour = max((h for h in range(24) if hourly_pv[h] > 0), default=0)
    print(f"  ⚡ Total: {total:.1f} kWh | Last hour: {last_hour:02d}:00")

    # Load predictions
    predicted = load_predictions()

    # Fetch irradiation
    today = datetime.now(SAST).strftime("%Y-%m-%d")
    irradiation = fetch_irradiation(today)

    # Build output in the format the main dashboard expects
    output = []
    for h in range(24):
        output.append({
            "hour": h,
            "time": f"{h:02d}:00",
            "pv_kw": round(hourly_pv[h], 2),
            "predicted_kw": round(predicted[h], 2),
            "irradiation_wm2": round(irradiation[h], 1),
        })

    # Write output
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  ✅ Saved: {OUTPUT_FILE}")
    print(f"  📊 {sum(1 for h in hourly_pv if h > 0)} hours with PV data")


if __name__ == "__main__":
    main()
