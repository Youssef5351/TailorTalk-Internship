from typing import TypedDict, Literal, Optional, List
from langgraph.graph import StateGraph, END
import dateparser
import re
from datetime import datetime, timedelta
from gcal import check_availability, create_event
from datetime import time

# Define the state schema
class AgentState(TypedDict):
    message: str
    proposed_start: Optional[datetime]
    proposed_end: Optional[datetime]
    intent: str
    available: bool
    reply: str
    suggested_slots: Optional[List[datetime]]  # Track what we suggested
    conversation_state: str  # Track conversation flow
    guest_email: Optional[str] 

# --- Define your node functions ---

def parse_time_manually(text):
    """Manual time parsing as fallback"""
    text = text.lower()
    now = datetime.now()
    
    # Extract time patterns
    time_patterns = [
        r'(\d{1,2}):(\d{2})\s*(am|pm)',  # 3:00 pm
        r'(\d{1,2})\s*(am|pm)',          # 3 pm
        r'(\d{1,2}):(\d{2})',            # 15:00 (24-hour)
    ]
    
    time_match = None
    for pattern in time_patterns:
        match = re.search(pattern, text)
        if match:
            time_match = match
            break
    
    if not time_match:
        return None
    
    # Parse the time
    if len(time_match.groups()) == 3:  # Has AM/PM
        hour = int(time_match.group(1))
        minute = int(time_match.group(2)) if time_match.group(2) else 0
        am_pm = time_match.group(3)
        
        if am_pm == 'pm' and hour != 12:
            hour += 12
        elif am_pm == 'am' and hour == 12:
            hour = 0
    elif len(time_match.groups()) == 2 and time_match.group(2):  # Just hour with AM/PM
        hour = int(time_match.group(1))
        minute = 0
        am_pm = time_match.group(2)
        
        if am_pm == 'pm' and hour != 12:
            hour += 12
        elif am_pm == 'am' and hour == 12:
            hour = 0
    else:  # 24-hour format
        hour = int(time_match.group(1))
        minute = int(time_match.group(2)) if time_match.group(2) else 0
    
    # Determine the date
    if 'tomorrow' in text:
        target_date = now.date() + timedelta(days=1)
    elif 'today' in text:
        target_date = now.date()
    elif 'next week' in text:
        target_date = now.date() + timedelta(days=7)
    else:
        # Check for specific days
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        target_date = None
        for i, day in enumerate(days):
            if day in text:
                days_ahead = (i - now.weekday()) % 7
                if days_ahead == 0:  # Today is that day, assume next week
                    days_ahead = 7
                target_date = now.date() + timedelta(days=days_ahead)
                break
        
        if not target_date:
            target_date = now.date()  # Default to today
    
    # Combine date and time
    try:
        parsed_datetime = datetime.combine(target_date, datetime.min.time().replace(hour=hour, minute=minute))
        return parsed_datetime
    except ValueError:
        return None

def find_available_slots(date: datetime.date, duration_minutes=30) -> list[datetime]:
    """
    Return a list of available start times on a given date.
    """
    slots = []
    work_hours_start = 9
    work_hours_end = 18

    for hour in range(work_hours_start, work_hours_end):
        start_dt = datetime.combine(date, time(hour=hour, minute=0))
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        if check_availability(start_dt, end_dt):
            slots.append(start_dt)

    return slots

def classify_intent(message: str, conversation_state: str) -> str:
    """Classify user intent based on message and conversation state"""
    message_lower = message.lower().strip()
    
    # Handle responses to suggestions
    if conversation_state == "awaiting_choice":
        # Check for acceptance
        if any(word in message_lower for word in ["yes", "ok", "okay", "sure", "first", "09:00", "9:00", "10:00", "11:00"]):
            return "accept_suggestion"
        # Check for rejection
        elif any(word in message_lower for word in ["no", "none", "different", "other"]):
            return "reject_suggestion"
        # Check if they're suggesting a new time instead
        elif any(word in message_lower for word in ["tomorrow", "today", "pm", "am", ":"]):
            return "book"
    
    # Handle initial booking requests
    if any(word in message_lower for word in ["book", "schedule", "meeting", "call", "appointment"]):
        return "book"
    
    # Check if message contains time information
    if any(word in message_lower for word in [
        "tomorrow", "today", "next week", "pm", "am", ":",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
    ]):
        return "book"
    
    return "unknown"

