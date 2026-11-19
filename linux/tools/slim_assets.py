#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""".nwp 素材瘦身：缩小分辨率 + RGB 减色（保留 8bit alpha），显著减小安装包体积。

原版素材是 2 倍分辨率（426×618）的 RGBA PNG，一张 100~140 KB。
桌宠 80% 缩放下实际只显示 170×247，2 倍素材主要为了旋转/缩放时的抗锯齿。
这里按 `--scale` 降采样、按 `--colors` 把 RGB 减色（alpha 保持 8 位，所以边缘依然柔和），
metadata.json 里的 width/height 保持原值，渲染层不用改任何代码。

用法：
    slim_assets.py <目录> [--scale 0.5] [--colors 192] [--keep dance.nwp]
"""
import argparse
import io
import json
import os
import sys
import zipfile

from PIL import Image


def slim_pack(path, scale, colors, backup=True):
    tmp = path + ".slim"
    total_in = total_out = 0
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            total_in += len(data)
            if not info.filename.lower().endswith(".png"):
                zout.writestr(info.filename, data)
                total_out += len(data)
                continue
            img = Image.open(io.BytesIO(data)).convert("RGBA")
            if scale != 1.0:
                w = max(1, int(round(img.width * scale)))
                h = max(1, int(round(img.height * scale)))
                img = img.resize((w, h), Image.LANCZOS)
            if colors:
                alpha = img.getchannel("A")
                rgb = img.convert("RGB").quantize(colors=colors, method=Image.MEDIANCUT,
                                                  dither=Image.FLOYDSTEINBERG).convert("RGB")
                img = rgb.convert("RGBA")
                img.putalpha(alpha)
            buf = io.BytesIO()
            img.save(buf, "PNG", optimize=True)
            blob = buf.getvalue()
            total_out += len(blob)
            zout.writestr(info.filename, blob)
    if backup:
        os.replace(path, path + ".orig")
    os.replace(tmp, path)
    return total_in, total_out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--colors", type=int, default=192)
    ap.add_argument("--keep", default="dance.nwp", help="保持原分辨率、只减色的包（逗号分隔）")
    ap.add_argument("--no-backup", action="store_true", help="不保留 .orig 备份")
    args = ap.parse_args()

    keep = set(x.strip() for x in args.keep.split(",") if x.strip())
    folder = args.folder
    names = sorted(n for n in os.listdir(folder) if n.endswith(".nwp"))
    grand_in = grand_out = 0
    for name in names:
        path = os.path.join(folder, name)
        scale = 1.0 if name in keep else args.scale
        before, after = slim_pack(path, scale, args.colors, backup=not args.no_backup)
        grand_in += before
        grand_out += after
        print("%-16s %8.1f MB -> %6.1f MB  (scale=%.2f)" %
              (name, before / 1048576.0, after / 1048576.0, scale))
    print("合计 %.1f MB -> %.1f MB（%.0f%%）" %
          (grand_in / 1048576.0, grand_out / 1048576.0, grand_out * 100.0 / max(1, grand_in)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
