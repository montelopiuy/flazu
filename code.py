#!/usr/bin/env python3
import os
import requests
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import json
import traceback
import io
import re
from collections import defaultdict
import time

# === Loading .env ===
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
FLAZU_API_KEY = os.getenv("FLAZU_API_KEY")
FLAZU_API_URL = "https://ai.flazu.my/v1/chat/completions"
FLAZU_MODELS_URL = "https://ai.flazu.my/v1/models"
FLAZU_IMAGES_URL = "https://ai.flazu.my/v1/images/generations"

if not DISCORD_TOKEN or not FLAZU_API_KEY:
    print("ERROR: DISCORD_TOKEN or FLAZU_API_KEY missing in .env")
    raise SystemExit(1)

# === Discord Intents ===
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# === Persistent Memory ===
MEMORY_FILE = "memory.json"
memory = {}

# List of available models (will be filled on ready)
available_models = []

# === SAFE TYPING SYSTEM (NO MORE 429 RATE LIMITS) ===
typing_queue = defaultdict(asyncio.Semaphore)
typing_last = defaultdict(float)
TYPING_COOLDOWN = 5.0  # Discord allows ~1 typing per 5 sec per channel

async def safe_typing(channel):
    """Send typing with queue + lock to avoid rate limits."""
    semaphore = typing_queue[channel.id]
    async with semaphore:
        now = time.time()
        last = typing_last[channel.id]
        if now - last < TYPING_COOLDOWN:
            await asyncio.sleep(TYPING_COOLDOWN - (now - last))
        try:
            async with channel.typing():
                typing_last[channel.id] = time.time()
                await asyncio.sleep(1)  # Simulate typing
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = e.response.headers.get("Retry-After", 5)
                print(f"[RATE LIMITED] Typing blocked, retry in {retry_after}s")
                await asyncio.sleep(float(retry_after))
            else:
                print(f"[ERROR] Typing failed: {e}")

def load_memory():
    global memory
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                temp_memory = {int(k): v for k, v in loaded.items()}
            for uid, data in temp_memory.items():
                if isinstance(data, list):
                    temp_memory[uid] = {"history": data, "model": "gpt-5"}
            memory = temp_memory
            print("[INFO] Memory loaded successfully.")
        except Exception as e:
            print(f"[WARN] Unable to load memory.json: {str(e)}. Initializing new memory.")
            memory = {}
    else:
        print("[INFO] No memory.json file found. Initializing new memory.")
        memory = {}

def save_memory():
    try:
        json_memory = {str(k): v for k, v in memory.items()}
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(json_memory, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ERROR] Unable to save memory.json: {str(e)}")

load_memory()

# === Utilities ===
def sanitize_messages(msgs, max_chars=3000):
    out = []
    total = 0
    for m in reversed(msgs):
        content = m.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        if total + len(content) > max_chars:
            allowed = max_chars - total
            if allowed <= 0:
                break
            content = content[-allowed:]
        out.append({"role": m.get("role", "user"), "content": content})
        total += len(content)
    return list(reversed(out))

def debug_print(*args, **kwargs):
    print("[DEBUG]", *args, **kwargs)