def extract_time_of_day(text: str) -> Optional[time]:
    """
    Map vague time-of-day words to specific times.
    """
    text = text.lower()
    if "morning" in text:
        return time(hour=10, minute=0)
    elif "afternoon" in text:
        return time(hour=14, minute=0)
    elif "evening" in text:
        return time(hour=18, minute=0)
    elif "night" in text:
        return time(hour=20, minute=0)
    return None

def parse_next_specific_date(text: str) -> Optional[datetime.date]:
    """
    Parse expressions like 'next 30 june' or 'next 5 september'
    """
    text = text.lower()

    # Look for phrases like "next 30 june"
    match = re.search(r'next\s+(\d{1,2})\s+([a-z]+)', text)
    if match:
        day = int(match.group(1))
        month_str = match.group(2)

        try:
            # Convert month name to month number
            month = datetime.strptime(month_str, "%B").month
        except ValueError:
            try:
                month = datetime.strptime(month_str, "%b").month
            except ValueError:
                return None

        now = datetime.now()
        year = now.year

        # Build candidate date
        candidate_date = datetime(year, month, day).date()

        # If that date has passed or is today, go to next year
        if candidate_date <= now.date():
            candidate_date = datetime(year + 1, month, day).date()

        return candidate_date

    return None



def parse_message(state: AgentState) -> AgentState:
    message = state["message"]
    conversation_state = state.get("conversation_state", "initial")
    if conversation_state == "awaiting_email":
        # Check if message looks like an email
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", message)
        if email_match:
            email = email_match.group(0)
            return {
                **state,
                "guest_email": email,
                "conversation_state": "booking",   # trigger booking
                "intent": "book_accepted"
            }
        else:
            return {
                **state,
                "reply": "Hmm, that doesn't look like a valid email. Please type your email address.",
                "conversation_state": "awaiting_email"
            }
    
    print("User said:", message)
    print("Conversation state:", conversation_state)
    
    # Classify intent first
    intent = classify_intent(message, conversation_state)
    print(f"Classified intent: {intent}")
    
    # Handle different intents
    if intent == "accept_suggestion":
        # Accepting one of the suggested slots (e.g. "yes")
        suggested_slots = state.get("suggested_slots", [])
        if suggested_slots and state["message"].strip().lower() in ["yes", "ok", "okay", "sure"]:
            return {
                **state,
                "proposed_start": suggested_slots[0],
                "proposed_end": suggested_slots[0] + timedelta(minutes=30),
                "intent": "book_accepted",
                "conversation_state": "booking"
            }
        else:
            # Otherwise treat as a new booking request
            return parse_message({
                **state,
                "conversation_state": "initial"
            })
    
    elif intent == "book":
        # Try to parse datetime
        dt = None
        
        # First try dateparser with multiple configurations
        settings_list = [
            {"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": False},
            {"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": False, "DATE_ORDER": "MDY"},
            {"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": False, "DATE_ORDER": "DMY"},
            {"RELATIVE_BASE": datetime.now(), "RETURN_AS_TIMEZONE_AWARE": False},
        ]
        
        for settings in settings_list:
            dt = dateparser.parse(message, settings=settings)
            if dt:
                print(f"Dateparser succeeded with settings: {settings}")
                break
        
        # If dateparser fails, try manual parsing
        if not dt:
            # Check for specific "next [date]" pattern first
            next_specific_date = parse_next_specific_date(message)
            if next_specific_date:
                time_only = parse_time_manually(message)
                if time_only:
                    dt = datetime.combine(next_specific_date, time_only.time())
                else:
                    vague_time = extract_time_of_day(message)
                    if vague_time:
                        dt = datetime.combine(next_specific_date, vague_time)
                    else:
                        dt = datetime.combine(next_specific_date, time(hour=9, minute=0))
                print(f"Parsed next-specific date: {dt}")
                return {
                    **state,
                    "proposed_start": dt,
                    "proposed_end": dt + timedelta(minutes=30),
                    "intent": "book",
                    "conversation_state": "checking"
                }
                    # Check for vague time phrases
        vague_time = extract_time_of_day(message)
        if vague_time:
            now = datetime.now()
            if "tomorrow" in message.lower():
                target_date = now.date() + timedelta(days=1)
            elif "today" in message.lower():
                target_date = now.date()
            elif "next week" in message.lower():
                target_date = now.date() + timedelta(days=7)
            else:
                # Default to today if no day mentioned
                target_date = now.date()
            
            dt = datetime.combine(target_date, vague_time)
            print(f"Mapped vague time to specific datetime: {dt}")
            return {
                **state,
                "proposed_start": dt,
                "proposed_end": dt + timedelta(minutes=30),
                "intent": "book",
                "conversation_state": "checking"
            }
        
        # Finally try purely manual parsing
        print("Dateparser failed, trying manual parsing...")
        dt = parse_time_manually(message)

        if dt:
            return {
                **state,
                "proposed_start": dt,
                "proposed_end": dt + timedelta(minutes=30),
                "intent": "book",
                "conversation_state": "checking"
            }
        else:
            return {
                **state,
                "intent": "unknown",
                "conversation_state": "initial"
            }
    
    else:
        return {
            **state,
            "intent": "unknown",
            "conversation_state": "initial"
        }

