#!/usr/bin/env python3
import os
import requests
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import json
import traceback
import io
import re
import base64
from collections import defaultdict
import time

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
FLAZU_API_KEY = ("sk-pro-f1ae98fb-6b4b-4c70-a94e-5ba8e-5ba8aa6d95ba")
FLAZU_API_URL = "https://ai.flazu.my/v1/chat/completions"
FLAZU_MODELS_URL = "https://ai.flazu.my/v1/models"
FLAZU_IMAGES_URL = "https://ai.flazu.my/v1/images/generations"

if not DISCORD_TOKEN or not FLAZU_API_KEY:
    print("ERROR: DISCORD_TOKEN or FLAZU_API_KEY missing in .env")
    raise SystemExit(1)

# Set up intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Global variables
MEMORY_FILE = "memory.json"
MODEL_FILE = "global_model.json"
memory = {}
available_models = []
global_model = "gpt-5.1"  # Default global model

# Typing system
typing_queue = defaultdict(asyncio.Semaphore)
typing_last = defaultdict(float)
TYPING_COOLDOWN = 5.0

async def safe_typing(channel):
    semaphore = typing_queue[channel.id]
    async with semaphore:
        now = time.time()
        last = typing_last[channel.id]
        if now - last < TYPING_COOLDOWN:
            await asyncio.sleep(TYPING_COOLDOWN - (now - last))
        try:
            async with channel.typing():
                typing_last[channel.id] = time.time()
                await asyncio.sleep(1)
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = e.response.headers.get("Retry-After", 5)
                print(f"[RATE LIMITED] Typing blocked, retry in {retry_after}s")
                await asyncio.sleep(float(retry_after))

# Memory management
def load_memory():
    global memory
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                temp_memory = {int(k): v for k, v in loaded.items()}
            for uid, data in temp_memory.items():
                if isinstance(data, list):
                    temp_memory[uid] = {"history": data}
                # Remove per-user model, use global
            memory = temp_memory
            print("[INFO] Memory loaded successfully.")
        except Exception as e:
            print(f"[WARN] Unable to load memory.json: {str(e)}. Initializing new memory.")
            memory = {}
    else:
        print("[INFO] No memory.json file found.")
        memory = {}

def save_memory():
    try:
        json_memory = {str(k): v for k, v in memory.items()}
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(json_memory, f, indent=2)
    except Exception as e:
        print(f"[ERROR] Unable to save memory.json: {str(e)}")

# Global model management
def load_global_model():
    global global_model
    if os.path.exists(MODEL_FILE):
        try:
            with open(MODEL_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                global_model = data.get("model", "gpt-5.1")
            print(f"[INFO] Global model loaded: {global_model}")
        except Exception as e:
            print(f"[WARN] Unable to load global_model.json: {str(e)}. Using default 'gpt-5.1'.")
    else:
        print("[INFO] No global_model.json found. Using default 'gpt-5.1'.")

def save_global_model():
    try:
        with open(MODEL_FILE, "w", encoding="utf-8") as f:
            json.dump({"model": global_model}, f, indent=2)
    except Exception as e:
        print(f"[ERROR] Unable to save global_model.json: {str(e)}")

load_memory()
load_global_model()

# Image handling
async def get_image_base64_from_message(message: discord.Message):
    images = []
    # Attachments
    for attachment in message.attachments:
        if attachment.content_type and attachment.content_type.startswith("image/"):
            try:
                data = await attachment.read()
                b64 = base64.b64encode(data).decode('utf-8')
                images.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{attachment.content_type};base64,{b64}"
                    }
                })
            except Exception as e:
                print(f"[ERROR] Failed to read attachment {attachment.filename}: {e}")
    # Image URLs in content
    url_pattern = r"https?://[^\s]+?\.(png|jpe?g|gif|webp)(\?[^\s]*)?"
    urls = re.findall(url_pattern, message.content, re.IGNORECASE)
    for url in set(urls):
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200 and "image" in resp.headers.get("Content-Type", ""):
                b64 = base64.b64encode(resp.content).decode('utf-8')
                mime = resp.headers.get("Content-Type", "image/png")
                images.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime};base64,{b64}"
                    }
                })
        except Exception as e:
            print(f"[ERROR] Failed to download image {url}: {e}")
    return images