# === Get available models ===
def get_available_models():
    headers = {"Authorization": f"Bearer {FLAZU_API_KEY}"}
    try:
        resp = requests.get(FLAZU_MODELS_URL, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return [m['id'] for m in data.get('data', [])]
    except Exception as e:
        print(f"[ERROR] Unable to retrieve models: {str(e)}")
        return []

# === Call Flazu ===
def ask_flazu(user_id: int, user_prompt: str) -> str:
    try:
        user_id = int(user_id)
    except Exception:
        return "Internal error: invalid user_id."

    user_prompt = str(user_prompt) if user_prompt is not None else ""

    if user_id not in memory:
        memory[user_id] = {
            "history": [{"role": "system", "content": "You are a helpful and concise AI."}],
            "model": "gpt-5"
        }

    memory[user_id]["history"].append({"role": "user", "content": user_prompt})
    msgs = sanitize_messages(memory[user_id]["history"], max_chars=3000)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {FLAZU_API_KEY}"
    }
    data = {
        "model": memory[user_id]["model"],
        "messages": msgs
    }

    debug_print(f"Call Flazu: user={user_id}, model={memory[user_id]['model']}, prompt='{user_prompt[:50]}...'")

    try:
        resp = requests.post(FLAZU_API_URL, headers=headers, json=data, timeout=30)
        resp.raise_for_status()
        j = resp.json()
        reply = j.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not isinstance(reply, str):
            reply = str(reply) if reply is not None else "Empty response."

        memory[user_id]["history"].append({"role": "assistant", "content": reply})
        if len(memory[user_id]["history"]) > 50:
            memory[user_id]["history"] = memory[user_id]["history"][-50:]
        save_memory()
        return reply

    except requests.exceptions.Timeout:
        return "The Flazu API took too long to respond."
    except requests.exceptions.RequestException as e:
        debug_print(f"Flazu request error: {e}")
        traceback.print_exc()
        return f"Flazu API error: {str(e)}"
    except Exception as e:
        debug_print(f"Flazu unexpected error: {e}")
        traceback.print_exc()
        return f"Unexpected error: {str(e)}"

# === Generate Image ===
def generate_image(prompt: str, model="dall-e-3", size="1024x1024", n=1) -> str:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {FLAZU_API_KEY}"
    }
    data = {
        "prompt": prompt,
        "model": model,
        "n": n,
        "size": size
    }
    try:
        resp = requests.post(FLAZU_IMAGES_URL, headers=headers, json=data, timeout=60)
        resp.raise_for_status()
        j = resp.json()
        if 'data' in j and len(j['data']) > 0 and 'url' in j['data'][0]:
            return j['data'][0]['url']
        return None
    except Exception as e:
        debug_print(f"Image generation error: {e}")
        return None

# === Extract code blocks ===
def extract_code_blocks(reply):
    code_blocks = re.findall(r'```(\w+)?\n(.*?)\n```', reply, re.DOTALL)
    non_code_parts = re.split(r'```(?:\w+)?\n.*?\n```', reply, flags=re.DOTALL)
    message_text = "\n".join(part for part in non_code_parts if part.strip())
    files = []
    for lang, code in code_blocks:
        ext = get_extension(lang)
        files.append((f"code{ext}", io.StringIO(code.strip())))
    return message_text.strip(), files

def get_extension(lang):
    lang = lang.lower() if lang else "txt"
    extensions = {
        "python": ".py", "javascript": ".js", "java": ".java", "c": ".c", "cpp": ".cpp",
        "html": ".html", "css": ".css", "json": ".json", "markdown": ".md", "bash": ".sh", "shell": ".sh"
    }
    return extensions.get(lang, ".txt")

# === Events ===
@bot.event
async def on_ready():
    global available_models
    available_models = await asyncio.to_thread(get_available_models)
    print(f"Connected as {bot.user} (ID: {bot.user.id})")
    if available_models:
        print(f"[INFO] {len(available_models)} available models loaded.")
    else:
        print("[WARN] No available models retrieved.")

# === Commands ===
@bot.command(name="chat")
async def cmd_chat(ctx, *, user_message: str):
    user_id = ctx.author.id
    await safe_typing(ctx.channel)
    reply = await asyncio.to_thread(ask_flazu, user_id, user_message)
    message_text, files = extract_code_blocks(reply)
    discord_files = [discord.File(fp=fp, filename=filename) for filename, fp in files]
    ping = f"{ctx.author.mention}"
    content = f"{ping}\n{message_text}" if message_text else ping
    try:
        await ctx.channel.send(content=content, files=discord_files)
    except Exception:
        await ctx.channel.send(f"{ping} An error occurred.")
    for fp in [f[1] for f in files]:
        fp.close()

@bot.command(name="reset")
async def cmd_reset(ctx):
    uid = ctx.author.id
    if uid in memory:
        del memory[uid]
        save_memory()
        await ctx.channel.send(f"{ctx.author.mention} Your memory has been cleared.")
    else:
        await ctx.channel.send(f"{ctx.author.mention} You had no memory recorded.")

