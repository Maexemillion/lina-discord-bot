import os, time, random, asyncio, json
from datetime import datetime
from dotenv import load_dotenv
import discord
from discord.ext import commands
from openai import OpenAI
from memory_sqlite import init_db, get_user_memory, save_user_memory


# ----------------------
# ENV + BASIC SETUP
# ----------------------
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PROMPT_FILE = os.getenv("LINA_SYSTEM_PROMPT_FILE", "persona_lina.txt")

client_ai = OpenAI(api_key=OPENAI_API_KEY)

def load_persona():
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        return f.read()

LINA_SYSTEM = load_persona()

intents = discord.Intents.default()
intents.message_content = True
intents.members = False

bot = commands.Bot(command_prefix="!", intents=intents)

# ----------------------
# MEMORY SYSTEM
# ----------------------

MEMORY_FILE = "memory.json"

def load_memory():
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_memory():
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=4, ensure_ascii=False)

memory = load_memory()

# ----------------------
# BASIC MEMORYLESS HISTORY
# ----------------------

USER_COOLDOWN_SEC = 6
last_user_reply = {}

history = {}
MAX_HISTORY = 12

def add_history(chan_id, role, content):
    history.setdefault(chan_id, [])
    history[chan_id].append((role, content))
    if len(history[chan_id]) > MAX_HISTORY:
        history[chan_id] = history[chan_id][-MAX_HISTORY:]

async def lina_typing_delay(channel):
    await channel.typing()
    await asyncio.sleep(random.uniform(1.2, 3.0))

def should_reply(message: discord.Message):
    if isinstance(message.channel, discord.DMChannel):
        return True
    if bot.user in message.mentions:
        return True
    if message.content.lower().startswith("lina"):
        return True
    return False

# ----------------------
# BUILD AI INPUT (WITH MEMORY!)
# ----------------------
async def build_input_messages(chan_id, author_id=None):
    msgs = [{"role": "system", "content": LINA_SYSTEM}]

    if author_id:
        uid = str(author_id)
        user_mem = await get_user_memory(uid)

        mem_text = (
            f"USER MEMORY:\n"
            f"- Name hint: {user_mem.get('name_hint','')}\n"
            f"- Favorite topics: {user_mem.get('fav_topics',[])}\n"
            f"- Notes: {user_mem.get('notes','')}\n"
            f"- Interaction count: {user_mem.get('interaction_count',0)}\n"
            f"- Last interaction: {user_mem.get('last_interaction','')}\n"
        )
        msgs.append({"role": "system", "content": mem_text})

    for role, content in history.get(chan_id, []):
        msgs.append({"role": role, "content": content})

    return msgs

# ----------------------
# OPENAI CALL
# ----------------------
def call_openai(messages):
    resp = client_ai.responses.create(
        model="gpt-4.1-mini",
        input=messages,
        max_output_tokens=250,
    )

    out_text = ""
    if hasattr(resp, "output"):
        for item in resp.output:
            if getattr(item, "type", None) == "message":
                for c in item.content:
                    if hasattr(c, "type") and c.type == "output_text":
                        out_text += c.text

    if not out_text and hasattr(resp, "output_text"):
        out_text = resp.output_text

    return out_text.strip()

# ----------------------
# DISCORD EVENTS
# ----------------------
@bot.event
async def on_ready():
    await init_db()
    print(f"✅ Lina online as {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if not should_reply(message):
        await bot.process_commands(message)
        return

    # COOLDOWN CHECK
    uid_raw = message.author.id
    now = time.time()
    if uid_raw in last_user_reply and now - last_user_reply[uid_raw] < USER_COOLDOWN_SEC:
        return
    last_user_reply[uid_raw] = now

    uid = str(uid_raw)
    user_text = message.content.strip()
    chan_id = message.channel.id

    # ----------- MEMORY UPDATE -----------
    uid = str(message.author.id)
    user_mem = await get_user_memory(uid)

    # Update basics
    user_mem["name_hint"] = message.author.display_name
    user_mem["interaction_count"] += 1
    user_mem["last_interaction"] = datetime.utcnow().isoformat()

    # Topic tracking
    keywords = {
        "kopenhagen": "Kopenhagen",
        "studium": "Studium",
        "uni": "Studium",
        "dänemark": "Dänemark",
        "lernen": "Lernen",
        "fanvue": "Fanvue",
        "wetter": "Wetter",
    }

    lowered = message.content.lower()
    for k, topic in keywords.items():
        if k in lowered and topic not in user_mem["fav_topics"]:
            user_mem["fav_topics"].append(topic)

    await save_user_memory(uid, user_mem)


    try:
        messages = await build_input_messages(chan_id, author_id=uid)
        answer = await asyncio.to_thread(call_openai, messages)

        if not answer:
            answer = "Oh sorry, ich hab gerade kurz nen Hänger 😅 Schreib’s mir nochmal?"

        add_history(chan_id, "assistant", answer)
        await message.reply(answer, mention_author=False)

    except Exception as e:
        print("OpenAI error:", e)
        await message.reply(
            "Uff, mein Kopf ist grad kurz überhitzt 🙈 Ich bin gleich wieder da. ✨",
            mention_author=False
        )

    await bot.process_commands(message)

# ----------------------
# RELOAD PERSONA COMMAND
# ----------------------
@bot.command(name="reload_persona")
@commands.is_owner()
async def reload_persona(ctx):
    global LINA_SYSTEM
    LINA_SYSTEM = load_persona()
    await ctx.reply("Persona neu geladen. ✨")

# ----------------------
# BOT START
# ----------------------
bot.run(DISCORD_TOKEN)
