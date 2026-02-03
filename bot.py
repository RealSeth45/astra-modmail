import os
import discord

# Enable intents (you can expand these later if needed)
intents = discord.Intents.default()
intents.message_content = True  # Needed if you want to read messages

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print("--------------------------------------------------")
    print(f"Bot is online as: {client.user} (ID: {client.user.id})")
    print("--------------------------------------------------")

@client.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == client.user:
        return

    # Simple test command
    if message.content.lower() == "!ping":
        await message.channel.send("Pong!")

# Load token from Railway environment variable
TOKEN = os.getenv("TOKEN")

if TOKEN is None:
    raise RuntimeError("ERROR: TOKEN environment variable not found in Railway.")

client.run(TOKEN)



