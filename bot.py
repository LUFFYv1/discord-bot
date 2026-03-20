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

points = {}

mute_time = {}
deaf_time = {}

DEAF_LIMIT = 20
MUTE_LIMIT = 60   # ✅ changed to 1 min


# ---------- LOAD ----------

if os.path.exists("points.json"):
    with open("points.json", "r") as f:
        points = json.load(f)


def save_points():
    with open("points.json", "w") as f:
        json.dump(points, f, indent=4)


# ---------- WEEK ----------

def get_week_key():

    today = datetime.utcnow()

    start = today - timedelta(days=(today.weekday() + 1) % 7)
    end = start + timedelta(days=6)

    return f"{start.date()}_to_{end.date()}"


def get_last_4_weeks():

    weeks = []

    for i in range(4):

        day = datetime.utcnow() - timedelta(days=7 * i)

        start = day - timedelta(days=(day.weekday() + 1) % 7)
        end = start + timedelta(days=6)

        weeks.append(f"{start.date()}_to_{end.date()}")

    return weeks


def clean_old_weeks():

    valid = get_last_4_weeks()

    for uid in list(points.keys()):

        for w in list(points[uid].keys()):

            if w not in valid:
                del points[uid][w]


# ---------- ACTIVE ----------

def is_active(state):

    return (
        state
        and state.channel
        and not state.self_mute
        and not state.self_deaf
        and not state.mute
        and not state.deaf
    )


# ---------- COMMANDS ----------

@bot.command()
async def start(ctx):

    global tracking
    tracking = True

    # ✅ initialize timers for users already in VC

    for guild in bot.guilds:
        for vc in guild.voice_channels:
            for member in vc.members:

                if member.voice:

                    if member.voice.self_mute:
                        mute_time[member.id] = time.time()

                    if member.voice.self_deaf:
                        deaf_time[member.id] = time.time()

    await ctx.send("Tracking started")


@bot.command()
async def end(ctx):

    global tracking
    tracking = False

    await ctx.send("Tracking stopped")


# ---------- POINTS ----------

@bot.command()
async def points_cmd(ctx, member: discord.Member = None):

    if member is None:
        member = ctx.author

    week = get_week_key()

    p = points.get(str(member.id), {}).get(week, 0)

    await ctx.send(f"{member.name} : {p}")


# ---------- LEADERBOARD ----------

@bot.command()
async def leaderboard(ctx):

    week = get_week_key()

    msg = "Leaderboard\n"

    for uid in points:

        if week in points[uid]:

            p = points[uid][week]

            member = ctx.guild.get_member(int(uid))

            if member:
                msg += f"{member.name} : {p}\n"

    await ctx.send(msg)


# ---------- VOICE STATE ----------

@bot.event
async def on_voice_state_update(member, before, after):

    if not tracking:
        return

    uid = member.id

    # mute timer

    if after.self_mute:
        if uid not in mute_time:
            mute_time[uid] = time.time()
    else:
        mute_time.pop(uid, None)

    # deaf timer

    if after.self_deaf:
        if uid not in deaf_time:
            deaf_time[uid] = time.time()
    else:
        deaf_time.pop(uid, None)


# ---------- LOOP ----------

@tasks.loop(seconds=60)   # ✅ 1 point per minute
async def track_loop():

    if not tracking:
        return

    week = get_week_key()

    clean_old_weeks()

    for guild in bot.guilds:

        for vc in guild.voice_channels:

            for member in vc.members:

                state = member.voice

                if state is None:
                    continue

                uid = member.id

                # ----- DEAF -----

                if uid in deaf_time:

                    if time.time() - deaf_time[uid] > DEAF_LIMIT:

                        await member.move_to(None)
                        deaf_time.pop(uid, None)
                        continue

                # ----- MUTE -----

                if uid in mute_time:

                    if time.time() - mute_time[uid] > MUTE_LIMIT:

                        await member.move_to(None)
                        mute_time.pop(uid, None)
                        continue

                # ----- ACTIVE -----

                if not is_active(state):
                    continue

                s = str(uid)

                if s not in points:
                    points[s] = {}

                if week not in points[s]:
                    points[s][week] = 0

                points[s][week] += 1

    save_points()


# ---------- READY ----------

@bot.event
async def on_ready():

    track_loop.start()
    print("Bot ready")


bot.run(TOKEN)
