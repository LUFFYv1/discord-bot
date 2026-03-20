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


# ---------- CLEAN OLD ----------

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


# ---------- HISTORY ----------

@bot.command()
async def history(ctx, member: discord.Member = None):

    if member is None:
        member = ctx.author

    uid = str(member.id)

    if uid not in points:
        await ctx.send("No data")
        return

    msg = ""

    for w, p in points[uid].items():
        msg += f"{w} : {p}\n"

    await ctx.send(msg)


# ---------- LOOP ----------

@tasks.loop(seconds=60)
async def track_loop():

    if not tracking:
        return

    week = get_week_key()

    clean_old_weeks()

    for guild in bot.guilds:

        for vc in guild.voice_channels:

            for member in vc.members:

                if not is_active(member.voice):
                    continue

                uid = str(member.id)

                if uid not in points:
                    points[uid] = {}

                if week not in points[uid]:
                    points[uid][week] = 0

                points[uid][week] += 1

    save_points()


# ---------- READY ----------

@bot.event
async def on_ready():
    track_loop.start()
    print("Bot ready")


bot.run(TOKEN)
