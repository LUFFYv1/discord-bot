import discord
from discord.ext import commands, tasks
import time
import json
import os
from datetime import datetime, timedelta

TOKEN = os.environ["TOKEN"]

intents = discord.Intents.all()

bot = commands.Bot(command_prefix="$", intents=intents)

tracking = False

active_start = {}
mute_time = {}
deaf_time = {}

DEAF_LIMIT = 20
MUTE_LIMIT = 300


# ---------------- JSON ----------------

if os.path.exists("points.json"):
    with open("points.json", "r") as f:
        points = json.load(f)
else:
    points = {}


def save_points():
    with open("points.json", "w") as f:
        json.dump(points, f, indent=4)


# ---------------- WEEK ----------------

def get_week_key():

    today = datetime.now()

    start = today - timedelta(days=(today.weekday() + 1) % 7)
    end = start + timedelta(days=6)

    s = start.strftime("%Y-%m-%d")
    e = end.strftime("%Y-%m-%d")

    return f"{s}_to_{e}"


# ---------------- ACTIVE ----------------

def is_active(state):
    return (
        state.channel is not None
        and not state.self_mute
        and not state.self_deaf
        and not state.mute
        and not state.deaf
    )


# ---------------- COMMANDS ----------------

@bot.command()
async def start(ctx):
    global tracking
    tracking = True
    await ctx.send("Tracking started")


@bot.command(aliases=["stop"])
async def end(ctx):
    global tracking
    tracking = False
    await ctx.send("Tracking stopped")


@bot.command()
async def points(ctx):

    user = str(ctx.author.id)
    week = get_week_key()

    if user in points and week in points[user]:
        p = points[user][week]
    else:
        p = 0

    await ctx.send(f"This week points: {p}")


@bot.command()
async def history(ctx):

    user = str(ctx.author.id)

    if user not in points:
        await ctx.send("No data")
        return

    msg = ""

    for w, p in points[user].items():
        msg += f"{w} : {p}\n"

    await ctx.send(msg)


# ---------------- VOICE ----------------

@bot.event
async def on_voice_state_update(member, before, after):

    global tracking

    if not tracking:
        return

    user = member.id

    before_active = is_active(before)
    after_active = is_active(after)

    if not before_active and after_active:
        active_start[user] = time.time()

    if before_active and not after_active:

        if user in active_start:

            duration = time.time() - active_start[user]

            gained = int(duration / 60)

            week = get_week_key()

            uid = str(user)

            if uid not in points:
                points[uid] = {}

            if week not in points[uid]:
                points[uid][week] = 0

            points[uid][week] += gained

            save_points()

            del active_start[user]

    if after.self_mute:
        if user not in mute_time:
            mute_time[user] = time.time()
    else:
        mute_time.pop(user, None)

    if after.self_deaf:
        if user not in deaf_time:
            deaf_time[user] = time.time()
    else:
        deaf_time.pop(user, None)


# ---------------- CHECK LOOP ----------------

@tasks.loop(seconds=5)
async def check_states():

    if not tracking:
        return

    for guild in bot.guilds:

        for vc in guild.voice_channels:

            for member in vc.members:

                user = member.id
                state = member.voice

                if state is None:
                    continue

                if user in deaf_time:
                    if time.time() - deaf_time[user] > DEAF_LIMIT:
                        await member.move_to(None)
                        deaf_time.pop(user, None)

                if user in mute_time:
                    if time.time() - mute_time[user] > MUTE_LIMIT:
                        await member.move_to(None)
                        mute_time.pop(user, None)


# ---------------- READY ----------------

@bot.event
async def on_ready():
    check_states.start()
    print("Bot ready")


bot.run(TOKEN)
