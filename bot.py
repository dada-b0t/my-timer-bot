import discord
from discord.ext import commands
import asyncio
import os
import struct
import math
import sqlite3
from datetime import datetime

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

GUILD_ID = discord.Object(id=1506990201204117565)

active_timers = {}

DB_PATH = "/app/data/donations.db"

def init_donation_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS donations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            amount INTEGER NOT NULL,
            image_url TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def generate_beep_wav():
    sample_rate = 44100
    duration = 1.5
    frequency = 880
    volume = 0.5
    num_samples = int(sample_rate * duration)
    wav_data = bytearray()
    data_size = num_samples * 2
    wav_data += b"RIFF"
    wav_data += struct.pack("<I", 36 + data_size)
    wav_data += b"WAVE"
    wav_data += b"fmt "
    wav_data += struct.pack("<I", 16)
    wav_data += struct.pack("<H", 1)
    wav_data += struct.pack("<H", 1)
    wav_data += struct.pack("<I", sample_rate)
    wav_data += struct.pack("<I", sample_rate * 2)
    wav_data += struct.pack("<H", 2)
    wav_data += struct.pack("<H", 16)
    wav_data += b"data"
    wav_data += struct.pack("<I", data_size)
    for i in range(num_samples):
        t = i / sample_rate
        fade = 1.0
        fade_samples = int(sample_rate * 0.05)
        if i < fade_samples:
            fade = i / fade_samples
        elif i > num_samples - fade_samples:
            fade = (num_samples - i) / fade_samples
        sample = int(volume * fade * 32767 * math.sin(2 * math.pi * frequency * t))
        wav_data += struct.pack("<h", sample)
    with open("beep.wav", "wb") as f:
        f.write(wav_data)
    print("✅ beep.wav 생성 완료")


@bot.event
async def on_ready():
    print(f"✅ 봇 로그인 완료: {bot.user}")
    if not os.path.exists("beep.wav"):
        generate_beep_wav()
    init_donation_db()
    init_raid_db()
    bot.tree.copy_global_to(guild=GUILD_ID)
    await bot.tree.sync(guild=GUILD_ID)
    print("✅ 슬래시 커맨드 서버 즉시 등록 완료")


class TimerView(discord.ui.View):
    def __init__(self, guild_id, voice_client, channel):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.voice_client = voice_client
        self.channel = channel

    @discord.ui.button(label="▶ 타이머 시작", style=discord.ButtonStyle.success)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = self.guild_id
        if guild_id in active_timers and active_timers[guild_id].get("task"):
            await interaction.response.send_message("⚠️ 이미 타이머가 실행 중이에요!", ephemeral=True)
            return
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("✅ 타이머 시작! **80초 후** 첫 알람, 이후 **90초마다** 알람을 울릴게요. 🔔")
        task = bot.loop.create_task(timer_loop(self.channel, guild_id, self.voice_client))
        active_timers[guild_id]["task"] = task

    @discord.ui.button(label="⏹ 종료", style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = self.guild_id
        if guild_id not in active_timers:
            await interaction.response.send_message("❌ 실행 중인 타이머가 없어요.", ephemeral=True)
            return
        await stop_timer(guild_id)
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("⏹ 타이머를 종료하고 음성 채널에서 나왔어요.")


async def timer_loop(channel, guild_id, voice_client):
    try:
        await asyncio.sleep(80)
        if guild_id not in active_timers or not voice_client.is_connected():
            return
        play_beep(voice_client)
        await channel.send("🔔 **첫 번째 알람!** (80초 경과)")
        count = 1
        while guild_id in active_timers and voice_client.is_connected():
            await asyncio.sleep(90)
            if guild_id not in active_timers or not voice_client.is_connected():
                break
            count += 1
            play_beep(voice_client)
            await channel.send(f"🔔 **{count}번째 알람!**")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"타이머 오류: {e}")


def play_beep(voice_client):
    if not voice_client.is_playing():
        source = discord.FFmpegPCMAudio("beep.wav")
        voice_client.play(source)
        print("🔔 비프음 재생")


