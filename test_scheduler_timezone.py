#!/usr/bin/env python3
"""
Test Scheduler Timezone Configuration
Verifies that the scheduler is using the correct timezone for weekly reports
"""
import os
import sys
from dotenv import load_dotenv
from datetime import datetime
import pytz

# Load environment variables
load_dotenv()

def test_timezone_config():
    """Test scheduler timezone configuration"""
    print("=" * 70)
    print("SCHEDULER TIMEZONE CONFIGURATION TEST")
    print("=" * 70)
    
    # Check environment variables
    scheduler_timezone_str = os.getenv("SCHEDULER_TIMEZONE", None)
    weekly_report_hour = int(os.getenv("WEEKLY_REPORT_SEND_HOUR", "12"))
    weekly_report_minute = int(os.getenv("WEEKLY_REPORT_SEND_MINUTE", "0"))
    weekly_report_enabled = os.getenv("WEEKLY_REPORT_ENABLED", "true").lower() == "true"
    
    print(f"\n[CONFIG] Environment Variables:")
    print(f"   SCHEDULER_TIMEZONE: {scheduler_timezone_str or 'Not set (will use UTC)'}")
    print(f"   WEEKLY_REPORT_ENABLED: {weekly_report_enabled}")
    print(f"   WEEKLY_REPORT_SEND_HOUR: {weekly_report_hour}")
    print(f"   WEEKLY_REPORT_SEND_MINUTE: {weekly_report_minute}")
    
    # Get timezone object
    scheduler_timezone = None
    if scheduler_timezone_str:
        try:
            scheduler_timezone = pytz.timezone(scheduler_timezone_str)
            print(f"\n[OK] Timezone Configuration:")
            print(f"   Timezone: {scheduler_timezone_str}")
            print(f"   Timezone Object: {scheduler_timezone}")
            
            # Get current time in configured timezone
            now_utc = datetime.now(pytz.UTC)
            now_local = now_utc.astimezone(scheduler_timezone)
            print(f"   Current UTC Time: {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"   Current Local Time ({scheduler_timezone_str}): {now_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except Exception as e:
            print(f"\n[ERROR] Invalid timezone '{scheduler_timezone_str}': {e}")
            scheduler_timezone = pytz.UTC
    else:
        scheduler_timezone = pytz.UTC
        print(f"\n[WARNING] No timezone configured, using UTC")
        print(f"   Current UTC Time: {datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    # Calculate next run time (works even without APScheduler installed)
    print(f"\n[TEST] Calculating Next Run Time:")
    
    try:
        from datetime import timedelta
        now = datetime.now(scheduler_timezone)
        
        # Find next Monday
        days_ahead = 0 - now.weekday()  # Monday is 0
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        
        next_monday = now + timedelta(days=days_ahead)
        next_monday = next_monday.replace(hour=weekly_report_hour, minute=weekly_report_minute, second=0, microsecond=0)
        
        # If the calculated time is in the past (e.g., if it's Monday and time hasn't passed yet)
        if next_monday <= now:
            next_monday += timedelta(days=7)
        
        # Convert to both UTC and local timezone for display
        next_run_utc = next_monday.astimezone(pytz.UTC)
        next_run_local = next_monday
        
        print(f"\n[OK] Weekly Report Schedule:")
        print(f"   Next Run (UTC): {next_run_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"   Next Run ({scheduler_timezone_str or 'UTC'}): {next_run_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"   Day of Week: Monday")
        print(f"   Time: {weekly_report_hour:02d}:{weekly_report_minute:02d}")
        
        # Calculate time until next run
        time_until = next_monday - now
        total_hours = time_until.total_seconds() / 3600
        days = int(total_hours / 24)
        hours = int(total_hours % 24)
        minutes = int((total_hours % 24 - hours) * 60)
        print(f"   Time Until Next Run: {days} days, {hours} hours, {minutes} minutes")
        
        # Test APScheduler if available
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
            
            print(f"\n[TEST] APScheduler Configuration:")
            print(f"   APScheduler imported successfully")
            
            # Create test scheduler with timezone
            test_scheduler = BackgroundScheduler(timezone=scheduler_timezone)
            
            # Add a test job
            def test_job():
                pass
            
            test_scheduler.add_job(
                func=test_job,
                trigger=CronTrigger(
                    day_of_week='mon',
                    hour=weekly_report_hour,
                    minute=weekly_report_minute,
                    timezone=scheduler_timezone
                ),
                id='test_weekly_report',
                replace_existing=True
            )
            
            # Start scheduler to verify it works
            test_scheduler.start()
            test_scheduler.shutdown()
            
            print(f"   [OK] Scheduler configuration test passed")
            
        except ImportError:
            print(f"\n[INFO] APScheduler not installed in test environment")
            print(f"   (This is OK - scheduler will work when server runs)")
        
        print(f"\n[OK] Schedule calculation completed successfully")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Schedule Calculation Error:")
        print(f"   {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n[ERROR] Scheduler Configuration Error:")
        print(f"   {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_server_config():
    """Test if server.py configuration matches"""
    print(f"\n" + "=" * 70)
    print("SERVER.PY CONFIGURATION CHECK")
    print("=" * 70)
    
    try:
        # Try to import config
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from config import SCHEDULER_TIMEZONE, WEEKLY_REPORT_ENABLED, WEEKLY_REPORT_SEND_HOUR, WEEKLY_REPORT_SEND_MINUTE
        
        print(f"\n[CONFIG] Server Configuration (from config.py):")
        print(f"   SCHEDULER_TIMEZONE: {SCHEDULER_TIMEZONE or 'None (will use UTC)'}")
        print(f"   WEEKLY_REPORT_ENABLED: {WEEKLY_REPORT_ENABLED}")
        print(f"   WEEKLY_REPORT_SEND_HOUR: {WEEKLY_REPORT_SEND_HOUR}")
        print(f"   WEEKLY_REPORT_SEND_MINUTE: {WEEKLY_REPORT_SEND_MINUTE}")
        
        if SCHEDULER_TIMEZONE:
            try:
                tz = pytz.timezone(SCHEDULER_TIMEZONE)
                print(f"   [OK] Timezone '{SCHEDULER_TIMEZONE}' is valid")
                return True
            except Exception as e:
                print(f"   [ERROR] Timezone '{SCHEDULER_TIMEZONE}' is invalid: {e}")
                return False
        else:
            print(f"   [WARNING] No timezone configured - scheduler will use UTC")
            return False
            
    except ImportError as e:
        print(f"\n[ERROR] Could not import config: {e}")
        return False
    except Exception as e:
        print(f"\n[ERROR] Error checking config: {e}")
        return False

if __name__ == "__main__":
    print("\n")
    success1 = test_timezone_config()
    success2 = test_server_config()
    
    print(f"\n" + "=" * 70)
    if success1 and success2:
        print("[OK] ALL TESTS PASSED - Scheduler timezone is configured correctly!")
    else:
        print("[WARNING] SOME TESTS FAILED - Please check the errors above")
    print("=" * 70)
    print("\n")
    
    # Summary
    print("SUMMARY:")
    print("1. Check the timezone configuration above")
    print("2. Verify 'Next Run' time is correct for your timezone")
    print("3. When you start the server, look for this log message:")
    print("   [SCHEDULER] Using configured timezone: Asia/Kolkata")
    print("   [STARTUP] [OK] Weekly report scheduler started (runs every Monday at 12:41 Asia/Kolkata)")
    print("\n")
