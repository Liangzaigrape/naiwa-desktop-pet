#!/bin/bash
# 跑 UI 逻辑自测
set -u
OUT=/tmp/naiwa-ui
mkdir -p "$OUT"
pkill -f "Xvfb :98" 2>/dev/null; sleep 0.5
Xvfb :98 -screen 0 1280x800x24 -nolisten tcp >"$OUT/xvfb.log" 2>&1 &
XV=$!
sleep 1.2
export DISPLAY=:98 GDK_BACKEND=x11
unset WAYLAND_DISPLAY
export NAIWA_PET_DATA=/mnt/c/Users/LiangzaiGrape/Documents/deepseek-harness/default-workspace/naiwa/deps/assets
export XDG_CONFIG_HOME="$OUT/config" XDG_DATA_HOME="$OUT/data"
rm -rf "$OUT/config" "$OUT/data"
python3 /mnt/c/Users/LiangzaiGrape/Documents/deepseek-harness/default-workspace/naiwa/linux/tools/ui_selftest.py
RC=$?
kill $XV 2>/dev/null
echo "--- settings after test ---"
cat "$OUT/config/naiwa-desktop-pet/settings.ini" 2>/dev/null
echo "--- trash dir ---"
ls -l "$HOME/.local/share/Trash/files" 2>/dev/null | tail -3
echo "RC=$RC"
