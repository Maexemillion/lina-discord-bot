import os
import discord
from discord.ext import commands
from openai import OpenAI
import asyncio

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
# Run Bot
# -----------------------------
if __name__ == "__main__":
    print("Starting Lina…")
    bot.run(DISCORD_TOKEN)
