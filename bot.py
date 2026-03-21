import discord
from discord.ext import commands, tasks
import time
import json
import os
from datetime import datetime, timedelta

TOKEN = os.environ.get("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="$", intents=intents)

# ---------- SETTINGS ----------
DEAF_LIMIT = 20
MUTE_LIMIT = 60

ADMIN_ROLES = ["DEVELOPER", "CEO"]
IGNORE_ROLE = "Music Bot"

tracking = False

points = {}
active = {}
mute_timer = {}
deaf_timer = {}

# ---------- DATA ----------

if os.path.exists("points.json"):
    with open("points.json", "r") as f:
        points = json.load(f)


def save():
    with open("points.json", "w") as f:
        json.dump(points, f, indent=4)


# ---------- HELPERS ----------

def can_control(member):
    return any(role.name in ADMIN_ROLES for role in member.roles)


def is_music_bot(member):
    return any(role.name == IGNORE_ROLE for role in member.roles)


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


# ---------- WEEK ----------

def get_week():

    now = datetime.utcnow()

    start = now - timedelta(days=(now.weekday() + 1) % 7)
    end = start + timedelta(days=6)

    return f"{start.date()}_{end.date()}"


def add_points(uid, seconds):

    mins = int(seconds // 60)

    if mins <= 0:
        return

    week = get_week()
    uid_s = str(uid)

    if uid_s not in points:
        points[uid_s] = {}

    points[uid_s][week] = points[uid_s].get(week, 0) + mins

    save()


# ---------- COMMANDS ----------

@bot.command()
async def start(ctx):

    global tracking

    if not can_control(ctx.author):
        return await ctx.send("❌ Need DEVELOPER or CEO")

    tracking = True

    active.clear()
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

    active.clear()
    mute_timer.clear()
    deaf_timer.clear()

    save()

    await ctx.send("Tracking Stopped")


@bot.command()
async def points_cmd(ctx, member: discord.Member = None):

    member = member or ctx.author

    week = get_week()

    p = points.get(str(member.id), {}).get(week, 0)

    await ctx.send(f"{member.name} : {p} mins")


@bot.command()
async def leaderboard(ctx):

    week = get_week()

    data = []

    for u, w in points.items():

        if week in w:
            data.append({"uid": int(u), "p": w[week]})

    data.sort(key=lambda x: x["p"], reverse=True)

    if not data:
        return await ctx.send("No points")

    msg = f"Leaderboard {week}\n"

    for i, user in enumerate(data[:10], 1):

        m = ctx.guild.get_member(user["uid"])

        name = m.name if m else user["uid"]

        msg += f"{i}. {name} : {user['p']} mins\n"

    await ctx.send(msg)


# ---------- VOICE ----------

@bot.event
async def on_voice_state_update(member, before, after):

    if not tracking:
        return

    if is_music_bot(member):
        return

    uid = member.id

    # left

    if before.channel and not after.channel:

        if uid in active:
            add_points(uid, time.time() - active[uid])
            active.pop(uid, None)

        mute_timer.pop(uid, None)
        deaf_timer.pop(uid, None)

        return

    # active

    if after.channel and is_active(after):
        active.setdefault(uid, time.time())

    # mute

    if after.self_mute or after.mute:
        mute_timer.setdefault(uid, time.time())
    else:
        mute_timer.pop(uid, None)

    # deaf

    if after.self_deaf or after.deaf:
        deaf_timer.setdefault(uid, time.time())
    else:
        deaf_timer.pop(uid, None)

    # inactive

    if uid in active and not is_active(after):

        add_points(uid, time.time() - active[uid])
        active.pop(uid, None)


# ---------- LOOP ----------

@tasks.loop(seconds=1)
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

                # DEAF

                if state.self_deaf or state.deaf:

                    t = deaf_timer.get(uid)

                    if t and now - t >= DEAF_LIMIT:

                        if uid in active:
                            add_points(uid, now - active[uid])
                            active.pop(uid, None)

                        await m.move_to(None)

                        deaf_timer.pop(uid, None)

                    elif not t:
                        deaf_timer[uid] = now

                    continue

                else:
                    deaf_timer.pop(uid, None)

                # MUTE

                if state.self_mute or state.mute:

                    t = mute_timer.get(uid)

                    if t and now - t >= MUTE_LIMIT:

                        if uid in active:
                            add_points(uid, now - active[uid])
                            active.pop(uid, None)

                        await m.move_to(None)

                        mute_timer.pop(uid, None)

                    elif not t:
                        mute_timer[uid] = now

                else:
                    mute_timer.pop(uid, None)


@bot.event
async def on_ready():

    print("Bot ready")


bot.run(TOKEN)
