import discord
from discord.ext import commands
import asyncio
import os
import struct
import math


intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

active_timers = {}  # guild_id -> {"voice_client": vc, "task": task}


def generate_beep_wav():
    sample_rate = 44100
    duration = 1.0
    frequency = 880
    volume = 0.5
    num_samples = int(sample_rate * duration)
    wav_data = bytearray()
    data_size = num_samples * 2

    wav_data += b'RIFF'
    wav_data += struct.pack('<I', 36 + data_size)
    wav_data += b'WAVE'
    wav_data += b'fmt '
    wav_data += struct.pack('<I', 16)
    wav_data += struct.pack('<H', 1)
    wav_data += struct.pack('<H', 1)
    wav_data += struct.pack('<I', sample_rate)
    wav_data += struct.pack('<I', sample_rate * 2)
    wav_data += struct.pack('<H', 2)
    wav_data += struct.pack('<H', 16)
    wav_data += b'data'
    wav_data += struct.pack('<I', data_size)

    for i in range(num_samples):
        t = i / sample_rate
        fade = 1.0
        if t < 0.05:
            fade = t / 0.05
        elif t > 0.8:
            fade = (1.0 - t) / 0.2
        sample = int(volume * fade * 32767 * math.sin(2 * math.pi * frequency * t))
        wav_data += struct.pack('<h', sample)

    with open("beep.wav", "wb") as f:
        f.write(wav_data)


@bot.event
async def on_ready():
    print(f"✅ 봇 로그인 완료: {bot.user}")
    if not os.path.exists("beep.wav"):
        generate_beep_wav()


class TimerView(discord.ui.View):
    def __init__(self, guild_id, voice_client, ctx):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.voice_client = voice_client
        self.ctx = ctx

    @discord.ui.button(label="▶ 타이머 시작", style=discord.ButtonStyle.success)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = self.guild_id

        if guild_id in active_timers and active_timers[guild_id].get("task"):
            await interaction.response.send_message("⚠️ 이미 타이머가 실행 중이에요!", ephemeral=True)
            return

        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("✅ 타이머 시작! **80초 후** 첫 알람, 이후 **90초마다** 알람을 울릴게요. 🔔")

        task = bot.loop.create_task(timer_loop(self.ctx, guild_id, self.voice_client))
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


async def timer_loop(ctx, guild_id, voice_client):
    try:
        await asyncio.sleep(80)
        if guild_id not in active_timers or not voice_client.is_connected():
            return
        play_beep(voice_client)
        await ctx.send("🔔 **첫 번째 알람!** (80초 경과)")

        count = 1
        while guild_id in active_timers and voice_client.is_connected():
            await asyncio.sleep(90)
            if guild_id not in active_timers or not voice_client.is_connected():
                break
            count += 1
            play_beep(voice_client)
            await ctx.send(f"🔔 **{count}번째 알람!** (이후 90초 간격)")

    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"타이머 오류: {e}")


def play_beep(voice_client):
    if not voice_client.is_playing():
        source = discord.FFmpegPCMAudio("beep.wav")
        voice_client.play(source)


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


@bot.command(name="카쿰단유타이머")
async def kakum_timer(ctx):
    if not ctx.author.voice:
        await ctx.send("❌ 먼저 음성 채널에 들어가 주세요!")
        return

    guild_id = ctx.guild.id

    if guild_id in active_timers:
        await ctx.send("⚠️ 이미 봇이 음성 채널에 있어요. 먼저 종료 버튼을 눌러주세요.")
        return

    channel = ctx.author.voice.channel
    voice_client = await channel.connect()
    active_timers[guild_id] = {"voice_client": voice_client, "task": None}

    await ctx.send(f"🔊 **{channel.name}** 에 입장했어요!")

    view = TimerView(guild_id, voice_client, ctx)
    await ctx.send(
        "⏱ 준비됐으면 아래 버튼을 눌러 타이머를 시작하세요!\n"
        "> 첫 알람: **80초 후**\n"
        "> 이후: **90초마다**",
        view=view
    )


TOKEN = os.getenv("DISCORD_TOKEN", "여기에_봇_토큰_입력")
bot.run(TOKEN)
