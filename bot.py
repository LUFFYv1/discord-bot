import discord
from discord.ext import commands, tasks
import time
import json
import os
from datetime import datetime, timedelta

TOKEN = os.environ["TOKEN"]

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="$", intents=intents)

# ---------- SETTINGS ----------

DEAF_LIMIT = 20
MUTE_LIMIT = 60

DEV_ROLE = "Developer"
IGNORE_ROLE = "Music Bot"

tracking = False

points = {}
active = {}
mute_timer = {}
deaf_timer = {}

# ---------- FILE ----------

if os.path.exists("points.json"):
    with open("points.json", "r") as f:
        points = json.load(f)


def save():
    with open("points.json", "w") as f:
        json.dump(points, f, indent=4)


# ---------- WEEK ----------

def get_week():
    now = datetime.utcnow()
    start = now - timedelta(days=(now.weekday() + 1) % 7)
    end = start + timedelta(days=6)
    return f"{start.date()}_{end.date()}"


def clean_old():

    valid = []

    for i in range(4):

        d = datetime.utcnow() - timedelta(days=i * 7)

        s = d - timedelta(days=(d.weekday() + 1) % 7)
        e = s + timedelta(days=6)

        valid.append(f"{s.date()}_{e.date()}")

    for u in list(points.keys()):
        for w in list(points[u].keys()):
            if w not in valid:
                del points[u][w]


# ---------- ROLE ----------

def has_dev(member):
    return any(r.name == DEV_ROLE for r in member.roles)


def ignore(member):
    return any(r.name == IGNORE_ROLE for r in member.roles)


# ---------- ACTIVE ----------

def is_active(state):

    if not state or not state.channel:
        return False

    if state.self_mute or state.self_deaf:
        return False

    if state.mute or state.deaf:
        return False

    return True


# ---------- POINT ADD ----------

def add_points(uid, seconds):

    mins = int(seconds // 60)

    if mins <= 0:
        return

    week = get_week()
    uid = str(uid)

    if uid not in points:
        points[uid] = {}

    if week not in points[uid]:
        points[uid][week] = 0

    points[uid][week] += mins

    clean_old()
    save()


# ---------- COMMANDS ----------

@bot.command()
async def start(ctx):

    global tracking

    if not has_dev(ctx.author):
        return

    tracking = True

    active.clear()
    mute_timer.clear()
    deaf_timer.clear()

    if not check_loop.is_running():
        check_loop.start()

    await ctx.send("Tracking started")


@bot.command()
async def end(ctx):

    global tracking

    if not has_dev(ctx.author):
        return

    tracking = False

    if check_loop.is_running():
        check_loop.stop()

    active.clear()
    mute_timer.clear()
    deaf_timer.clear()

    save()

    await ctx.send("Tracking stopped")


# ---------- POINTS ----------

@bot.command()
async def points_cmd(ctx, member: discord.Member = None):

    if member is None:
        member = ctx.author

    week = get_week()

    p = points.get(str(member.id), {}).get(week, 0)

    await ctx.send(f"{member.name} : {p} mins")


# ---------- LEADERBOARD ----------

@bot.command()
async def leaderboard(ctx):

    week = get_week()

    data = []

    for uid, weeks in points.items():
        if week in weeks:
            try:
                data.append({
                    "uid": int(uid),
                    "p": weeks[week]
                })
            except:
                continue

    data.sort(key=lambda x: x["p"], reverse=True)

    if not data:
        await ctx.send("No points recorded for this week yet.")
        return

    msg = f"🏆 Weekly Leaderboard ({week})\n\n"

    for i, user_data in enumerate(data, start=1):

        m = ctx.guild.get_member(user_data["uid"])
        name = m.name if m else f"User {user_data['uid']}"

        msg += f"{i}. {name} : {user_data['p']} mins\n"

    await ctx.send(msg)


# ---------- VOICE UPDATE (FIXED) ----------

@bot.event
async def on_voice_state_update(member, before, after):

    if not tracking:
        return

    if ignore(member):
        return

    uid = member.id

    # LEFT VC

    if before.channel and not after.channel:

        if uid in active:
            add_points(uid, time.time() - active[uid])
            del active[uid]

        mute_timer.pop(uid, None)
        deaf_timer.pop(uid, None)

        return

    # BECAME ACTIVE (no reset bug)

    if after.channel and is_active(after):
        active.setdefault(uid, time.time())

    # MUTE

    if after.self_mute or after.mute:
        mute_timer.setdefault(uid, time.time())
    else:
        mute_timer.pop(uid, None)

    # DEAF

    if after.self_deaf or after.deaf:
        deaf_timer.setdefault(uid, time.time())
    else:
        deaf_timer.pop(uid, None)

    # BECAME INACTIVE

    if uid in active and not is_active(after):

        add_points(uid, time.time() - active[uid])
        del active[uid]


# ---------- LOOP ----------

@tasks.loop(seconds=1)
async def check_loop():

    if not tracking:
        return

    now = time.time()

    for guild in bot.guilds:

        for m in guild.members:

            if not m.voice:
                continue

            if ignore(m):
                continue

            uid = m.id

            # DEAF

            if m.voice.self_deaf or m.voice.deaf:

                start = deaf_timer.get(uid)

                if start and now - start >= DEAF_LIMIT:

                    if uid in active:
                        add_points(uid, now - active[uid])
                        active.pop(uid, None)

                    await m.move_to(None)

                    deaf_timer.pop(uid, None)
                    mute_timer.pop(uid, None)

                elif not start:
                    deaf_timer[uid] = now

                continue

            else:
                deaf_timer.pop(uid, None)

            # MUTE

            if m.voice.self_mute or m.voice.mute:

                start = mute_timer.get(uid)

                if start and now - start >= MUTE_LIMIT:

                    if uid in active:
                        add_points(uid, now - active[uid])
                        active.pop(uid, None)

                    await m.move_to(None)

                    mute_timer.pop(uid, None)

                elif not start:
                    mute_timer[uid] = now

            else:
                mute_timer.pop(uid, None)


@bot.event
async def on_ready():
    print("Bot ready")


bot.run(TOKEN)