# Sanitize messages
def sanitize_messages(msgs, max_chars=12000):
    out = []
    total = 0
    for m in reversed(msgs):
        content = m.get("content", "")
        if isinstance(content, list):
            est_len = sum(1000 if c["type"] == "image_url" else len(c.get("text","")) for c in content)
        else:
            est_len = len(str(content))
        if total + est_len > max_chars:
            break
        out.append(m)
        total += est_len
    return list(reversed(out))

# Get models
def get_available_models():
    headers = {"Authorization": f"Bearer {FLAZU_API_KEY}"}
    try:
        resp = requests.get(FLAZU_MODELS_URL, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return [m['id'] for m in data.get('data', [])]
    except Exception as e:
        print(f"[ERROR] Unable to retrieve models: {str(e)}")
        return []

# Main AI call (use global model)
async def ask_flazu(user_id: int, user_prompt: str, message: discord.Message = None) -> str:
    try:
        user_id = int(user_id)
    except Exception:
        return "Internal error: invalid user_id."
    if user_id not in memory:
        memory[user_id] = {
            "history": [{"role": "system", "content": "You are a helpful, concise and friendly AI assistant with vision capabilities."}]
        }
    image_contents = []
    if message:
        image_contents = await get_image_base64_from_message(message)
    text_prompt = user_prompt.strip()
    if not text_prompt and image_contents:
        text_prompt = "Describe this image in detail."
    user_content = [{"type": "text", "text": text_prompt}]
    user_content.extend(image_contents)
    memory[user_id]["history"].append({"role": "user", "content": user_content})
    model_to_use = global_model
    if image_contents and model_to_use not in ["gpt-5.1", "gpt-4o", "gpt-4-turbo"]:
        model_to_use = "gpt-5.1"  # Force vision model if needed
    msgs = sanitize_messages(memory[user_id]["history"])
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {FLAZU_API_KEY}"}
    data = {"model": model_to_use, "messages": msgs, "max_tokens": 2000}
    try:
        resp = requests.post(FLAZU_API_URL, headers=headers, json=data, timeout=120)
        resp.raise_for_status()
        j = resp.json()
        reply = j.get("choices", [{}])[0].get("message", {}).get("content", "No response.")
        if not isinstance(reply, str):
            reply = str(reply)
        memory[user_id]["history"].append({"role": "assistant", "content": reply})
        if len(memory[user_id]["history"]) > 50:
            memory[user_id]["history"] = memory[user_id]["history"][-50:]
        save_memory()
        return reply
    except requests.exceptions.Timeout:
        return "The Flazu API took too long to respond."
    except requests.exceptions.RequestException as e:
        return f"Flazu API error: {str(e)}"
    except Exception as e:
        traceback.print_exc()
        return f"Unexpected error: {str(e)}"

# Generate image
def generate_image(prompt: str, model="dall-e-3", size="1024x1024", n=1) -> str:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {FLAZU_API_KEY}"}
    data = {"prompt": prompt, "model": model, "n": n, "size": size}
    try:
        resp = requests.post(FLAZU_IMAGES_URL, headers=headers, json=data, timeout=60)
        resp.raise_for_status()
        j = resp.json()
        return j['data'][0]['url'] if j.get('data') else None
    except Exception as e:
        print(f"Image generation error: {e}")
        return None

# Extract code blocks
def extract_code_blocks(reply):
    code_blocks = re.findall(r'```(\w+)?\n(.*?)\n```', reply, re.DOTALL)
    non_code_parts = re.split(r'```(?:\w+)?\n.*?\n```', reply, flags=re.DOTALL)
    message_text = "\n".join(part.strip() for part in non_code_parts if part.strip())
    files = []
    for lang, code in code_blocks:
        ext = {"python": ".py", "javascript": ".js", "java": ".java", "c": ".c", "cpp": ".cpp",
               "html": ".html", "css": ".css", "json": ".json", "bash": ".sh", "shell": ".sh",
               "txt": ".txt"}.get(lang.lower() if lang else "", ".txt")
        files.append((f"code{ext}", io.StringIO(code.strip())))
    return message_text, files

# On ready
@bot.event
async def on_ready():
    global available_models
    available_models = await asyncio.to_thread(get_available_models)
    print(f"Bot connected: {bot.user} ({bot.user.id})")
    print(f"Available models: {len(available_models)} loaded.")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands globally.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# Slash commands
@bot.tree.command(name="chat", description="Chat with the AI")
@app_commands.describe(user_message="Your message to the AI")
async def slash_chat(interaction: discord.Interaction, user_message: str):
    await interaction.response.defer()
    await safe_typing(interaction.channel)
    reply = await ask_flazu(interaction.user.id, user_message, message=interaction.message)
    text, files = extract_code_blocks(reply)
    discord_files = [discord.File(fp=fp, filename=name) for name, fp in files]
    content = f"{interaction.user.mention}\n{text}" if text else interaction.user.mention
    await interaction.followup.send(content=content, files=discord_files)
    for _, fp in files:
        fp.close()

@bot.tree.command(name="reset", description="Clear your conversation memory")
async def slash_reset(interaction: discord.Interaction):
    if interaction.user.id in memory:
        del memory[interaction.user.id]
        save_memory()
        await interaction.response.send_message(f"{interaction.user.mention} Memory cleared.")
    else:
        await interaction.response.send_message(f"{interaction.user.mention} No memory to clear.")

@bot.tree.command(name="memory", description="Display your current memory")
async def slash_memory(interaction: discord.Interaction):
    uid = interaction.user.id
    if uid not in memory or not memory[uid].get("history"):
        await interaction.response.send_message(f"{interaction.user.mention} No memory recorded.")
        return
    lines = []
    for m in memory[uid]["history"]:
        role = m.get("role", "?")
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join([c.get("text", "") if c["type"] == "text" else "[image]" for c in content])
        if len(content) > 600:
            content = content[:600] + "..."
        lines.append(f"{role}: {content}")
    text = "\n".join(lines)
    if len(text) > 1900:
        text = text[-1900:] + "\n...(truncated)"
    await interaction.response.send_message(f"{interaction.user.mention} Memory:\n{text}")

@bot.tree.command(name="model", description="Change the global AI model for everyone")
@app_commands.describe(new_model="The new model name (use /dispo to list)")
async def slash_model(interaction: discord.Interaction, new_model: str):
    new_model = new_model.strip()
    if new_model not in available_models:
        await interaction.response.send_message(f"{interaction.user.mention} Model `{new_model}` not available. Use `/dispo`.")
        return
    global global_model
    global_model = new_model
    save_global_model()
    await interaction.response.send_message(f"{interaction.user.mention} Global model changed to `{new_model}` for everyone.")

@bot.tree.command(name="dispo", description="List available models")
async def slash_dispo(interaction: discord.Interaction):
    if available_models:
        liste = "\n".join(available_models)
        await interaction.response.send_message(f"{interaction.user.mention} Available models:\n```{liste}```")
    else:
        await interaction.response.send_message(f"{interaction.user.mention} Retrieving models...")

@bot.tree.command(name="usage", description="Display usage (not implemented)")
async def slash_usage(interaction: discord.Interaction):
    await interaction.response.send_message(f"{interaction.user.mention} Usage: endpoint not implemented. Contact Flazu support.")

@bot.tree.command(name="image", description="Generate an image")
@app_commands.describe(prompt="The image prompt")
async def slash_image(interaction: discord.Interaction, prompt: str):
    await interaction.response.send_message(f"{interaction.user.mention} Generate an image for: `{prompt}`?\nReply **yes** to confirm.")
    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel and m.content.lower() == "yes"
    try:
        msg = await bot.wait_for("message", check=check, timeout=60)
        await safe_typing(interaction.channel)
        url = await asyncio.to_thread(generate_image, prompt)
        if url:
            await interaction.channel.send(f"{interaction.user.mention} Here is your image:\n{url}")
        else:
            await interaction.channel.send(f"{interaction.user.mention} Generation failed.")
    except asyncio.TimeoutError:
        await interaction.channel.send(f"{interaction.user.mention} Cancelled (timeout).")

@bot.tree.command(name="whelp", description="Show available commands")
async def slash_whelp(interaction: discord.Interaction):
    help_text = """
Available commands:
- `/chat <message>`: Chat with the AI.
- `/reset`: Clear your conversation memory.
- `/memory`: Display your current memory.
- `/model <name>`: Change the global AI model for everyone (see `/dispo`).
- `/dispo`: List available models.
- `/usage`: Display usage (not implemented).
- `/image <prompt>`: Generate an image (confirmation required).
- `/bypass <link>`: Bypass a link using Flazu API.
- Mention the bot or use `,` for quick chat.

For vision: Send an image as attachment or URL with your question.
"""
    await interaction.response.send_message(f"{interaction.user.mention} {help_text}")

@bot.tree.command(name="sync", description="Sync slash commands (bot owner only)")
@app_commands.describe(guild_only="Sync to this guild only? (faster for testing)")
async def slash_sync(interaction: discord.Interaction, guild_only: bool = False):
    if not await bot.is_owner(interaction.user):
        await interaction.response.send_message("Only the bot owner can use this command.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    if guild_only:
        guild = interaction.guild
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
    else:
        synced = await bot.tree.sync()
    await interaction.followup.send(f"Synced {len(synced)} commands {'to this guild' if guild_only else 'globally'}.")

# Bypass command
@bot.tree.command(name="bypass", description="Bypass a link using Flazu API")
@app_commands.describe(link="The link to bypass")
async def slash_bypass(interaction: discord.Interaction, link: str):
    await interaction.response.defer()
    await safe_typing(interaction.channel)
    try:
        resp = requests.get(f"https://bypass.flazu.my/v1/free/bypass?link={link}", timeout=100)
        resp.raise_for_status()
        result = resp.text  # Assuming text response; change to resp.json() if JSON
        content = f"{interaction.user.mention}\n{result}"
        await interaction.followup.send(content=content)
    except Exception as e:
        await interaction.followup.send(f"{interaction.user.mention} Error bypassing link: {str(e)}")

# IP command
@bot.command(name="IP")
async def cmd_ip(ctx):
    try:
        ip = requests.get('https://api.ipify.org').text
        await ctx.send(f"{ctx.author.mention} The bot's IP address is: {ip}")
    except Exception as e:
        await ctx.send(f"{ctx.author.mention} Failed to retrieve IP: {str(e)}")

# On message
@bot.event
async def on_message(msg):
    if msg.author == bot.user:
        return
    await bot.process_commands(msg)
    if bot.user.mentioned_in(msg) or msg.content.startswith(','):
        prompt = msg.content
        if bot.user.mentioned_in(msg):
            prompt = re.sub(f"<@!?{bot.user.id}>", "", prompt).strip()
        if msg.content.startswith(','):
            prompt = prompt[1:].strip()
        if prompt.startswith('!'):
            return  # Skip if looks like a prefix command
        if not prompt and not msg.attachments and not re.search(r"https?://[^\s]+\.(png|jpe?g|webp|gif)", msg.content):
            return
        await safe_typing(msg.channel)
        reply = await ask_flazu(msg.author.id, prompt, message=msg)
        text, files = extract_code_blocks(reply)
        discord_files = [discord.File(fp=fp, filename=name) for name, fp in files]
        content = f"{msg.author.mention}\n{text}" if text else msg.author.mention
        try:
            await msg.channel.send(content=content, files=discord_files)
        except Exception as e:
            print(f"[ERROR] Send failed: {e}")
            await msg.channel.send(f"{msg.author.mention} Error during send.")
        finally:
            for _, fp in files:
                fp.close()

# Run bot
if __name__ == "__main__":
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"[FATAL] bot.run error: {str(e)}")
        traceback.print_exc()
