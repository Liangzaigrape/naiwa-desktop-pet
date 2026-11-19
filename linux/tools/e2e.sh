#!/bin/bash
# 端到端测试：Xvfb + picom + feh 壁纸，真实 GTK 窗口截图 + 交互
# 用法：e2e.sh <素材目录> <输出目录>
set -u
DATA="${1:-/tmp/naiwa-smoke/assets}"
OUT="${2:-/tmp/naiwa-e2e}"
APP=/mnt/c/Users/LiangzaiGrape/Documents/deepseek-harness/default-workspace/naiwa/linux/naiwa-pet
mkdir -p "$OUT"
pkill -f "Xvfb :99" 2>/dev/null; pkill -f picom 2>/dev/null; pkill -f "python3 -m naiwa" 2>/dev/null
sleep 0.6

Xvfb :99 -screen 0 1280x800x24 -nolisten tcp >"$OUT/xvfb.log" 2>&1 &
XVFB_PID=$!
sleep 1.5
export DISPLAY=:99 GDK_BACKEND=x11
unset WAYLAND_DISPLAY
convert -size 1280x800 gradient:'#204060-#7fb2e5' "$OUT/bg.png" 2>/dev/null
feh --bg-fill "$OUT/bg.png" >/dev/null 2>&1
picom --config /dev/null --backend xrender --no-fading-openclose >"$OUT/picom.log" 2>&1 &
COMP_PID=$!
sleep 1

export NAIWA_PET_DATA="$DATA"
export XDG_CONFIG_HOME="$OUT/config"
export XDG_DATA_HOME="$OUT/data"
export PYTHONPATH="$APP"
rm -rf "$OUT/config" "$OUT/data"

python3 -m naiwa >"$OUT/app.log" 2>&1 &
APP_PID=$!
sleep 5

if ! kill -0 $APP_PID 2>/dev/null; then
  echo "APP DIED"; cat "$OUT/app.log"; kill $COMP_PID $XVFB_PID 2>/dev/null; exit 1
fi

WID=$(xdotool search --name "^naiwa-pet$" 2>/dev/null | head -1)
echo "pid=$APP_PID wid=${WID:-none}"
if [ -n "${WID:-}" ]; then
  xdotool getwindowgeometry "$WID"
  xwininfo -id "$WID" | grep -E "Depth|Width|Height|Absolute"
fi
import -window root "$OUT/root1.png" 2>/dev/null
[ -n "${WID:-}" ] && import -window "$WID" "$OUT/win1.png" 2>/dev/null

GEO=$(xdotool getwindowgeometry --shell "${WID:-0}" 2>/dev/null)
eval "$GEO"
if [ -n "${WIDTH:-}" ]; then
  CX=$((X + WIDTH / 2)); CY=$((Y + HEIGHT * 75 / 100))
  echo "click belly at $CX,$CY"
  xdotool mousemove $CX $CY; sleep 0.5
  import -window root "$OUT/root_hover.png" 2>/dev/null
  xdotool click 1; sleep 0.12; xdotool click 1
  sleep 0.8
  import -window root "$OUT/root_laugh.png" 2>/dev/null
  # 拖到左侧并抛起
  xdotool mousemove $CX $CY mousedown 1
  for i in 1 2 3 4 5 6 7 8; do xdotool mousemove_relative -- -20 6; sleep 0.05; done
  xdotool mouseup 1
  sleep 1.0
  import -window root "$OUT/root_drag.png" 2>/dev/null
  # 右键菜单
  GEO=$(xdotool getwindowgeometry --shell "$WID" 2>/dev/null)
  eval "$GEO"
  CX=$((X + WIDTH / 2)); CY=$((Y + HEIGHT * 60 / 100))
  echo "right click at $CX,$CY"
  xdotool mousemove $CX $CY; sleep 0.3
  xdotool click 3
  sleep 1.0
  echo "windows now: $(xwininfo -root -children 2>/dev/null | grep -c '0x')"
  import -window root "$OUT/root_menu.png" 2>/dev/null
  xdotool key Escape 2>/dev/null
  sleep 0.3
fi

echo "--- app log (tail) ---"
tail -25 "$OUT/app.log"
echo "--- settings ---"
cat "$OUT/config/naiwa-desktop-pet/settings.ini" 2>/dev/null
kill $APP_PID 2>/dev/null; sleep 0.8
kill $COMP_PID $XVFB_PID 2>/dev/null
echo "E2E DONE"