@bot.command(name="memory")
async def cmd_memory(ctx):
    uid = ctx.author.id
    if uid not in memory or not memory[uid].get("history"):
        await ctx.channel.send(f"{ctx.author.mention} No memory for you.")
        return
    lines = []
    for m in memory[uid]["history"]:
        role = m.get("role", "?")
        content = m.get("content", "")
        if len(content) > 600:
            content = content[:600] + "..."
        lines.append(f"{role}: {content}")
    text = "\n".join(lines)
    if len(text) > 1900:
        text = text[-1900:] + "\n...(truncated)"
    await ctx.channel.send(f"{ctx.author.mention} Memory:\n{text}")

@bot.command(name="model")
async def cmd_model(ctx, new_model: str):
    uid = ctx.author.id
    new_model = new_model.strip()
    if new_model not in available_models:
        await ctx.channel.send(f"{ctx.author.mention} Model '{new_model}' not available. Use !dispo.")
        return
    if uid not in memory:
        memory[uid] = {"history": [], "model": new_model}
    else:
        memory[uid]["model"] = new_model
    save_memory()
    await ctx.channel.send(f"{ctx.author.mention} Model changed to `{new_model}` for you.")

@bot.command(name="dispo")
async def cmd_dispo(ctx):
    global available_models
    if available_models:
        models_list = "\n".join(available_models)
        await ctx.channel.send(f"{ctx.author.mention} Available models:\n{models_list}")
    else:
        models = await asyncio.to_thread(get_available_models)
        if models:
            available_models = models
            models_list = "\n".join(models)
            await ctx.channel.send(f"{ctx.author.mention} Available models:\n{models_list}")
        else:
            await ctx.channel.send(f"{ctx.author.mention} Unable to retrieve models.")

@bot.command(name="usage")
async def cmd_usage(ctx):
    await ctx.channel.send(f"{ctx.author.mention} Usage: endpoint not implemented. Contact Flazu support.")

@bot.command(name="image")
async def cmd_image(ctx, *, prompt: str):
    await ctx.channel.send(f"{ctx.author.mention} Do you want me to generate an image for: '{prompt}'? Reply 'yes' to confirm.")
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == 'yes'
    try:
        await bot.wait_for('message', check=check, timeout=60.0)
        await safe_typing(ctx.channel)
        image_url = await asyncio.to_thread(generate_image, prompt)
        if image_url:
            await ctx.channel.send(f"{ctx.author.mention} {image_url}")
        else:
            await ctx.channel.send(f"{ctx.author.mention} Failed to generate image.")
    except asyncio.TimeoutError:
        await ctx.channel.send(f"{ctx.author.mention} Image generation cancelled due to timeout.")

# === on_message : PING USER + NO REPLY ===
@bot.event
async def on_message(msg):
    if msg.author == bot.user:
        return

    await bot.process_commands(msg)

    if bot.user.mentioned_in(msg) or msg.content.startswith(','):
        uid = msg.author.id
        prompt = msg.content
        if bot.user.mentioned_in(msg):
            prompt = prompt.replace(f"<@{bot.user.id}>", "").strip()
        elif msg.content.startswith(','):
            prompt = prompt[1:].strip()

        if prompt:
            await safe_typing(msg.channel)
            reply = await asyncio.to_thread(ask_flazu, uid, prompt)
            message_text, files = extract_code_blocks(reply)
            discord_files = [discord.File(fp=fp, filename=filename) for filename, fp in files]

            ping = f"{msg.author.mention}"
            content = f"{ping}\n{message_text}" if message_text else ping

            try:
                await msg.channel.send(content=content, files=discord_files)
            except Exception as e:
                print(f"[ERROR] Failed to send message: {e}")
                await msg.channel.send(f"{ping} An error occurred.")
            finally:
                for fp in [f[1] for f in files]:
                    fp.close()

# === Launch ===
if __name__ == "__main__":
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"[FATAL] bot.run raised: {str(e)}")
        traceback.print_exc()