async def stop_timer(guild_id):
    if guild_id not in active_timers:
        return
    data = active_timers.pop(guild_id)
    task = data.get("task")
    if task:
        task.cancel()
    vc = data.get("voice_client")
    if vc:
        if vc.is_playing():
            vc.stop()
        if vc.is_connected():
            await vc.disconnect()


@bot.tree.command(name="카쿰단유타이머", description="음성 채널에 입장하고 타이머를 시작합니다", guild=GUILD_ID)
async def kakum_timer(interaction: discord.Interaction):
    if not interaction.user.voice:
        await interaction.response.send_message("❌ 먼저 음성 채널에 들어가 주세요!", ephemeral=True)
        return
    guild_id = interaction.guild.id
    if guild_id in active_timers:
        await interaction.response.send_message("⚠️ 이미 봇이 음성 채널에 있어요. 먼저 종료 버튼을 눌러주세요.", ephemeral=True)
        return
    channel = interaction.user.voice.channel
    voice_client = await channel.connect()
    active_timers[guild_id] = {"voice_client": voice_client, "task": None}
    await interaction.response.send_message(
        f"🔊 **{channel.name}** 에 입장했어요!\n"
        "⏱ 준비됐으면 아래 버튼을 눌러 타이머를 시작하세요!\n"
        "> 첫 알람: **80초 후**\n"
        "> 이후: **90초마다**",
        view=TimerView(guild_id, voice_client, interaction.channel)
    )


# ─────────────────────────────────────────
# 기부 시스템
# ─────────────────────────────────────────

