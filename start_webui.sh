#!/bin/bash
cd "$(dirname "$0")"
# This is a headless server: use the local headless Xorg :0 when it is up.
# Do not trust an inherited DISPLAY such as localhost:11.0 (SSH X forwarding),
# which may not have a local X socket and would make Qt fall back to offscreen.
export DISPLAY=:0
if [ -S "/tmp/.X11-unix/X0" ]; then
  export QT_QPA_PLATFORM=xcb
else
  export QT_QPA_PLATFORM=offscreen
fi
exec uv run python -m app.webui --port 7860

