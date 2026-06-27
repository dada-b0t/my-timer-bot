import discord
from discord.ext import commands
import asyncio
import os
import sqlite3
from datetime import datetime

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

GUILD_ID = discord.Object(id=1506990201204117565)

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



@bot.event
async def on_ready():
    print(f"✅ 봇 로그인 완료: {bot.user}")
    init_donation_db()
    # 글로벌 + 서버 커맨드 전체 초기화 후 재등록
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync()
    bot.tree.clear_commands(guild=GUILD_ID)
    await bot.tree.sync(guild=GUILD_ID)
    bot.tree.copy_global_to(guild=GUILD_ID)
    await bot.tree.sync(guild=GUILD_ID)
    print("✅ 슬래시 커맨드 서버 즉시 등록 완료")


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
    cur.execute("SELECT id, username, amount, created_at FROM donations WHERE id = ? AND guild_id = ?", (기록id, guild_id))
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
    cur.execute("SELECT user_id, SUM(amount) as total FROM donations WHERE guild_id = ? GROUP BY user_id", (guild_id,))
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
    embed = discord.Embed(title=f"📋 전체 기부 현황 (총 {len(members)}명)", description=text, color=0xF1C40F)
    embed.set_footer(text=f"기부자 {len(done)}명 | 미기부 {len(not_done)}명")
    await interaction.followup.send(embed=embed)


# ─────────────────────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN", "여기에_봇_토큰_입력")
bot.run(TOKEN)
