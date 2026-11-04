# YouCube Server

Fork of [CC-YouCube/server](https://github.com/CC-YouCube/server). Upstream was archived in May 2025. This fork keeps the official YouCube ComputerCraft client working against current YouTube.

The websocket protocol is unchanged. `api.version` is still `0.0.0-poc.1.0.0`, and the actions are still `handshake`, `request_media`, `get_chunk`, and `get_vid`. With `YOUCUBE_TOKEN` unset, an unmodified official client connects exactly as before.

## What changed compared with upstream

- Python 3.12+, Sanic 25.12, yt-dlp 2026.10, yt-dlp-ejs, Spotipy 2.26, orjson, and uvloop.
- The Docker image installs the newest yt-dlp at build time. On container start it updates yt-dlp and yt-dlp-ejs again when `YTDLP_AUTO_UPDATE=true` (the default).
- Optional Netscape cookies, YouTube player client, PO token, extractor args, and extra yt-dlp arguments. Sign-in and bot-check failures are logged with those variable names.
- Node.js 22 is in the image so yt-dlp can solve YouTube's JavaScript challenges. A local install uses Deno or Node when one is on `PATH`.
- Optional shared secret (`YOUCUBE_TOKEN`). Open by default.
- `GET /health` for probes. It does not require the token.
- Websocket JSON is always a text frame, including when orjson is installed.
- Published image: `ghcr.io/6ma-606/cc-youcube`. GitHub Actions builds it on every push to `main` and every Monday.

## Requirements

- Python 3.12+
- FFmpeg 5.1+ with the DFPWM encoder
- [sanjuuni](https://github.com/MCJack123/sanjuuni) for video
- Node.js 20+ or Deno, so yt-dlp can solve YouTube challenges
- Packages in `src/requirements.txt`

```shell
pip install -r src/requirements.txt
```

## Run without Docker

```bash
python src/youcube/youcube.py
```

The process listens on `127.0.0.1:5000` unless `HOST` and `PORT` are set.

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | Bind address. The Docker image sets `0.0.0.0`. |
| `PORT` | `5000` | Listen port. |
| `YOUCUBE_TOKEN` | unset | Shared secret. Unset or blank means the server is open. |
| `YTDLP_AUTO_UPDATE` | `true` in Docker | On container start, `pip install -U yt-dlp yt-dlp-ejs`. Set to `false` to keep the baked-in copy. |
| `YTDLP_COOKIES` | unset | Path to a Netscape `cookies.txt` from a signed-in browser session. |
| `YTDLP_PLAYER_CLIENT` | unset | Comma-separated YouTube player clients, for example `default,mweb`. |
| `YTDLP_PO_TOKEN` | unset | One yt-dlp PO token, in `client.context+TOKEN` form (for example `mweb.gvs+...`). |
| `YTDLP_EXTRACTOR_ARGS` | unset | Raw extractor args, for example `youtube:player_client=default,mweb;po_token=mweb.gvs+TOKEN`. |
| `YTDLP_EXTRA_ARGS` | unset | Extra yt-dlp CLI arguments, for example `--retries 10`. |
| `YTDLP_JS_RUNTIMES` | first of deno, node, bun, quickjs on `PATH` | Set to `node` or `deno:/usr/bin/deno`. `none` disables JavaScript runtimes. |
| `YTDLP_AUDIO_FORMAT` | `worstaudio/worst` | yt-dlp format selector for audio requests. |
| `YTDLP_VIDEO_FORMAT` | `worst[ext=mp4]/worst` | yt-dlp format selector for video requests. |
| `FFMPEG_PATH` | `ffmpeg` | FFmpeg executable. |
| `SANJUUNI_PATH` | `sanjuuni` | sanjuuni executable. |
| `NO_COLOR` | unset | Any non-empty value disables colored logs. |
| `LOGLEVEL` | `DEBUG` | Python log level. |
| `DISABLE_OPENCL` | unset | Pass `--disable-opencl` to sanjuuni. |
| `NO_FAST` | unset | Any non-empty value runs Sanic in a single process. |
| `SPOTIPY_CLIENT_ID` | unset | Spotify application client id. Both Spotify variables are required. |
| `SPOTIPY_CLIENT_SECRET` | unset | Spotify application secret. |
| `DATA_CACHE_CLEANUP_INTERVAL` | `300` | Seconds between cache sweeps. `0` disables the sweeper. |
| `DATA_CACHE_CLEANUP_AFTER` | `3600` | Drop cached media that has not been read for this many seconds. |

Sanic's own variables are also honored. See the [Sanic configuration guide](https://sanic.dev/en/guide/running/configuration.html#builtin-values).

`YTDLP_COOKIES`, `YTDLP_PO_TOKEN`, and `YTDLP_EXTRA_ARGS` are not logged. If YouTube answers with a sign-in or bot check, the log says so and names the variables above.

## Docker and Cloudflare Tunnel

```bash
docker compose up -d --build
```

The compose file publishes port 5000 and stores converted media in the `youcube-data` volume. The image's health check calls `GET /health`.

To publish the server from a home machine without opening a port:

1. Create a tunnel in the Cloudflare dashboard (Zero Trust, Networks, Tunnels) and copy the token.
2. In that tunnel, add a public hostname whose service URL is `http://youcube:5000`. WebSocket upgrade is proxied as a normal HTTP service. No extra WebSocket setting is required.
3. Uncomment the `cloudflared` service in `docker-compose.yml`.
4. Export `CLOUDFLARE_TUNNEL_TOKEN` and start the stack again. You can remove the `ports:` mapping on `youcube` when the tunnel is the only way in.

Pull a prebuilt image instead of building locally:

```bash
docker pull ghcr.io/6ma-606/cc-youcube:latest
```

The package is private until it is made public in GitHub's package settings. A weekly Actions rebuild keeps yt-dlp current even when the server code does not change.

## Point the ComputerCraft client at this server

The official client has a configurable server URL. Set that URL to this server. Do not change the client when the server is open.

- LAN or local Docker: `ws://YOUR_HOST:5000`
- Cloudflare Tunnel, or any TLS reverse proxy: `wss://your.hostname`

`YOUR_HOST` is the computer running Docker, as seen from the Minecraft machine.

### Shared secret

Leave `YOUCUBE_TOKEN` unset if anyone who can reach the port may use the server.

When it is set, put the same value in the client URL query string. The stock client does not have a separate token field; it uses whatever websocket URL you configure.

- `ws://YOUR_HOST:5000/?token=YOUR_TOKEN`
- `wss://your.hostname/?token=YOUR_TOKEN`

The query name is `token`. An `Authorization: Bearer YOUR_TOKEN` header is also accepted, which helps non-ComputerCraft clients. The token is compared in constant time and redacted from logs.

A missing or wrong token closes the websocket after one text message: `{"action":"error","message":"Unauthorized"}`. `GET /health` stays open so probes keep working. The unfinished HTTP media routes require the token when auth is on.

## Cookies and PO tokens

YouTube often refuses datacenter and home IPs until the request looks like a logged-in browser.

1. In a browser where you are signed in to YouTube, export cookies in Netscape format (the "cookies.txt" format).
2. Mount that file into the container and set `YTDLP_COOKIES` to the path inside the container. The compose file has a commented example.
3. If yt-dlp asks for a PO token or a different player client, set `YTDLP_PO_TOKEN` and `YTDLP_PLAYER_CLIENT`, or pass the same values through `YTDLP_EXTRACTOR_ARGS`.

Treat the cookies file like a password. It is a live session for that Google account.

## Development

```bash
pip install -r src/requirements.txt pytest
make test
make pylint
```

`tests/test_dfpwm.py` converts a generated tone through the same FFmpeg arguments the server uses. `tests/test_server_smoke.py` starts the server and checks the handshake, a DFPWM chunk, and token rejection.

[sanjuuni]: https://github.com/MCJack123/sanjuuni
