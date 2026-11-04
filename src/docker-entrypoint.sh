#!/bin/sh
# Container entrypoint. Optionally refreshes yt-dlp before the server starts.
set -u

auto_update="${YTDLP_AUTO_UPDATE:-true}"
case "$(printf '%s' "$auto_update" | tr '[:upper:]' '[:lower:]')" in
true | yes | on | 1)
    echo "[youcube] Updating yt-dlp and yt-dlp-ejs (YTDLP_AUTO_UPDATE=true)"
    if ! python -m pip install --no-cache-dir -U yt-dlp yt-dlp-ejs; then
        echo "[youcube] yt-dlp update failed; starting with the version baked into the image"
    fi
    ;;
*)
    echo "[youcube] Skipping yt-dlp self-update (YTDLP_AUTO_UPDATE=${auto_update})"
    ;;
esac

exec python youcube.py
