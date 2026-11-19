#!/bin/bash
# 从素材.nwp 里取一帧生成 256x256 图标
set -e
ASSETS="$1"
OUT="$2"
python3 - "$ASSETS" "$OUT" <<'PY'
import sys
import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf
import zipfile

assets, out = sys.argv[1], sys.argv[2]
src = None
with zipfile.ZipFile(assets + "/素材.nwp") as z:
    for name in ("look/00.png", "laugh/0000.png"):
        try:
            data = z.read(name)
            break
        except KeyError:
            continue
loader = GdkPixbuf.PixbufLoader.new_with_type("png")
loader.write(data)
loader.close()
pix = loader.get_pixbuf()
w, h = pix.get_width(), pix.get_height()
side = max(w, h)
canvas = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, side, side)
canvas.fill(0x00000000)
pix.copy_area(0, 0, w, h, canvas, (side - w) // 2, (side - h) // 2)
icon = canvas.scale_simple(256, 256, GdkPixbuf.InterpType.BILINEAR)
icon.savev(out, "png", [], [])
print("icon ->", out, icon.get_width(), "x", icon.get_height())
PY
