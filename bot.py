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

active_start = {}
mute_time = {}
deaf_time = {}

DEAF_LIMIT = 20
MUTE_LIMIT = 60


# ---------------- LOAD ----------------

if os.path.exists("points.json"):
    with open("points.json", "r") as f:
        points = json.load(f)


def save_points():
    with open("points.json", "w") as f:
        json.dump(points, f, indent=4)


# ---------------- WEEK ----------------

def get_week_key():

    today = datetime.utcnow()

    start = today - timedelta(days=(today.weekday() + 1) % 7)
    end = start + timedelta(days=6)

    return f"{start.date()}_to_{end.date()}"


def get_last_4_weeks():

    weeks = []

    for i in range(4):

        d = datetime.utcnow() - timedelta(days=7 * i)

        s = d - timedelta(days=(d.weekday() + 1) % 7)
        e = s + timedelta(days=6)

        weeks.append(f"{s.date()}_to_{e.date()}")

    return weeks


def clean_old():

    valid = get_last_4_weeks()

    for uid in list(points.keys()):
        for w in list(points[uid].keys()):
            if w not in valid:
                del points[uid][w]


# ---------------- ACTIVE ----------------

def is_active(state):

    return (
        state
        and state.channel
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

    active_start.clear()
    mute_time.clear()
    deaf_time.clear()

    await ctx.send("Tracking started")


@bot.command()
async def end(ctx):

    global tracking
    tracking = False

    save_points()

    await ctx.send("Tracking stopped")


# ---------------- POINTS ----------------

@bot.command(name="points")
async def points_cmd(ctx, member: discord.Member = None):

    if member is None:
        member = ctx.author

    week = get_week_key()

    p = points.get(str(member.id), {}).get(week, 0)

    await ctx.send(f"{member.name} : {p}")


# ---------------- LEADERBOARD ----------------

@bot.command()
async def leaderboard(ctx):

    week = get_week_key()

    msg = "Leaderboard\n"

    for uid in points:

        if week in points[uid]:

            member = ctx.guild.get_member(int(uid))

            if member:
                msg += f"{member.name} : {points[uid][week]}\n"

    await ctx.send(msg)


# ---------------- VOICE STATE ----------------

@bot.event
async def on_voice_state_update(member, before, after):

    if not tracking:
        return

    uid = member.id

    # left VC → stop timer

    if before.channel and not after.channel:

        if uid in active_start:

            duration = time.time() - active_start[uid]

            add_points(uid, duration)

            del active_start[uid]

        mute_time.pop(uid, None)
        deaf_time.pop(uid, None)

        return

    # joined VC

    if after.channel:

        if is_active(after):

            active_start[uid] = time.time()

    # mute

    if after.self_mute:

        mute_time[uid] = time.time()

    else:

        mute_time.pop(uid, None)

    # deaf

    if after.self_deaf:

        deaf_time[uid] = time.time()

    else:

        deaf_time.pop(uid, None)

    # became inactive

    if uid in active_start and not is_active(after):

        duration = time.time() - active_start[uid]

        add_points(uid, duration)

        del active_start[uid]


# ---------------- ADD POINTS ----------------

def add_points(uid, duration):

    mins = int(duration // 60)

    if mins <= 0:
        return

    week = get_week_key()

    uid = str(uid)

    if uid not in points:
        points[uid] = {}

    if week not in points[uid]:
        points[uid][week] = 0

    points[uid][week] += mins

    clean_old()

    save_points()


# ---------------- LOOP ----------------

@tasks.loop(seconds=5)
async def check_loop():

    if not tracking:
        return

    for guild in bot.guilds:

        for vc in guild.voice_channels:

            for m in vc.members:

                uid = m.id
                state = m.voice

                if not state:
                    continue

                # deaf

                if uid in deaf_time:

                    if time.time() - deaf_time[uid] > DEAF_LIMIT:

                        await m.move_to(None)
                        deaf_time.pop(uid, None)

                        continue

                # mute

                if uid in mute_time:

                    if time.time() - mute_time[uid] > MUTE_LIMIT:

                        await m.move_to(None)
                        mute_time.pop(uid, None)

                        continue


# ---------------- READY ----------------

@bot.event
async def on_ready():

    check_loop.start()

    print("Bot ready")


bot.run(TOKEN)