@bot.tree.command(name="기부인증", description="길드 기부를 스크린샷과 함께 인증합니다.", guild=GUILD_ID)
async def donate(interaction: discord.Interaction, 횟수: int, 스크린샷: discord.Attachment):
    if 횟수 < 1:
        await interaction.response.send_message("❌ 기부 횟수는 1회 이상이어야 해요.", ephemeral=True)
        return
    if not 스크린샷.content_type or not 스크린샷.content_type.startswith("image/"):
        await interaction.response.send_message("❌ 스크린샷 이미지만 첨부할 수 있어요.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)
    username = interaction.user.display_name
    image_url = 스크린샷.url
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM donations
        WHERE guild_id = ? AND user_id = ? AND created_at LIKE ?
        AND image_url != '관리자 수동 수정'
    """, (guild_id, user_id, f"{today}%"))
    already = cur.fetchone()[0]
    if already > 0:
        conn.close()
        await interaction.response.send_message("❌ 오늘은 이미 기부를 등록했어요.", ephemeral=True)
        return
    cur.execute("""
        INSERT INTO donations (guild_id, user_id, username, amount, image_url, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (guild_id, user_id, username, 횟수, image_url, now))
    cur.execute("SELECT SUM(amount) FROM donations WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    total = cur.fetchone()[0] or 0
    conn.commit()
    conn.close()
    embed = discord.Embed(title="💰 길드 기부 인증", color=0xF1C40F)
    embed.add_field(name="👤 길드원", value=interaction.user.mention, inline=True)
    embed.add_field(name="🎁 이번 기부", value=f"{횟수}회", inline=True)
    embed.add_field(name="📊 누적 기부", value=f"{total}회", inline=True)
    embed.add_field(name="🕒 인증 시간", value=now, inline=False)
    embed.set_image(url=image_url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="기부대리등록", description="관리자가 다른 길드원의 기부 인증을 대신 등록합니다.", guild=GUILD_ID)
async def donation_proxy_register(interaction: discord.Interaction, 유저: discord.Member, 횟수: int, 스크린샷: discord.Attachment):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ 관리자만 사용할 수 있어요.", ephemeral=True)
        return
    if 횟수 < 1:
        await interaction.response.send_message("❌ 기부 횟수는 1회 이상이어야 해요.", ephemeral=True)
        return
    if not 스크린샷.content_type or not 스크린샷.content_type.startswith("image/"):
        await interaction.response.send_message("❌ 스크린샷 이미지만 첨부할 수 있어요.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    user_id = str(유저.id)
    username = 유저.display_name
    image_url = 스크린샷.url
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO donations (guild_id, user_id, username, amount, image_url, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (guild_id, user_id, username, 횟수, image_url, now))
    cur.execute("SELECT SUM(amount) FROM donations WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    total = cur.fetchone()[0] or 0
    conn.commit()
    conn.close()
    embed = discord.Embed(title="💰 길드 기부 대리 등록", color=0xF1C40F)
    embed.add_field(name="👤 길드원", value=유저.mention, inline=True)
    embed.add_field(name="📝 등록자", value=interaction.user.mention, inline=True)
    embed.add_field(name="🎁 이번 기부", value=f"{횟수}회", inline=True)
    embed.add_field(name="📊 누적 기부", value=f"{total}회", inline=True)
    embed.add_field(name="🕒 등록 시간", value=now, inline=False)
    embed.set_image(url=image_url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="기부랭킹", description="길드 기부 랭킹을 확인합니다.", guild=GUILD_ID)
async def donation_ranking(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT username, SUM(amount) as total
        FROM donations WHERE guild_id = ?
        GROUP BY user_id ORDER BY total DESC LIMIT 10
    """, (guild_id,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await interaction.response.send_message("아직 기부 인증 기록이 없어요.")
        return
    medals = ["🥇", "🥈", "🥉"]
    text = ""
    for i, (username, total) in enumerate(rows, start=1):
        medal = medals[i - 1] if i <= 3 else f"{i}."
        text += f"{medal} **{username}** - {total}회\n"
    embed = discord.Embed(title="🏆 길드 기부 랭킹", description=text, color=0xF1C40F)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="기부조회", description="특정 유저의 기부 기록을 조회합니다.", guild=GUILD_ID)
async def donation_check(interaction: discord.Interaction, 유저: discord.Member):
    guild_id = str(interaction.guild.id)
    user_id = str(유저.id)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT SUM(amount) FROM donations WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    total = cur.fetchone()[0] or 0
    cur.execute("""
        SELECT amount, image_url, created_at FROM donations
        WHERE guild_id = ? AND user_id = ?
        ORDER BY id DESC LIMIT 5
    """, (guild_id, user_id))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await interaction.response.send_message(f"❌ {유저.mention}님의 기부 기록이 없어요.")
        return
    desc = f"📊 누적 기부: **{total}회**\n\n최근 인증 기록\n"
    first_valid_image = None
    for amount, image_url, created_at in rows:
        if image_url and isinstance(image_url, str) and image_url.startswith("http"):
            desc += f"- {created_at} / {amount}회 / [스크린샷]({image_url})\n"
            if first_valid_image is None:
                first_valid_image = image_url
        else:
            desc += f"- {created_at} / {amount:+}회 / 🛠 관리자 수동 수정\n"
    embed = discord.Embed(title=f"💰 {유저.display_name} 기부 조회", description=desc, color=0xF1C40F)
    if first_valid_image:
        embed.set_image(url=first_valid_image)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="기부수정", description="관리자가 유저의 기부 횟수를 수동으로 추가/차감합니다.", guild=GUILD_ID)
async def donation_edit(interaction: discord.Interaction, 유저: discord.Member, 횟수: int):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ 관리자만 사용할 수 있어요.", ephemeral=True)
        return
    if 횟수 == 0:
        await interaction.response.send_message("❌ 0회는 입력할 수 없어요.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    user_id = str(유저.id)
    username = 유저.display_name
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO donations (guild_id, user_id, username, amount, image_url, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (guild_id, user_id, username, 횟수, "관리자 수동 수정", now))
    cur.execute("SELECT SUM(amount) FROM donations WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    total = cur.fetchone()[0] or 0
    conn.commit()
    conn.close()
    await interaction.response.send_message(
        f"✅ {유저.mention}님의 기부 기록을 `{횟수:+}회` 수정했어요.\n현재 누적: **{total}회**"
    )


@bot.tree.command(name="기부삭제", description="관리자가 잘못된 기부 기록을 삭제합니다.", guild=GUILD_ID)
async def donation_delete(interaction: discord.Interaction, 유저: discord.Member):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ 관리자만 사용할 수 있어요.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    user_id = str(유저.id)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, amount, image_url, created_at FROM donations
        WHERE guild_id = ? AND user_id = ?
        ORDER BY id DESC LIMIT 10
    """, (guild_id, user_id))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await interaction.response.send_message(f"❌ {유저.mention}님의 기부 기록이 없어요.", ephemeral=True)
        return
    desc = f"**{유저.display_name}** 님의 최근 기록이에요.\n삭제할 기록의 ID를 `/기부id삭제` 로 입력해주세요.\n\n"
    for record_id, amount, image_url, created_at in rows:
        if image_url.startswith("http"):
            desc += f"`ID: {record_id}` | {created_at} | {amount}회 | [스크린샷]({image_url})\n"
        else:
            desc += f"`ID: {record_id}` | {created_at} | {amount:+}회 | 🛠 관리자 수동 수정\n"
    embed = discord.Embed(title=f"🗑 기부 기록 삭제 - {유저.display_name}", description=desc, color=0xE74C3C)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="기부id삭제", description="관리자가 기부 기록 id로 특정 기록을 삭제합니다.", guild=GUILD_ID)
async def donation_delete_by_id(interaction: discord.Interaction, 기록id: int):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ 관리자만 사용할 수 있어요.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, username, amount, created_at FROM donations
        WHERE id = ? AND guild_id = ?
    """, (기록id, guild_id))
    row = cur.fetchone()
    if not row:
        conn.close()
        await interaction.response.send_message(f"❌ ID `{기록id}` 기록을 찾을 수 없어요.", ephemeral=True)
        return
    record_id, username, amount, created_at = row
    cur.execute("DELETE FROM donations WHERE id = ?", (기록id,))
    conn.commit()
    conn.close()
    await interaction.response.send_message(
        f"✅ 기록을 삭제했어요.\n> ID: `{record_id}` | {username} | {amount}회 | {created_at}"
    )



@bot.tree.command(name="기부전체조회", description="전체 길드원의 기부 현황을 확인합니다.", guild=GUILD_ID)
async def donation_all(interaction: discord.Interaction):
    await interaction.response.defer()

    guild_id = str(interaction.guild.id)
    guild = interaction.guild

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, SUM(amount) as total
        FROM donations WHERE guild_id = ?
        GROUP BY user_id
    """, (guild_id,))
    donation_map = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()

    members = [m for m in guild.members if not m.bot]
    members.sort(key=lambda m: donation_map.get(str(m.id), 0), reverse=True)

    done = []
    not_done = []
    for m in members:
        total = donation_map.get(str(m.id), 0)
        if total > 0:
            done.append(f"✅ {m.display_name} - {total}회")
        else:
            not_done.append(f"❌ {m.display_name} - 0회")

    text = "\n".join(done + not_done)
    if len(text) > 4000:
        text = text[:4000] + "\n..."

    embed = discord.Embed(
        title=f"📋 전체 기부 현황 (총 {len(members)}명)",
        description=text,
        color=0xF1C40F
    )
    embed.set_footer(text=f"기부자 {len(done)}명 | 미기부 {len(not_done)}명")
    await interaction.followup.send(embed=embed)



# ─────────────────────────────────────────
# 공대 신청 시스템
# ─────────────────────────────────────────

RAID_JOBS = ["비숍", "달나", "궁수", "근격", "원격"]

def init_raid_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS raids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT NOT NULL,
            name TEXT NOT NULL,
            raid_time TEXT NOT NULL,
            slots TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS raid_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raid_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL,
            job TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def get_raid_embed(raid_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT name, raid_time, slots FROM raids WHERE id = ?", (raid_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    name, raid_time, slots_json = row
    import json
    slots = json.loads(slots_json)

    cur.execute("SELECT username, job FROM raid_members WHERE raid_id = ?", (raid_id,))
    members = cur.fetchall()
    conn.close()

    # 직업별 멤버 정리
    job_members = {job: [] for job in RAID_JOBS}
    for username, job in members:
        if job in job_members:
            job_members[job].append(username)

    embed = discord.Embed(
        title=f"⚔️ {name}",
        description=f"🕒 시간: **{raid_time}**",
        color=0x9B59B6
    )

    for job in RAID_JOBS:
        limit = slots.get(job, 0)
        if limit == 0:
            continue
        current = job_members[job]
        filled = len(current)
        member_text = "\n".join(current) if current else "없음"
        embed.add_field(
            name=f"{job} ({filled}/{limit})",
            value=member_text,
            inline=True
        )

    total = len(members)
    embed.set_footer(text=f"총 {total}명 신청 중")
    return embed


def make_raid_view(raid_id):
    import json
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT slots FROM raids WHERE id = ?", (raid_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    slots = json.loads(row[0])

    view = discord.ui.View(timeout=None)

    for job in RAID_JOBS:
        if slots.get(job, 0) == 0:
            continue

        async def make_callback(j=job, rid=raid_id):
            async def callback(interaction: discord.Interaction):
                await handle_raid_join(interaction, rid, j)
            return callback

        btn = discord.ui.Button(
            label=f"{job} 신청",
            style=discord.ButtonStyle.primary,
            custom_id=f"raid_{raid_id}_{job}"
        )
        import asyncio
        btn.callback = asyncio.get_event_loop().run_until_complete(make_callback(job, raid_id)) if False else None

        view.add_item(btn)

    cancel_btn = discord.ui.Button(
        label="❌ 신청 취소",
        style=discord.ButtonStyle.danger,
        custom_id=f"raid_{raid_id}_cancel"
    )
    view.add_item(cancel_btn)
    return view


async def handle_raid_join(interaction: discord.Interaction, raid_id: int, job: str):
    import json
    guild_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)
    username = interaction.user.display_name

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT slots FROM raids WHERE id = ? AND guild_id = ?", (raid_id, guild_id))
    row = cur.fetchone()
    if not row:
        conn.close()
        await interaction.response.send_message("❌ 공대를 찾을 수 없어요.", ephemeral=True)
        return

    slots = json.loads(row[0])
    limit = slots.get(job, 0)

    # 이미 신청했는지 확인
    cur.execute("SELECT job FROM raid_members WHERE raid_id = ? AND user_id = ?", (raid_id, user_id))
    existing = cur.fetchone()
    if existing:
        conn.close()
        await interaction.response.send_message(f"⚠️ 이미 **{existing[0]}**으로 신청했어요. 취소 후 다시 신청해주세요.", ephemeral=True)
        return

    # 슬롯 확인
    cur.execute("SELECT COUNT(*) FROM raid_members WHERE raid_id = ? AND job = ?", (raid_id, job))
    current = cur.fetchone()[0]
    if current >= limit:
        conn.close()
        await interaction.response.send_message(f"❌ **{job}** 슬롯이 꽉 찼어요. ({current}/{limit})", ephemeral=True)
        return

    cur.execute("INSERT INTO raid_members (raid_id, user_id, username, job) VALUES (?, ?, ?, ?)",
                (raid_id, user_id, username, job))
    conn.commit()
    conn.close()

    embed = get_raid_embed(raid_id)
    await interaction.response.edit_message(embed=embed)
    await interaction.followup.send(f"✅ **{job}**으로 신청했어요!", ephemeral=True)


async def handle_raid_cancel(interaction: discord.Interaction, raid_id: int):
    user_id = str(interaction.user.id)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT job FROM raid_members WHERE raid_id = ? AND user_id = ?", (raid_id, user_id))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        await interaction.response.send_message("❌ 신청 내역이 없어요.", ephemeral=True)
        return

    cur.execute("DELETE FROM raid_members WHERE raid_id = ? AND user_id = ?", (raid_id, user_id))
    conn.commit()
    conn.close()

    embed = get_raid_embed(raid_id)
    await interaction.response.edit_message(embed=embed)
    await interaction.followup.send("✅ 신청을 취소했어요.", ephemeral=True)


@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id", "")
        if custom_id.startswith("raid_"):
            parts = custom_id.split("_")
            raid_id = int(parts[1])
            action = "_".join(parts[2:])
            if action == "cancel":
                await handle_raid_cancel(interaction, raid_id)
            else:
                await handle_raid_join(interaction, raid_id, action)
            return
    await bot.process_application_commands(interaction)


@bot.tree.command(name="공대생성", description="새 공대를 생성합니다. (관리자 전용)", guild=GUILD_ID)
async def raid_create(
    interaction: discord.Interaction,
    공대이름: str,
    시간: str,
    비숍: int = 0,
    달나: int = 0,
    궁수: int = 0,
    근격: int = 0,
    원격: int = 0
):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ 관리자만 사용할 수 있어요.", ephemeral=True)
        return

    import json
    guild_id = str(interaction.guild.id)
    slots = {"비숍": 비숍, "달나": 달나, "궁수": 궁수, "근격": 근격, "원격": 원격}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO raids (guild_id, name, raid_time, slots, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (guild_id, 공대이름, 시간, json.dumps(slots, ensure_ascii=False), now))
    raid_id = cur.lastrowid
    conn.commit()
    conn.close()

    embed = get_raid_embed(raid_id)

    # 버튼 생성
    view = discord.ui.View(timeout=None)
    for job in RAID_JOBS:
        if slots.get(job, 0) == 0:
            continue
        btn = discord.ui.Button(
            label=f"{job} 신청",
            style=discord.ButtonStyle.primary,
            custom_id=f"raid_{raid_id}_{job}"
        )
        view.add_item(btn)

    cancel_btn = discord.ui.Button(
        label="❌ 신청 취소",
        style=discord.ButtonStyle.danger,
        custom_id=f"raid_{raid_id}_cancel"
    )
    view.add_item(cancel_btn)

    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="공대강퇴", description="공대에서 특정 유저를 강제 퇴출합니다. (관리자 전용)", guild=GUILD_ID)
async def raid_kick(
    interaction: discord.Interaction,
    공대id: int,
    유저: discord.Member
):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ 관리자만 사용할 수 있어요.", ephemeral=True)
        return

    user_id = str(유저.id)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT job FROM raid_members WHERE raid_id = ? AND user_id = ?", (공대id, user_id))
    row = cur.fetchone()
    if not row:
        conn.close()
        await interaction.response.send_message(f"❌ {유저.mention}님은 해당 공대에 신청하지 않았어요.", ephemeral=True)
        return

    cur.execute("DELETE FROM raid_members WHERE raid_id = ? AND user_id = ?", (공대id, user_id))
    conn.commit()
    conn.close()

    await interaction.response.send_message(f"✅ {유저.mention}님을 공대 #{공대id}에서 강제 퇴출했어요.")


@bot.tree.command(name="공대목록", description="현재 공대 목록을 확인합니다.", guild=GUILD_ID)
async def raid_list(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, name, raid_time FROM raids WHERE guild_id = ? ORDER BY id DESC LIMIT 10", (guild_id,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await interaction.response.send_message("현재 생성된 공대가 없어요.")
        return

    text = "\n".join(f"`ID: {r[0]}` | **{r[1]}** | {r[2]}" for r in rows)
    embed = discord.Embed(title="⚔️ 공대 목록", description=text, color=0x9B59B6)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="공대삭제", description="공대를 삭제합니다. (관리자 전용)", guild=GUILD_ID)
async def raid_delete(interaction: discord.Interaction, 공대id: int):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ 관리자만 사용할 수 있어요.", ephemeral=True)
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM raid_members WHERE raid_id = ?", (공대id,))
    cur.execute("DELETE FROM raids WHERE id = ?", (공대id,))
    conn.commit()
    conn.close()

    await interaction.response.send_message(f"✅ 공대 #{공대id}를 삭제했어요.")


# ─────────────────────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN", "여기에_봇_토큰_입력")
bot.run(TOKEN)
