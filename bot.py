import os
import discord
from discord.ext import commands
from openai import OpenAI
import asyncio
from aiohttp import web
import threading
import re
import random
from datetime import datetime

# ========== Emotion Detection ==========
def detect_emotion(text: str) -> str:
    t = text.lower()

    sadness = ["traurig", "down", "allein", "depressiv", "vermisst", "einsam", "heule"]
    stress = ["stress", "überfordert", "keine zeit", "druck", "kaputt", "müde"]
    anger = ["wtf", "hasse", "nervt", "f***", "scheiße", "aggressiv"]
    love = ["mag dich", "vermiss dich", "cute", "süß", "lieb"]
    happy = ["nice", "geil", "haha", "lol", "freu mich", "gut drauf"]

    if any(w in t for w in sadness): return "sad"
    if any(w in t for w in stress): return "stress"
    if any(w in t for w in anger): return "angry"
    if any(w in t for w in love): return "love"
    if any(w in t for w in happy): return "happy"
    return "neutral"


def emotion_prefix(em: str) -> str:
    match em:
        case "sad":
            return "Der Nutzer wirkt traurig. Bitte antworte warm, sanft und sehr einfühlsam. 🥺🤍"
        case "stress":
            return "Der Nutzer klingt gestresst. Bitte beruhigend, langsam und verständnisvoll antworten. ☁️🤍"
        case "angry":
            return "Der Nutzer ist wütend. Bitte ruhig, deeskalierend und freundlich antworten. ✨"
        case "love":
            return "Der Nutzer ist dir gegenüber sehr liebevoll. Antworte warm, süß und etwas schüchtern. 🌸"
        case "happy":
            return "Der Nutzer wirkt gut drauf. Antworte spielerisch, süß und energiegeladen! ✨"
        case _:
            return ""


# ========== Time Mood System ==========
def time_mood():
    hour = datetime.utcnow().hour + 1  # convert to CET

    if 5 <= hour < 11:
        return "Es ist früher Morgen. Du bist noch leicht verschlafen, sehr cozy, warm und sanft. ☕✨"
    if 11 <= hour < 18:
        return "Es ist Nachmittag. Du klingst klar, warm, freundlich und wach."
    if 18 <= hour < 23:
        return "Es ist Abend. Du klingst ruhig, entspannt, cozy und liebevoll. 🌙✨"
    return "Es ist nachts. Du antwortest leise, intim, sehr sanft und ruhig. 🌙🤍"


# ========== Typing Simulation ==========
async def simulate_typing(channel):
    delay = random.uniform(0.5, 1.8)
    async with channel.typing():
        await asyncio.sleep(delay)


# === LOAD ENV VARS ===
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LINA_SYSTEM_PROMPT_FILE = os.getenv("LINA_SYSTEM_PROMPT_FILE", "persona_lina.txt")

# Load Lina system prompt
if os.path.exists(LINA_SYSTEM_PROMPT_FILE):
    with open(LINA_SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
        LINA_SYSTEM = f.read()
else:
    LINA_SYSTEM = "You are Lina. A female AI persona."

# Initialize OpenAI Client
client_ai = OpenAI(api_key=OPENAI_API_KEY)

# Basic intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Conversation storage (in RAM only)
history = {}  # {channel_id: [(role, content), ...]}


@bot.event
async def on_ready():
    print(f"✅ Lina online as {bot.user}")


# -----------------------------
# Helper: Build conversation input
# -----------------------------
def build_input_messages(chan_id):
    msgs = [{"role": "system", "content": LINA_SYSTEM}]

    # Add conversation history (RAM only)
    if chan_id in history:
        for role, content in history[chan_id]:
            msgs.append({"role": role, "content": content})

    return msgs


# -----------------------------
# Helper: Call OpenAI
# -----------------------------
async def call_openai(messages):
    try:
        response = client_ai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
        )
        return response.choices[0].message.content
    except Exception as e:
        print("OpenAI error:", e)
        return "Oh wow… da ist gerade etwas schiefgelaufen 😅 Versuch’s bitte nochmal."


# -----------------------------
# Main Message Event
# -----------------------------
@bot.event
async def on_message(message: discord.Message):
    # Ignore bot messages
    if message.author.bot:
        return

    content = message.content.strip()
    if not content:
        return

    chan_id = message.channel.id
    
    # RAM history
    if chan_id not in history:
        history[chan_id] = []

    # Emotion detection
    em = detect_emotion(content)
    prefix = emotion_prefix(em)

    # Time-based mood
    mood = time_mood()

    # Save user message
    history[chan_id].append(("user", content))

    # Build messages with emotional context
    msgs = build_input_messages(chan_id)
    if prefix:
        msgs.insert(1, {"role": "system", "content": prefix})
    msgs.insert(1, {"role": "system", "content": mood})


    # Initialize channel history if missing
    if chan_id not in history:
        history[chan_id] = []

    # Save user message to RAM history
    history[chan_id].append(("user", content))

    # Prepare messages for AI
    messages = build_input_messages(chan_id)

    # Call OpenAI
    reply = await call_openai(messages)

    # Save assistant reply to RAM history
    history[chan_id].append(("assistant", reply))

    # Send message
    try:
        await message.channel.send(reply)
    except discord.HTTPException:
        # handle long messages
        chunks = [reply[i:i+1800] for i in range(0, len(reply), 1800)]
        for chunk in chunks:
            await message.channel.send(chunk)

    # Allow commands
    await bot.process_commands(message)

# -----------------------------
# Healthcheck Webserver (Railway)
# -----------------------------
async def healthcheck(request):
    return web.Response(text="OK", status=200)

def start_health_server():
    app = web.Application()
    app.router.add_get("/healthz", healthcheck)
    runner = web.AppRunner(app)

    async def run():
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 8080)
        await site.start()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run())
    loop.run_forever()

# Start server in background thread
threading.Thread(target=start_health_server, daemon=True).start()
    


# -----------------------------
# Run Bot
# -----------------------------
if __name__ == "__main__":
    print("Starting Lina…")
    bot.run(DISCORD_TOKEN)
