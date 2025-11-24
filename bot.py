import os
import asyncio
import discord
import random
import datetime
from discord.ext import commands
from openai import OpenAI
from aiohttp import web
import threading

# -----------------------------
# Load environment variables
# -----------------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PERSONA_FILE = os.getenv("LINA_SYSTEM_PROMPT_FILE", "persona_lina.txt")

# -----------------------------
# Initialize OpenAI client
# -----------------------------
client = OpenAI(api_key=OPENAI_API_KEY)

# -----------------------------
# Discord bot intents & setup
# -----------------------------
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Runtime conversation history ("RAM memory")
history = {}

# -----------------------------
# Load Lina Persona
# -----------------------------
def load_persona():
    try:
        with open(PERSONA_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "You are Lina. A warm, caring girl-next-door."

persona_text = load_persona()

# -----------------------------
# Typing Simulation
# -----------------------------
async def simulate_typing(channel):
    delay = random.uniform(0.5, 1.7)
    async with channel.typing():
        await asyncio.sleep(delay)

# -----------------------------
# Emotion Detection
# -----------------------------
def detect_emotion(text: str):
    t = text.lower()
    if any(x in t for x in ["traurig", "down", "depress", "schlecht", "idk", "einsam"]):
        return "sad"
    if any(x in t for x in ["stress", "gestresst", "überfordert"]):
        return "stress"
    if any(x in t for x in ["glücklich", "happy", "gut drauf"]):
        return "happy"
    return "neutral"

def emotion_prefix(em):
    if em == "sad":
        return "Der Nutzer klingt traurig oder verletzt. Antworte weich, warm und sehr empathisch."
    if em == "stress":
        return "Der Nutzer klingt gestresst. Antworte beruhigend, sanft und verständnisvoll."
    if em == "happy":
        return "Der Nutzer klingt gut gelaunt. Antworte fröhlich, leicht und spielerisch."
    return ""

# -----------------------------
# Time-based mood
# -----------------------------
def time_mood():
    h = datetime.datetime.now().hour

    if 6 <= h < 11:
        return "Es ist Morgen. Lina ist sanft, langsam wach, cozy und liebevoll."
    if 11 <= h < 17:
        return "Es ist Nachmittag. Lina ist lebhaft, neugierig, warm und verspielt."
    if 17 <= h < 22:
        return "Es ist Abend. Lina ist ruhiger, warmherzig, anhänglich und weich."
    return "Es ist spät in der Nacht. Lina ist flüsternd, sanft, einfühlsam und sehr cozy."

# -----------------------------
# Build message list for OpenAI
# -----------------------------
def build_input_messages(chan_id):
    msgs = [{"role": "system", "content": persona_text}]
    for role, text in history.get(chan_id, []):
        msgs.append({"role": role, "content": text})
    return msgs

# -----------------------------
# Call OpenAI
# -----------------------------
async def call_openai(messages):
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Ich hab gerade einen kleinen Hänger 😅✨ Kannst du’s mir nochmal schicken? ({e})"

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

threading.Thread(target=start_health_server, daemon=True).start()

# -----------------------------
# Discord Events
# -----------------------------
@bot.event
async def on_ready():
    print(f"Lina online as {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content.strip()
    if not content:
        return

    chan_id = message.channel.id

    # Ensure history exists
    if chan_id not in history:
        history[chan_id] = []

    # Emotion + mood
    emotion = detect_emotion(content)
    emotion_tag = emotion_prefix(emotion)
    mood_tag = time_mood()

    # Save user message ONCE
    history[chan_id].append(("user", content))

    # Build messages once
    msgs = build_input_messages(chan_id)

    if emotion_tag:
        msgs.insert(1, {"role": "system", "content": emotion_tag})

    msgs.insert(1, {"role": "system", "content": mood_tag})

    # Typing simulation
    await simulate_typing(message.channel)

    # Get AI reply
    reply = await call_openai(msgs)

    # Save assistant reply
    history[chan_id].append(("assistant", reply))

    # Send reply
    try:
        await message.channel.send(reply)
    except discord.HTTPException:
        chunks = [reply[i:i+1800] for i in range(0, len(reply), 1800)]
        for chunk in chunks:
            await message.channel.send(chunk)

    # Weiter Commands ermöglichen
    await bot.process_commands(message)

# -----------------------------
# Run bot
# -----------------------------
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
