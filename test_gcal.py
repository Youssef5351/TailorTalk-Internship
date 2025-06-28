# test_gcal.py
from datetime import datetime, timedelta, timezone
from gcal import check_availability, create_event

# Define a test time slot
start_time = datetime.utcnow() + timedelta(hours=2)
end_time = start_time + timedelta(minutes=30)

# Check if it's free
if check_availability(start_time, end_time):
    print("Time slot is free! Creating event...")
    event_link = create_event(start_time, end_time, summary="Test AI Meeting")
    print("Event created:", event_link)
else:
    print("Time slot is busy. Pick another time.")
