#!/usr/bin/env python3
"""
Check for downtime in the last hour and send Telegram notification
"""
import json
import os
import sys
from datetime import datetime, timedelta
import requests

def send_telegram_message(bot_token, chat_id, message):
    """Send message via Telegram Bot API"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("✅ Telegram notification sent successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to send Telegram notification: {e}")
        return False

def check_recent_downtime(dashboard_file='dashboard_data.json'):
    """Check for downtime in the last hour"""
    
    # Load dashboard data
    try:
        with open(dashboard_file, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"⚠️ {dashboard_file} not found")
        return None
    
    # Get today's date
    today = datetime.now().strftime('%Y-%m-%d')
    current_hour = datetime.now().hour
    current_minute = datetime.now().minute
    
    # Find today's record
    today_record = None
    for record in data.get('daily_records', []):
        if record['date'] == today:
            today_record = record
            break
    
    if not today_record or not today_record.get('hourly_data'):
        print(f"⚠️ No data for today ({today})")
        return None
    
    hourly_data = today_record['hourly_data']
    
    # Check the last hour for downtime
    downtime_detected = False
    downtime_start = None
    downtime_end = None
    consecutive_zeros = 0
    
    # Look back 1 hour from now
    lookback_minutes = 60
    
    for entry in reversed(hourly_data):
        time_str = entry.get('time', '00:00:00')
        hour = int(time_str.split(':')[0])
        minute = int(time_str.split(':')[1])
        
        # Calculate minutes difference from now
        entry_total_minutes = (hour * 60) + minute
        current_total_minutes = (current_hour * 60) + current_minute
        minutes_ago = current_total_minutes - entry_total_minutes
        
        # Only check last hour (and only during daylight hours)
        if minutes_ago > lookback_minutes or minutes_ago < 0:
            continue
        
        if hour < 6 or hour >= 19:
            continue  # Skip nighttime
        
        generation = entry.get('generation_kw', 0)
        
        # Check if generation is zero or very low during expected production hours
        if generation < 0.5:
            consecutive_zeros += 1
            if downtime_start is None:
                downtime_start = time_str
            downtime_end = time_str
            
            # If we have 10+ minutes (2+ intervals) of zero generation, flag it
            if consecutive_zeros >= 2:  # 2 x 5min = 10 minutes
                downtime_detected = True
    
    if downtime_detected:
        return {
            'date': today,
            'start_time': downtime_start,
            'end_time': downtime_end,
            'duration_minutes': consecutive_zeros * 5
        }
    
    return None

def main():
    # Get environment variables
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not bot_token or not chat_id:
        print("⚠️ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        print("Skipping notification")
        sys.exit(0)  # Don't fail the workflow
    
    # Check for downtime
    downtime = check_recent_downtime()
    
    if downtime:
        # Format message
        duration = downtime['duration_minutes']
        hours = duration // 60
        minutes = duration % 60
        
        if hours > 0:
            duration_str = f"{hours}h {minutes}m"
        else:
            duration_str = f"{minutes}m"
        
        message = f"""
🔴 <b>Solar System Downtime Alert</b>

<b>Date:</b> {downtime['date']}
<b>Time:</b> {downtime['start_time']} - {downtime['end_time']}
<b>Duration:</b> {duration_str}

⚠️ System had zero/low generation during expected production hours.

Check dashboard: https://genergydashboard.github.io/1stAveSpar/
"""
        
        print(f"⚠️ Downtime detected: {duration_str}")
        send_telegram_message(bot_token, chat_id, message)
    else:
        print("✅ No downtime detected in the last hour")

if __name__ == '__main__':
    main()
