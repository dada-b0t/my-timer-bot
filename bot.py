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

bot = commands.Bot(command_prefix="!", intents=intents)

GUILD_ID = discord.Object(id=1506990201204117565)

active_timers = {}

DB_PATH = "donations.db"


def init_donation_db():
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
        await interaction.followup.send(
            "✅ 타이머 시작! **80초 후** 첫 알람, 이후 **90초마다** 알람을 울릴게요. 🔔"
        )

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

    active_timers[guild_id] = {
        "voice_client": voice_client,
        "task": None
    }

    await interaction.response.send_message(
        f"🔊 **{channel.name}** 에 입장했어요!\n"
        "⏱ 준비됐으면 아래 버튼을 눌러 타이머를 시작하세요!\n"
        "> 첫 알람: **80초 후**\n"
        "> 이후: **90초마다**",
        view=TimerView(guild_id, voice_client, interaction.channel)
    )


@bot.tree.command(name="기부인증", description="길드 기부를 스크린샷과 함께 인증합니다.", guild=GUILD_ID)
async def donate(
    interaction: discord.Interaction,
    횟수: int,
    스크린샷: discord.Attachment
):
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

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO donations (guild_id, user_id, username, amount, image_url, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (guild_id, user_id, username, 횟수, image_url, now))

    cur.execute("""
        SELECT SUM(amount)
        FROM donations
        WHERE guild_id = ? AND user_id = ?
    """, (guild_id, user_id))

    total = cur.fetchone()[0] or 0

    conn.commit()
    conn.close()

    embed = discord.Embed(
        title="💰 길드 기부 인증",
        color=0xF1C40F
    )
    embed.add_field(name="👤 길드원", value=interaction.user.mention, inline=True)
    embed.add_field(name="🎁 이번 기부", value=f"{횟수}회", inline=True)
    embed.add_field(name="📊 누적 기부", value=f"{total}회", inline=True)
    embed.add_field(name="🕒 인증 시간", value=now, inline=False)
    embed.set_image(url=image_url)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="기부대리등록", description="관리자가 다른 길드원의 기부 인증을 대신 등록합니다.", guild=GUILD_ID)
async def donation_proxy_register(
    interaction: discord.Interaction,
    유저: discord.Member,
    횟수: int,
    스크린샷: discord.Attachment
):
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

    cur.execute("""
        SELECT SUM(amount)
        FROM donations
        WHERE guild_id = ? AND user_id = ?
    """, (guild_id, user_id))

    total = cur.fetchone()[0] or 0

    conn.commit()
    conn.close()

    embed = discord.Embed(
        title="💰 길드 기부 대리 등록",
        color=0xF1C40F
    )
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
        FROM donations
        WHERE guild_id = ?
        GROUP BY user_id
        ORDER BY total DESC
        LIMIT 10
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

    embed = discord.Embed(
        title="🏆 길드 기부 랭킹",
        description=text,
        color=0xF1C40F
    )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="기부조회", description="특정 유저의 기부 기록을 조회합니다.", guild=GUILD_ID)
async def donation_check(
    interaction: discord.Interaction,
    유저: discord.Member
):
    guild_id = str(interaction.guild.id)
    user_id = str(유저.id)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT SUM(amount)
        FROM donations
        WHERE guild_id = ? AND user_id = ?
    """, (guild_id, user_id))

    total = cur.fetchone()[0] or 0

    cur.execute("""
        SELECT amount, image_url, created_at
        FROM donations
        WHERE guild_id = ? AND user_id = ?
        ORDER BY id DESC
        LIMIT 5
    """, (guild_id, user_id))

    rows = cur.fetchall()
    conn.close()

    if not rows:
        await interaction.response.send_message(f"❌ {유저.mention}님의 기부 기록이 없어요.")
        return

    desc = f"📊 누적 기부: **{total}회**\n\n최근 인증 기록\n"

    first_valid_image = None

    for amount, image_url, created_at in rows:
        if image_url.startswith("http"):
            desc += f"- {created_at} / {amount}회 / [스크린샷]({image_url})\n"
            if first_valid_image is None:
                first_valid_image = image_url
        else:
            desc += f"- {created_at} / {amount:+}회 / 관리자 수동 수정\n"

    embed = discord.Embed(
        title=f"💰 {유저.display_name} 기부 조회",
        description=desc,
        color=0xF1C40F
    )

    if first_valid_image:
        embed.set_image(url=first_valid_image)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="기부수정", description="관리자가 유저의 기부 횟수를 수동으로 추가/차감합니다.", guild=GUILD_ID)
async def donation_edit(
    interaction: discord.Interaction,
    유저: discord.Member,
    횟수: int
):
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

    cur.execute("""
        SELECT SUM(amount)
        FROM donations
        WHERE guild_id = ? AND user_id = ?
    """, (guild_id, user_id))

    total = cur.fetchone()[0] or 0

    conn.commit()
    conn.close()

    await interaction.response.send_message(
        f"✅ {유저.mention}님의 기부 기록을 `{횟수:+}회` 수정했어요.\n"
        f"현재 누적: **{total}회**"
    )


TOKEN = os.getenv("DISCORD_TOKEN", "여기에_봇_토큰_입력")
bot.run(TOKEN)
