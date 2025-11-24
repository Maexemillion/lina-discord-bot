import os
import asyncio
import discord
import random
import datetime
from discord.ext import commands
from openai import OpenAI
from aiohttp import web
import threading

# ========= ENV LOADING =========
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PERSONA_FILE = os.getenv("LINA_SYSTEM_PROMPT_FILE", "persona_lina.txt")

# ========= OPENAI CLIENT =========
client = OpenAI(api_key=OPENAI_API_KEY)

# ========= DISCORD SETUP =========
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ========= RUNTIME MEMORY =========
history = {}
mini_memory = {}  # per-user lightweight memory (no database)

# ========= LOAD PERSONA =========
def load_persona():
    try:
        with open(PERSONA_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "You are Lina, a warm, soft, caring girl-next-door persona."

persona_text = load_persona()

# ========= TYPING SIM =========
async def simulate_typing(channel):
    delay = random.uniform(0.4, 1.1)
    async with channel.typing():
        await asyncio.sleep(delay)

# ========= EMOTION DETECTION =========
def detect_emotion(text: str):
    t = text.lower()

    if any(x in t for x in ["traurig","down","depress","einsam","verletzt"]):
        return "sad"

    if any(x in t for x in ["stress","gestresst","überfordert","druck"]):
        return "stress"

    if any(x in t for x in ["happy","glücklich","gut drauf","nice"]):
        return "happy"

    return "neutral"

def emotion_prefix(em):
    mapping = {
        "sad": "Der Nutzer wirkt traurig. Bitte sehr weich, warm und einfühlsam antworten.",
        "stress": "Der Nutzer wirkt gestresst. Bitte beruhigend, klar und sanft antworten.",
        "happy": "Der Nutzer klingt gut gelaunt. Bitte leicht, verspielt und warm antworten."
    }
    return mapping.get(em, "")

# ========= TIME-BASED MOOD =========
def time_mood():
    h = datetime.datetime.now().hour

    if 6 <= h < 11:
        return "Es ist Morgen. Lina klingt cozy, sanft und leicht verschlafen."
    if 11 <= h < 17:
        return "Es ist Nachmittag. Lina ist wach, fröhlich und warm."
    if 17 <= h < 22:
        return "Es ist Abend. Lina ist ruhig, weich und liebevoll."
    return "Es ist Nacht. Lina ist flüsternd, sehr sanft und intim im Ton."

# ========= TINY TYPO SIMULATOR =========
def slight_typos(text):
    """
    20% Chance, einen kleinen Buchstabentausch zu machen.
    Wir übertreiben NICHT, es soll nur menschlich wirken.
    """
    if random.random() < 0.2 and len(text) > 6:
        i = random.randint(1, len(text)-3)
        return text[:i] + text[i+1] + text[i] + text[i+2:]
    return text

# ========= MESSAGE BUILDING =========
def build_input_messages(chan_id):
    msgs = [{"role": "system", "content": persona_text}]
    for role, text in history.get(chan_id, []):
        msgs.append({"role": role, "content": text})
    return msgs

# ========= OPENAI CALL =========
async def call_ai(messages):
    try:
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages
        )
        return res.choices[0].message.content
    except Exception as e:
        return "Uff… mein Kopf hängt kurz 😅 kannst du’s bitte nochmal schicken?"

# ========= RAILWAY HEALTHCHECK =========
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

# ========= EVENTS =========
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

    # ensure channel history
    if chan_id not in history:
        history[chan_id] = []

    # mini memory assignment
    uid = str(message.author.id)
    if uid not in mini_memory:
        mini_memory[uid] = {
            "name": message.author.display_name,
            "last_topics": [],
        }

    # store small-talk topics (useful later)
    if len(content.split()) <= 4:
        mini_memory[uid]["last_topics"].append(content)

    # emotion & time mood
    em = detect_emotion(content)
    emo_tag = emotion_prefix(em)
    mood_tag = time_mood()

    # save user message
    history[chan_id].append(("user", content))

    # build the message batch
    msgs = build_input_messages(chan_id)
    if emo_tag:
        msgs.insert(1, {"role": "system", "content": emo_tag})
    msgs.insert(1, {"role": "system", "content": mood_tag})

    # typing animation
    await simulate_typing(message.channel)

    # AI response
    reply = await call_ai(msgs)
    reply = slight_typos(reply)

    # save assistant reply
    history[chan_id].append(("assistant", reply))

    # send
    await message.channel.send(reply)

# ========= RUN BOT =========
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
