"""Resolve server.py merge conflict (weekly report scheduler)."""
import os

path = os.path.join(os.path.dirname(__file__), "server.py")
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find conflict block by markers
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if line.strip() == "<<<<<<< HEAD":
        start_idx = i
    if start_idx is not None and ">>>>>>>" in line:
        end_idx = i
        break

if start_idx is None or end_idx is None:
    print("Conflict markers not found")
else:
    resolved = [
        '            logger.info(f"[STARTUP] Weekly report scheduler started '
        '(runs every Monday at {WEEKLY_REPORT_SEND_HOUR:02d}:{WEEKLY_REPORT_SEND_MINUTE:02d} {timezone_str})")\n',
        '            run_weekly_report_if_missed(WEEKLY_REPORT_SEND_HOUR, WEEKLY_REPORT_SEND_MINUTE)\n',
    ]
    new_lines = lines[:start_idx] + resolved + lines[end_idx + 1:]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    print("Conflict resolved in server.py")

# Ensure run_weekly_report_if_missed is imported
with open(path, "r", encoding="utf-8") as f:
    content = f.read()
old_import = "from app.weekly_reports_scheduler import scheduled_weekly_reports_sync"
new_import = "from app.weekly_reports_scheduler import scheduled_weekly_reports_sync, run_weekly_report_if_missed"
if new_import not in content and old_import in content:
    content = content.replace(old_import, new_import, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Import updated in server.py")
