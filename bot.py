import os, time, random, asyncio
from dotenv import load_dotenv
import discord
from discord.ext import commands
from openai import OpenAI

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
intents.message_content = True  # privileged intent
intents.members = False

bot = commands.Bot(command_prefix="!", intents=intents)

# Simple per-user cooldown to avoid spam + stay in rate limits
USER_COOLDOWN_SEC = 6
last_user_reply = {}

# Light memory (per channel / DM) – keeps last few msgs
history = {}  # key: channel_id, value: list of (role, content)

MAX_HISTORY = 12

def add_history(chan_id, role, content):
    history.setdefault(chan_id, [])
    history[chan_id].append((role, content))
    if len(history[chan_id]) > MAX_HISTORY:
        history[chan_id] = history[chan_id][-MAX_HISTORY:]

async def lina_typing_delay(channel):
    # human-like delay
    await channel.typing()
    await asyncio.sleep(random.uniform(1.2, 3.0))

def should_reply(message: discord.Message):
    # Reply if DM OR bot is mentioned OR message starts with "lina"
    if isinstance(message.channel, discord.DMChannel):
        return True
    if bot.user in message.mentions:
        return True
    if message.content.lower().startswith("lina"):
        return True
    return False

def build_input_messages(chan_id):
    msgs = [{"role": "system", "content": LINA_SYSTEM}]
    for role, content in history.get(chan_id, []):
        msgs.append({"role": role, "content": content})
    return msgs

def call_openai(messages):
    resp = client_ai.responses.create(
        model="gpt-4.1-mini",
        input=messages,
        max_output_tokens=250,
    )

    # ---- Responses API: Text extrahieren ----
    out_text = ""

    if hasattr(resp, "output"):
        for item in resp.output:
            if getattr(item, "type", None) == "message":
                for c in item.content:
                    if hasattr(c, "type") and c.type == "output_text":
                        out_text += c.text

    # Falls Modell "message" anders liefert:
    if not out_text and hasattr(resp, "output_text"):
        out_text = resp.output_text

    return out_text.strip()

@bot.event
async def on_ready():
    print(f"✅ Lina online as {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if not should_reply(message):
        await bot.process_commands(message)
        return

    uid = message.author.id
    now = time.time()
    if uid in last_user_reply and now - last_user_reply[uid] < USER_COOLDOWN_SEC:
        return  # silently ignore to avoid spam loops
    last_user_reply[uid] = now

    chan_id = message.channel.id

    add_history(chan_id, "user", message.content)

    await lina_typing_delay(message.channel)

    try:
        messages = build_input_messages(chan_id)
        answer = await asyncio.to_thread(call_openai, messages)

        # safety fallback:
        if not answer:
            answer = "Oh sorry, ich hab gerade kurz nen Hänger 😅 Schreib’s mir nochmal?"

        add_history(chan_id, "assistant", answer)
        await message.reply(answer, mention_author=False)

    except Exception as e:
        print("OpenAI error:", e)
        await message.reply(
            "Uff, mein Kopf ist grad bisschen überhitzt 🙈 Ich bin gleich wieder da. ✨",
            mention_author=False
        )

    await bot.process_commands(message)

# Optional: command to reload persona without restart
@bot.command(name="reload_persona")
@commands.is_owner()
async def reload_persona(ctx):
    global LINA_SYSTEM
    LINA_SYSTEM = load_persona()
    await ctx.reply("Persona neu geladen. ✨")

bot.run(DISCORD_TOKEN)
