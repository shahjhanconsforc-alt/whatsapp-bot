#!/bin/sh
set -eu

APP_CMD="python -c \"import main; main.app.run(host='0.0.0.0', port=5000, debug=False)\""
DISPLAY_MODE="${PLAYWRIGHT_DISPLAY_MODE:-xvfb}"
XVFB_SCREEN="${XVFB_SCREEN:-1440x900x24}"
XVFB_DISPLAY="${XVFB_DISPLAY:-:99}"
VNC_ENABLED="${VNC_ENABLED:-true}"
VNC_PORT="${VNC_PORT:-5900}"
VNC_PASSWORD="${VNC_PASSWORD:-}"

# ---------------------------------------------------------------------------
# host mode: use the VM's own X display (Linux desktop VM). Windows appear on
# the VM desktop itself.
# ---------------------------------------------------------------------------
if [ "$DISPLAY_MODE" = "host" ]; then
    if [ -z "${DISPLAY:-}" ]; then
        echo "PLAYWRIGHT_DISPLAY_MODE=host requires DISPLAY to be set." >&2
        exit 1
    fi
    echo "Display mode: host (DISPLAY=$DISPLAY). Chromium windows open on the VM desktop."
    exec sh -lc "$APP_CMD"
fi

# ---------------------------------------------------------------------------
# xvfb mode (default): Chromium runs HEADED on a virtual X display inside the
# container, and x11vnc shares that display so the automation windows can be
# watched live from any VNC viewer (port $VNC_PORT).
# ---------------------------------------------------------------------------
echo "Display mode: xvfb (virtual display $XVFB_DISPLAY, screen $XVFB_SCREEN)."
Xvfb "$XVFB_DISPLAY" -screen 0 "$XVFB_SCREEN" -nolisten tcp -ac >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!
export DISPLAY="$XVFB_DISPLAY"

# Wait for the X server socket before starting anything that needs it.
SOCKET="/tmp/.X11-unix/X${XVFB_DISPLAY#:}"
i=0
while [ ! -S "$SOCKET" ] && [ "$i" -lt 100 ]; do
    i=$((i + 1))
    sleep 0.1
done
if [ ! -S "$SOCKET" ]; then
    echo "Xvfb did not start (see /tmp/xvfb.log)." >&2
    cat /tmp/xvfb.log >&2 || true
    exit 1
fi

if [ "$VNC_ENABLED" = "true" ]; then
    if [ -n "$VNC_PASSWORD" ]; then
        mkdir -p /root/.vnc
        x11vnc -storepasswd "$VNC_PASSWORD" /root/.vnc/passwd >/dev/null 2>&1
        VNC_AUTH="-rfbauth /root/.vnc/passwd"
    else
        VNC_AUTH="-nopw"
        echo "WARNING: VNC has no password (set VNC_PASSWORD in .env). Do not expose port $VNC_PORT publicly." >&2
    fi
    # -forever: keep serving after a viewer disconnects; -shared: several viewers at once.
    if x11vnc -display "$DISPLAY" -forever -shared -rfbport "$VNC_PORT" $VNC_AUTH \
        -noxdamage -bg -o /tmp/x11vnc.log >/dev/null 2>&1; then
        echo "VNC: automation windows viewable at <host-ip>:$VNC_PORT (display $DISPLAY)."
    else
        echo "WARNING: x11vnc failed to start; see /tmp/x11vnc.log." >&2
    fi
else
    echo "VNC disabled (VNC_ENABLED=$VNC_ENABLED)."
fi

cleanup() {
    kill "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sh -lc "$APP_CMD"
