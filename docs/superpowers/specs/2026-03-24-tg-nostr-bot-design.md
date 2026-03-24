# tg-nostr-bot — Design Spec

**Date:** 2026-03-24
**Status:** Draft

## Overview

A Telegram-Nostr bridge. Each CLI instance bridges a Telegram Bot to the Nostr network. The Gateway acts as a WebSocket message router and relay pool manager. Multiple CLI instances can connect to a single Gateway, each with an independent npub.

If UDP hole punching fails, the program exits cleanly.

## Architecture

```
[Telegram Bot] → POST /webhook → [CLI (FastAPI)]
                                          ↓ WebSocket
                                    [Gateway (WS Server)]
                                          ↓ Relay WebSocket
                                   [Nostr Relay Pool]
```

**Message Flow:**

- **TG → Nostr**: Telegram → CLI Webhook → NIP-17 encrypt → WebSocket → Gateway → Relay
- **Nostr → TG**: Relay → Gateway → decrypt NIP-17 → route by to_npub → WebSocket → CLI → Telegram Bot

## Components

### Gateway

**Responsibility:** WebSocket server + Nostr relay pool manager + key registry

- Manages `all_key.json` with all registered npub/nsec pairs
- Accepts WebSocket connections from multiple CLI instances
- Subscribes to Nostr relays (kind:1059) for each registered npub on demand
- Routes messages: decrypts incoming NIP-17 DM, extracts `to_npub`, forwards to the corresponding CLI
- Forwards outgoing messages from CLI to relays

**CLI:**
- FastAPI webhook server (receives Telegram updates)
- WebSocket client (connects to Gateway)
- Each CLI has one independent npub
- Startup: reads `key.json` → if missing, requests from Gateway → saves locally
- Encrypts outgoing messages with NIP-17 Gift Wrap, sends to Gateway
- Decrypts incoming NIP-17 Gift Wrap messages, forwards to Telegram

## Project Structure

```
tg-nostr-bot/
├── gateway/
│   ├── __init__.py
│   ├── main.py              # Entry: python -m gateway.main
│   ├── config.py            # .env loader
│   ├── key_manager.py        # NIP-44 / NIP-17 (reused from py_gateway)
│   ├── relay_client.py       # Relay pool (reused from py_gateway)
│   ├── websocket_server.py   # WS server, CLI registration + routing
│   ├── all_key.json          # All npub/nsec managed by gateway
│   ├── .env.example
│   └── requirements.txt
└── cli/
    ├── __init__.py
    ├── main.py               # Entry: python -m cli.main
    ├── config.py             # .env loader
    ├── app.py                # FastAPI Webhook (Telegram)
    ├── ws_client.py          # WebSocket client to Gateway
    ├── nip17_client.py       # NIP-17 encrypt/decrypt wrappers
    ├── key.json              # Local key (persistent across restarts)
    ├── .env.example
    └── requirements.txt
```

## Key Flow

### CLI Startup

1. Load `.env` (BOT_TOKEN, GATEWAY_WS_URL, MSG_TO, PORT, ALLOWED_USERS)
2. Check local `key.json`:
   - Exists → load npub/nsec
   - Missing → connect to Gateway WS, send `{"type":"register_request"}`, receive `{"type":"register_done","npub":"...","nsec":"..."}`, save to `key.json`
3. Connect to Gateway WS, send `{"type":"register","npub":"<npub>"}`
4. Gateway subscribes relay for this npub (kind:1059)
5. Start FastAPI webhook server

### Gateway Startup

1. Load `.env` (GATEWAY_HOST, GATEWAY_PORT, NOSTR_RELAYS)
2. Start WebSocket server on GATEWAY_PORT
3. Connect to Nostr relays
4. Load `all_key.json` (create if missing)
5. Wait for CLI registrations

### Outgoing Message (TG → Nostr)

```
Telegram webhook → CLI app.py → nip17_client.wrap(plaintext, my_nsec, MSG_TO_npub)
  → ws_client → Gateway → relay_client.publish(gift_wrap_event)
```

### Incoming Message (Nostr → TG)

```
relay_client receives kind:1059 → key_manager.nip17_unwrap(seckey, event)
  → extract to_npub → websocket_server route to CLI by npub
  → ws_client receives → nip17_client.unwrap() → app.py → tg_api.sendMessage()
```

## WebSocket Protocol

### CLI → Gateway

```json
// Registration
{"type": "register_request"}
{"type": "register", "npub": "npub1..."}

// Outgoing DM
{"type": "dm", "to_npub": "npub1...", "content": "hello"}
```

### Gateway → CLI

```json
// Registration confirmation (only on register_request)
{"type": "register_done", "npub": "npub1...", "nsec": "nsec1..."}

// Incoming DM (decrypted)
{"type": "dm", "from_npub": "npub1...", "to_npub": "npub1...", "content": "hello"}
```

## Configuration

### gateway/.env.example

```
GATEWAY_HOST=127.0.0.1
GATEWAY_PORT=7899
NOSTR_RELAYS=wss://relay.damus.io,wss://relay.0xchat.com,wss://nostr.oxtr.dev,wss://relay.primal.net
LOG_LEVEL=INFO
```

> If NOSTR_RELAYS is empty/not set, fall back to default relays above.

### cli/.env.example

```
BOT_TOKEN=your_telegram_bot_token
WEBHOOK_URL=https://your-domain.com/bot
ALLOWED_USERS=123456789,987654321
PORT=8000
GATEWAY_WS_URL=ws://127.0.0.1:7899
MSG_TO=npub1...    # default destination npub for incoming TG messages
LOG_LEVEL=INFO
```

## Reuse from Existing Code

| Component | Source | Notes |
|-----------|--------|-------|
| NIP-44 encrypt/decrypt | py_gateway/key_manager.py | ChaCha20-Poly1305 |
| NIP-17 Gift Wrap | py_gateway/key_manager.py | nip17_wrap_message, nip17_unwrap |
| Relay pool | py_gateway/relay_client.py | Connect, subscribe, publish |
| WS Server | py_gateway/websocket_server.py | Adapt for CLI registration |
| FastAPI Webhook | tg_bot/main.py | Adapt for CLI app |
| .env loader | Both | python-dotenv |

## Dependencies

```
# gateway
aiohttp
websockets
python-dotenv
secp256k1
bech32
cryptography

# cli
aiohttp
websockets
fastapi
uvicorn
httpx
python-dotenv
pydantic
secp256k1
bech32
cryptography
```

## Error Handling

- Gateway: relay connection failure → warning log, continue without relay
- CLI: WS connection failure → retry 3 times, then exit(1)
- Telegram API failure → error log, continue
- NIP-17 unwrap failure → skip message, log warning
- Missing key.json on startup → request from Gateway, retry once on failure
