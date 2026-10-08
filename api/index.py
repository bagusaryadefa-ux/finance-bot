from fastapi import FastAPI, Request
from bot.handlers import process_update
from bot.config import TELEGRAM_TOKEN
import asyncio

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Bot is running"}

@app.post(f"/{TELEGRAM_TOKEN}")
async def handle_telegram_update(request: Request):
    update = await request.json()
    # Run in background to respond quickly to Telegram webhook
    asyncio.create_task(process_update(update))
    return {"ok": True}
