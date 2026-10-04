# Cloudflare IP List Automation Telegram Bot

A tiny Telegram bot that automatically keeps a Cloudflare IP list updated with my home IP, with options to add and delete custom IPs. Runs on a Raspberry Pi Zero 2 W.

I have a number of personal projects and websites using public domains. I use Cloudflare IP Lists with security rules to restrict access to specific IP addresses.

Most of my IPs are static, but my home IPv6 address keeps changing. Of course, I could turn off IPv6 on the router, but I need IPv6 for other purposes. Updating the Cloudflare list manually every time was annoying.

This bot runs on a Raspberry Pi in my home network and checks the current IPv6 address. If the home IPv6 `/64` changes, it automatically updates the Cloudflare IP list.

That was the primary purpose of the project. Later decided to add an option for manually adding and deleting IPs as well.

## In short

- Checks the home IPv6 address periodically.
- Updates the Cloudflare IP list when the home `/64` changes.
- Keeps the home IP entry separate from other entries.
- Allows adding custom IPv4/IPv6 addresses or networks.
- Allows deleting custom IPs added by the bot.
- Provides list and status information through Telegram.
- Telegram access is restricted to configured users.
- Runs continuously on a Raspberry Pi.

The Cloudflare IP list can then be used in Cloudflare security rules to allow or restrict access to the projects and sites.

## How it works

Basically like in this image. 

<img width="1536" height="1024" alt="image" src="https://github.com/user-attachments/assets/67b63ceb-96f0-458b-a9df-11404c40c94d" />

## Requirements

- Raspberry Pi or another always-on Linux system
- Python 3
- Cloudflare account
- Cloudflare API token with permission to edit the required IP List
- Telegram bot. Create one from Botfather and note down the token.
- A Cloudflare IP List
- IPv6 connectivity on the machine running the bot

## Configuration

Create a `config.env` file:

CF_API_TOKEN="..."
CF_ACCOUNT_ID="..."
CF_LIST_ID="..."

TG_BOT_TOKEN="..."
TG_CHAT_ID="..."

CHECK_INTERVAL=900

ALLOWED_USERS="12345 67890"

HOME_COMMENT="managed-home-ip"
CUSTOM_COMMENT="managed-custom-ip"

Included `config.env.example` file can be renamed to config.env and used as a template. Contains instructions as well. 

## Telegram

The bot supports buttons as well as commands.

Main options:

- Update Home IP
- Add Custom IP
- Delete Custom IP
- List
- Status

Custom IPs are useful when accessing the sites from somewhere other than the home network. They can be added and removed as needed.

## Screenshots

<!-- Add screenshots here -->

### Main menu

<img width="483" height="233" alt="image" src="https://github.com/user-attachments/assets/5eccad17-0a42-4c04-946f-3317050aa574" />

### IP list

<img width="1273" height="1236" alt="image" src="https://github.com/user-attachments/assets/0e6c907b-63d3-4110-8535-0990851a784f" />

### Status

<img width="1760" height="894" alt="image" src="https://github.com/user-attachments/assets/9140f8f5-66b8-4939-bca7-19b2a09a24cd" />

## Running

The bot can be run directly with:

python3 bot.py

For a permanent setup, it can be run as a systemd service on the Raspberry Pi.

## Notes

I'm pretty sure there are like 42 thousand projects that accomplish the same thing, or even do it better. But this is mainly built to solve a very specific problem for me.

It could definitely be extended to handle automatic IPv4 updates as well, but for now it is intentionally kept simple and does not try to be a general-purpose Cloudflare IP management system.

## Security

Keep the device running this bot secure. It is assumed that the `config.env` values, terminal logs, and other sensitive information are not accessible to unauthorized persons.

Also, restrict who can use the bot through BotFather as well as the `ALLOWED_USERS` setting in `config.env`.

Make sure the Cloudflare API token does not have any additional privileges beyond what is required for managing the IP List.