def check_calendar(state: AgentState) -> AgentState:
    if state.get("intent") in ["book", "book_accepted"]:
        start_time = state["proposed_start"]
        end_time = state["proposed_end"]
        
        available = check_availability(start_time, end_time)
        return {
            **state,
            "available": available
        }
    return state

def book_meeting(state: AgentState) -> AgentState:
    if not state.get("guest_email"):
        return {
            **state,
            "reply": "Great! Before I book this meeting, could you please provide your email so I can add it to the calendar invite?",
            "conversation_state": "awaiting_email"
        }
    if state.get("available"):
        start_time = state["proposed_start"]
        end_time = state["proposed_end"]
        
        link = create_event(
            start_time,
            end_time,
            summary="Meeting Is Booked with AI Bot",
            guest_email=state.get("guest_email")
        )
        
        return {
            **state,
            "reply": f"✅ Your meeting is booked for {start_time.strftime('%Y-%m-%d %H:%M')}. Here's the link: {link}",
            "conversation_state": "completed"
        }
    else:
        return {
            **state,
            "reply": "Sorry, that time slot is busy. Please suggest another time.",
            "conversation_state": "initial"
        }

def collect_email(state: AgentState) -> AgentState:
    message = state["message"]
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", message)
    if email_match:
        email = email_match.group(0)
        return {
            **state,
            "guest_email": email,
            "conversation_state": "booking"
        }
    else:
        return {
            **state,
            "reply": "Hmm, that doesn't look like a valid email. Please type your email address.",
            "conversation_state": "awaiting_email"
        }

def handle_rejection(state: AgentState) -> AgentState:
    """Handle when user rejects our suggestions"""
    return {
        **state,
        "reply": "No problem! Please suggest another time that works for you (e.g., 'tomorrow at 2pm' or 'Friday at 10am').",
        "conversation_state": "initial",
        "suggested_slots": None  # Clear previous suggestions
    }

def suggest_alternatives(state: AgentState) -> AgentState:
    """Suggest alternative times when requested slot is busy"""
    proposed_dt = state.get("proposed_start")
    if proposed_dt:
        date = proposed_dt.date()
        free_slots = find_available_slots(date)
        
        if free_slots:
            # Store suggestions in state for later reference
            suggested_slots = free_slots[:3]  # Keep top 3 suggestions
            times_str = ", ".join(
                slot.strftime("%H:%M") for slot in suggested_slots
            )
            reply = f"Sorry, that time slot is busy. But I'm free at these times on {date}: {times_str}. Would you like one of those?"
            
            return {
                **state,
                "reply": reply,
                "conversation_state": "awaiting_choice",
                "suggested_slots": suggested_slots
            }
        else:
            return {
                **state,
                "reply": f"Sorry, that time slot is busy and I found no other free times on {date}. Please suggest another day or time.",
                "conversation_state": "initial"
            }
    else:
        return {
            **state,
            "reply": "Sorry, that time slot is busy. Please suggest another time.",
            "conversation_state": "initial"
        }

