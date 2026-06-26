import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
import struct
import math
import array

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

active_timers = {}


class BeepAudio(discord.AudioSource):
    """FFmpeg 없이 PCM 비프음을 직접 생성하는 AudioSource"""
    def __init__(self, frequency=880, duration=1.0, volume=0.5):
        self.frequency = frequency
        self.volume = volume
        self.sample_rate = 48000  # discord 기본 샘플레이트
        self.channels = 2
        self.total_samples = int(self.sample_rate * duration)
        self.pos = 0

    def read(self):
        # 20ms 분량의 프레임 (960 샘플 * 2채널 * 2바이트)
        frame_size = 960
        if self.pos >= self.total_samples:
            return b''

        frames = []
        for i in range(frame_size):
            idx = self.pos + i
            if idx >= self.total_samples:
                sample = 0
            else:
                t = idx / self.sample_rate
                # 페이드 인/아웃
                fade = 1.0
                fade_samples = int(self.sample_rate * 0.05)
                if idx < fade_samples:
                    fade = idx / fade_samples
                elif idx > self.total_samples - fade_samples:
                    fade = (self.total_samples - idx) / fade_samples
                sample = int(self.volume * fade * 32767 * math.sin(2 * math.pi * self.frequency * t))
                sample = max(-32768, min(32767, sample))
            # stereo (L, R 동일)
            frames.append(struct.pack('<hh', sample, sample))

        self.pos += frame_size
        return b''.join(frames)

    def is_opus(self):
        return False

    def cleanup(self):
        pass


@bot.event
async def on_ready():
    print(f"✅ 봇 로그인 완료: {bot.user}")
    await tree.sync()
    print("✅ 슬래시 커맨드 등록 완료")


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
        await interaction.followup.send("✅ 타이머 시작! **5초 후** 첫 알람, 이후 **5초마다** 알람을 울릴게요. 🔔")

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
        await asyncio.sleep(5)
        if guild_id not in active_timers or not voice_client.is_connected():
            return
        play_beep(voice_client)
        await channel.send("🔔 **첫 번째 알람!** (5초 경과)")

        count = 1
        while guild_id in active_timers and voice_client.is_connected():
            await asyncio.sleep(5)
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
        source = BeepAudio(frequency=880, duration=1.5, volume=0.5)
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


@tree.command(name="카쿰단유타이머", description="음성 채널에 입장하고 타이머를 시작합니다")
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
        "> 첫 알람: **5초 후** (테스트용)\n"
        "> 이후: **5초마다**",
        view=TimerView(guild_id, voice_client, interaction.channel)
    )


TOKEN = os.getenv("DISCORD_TOKEN", "여기에_봇_토큰_입력")
bot.run(TOKEN)
