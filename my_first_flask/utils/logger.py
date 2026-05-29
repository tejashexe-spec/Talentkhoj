import os
from datetime import datetime

def log_activity(log_type, message):
    try:
        # Determine the base directory of the project
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logs_dir = os.path.join(base_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        log_file = os.path.join(logs_dir, "activity_logs.md")
        
        # Format log entry in Markdown table row
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"| {timestamp} | **{log_type.upper()}** | {message} |\n"
        
        # If file doesn't exist, create it with header first
        if not os.path.exists(log_file):
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("# TalentKhoj System Activity Logs\n\n")
                f.write("| Timestamp | Log Type | Message |\n")
                f.write("| --- | --- | --- |\n")
                
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Failed to write system log: {e}")
