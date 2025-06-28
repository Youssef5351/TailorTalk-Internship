# app.py

import streamlit as st
import requests
import subprocess
import os

if not os.environ.get("FASTAPI_STARTED"):
    os.environ["FASTAPI_STARTED"] = "1"
    subprocess.Popen(["uvicorn", "fastapi_app:app", "--host", "0.0.0.0", "--port", "8000"])
# FastAPI URL
API_URL = "https://tailortalk-internship-production.up.railway.app"


# Initialize chat history
if "messages" not in st.session_state:
    st.session_state["messages"] = []

st.title("🤖 TailorTalk AI Booking Agent")

st.write("Chat with me to book meetings in your calendar!")

# Chat display
for msg in st.session_state["messages"]:
    if msg["role"] == "user":
        st.chat_message("user").markdown(msg["content"])
    else:
        st.chat_message("assistant").markdown(msg["content"])

# User input
user_input = st.chat_input("Say something...")

if user_input:
    # Show user message immediately
    st.chat_message("user").markdown(user_input)
    st.session_state["messages"].append({"role": "user", "content": user_input})

    # Send message to FastAPI
    payload = {"message": user_input}
    try:
        response = requests.post(API_URL, json=payload, timeout=20)
        response.raise_for_status()
        reply = response.json().get("reply", "Sorry, I didn't understand that.")
    except Exception as e:
        reply = f"⚠️ Error talking to the backend: {e}"

    # Show bot reply
    st.chat_message("assistant").markdown(reply)
    st.session_state["messages"].append({"role": "assistant", "content": reply})