def fallback(state: AgentState) -> AgentState:
    message = state.get("message", "")
    intent = state.get("intent", "")
    message = state.get("message", "").strip().lower()
    if message in ["hi", "hello", "hey"]:
        return {
            **state,
            "reply": "Hi there! Let me know if you'd like to book a call. For example, you can say 'Book me a call tomorrow at 3pm.'",
            "conversation_state": "initial"
        }
    if intent == "unknown":
        if any(word in message.lower() for word in [
            "tomorrow", "today", "next week",
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
        ]):
            reply = (
                f"I detected time-related words in '{message}' but couldn't parse the exact time. "
                "Please try formats like 'tomorrow at 3pm' or 'next Monday at 2:30pm'."
            )
        else:
            reply = (
                "I couldn't find any time information in your message. "
                "Please try something like 'book me a call tomorrow at 3pm'."
            )
    else:
        reply = "I'm not sure how to help with that. Please try booking a meeting with a specific time."

    return {
        **state,
        "reply": reply,
        "conversation_state": "initial"
    }

# --- Build your graph ---

# Create the StateGraph with the state schema
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("parse", parse_message)
workflow.add_node("calendar", check_calendar)
workflow.add_node("book", book_meeting)
workflow.add_node("suggest_alternatives", suggest_alternatives)
workflow.add_node("handle_rejection", handle_rejection)
workflow.add_node("fallback", fallback)
workflow.add_node("collect_email", collect_email)

# Set entry point
workflow.set_entry_point("parse")

# Add conditional edges
def route_after_parse(state: AgentState) -> Literal["calendar", "handle_rejection", "fallback"]:
    intent = state.get("intent")
    if intent in ["book", "book_accepted"]:
        return "calendar"
    elif intent == "reject_suggestion":
        return "handle_rejection"
    else:
        return "fallback"

def route_after_calendar(state: AgentState) -> Literal["book", "suggest_alternatives"]:
    if state.get("available"):
        return "book"
    else:
        return "suggest_alternatives"

workflow.add_conditional_edges("parse", route_after_parse)
workflow.add_conditional_edges("calendar", route_after_calendar)
workflow.add_conditional_edges(
    "collect_email",
    lambda state: "book" if state.get("guest_email") else "collect_email"
)

# End the workflow after terminal nodes
workflow.add_edge("book", END)
workflow.add_edge("suggest_alternatives", END)
workflow.add_edge("handle_rejection", END)
workflow.add_edge("fallback", END)
workflow.add_edge("collect_email", END)

# Compile the graph
app = workflow.compile()

# --- Exposed functions for FastAPI ---

# Global state storage (in production, use proper session management)
conversation_states = {}

def handle_message(message: str, user_id: str = "default") -> str:
    """
    Handle a message and return reply, automatically managing conversation state
    """
    # Get previous state for this user
    previous_state = conversation_states.get(user_id)
    
    # Initialize state with previous conversation context
    if previous_state:
        initial_state = {
            **previous_state,
            "message": message
        }
    else:
        initial_state = {
            "message": message,
            "conversation_state": "initial"
        }
    
    result = app.invoke(initial_state)
    reply = result.get("reply", "Something went wrong.")
    
    # Store updated state for this user
    conversation_states[user_id] = result
    
    return reply

def handle_message_with_state(message: str, previous_state: dict = None) -> tuple[str, dict]:
    """
    Alternative function that returns both reply and state for advanced usage
    """
    # Initialize state with previous conversation context
    if previous_state:
        initial_state = {
            **previous_state,
            "message": message
        }
    else:
        initial_state = {
            "message": message,
            "conversation_state": "initial"
        }
    
    result = app.invoke(initial_state)
    reply = result.get("reply", "Something went wrong.")
    
    # Return both reply and state for conversation continuity
    return reply, result

def clear_conversation(user_id: str = "default") -> None:
    """Clear conversation state for a user"""
    conversation_states.pop(user_id, None)
