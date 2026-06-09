import os
import threading
import time
import discord
from discord.ext import commands, tasks
from flask import Flask

# ───────────────────────────────────────────────────────────────────
#  WEB SERVER LAYER (Required to bypass Render Free Tier Rules)
# ───────────────────────────────────────────────────────────────────
app = Flask('')

@app.route('/')
def home():
    return "Anti-AFK Moderation System Online"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# Spin up web listener on an isolated background thread
threading.Thread(target=run_web_server, daemon=True).start()

# ───────────────────────────────────────────────────────────────────
#  BOT INITIALIZATION & CORE CONFIG
# ───────────────────────────────────────────────────────────────────
TOKEN = os.environ.get("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="$", intents=intents)

# ---------- SETTINGS ----------
DEAF_LIMIT = 20
MUTE_LIMIT = 60

ADMIN_ROLES = ["DEVELOPER", "CEO"]
IGNORE_ROLE = "Music Bot"

tracking = False

mute_timer = {}
deaf_timer = {}

# ---------- HELPERS ----------
def can_control(member):
    return any(role.name in ADMIN_ROLES for role in member.roles)

def is_music_bot(member):
    return any(role.name == IGNORE_ROLE for role in member.roles)

# ---------- COMMANDS ----------
@bot.command()
async def start(ctx):
    global tracking
    if not can_control(ctx.author):
        return await ctx.send("❌ Need DEVELOPER or CEO")

    tracking = True
    mute_timer.clear()
    deaf_timer.clear()

    if not check_loop.is_running():
        check_loop.start()

    await ctx.send("Tracking Started")

@bot.command()
async def end(ctx):
    global tracking
    if not can_control(ctx.author):
        return

    tracking = False
    if check_loop.is_running():
        check_loop.stop()

    mute_timer.clear()
    deaf_timer.clear()
    await ctx.send("Tracking Stopped")

# ---------- VOICE STATE TRACER ----------
@bot.event
async def on_voice_state_update(member, before, after):
    if not tracking or is_music_bot(member):
        return

    uid = member.id

    # Handle disconnect (left voice channel entirely)
    if before.channel and not after.channel:
        mute_timer.pop(uid, None)
        deaf_timer.pop(uid, None)
        return

    # Manage timers for AFK properties when status changes
    if after.self_mute or after.mute:
        mute_timer.setdefault(uid, time.time())
    else:
        mute_timer.pop(uid, None)

    if after.self_deaf or after.deaf:
        deaf_timer.setdefault(uid, time.time())
    else:
        deaf_timer.pop(uid, None)

# ---------- OPTIMIZED BACKGROUND EVALUATION LOOP ----------
@tasks.loop(seconds=3)
async def check_loop():
    if not tracking:
        return

    now = time.time()

    for guild in bot.guilds:
        for vc in guild.voice_channels:
            for m in vc.members:
                if is_music_bot(m):
                    continue

                uid = m.id
                state = m.voice
                if not state:
                    continue

                # Evaluate Deaf Status Rules
                if state.self_deaf or state.deaf:
                    t = deaf_timer.get(uid)
                    if t and now - t >= DEAF_LIMIT:
                        try:
                            await m.move_to(None)
                        except Exception:
                            pass
                        deaf_timer.pop(uid, None)
                    elif not t:
                        deaf_timer[uid] = now
                    continue
                else:
                    deaf_timer.pop(uid, None)

                # Evaluate Mute Status Rules
                if state.self_mute or state.mute:
                    t = mute_timer.get(uid)
                    if t and now - t >= MUTE_LIMIT:
                        try:
                            await m.move_to(None)
                        except Exception:
                            pass
                        mute_timer.pop(uid, None)
                    elif not t:
                        mute_timer[uid] = now
                else:
                    mute_timer.pop(uid, None)

@bot.event
async def on_ready():
    print(f"✅ Anti-AFK Bot ready and tracking via web worker framework as {bot.user}")

bot.run(TOKEN)
