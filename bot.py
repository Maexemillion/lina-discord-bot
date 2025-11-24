import os
import asyncio
import discord
import random
import datetime
from collections import deque, defaultdict
from discord.ext import commands
from openai import OpenAI
from aiohttp import web
import threading

# ========= ENV LOADING =========
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PERSONA_FILE = os.getenv("LINA_SYSTEM_PROMPT_FILE", "persona_lina.txt")

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")

# ========= OPENAI CLIENT =========
client = OpenAI(api_key=OPENAI_API_KEY)

# ========= DISCORD SETUP =========
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ========= RUNTIME MEMORY =========
history = {}  # {chan_id: deque([(role, text), ...])}

# Soft mini-memory per user (RAM only, no persistence)
mini_memory = defaultdict(lambda: {
    "name": None,
    "facts": deque(maxlen=25),
    "topics": deque(maxlen=12),
    "last_emotion": "neutral",
    "last_seen": None,
    "interaction_count": 0
})

# ========= LOAD PERSONA =========
def load_persona():
    try:
        with open(PERSONA_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "You are Lina, a warm, soft, cozy girl-next-door persona."

persona_text = load_persona()

# ========= TYPING SIM (human-like) =========
async def simulate_typing(channel, text_len=0):
    base = random.uniform(0.4, 1.2)
    extra = min(1.0, text_len / 400) * random.uniform(0.5, 1.0)
    delay = base + extra
    async with channel.typing():
        await asyncio.sleep(delay)

# ========= EMOTION DETECTION V2 =========
EMO_LEX = {
    "sad": ["traurig","down","depress","einsam","verletzt","kaputt","heule","vermisse","leer","negativ"],
    "stress": ["stress","gestresst","überfordert","druck","keine kraft","müde","zu viel","burnout","kopfvollen"],
    "angry": ["wütend","sauer","nervt","kotzt","hasse","fuck","scheiße","aggressiv"],
    "happy": ["happy","glücklich","gut drauf","freu","mega","nice","lol","haha","geil","top"],
    "love": ["mag dich","vermiss dich","lieb","süß","cute","knuffig","❤️","🤍","🥺"]
}

def detect_emotion(text: str):
    t = text.lower()
    for emo, words in EMO_LEX.items():
        if any(w in t for w in words):
            return emo
    return "neutral"

def emotion_prefix(em):
    mapping = {
        "sad": "USER EMOTION: sad. The user seems sad or hurt. Be very warm, soft, reassuring and gentle.",
        "stress": "USER EMOTION: stressed. The user seems overwhelmed. Be calm, soothing, patient, supportive.",
        "angry": "USER EMOTION: angry/frustrated. De-escalate gently, stay kind, don't mirror anger.",
        "happy": "USER EMOTION: happy. Be playful, bright and cozy.",
        "love": "USER EMOTION: affectionate. Be a bit shy-but-sweet, warm and tender."
    }
    return mapping.get(em, "")

# ========= TIME-BASED MOOD (A: cozy soft) =========
def time_mood():
    h = datetime.datetime.now().hour
    if 6 <= h < 11:
        return "TIME MOOD: morning. Lina is sleepy-cozy, soft, tea/coffee vibe, gentle energy."
    if 11 <= h < 17:
        return "TIME MOOD: afternoon. Lina is warm, present, lightly playful, student-day vibe."
    if 17 <= h < 22:
        return "TIME MOOD: evening. Lina is calm, affectionate, cozy, slower pace."
    return "TIME MOOD: night. Lina is very soft-spoken, dreamy, intimate-but-innocent."

# ========= LIGHT SCENE FLAVOR =========
SCENES = [
    "light rain tapping at the window in Copenhagen, coffee in hand",
    "just got back from uni, hoodie on, a bit tired but comfy",
    "wrapped in a blanket on the sofa, warm lamp light",
    "walking home in chilly air, cheeks a little cold but happy"
]

def maybe_scene():
    return random.choice(SCENES) if random.random() < 0.12 else None

# ========= SOFT MEMORY EXTRACTOR =========
def extract_facts(text: str):
    t = text.strip()
    facts = []
    low = t.lower()
    triggers = [
        "ich bin ", "i am ", "i'm ",
        "ich habe ", "i have ",
        "ich mag ", "i like ",
        "mein ", "my ",
        "morgen ", "tomorrow ",
        "heute ", "today ",
    ]
    if any(tr in low for tr in triggers) and len(t) < 140:
        facts.append(t)
    return facts

# ========= SMART REPLY LENGTH =========
def user_length_bucket(user_text: str):
    n = len(user_text.split())
    if n <= 6:
        return "short"
    if n <= 18:
        return "medium"
    return "long"

def length_instruction(bucket: str):
    if bucket == "short":
        return "REPLY LENGTH: short. 1-3 short sentences, chatty, not formal."
    if bucket == "medium":
        return "REPLY LENGTH: medium. 3-6 sentences, warm and personal."
    return "REPLY LENGTH: long. Be more detailed but still chatty and soft."

# ========= TINY TYPO + SELF-CORRECTION SIM =========
def slight_typos(text):
    out = text
    if random.random() < 0.18 and len(out) > 12:
        words = out.split()
        wi = random.randrange(len(words))
        w = words[wi]
        if len(w) >= 5 and w.isalpha():
            i = random.randint(1, len(w)-2)
            w2 = w[:i] + w[i+1] + w[i] + w[i+2:]
            words[wi] = w2
            out = " ".join(words)
    if random.random() < 0.10:
        add = random.choice(["— oh wait 😅", "…also, you know what I mean 😄", "— haha sorry"])
        if len(out) < 180:
            out = out + " " + add
    return out

# ========= MESSAGE BUILDING =========
MAX_HISTORY = 18

def build_input_messages(chan_id, user_id: str, user_text: str):
    msgs = [{"role": "system", "content": persona_text}]
    mem = mini_memory[user_id]
    name = mem["name"]
    facts = list(mem["facts"])
    topics = list(mem["topics"])
    last_emo = mem["last_emotion"]

    mem_blob = []
    if name:
        mem_blob.append(f"- User name: {name}")
    if topics:
        mem_blob.append(f"- Recent topics: {topics[-6:]}")
    if facts:
        mem_blob.append(f"- Remembered facts: {facts[-8:]}")
    if last_emo and last_emo != "neutral":
        mem_blob.append(f"- Last emotion noticed: {last_emo}")

    if mem_blob:
        msgs.append({"role": "system", "content": "SOFT USER MEMORY (session only):\n" + "\n".join(mem_blob)})

    emo = detect_emotion(user_text)
    emo_tag = emotion_prefix(emo)
    mood_tag = time_mood()
    len_tag = length_instruction(user_length_bucket(user_text))

    if emo_tag:
        msgs.append({"role": "system", "content": emo_tag})
    msgs.append({"role": "system", "content": mood_tag})
    msgs.append({"role": "system", "content": len_tag})

    scene = maybe_scene()
    if scene:
        msgs.append({"role": "system", "content": f"SCENE FLAVOR (use lightly, not every time): {scene}."})

    for role, text in history.get(chan_id, deque()):
        msgs.append({"role": role, "content": text})

    return msgs, emo

# ========= OPENAI CALL =========
async def call_ai(messages):
    try:
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
        )
        return res.choices[0].message.content
    except Exception:
        return "Oh noo… mein Kopf hängt grad kurz 🥺✨ Schreib’s mir gleich nochmal?"

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
    uid = str(message.author.id)

    if chan_id not in history:
        history[chan_id] = deque(maxlen=MAX_HISTORY)

    mem = mini_memory[uid]
    mem["interaction_count"] += 1
    mem["last_seen"] = datetime.datetime.utcnow().isoformat()
    if not mem["name"]:
        mem["name"] = message.author.display_name

    for f in extract_facts(content):
        mem["facts"].append(f)

    if len(content.split()) <= 5:
        mem["topics"].append(content)

    msgs, emo = build_input_messages(chan_id, uid, content)
    mem["last_emotion"] = emo

    history[chan_id].append(("user", content))

    await simulate_typing(message.channel, text_len=len(content))

    reply = await call_ai(msgs)
    reply = slight_typos(reply)

    history[chan_id].append(("assistant", reply))

    await message.channel.send(reply)

# ========= RUN BOT =========
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
