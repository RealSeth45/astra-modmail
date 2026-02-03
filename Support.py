import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.dm_messages = True

bot = commands.Bot(command_prefix=".", intents=intents)

# Load from Railway environment variables
STAFF_CATEGORY_ID = int(os.getenv("STAFF_CATEGORY_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))

open_tickets = {}       # user_id : channel_id
claimed_tickets = {}    # channel_id : staff_id
staff_notes = {}        # channel_id : [notes]


# ---------------------------------------------------
# TRANSCRIPT GENERATOR
# ---------------------------------------------------
async def generate_transcript(channel: discord.TextChannel):
    messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]

    html = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Transcript - {channel.name}</title>
        <style>
            body {{ font-family: Arial; background: #f5f5f5; padding: 20px; }}
            .msg {{ background: white; padding: 10px; margin-bottom: 10px; border-radius: 5px; }}
            .author {{ font-weight: bold; }}
            .time {{ color: gray; font-size: 12px; }}
        </style>
    </head>
    <body>
        <h2>Ticket Transcript - {channel.name}</h2>
    """

    for msg in messages:
        safe = msg.content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html += f"""
        <div class="msg">
            <div class="author">{msg.author}:</div>
            <div class="content">{safe}</div>
            <div class="time">{msg.created_at}</div>
        </div>
        """

    if channel.id in staff_notes:
        html += "<h3>Staff Notes</h3>"
        for note in staff_notes[channel.id]:
            html += f"<p><b>{note}</b></p>"

    html += "</body></html>"
    return html


# ---------------------------------------------------
# DM HANDLING
# ---------------------------------------------------
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if isinstance(message.channel, discord.DMChannel):
        user = message.author

        # Forward message to ticket channel
        if user.id in open_tickets:
            channel = bot.get_channel(open_tickets[user.id])
            if channel:
                embed = discord.Embed(
                    title="User Message",
                    description=message.content,
                    color=discord.Color.blue()
                )
                avatar = user.avatar.url if user.avatar else None
                embed.set_author(name=str(user), icon_url=avatar)
                await channel.send(embed=embed)
            return

        # Send open ticket button
        embed = discord.Embed(
            title="ModMail Support",
            description="Click the button below to open a ticket.",
            color=discord.Color.green()
        )
        view = OpenTicketView(user)
        await user.send(embed=embed, view=view)

    await bot.process_commands(message)


# ---------------------------------------------------
# MODAL + BUTTONS
# ---------------------------------------------------
class IssueModal(discord.ui.Modal, title="Describe Your Issue"):
    issue = discord.ui.TextInput(
        label="What do you need help with?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )

    def __init__(self, user):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Confirm Ticket",
            description=f"**Your issue:**\n{self.issue.value}\n\nConfirm?",
            color=discord.Color.orange()
        )
        view = ConfirmView(self.user, self.issue.value)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class OpenTicketView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=None)
        self.user = user

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.green)
    async def open_ticket(self, interaction, button):
        await interaction.response.send_modal(IssueModal(self.user))


class ConfirmView(discord.ui.View):
    def __init__(self, user, issue):
        super().__init__(timeout=None)
        self.user = user
        self.issue = issue

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction, button):
        guild = interaction.guild or bot.guilds[0]
        category = guild.get_channel(STAFF_CATEGORY_ID)

        if not category:
            return await interaction.response.edit_message(
                content="Staff category not found.", embed=None, view=None
            )

        channel = await guild.create_text_channel(
            name=f"ticket-{self.user.name}",
            category=category
        )

        open_tickets[self.user.id] = channel.id

        embed = discord.Embed(
            title="New Ticket",
            description=f"**User:** {self.user}\n**Issue:**\n{self.issue}",
            color=discord.Color.green()
        )
        await channel.send(embed=embed)

        await self.user.send("Your ticket has been opened. Staff will reply soon.")
        await interaction.response.edit_message(content="Ticket created.", embed=None, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content="Ticket cancelled.", embed=None, view=None)


# ---------------------------------------------------
# STAFF COMMANDS
# ---------------------------------------------------
@bot.command(name="r")
async def reply(ctx, *, message):
    for user_id, channel_id in open_tickets.items():
        if channel_id == ctx.channel.id:
            user = await bot.fetch_user(user_id)
            break
    else:
        return await ctx.send("This is not a ticket channel.")

    embed = discord.Embed(
        title="Staff Reply",
        description=message,
        color=discord.Color.orange()
    )
    avatar = ctx.author.avatar.url if ctx.author.avatar else None
    embed.set_author(name=str(ctx.author), icon_url=avatar)

    await user.send(embed=embed)
    await ctx.send(embed=embed)


@bot.command()
async def standby(ctx):
    for user_id, channel_id in open_tickets.items():
        if channel_id == ctx.channel.id:
            user = await bot.fetch_user(user_id)
            await user.send("A staff member has seen your ticket and will respond soon.")
            return await ctx.send("Standby message sent.")
    await ctx.send("Not a ticket channel.")


@bot.command()
async def claim(ctx):
    channel = ctx.channel

    if channel.id in claimed_tickets:
        return await ctx.send("Already claimed.")

    claimed_tickets[channel.id] = ctx.author.id

    await channel.set_permissions(ctx.guild.default_role, read_messages=False)
    await channel.set_permissions(ctx.author, read_messages=True, send_messages=True)

    await ctx.send(f"Ticket claimed by {ctx.author}.")

    for user_id, channel_id in open_tickets.items():
        if channel_id == channel.id:
            user = await bot.fetch_user(user_id)
            break
    else:
        return

    greet = discord.Embed(
        title="Support Ticket Update",
        description=(
            f"I'm **{ctx.author}** and I will be helping you today.\n\n"
            "Some issues may take time to resolve. Thank you for your patience."
        ),
        color=discord.Color.gold()
    )
    await user.send(embed=greet)


@bot.command()
async def unclaim(ctx):
    if ctx.channel.id not in claimed_tickets:
        return await ctx.send("Not claimed.")
    del claimed_tickets[ctx.channel.id]
    await ctx.send("Ticket unclaimed.")


@bot.command()
async def transfer(ctx, member: discord.Member):
    if ctx.channel.id not in claimed_tickets:
        return await ctx.send("Not claimed.")

    claimed_tickets[ctx.channel.id] = member.id
    await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
    await ctx.send(f"Ticket transferred to {member}.")


@bot.command()
async def note(ctx, *, message):
    channel = ctx.channel

    if channel.id not in open_tickets.values():
        return await ctx.send("Not a ticket channel.")

    staff_notes.setdefault(channel.id, []).append(f"{ctx.author}: {message}")

    embed = discord.Embed(
        title="Staff Note Added",
        description=message,
        color=discord.Color.dark_gray()
    )
    embed.set_footer(text="Private note (not sent to user).")
    await ctx.send(embed=embed)


# ---------------------------------------------------
# CLOSE TICKET
# ---------------------------------------------------
@bot.command()
async def close(ctx):
    channel = ctx.channel

    for user_id, channel_id in open_tickets.items():
        if channel_id == channel.id:
            user = await bot.fetch_user(user_id)
            break
    else:
        return await ctx.send("Not a ticket channel.")

    transcript_html = await generate_transcript(channel)
    transcript_file = discord.File(
        fp=bytes(transcript_html, "utf-8"),
        filename=f"{channel.name}-transcript.html"
    )

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(
            content=f"Transcript for **{channel.name}**",
            file=transcript_file
        )

    try:
        await user.send("Your ticket has been closed.")
    except:
        pass

    del open_tickets[user_id]
    await ctx.send("Closing ticket...")
    await channel.delete()


# ---------------------------------------------------
# CHANNEL DELETE HANDLER
# ---------------------------------------------------
@bot.event
async def on_guild_channel_delete(channel):
    for user_id, channel_id in list(open_tickets.items()):
        if channel_id == channel.id:
            user = await bot.fetch_user(user_id)
            try:
                await user.send("Your support ticket has been closed.")
            except:
                pass
            del open_tickets[user_id]
            break


# ---------------------------------------------------
# RUN BOT
# ---------------------------------------------------
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN not set in Railway environment variables.")

bot.run(TOKEN)
