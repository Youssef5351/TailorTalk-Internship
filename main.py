from fastapi import FastAPI, Request
from agent import handle_message

app = FastAPI()

@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    user_message = data.get("message")
    
    reply = handle_message(user_message)
    
    return {"reply": reply}
