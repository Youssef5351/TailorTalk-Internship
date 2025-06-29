# gcal.py

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from google.auth.transport.requests import Request
import pickle
import os.path

SCOPES = ['https://www.googleapis.com/auth/calendar']

# Reuse credentials to avoid opening a browser each call
_service = None

def get_calendar_service():
    creds = None

    # Check if token file exists
    if not os.path.exists('token.pickle'):
        raise RuntimeError("Google credentials missing in deployment. Upload token.pickle.")

    # Load token
    try:
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    except Exception as e:
        raise RuntimeError(f"Error loading token.pickle: {e}")

    # Check if credentials are valid
    if not creds:
        raise RuntimeError("Invalid credentials in token.pickle")
    
    # Refresh if expired
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Save refreshed token
                with open('token.pickle', 'wb') as token:
                    pickle.dump(creds, token)
            except Exception as e:
                raise RuntimeError(f"Failed to refresh credentials: {e}")
        else:
            raise RuntimeError("Credentials expired and cannot be refreshed. Please re-authenticate.")

    service = build('calendar', 'v3', credentials=creds)
    return service


def check_availability(start_time, end_time):
    """
    Checks if there are any busy slots between start_time and end_time.

    start_time, end_time: datetime objects (timezone-aware or naive)
    Returns: True if time slot is free, False if busy
    """
    service = get_calendar_service()
    
    # Ensure datetime objects have timezone info
    cairo_tz = ZoneInfo("Africa/Cairo")
    
    # If datetime is naive (no timezone), assume it's in Cairo timezone
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=cairo_tz)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=cairo_tz)

    # Convert datetimes to RFC3339 format with timezone
    body = {
        "timeMin": start_time.isoformat(),
        "timeMax": end_time.isoformat(),
        "items": [{"id": "primary"}]
    }
    
    print(f"DEBUG: Checking availability from {start_time.isoformat()} to {end_time.isoformat()}")
    print(f"DEBUG: Request body: {body}")

    try:
        events_result = service.freebusy().query(body=body).execute()
        busy_times = events_result['calendars']['primary']['busy']
        print(f"DEBUG: Busy times found: {busy_times}")
        return not busy_times
    except Exception as e:
        print(f"ERROR in check_availability: {e}")
        # Print more details about the error
        if hasattr(e, 'resp'):
            print(f"Response status: {e.resp.status}")
            print(f"Response reason: {e.resp.reason}")
        raise


def create_event(start_time, end_time, summary="Meeting with AI Bot", guest_email=None):
    """
    Creates a calendar event.

    start_time, end_time: datetime objects (timezone-aware or naive)
    summary: title of the event
    guest_email: optional email address to invite

    Returns: event link
    """
    service = get_calendar_service()
    
    cairo_tz = ZoneInfo("Africa/Cairo")
    
    # If datetime is naive (no timezone), assume it's in Cairo timezone
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=cairo_tz)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=cairo_tz)

    event = {
        'summary': summary,
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'Africa/Cairo',
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'Africa/Cairo',
        }
    }

    if guest_email:
        event['attendees'] = [{'email': guest_email}]

    event_result = service.events().insert(
        calendarId='primary',
        body=event,
        sendUpdates='all' if guest_email else 'none'
    ).execute()

    return event_result.get('htmlLink')


# Example usage for testing
if __name__ == "__main__":
    tz = ZoneInfo("Africa/Cairo")
    start_time = datetime(2025, 6, 29, 16, 0, tzinfo=tz)
    end_time = start_time + timedelta(hours=1)

    is_free = check_availability(start_time, end_time)
    print("Available:", is_free)

    if is_free:
        test_email = "test.user@example.com"
        link = create_event(
            start_time,
            end_time,
            summary="Test Meeting",
            guest_email=test_email
        )
        print("Event link:", link)
    else:
        print("Time slot is busy.")
