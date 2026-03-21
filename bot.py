import discord
from discord.ext import commands, tasks
import time
import json
import os
from datetime import datetime, timedelta


TOKEN = os.environ["TOKEN"]

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="$", intents=intents)


# ---------------- CONFIG ----------------

DEAF_LIMIT = 20
MUTE_LIMIT = 60

tracking = False

points = {}

active_users = {}
mute_timer = {}
deaf_timer = {}


# ---------------- FILE ----------------

if os.path.exists("points.json"):
    with open("points.json", "r") as f:
        points = json.load(f)


def save_points():
    with open("points.json", "w") as f:
        json.dump(points, f, indent=4)


# ---------------- WEEK ----------------

def get_week():

    now = datetime.utcnow()

    start = now - timedelta(days=(now.weekday() + 1) % 7)
    end = start + timedelta(days=6)

    return f"{start.date()}_{end.date()}"


def last_4_weeks():

    weeks = []

    for i in range(4):

        d = datetime.utcnow() - timedelta(days=i * 7)

        s = d - timedelta(days=(d.weekday() + 1) % 7)
        e = s + timedelta(days=6)

        weeks.append(f"{s.date()}_{e.date()}")

    return weeks


def clean_weeks():

    valid = last_4_weeks()

    for uid in list(points.keys()):
        for w in list(points[uid].keys()):
            if w not in valid:
                del points[uid][w]


# ---------------- STATE ----------------

def is_active(state):

    if not state:
        return False

    if not state.channel:
        return False

    if state.self_mute or state.self_deaf:
        return False

    if state.mute or state.deaf:
        return False

    return True


# ---------------- POINT ADD ----------------

def add_points(user_id, seconds):

    mins = int(seconds // 60)

    if mins <= 0:
        return

    week = get_week()
    uid = str(user_id)

    if uid not in points:
        points[uid] = {}

    if week not in points[uid]:
        points[uid][week] = 0

    points[uid][week] += mins

    clean_weeks()
    save_points()


# ---------------- COMMANDS ----------------

@bot.command()
async def start(ctx):

    global tracking

    tracking = True

    active_users.clear()
    mute_timer.clear()
    deaf_timer.clear()

    await ctx.send("Tracking started")


@bot.command()
async def end(ctx):

    global tracking

    tracking = False

    save_points()

    await ctx.send("Tracking stopped")


@bot.command()
async def points_cmd(ctx, member: discord.Member = None):

    if member is None:
        member = ctx.author

    week = get_week()

    p = points.get(str(member.id), {}).get(week, 0)

    await ctx.send(f"{member.name} : {p}")


@bot.command()
async def leaderboard(ctx):

    week = get_week()

    text = "Leaderboard\n"

    for uid in points:

        if week in points[uid]:

            m = ctx.guild.get_member(int(uid))

            if m:
                text += f"{m.name} : {points[uid][week]}\n"

    await ctx.send(text)


# ---------------- VOICE UPDATE ----------------

@bot.event
async def on_voice_state_update(member, before, after):

    if not tracking:
        return

    uid = member.id

    # left channel

    if before.channel and not after.channel:

        if uid in active_users:

            duration = time.time() - active_users[uid]
            add_points(uid, duration)

            del active_users[uid]

        mute_timer.pop(uid, None)
        deaf_timer.pop(uid, None)

        return

    # joined / changed

    if after.channel:

        if is_active(after):
            active_users[uid] = time.time()

    # mute

    if after.self_mute:
        mute_timer[uid] = time.time()
    else:
        mute_timer.pop(uid, None)

    # deaf

    if after.self_deaf:
        deaf_timer[uid] = time.time()
    else:
        deaf_timer.pop(uid, None)

    # became inactive

    if uid in active_users and not is_active(after):

        duration = time.time() - active_users[uid]

        add_points(uid, duration)

        del active_users[uid]


# ---------------- CHECK LOOP ----------------

@tasks.loop(seconds=5)
async def check_loop():

    if not tracking:
        return

    for guild in bot.guilds:

        for vc in guild.voice_channels:

            for member in vc.members:

                uid = member.id
                state = member.voice

                if not state:
                    continue

                # deaf check

                if uid in deaf_timer:

                    if time.time() - deaf_timer[uid] > DEAF_LIMIT:

                        await member.move_to(None)
                        deaf_timer.pop(uid, None)

                        continue

                # mute check

                if uid in mute_timer:

                    if time.time() - mute_timer[uid] > MUTE_LIMIT:

                        await member.move_to(None)
                        mute_timer.pop(uid, None)

                        continue


# ---------------- READY ----------------

@bot.event
async def on_ready():

    check_loop.start()

    print("Bot ready")


bot.run(TOKEN)
