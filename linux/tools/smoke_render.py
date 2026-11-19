#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""开发期渲染冒烟测试：用仓库自带的 walk.nwp 造一个临时 素材.nwp，
把各个状态渲染成 PNG，便于肉眼/程序化检查。"""
import io
import json
import os
import shutil
import sys
import zipfile

SRC = sys.argv[1] if len(sys.argv) > 1 else "/home/builder/naiwa-src"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/naiwa-smoke"
FAKE = os.path.join(OUT, "assets")


def build_fake_assets():
    os.makedirs(FAKE, exist_ok=True)
    for name in ("walk.nwp", "hold.nwp", "head.nwp", "seq.nwp", "dance.nwp",
                 "hunger.nwp", "fat.nwp", "rest.nwp", "rest2.nwp", "sad.nwp"):
        src = os.path.join(SRC, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(FAKE, name))
    for name in ("原版笑声.wav", "cry.wav"):
        src = os.path.join(SRC, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(FAKE, name))
    # 素材.nwp：用 walk.nwp 的帧当 laugh 帧，look/blink 用同一帧缩放
    with zipfile.ZipFile(os.path.join(SRC, "walk.nwp")) as z:
        frames = [z.read(n) for n in z.namelist() if n.endswith(".png")]
    meta = {"width": 426, "height": 618, "frames": len(frames), "fps": 10.0,
            "eyeFrames": 2, "blinkFrames": 2, "blinkFps": 10.0}
    with zipfile.ZipFile(os.path.join(FAKE, "素材.nwp"), "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("metadata.json", json.dumps(meta))
        for i, f in enumerate(frames):
            z.writestr("laugh/%04d.png" % i, f)
        z.writestr("look/00.png", frames[0])
        z.writestr("look/01.png", frames[0])
        z.writestr("blink/0/00.png", frames[0])
        z.writestr("blink/0/01.png", frames[0])
        z.writestr("blink/1/00.png", frames[0])
        z.writestr("blink/1/01.png", frames[0])
    # idle_gif.nwp / drag.nwp / feed.nwp 用现有帧凑
    with zipfile.ZipFile(os.path.join(FAKE, "idle_gif.nwp"), "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("metadata.json", json.dumps({"frames": len(frames), "fps": 12.5,
                                                "width": 426, "height": 618}))
        for i, f in enumerate(frames):
            z.writestr("idle_gif/%04d.png" % i, f)
    with zipfile.ZipFile(os.path.join(FAKE, "drag.nwp"), "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("metadata.json", json.dumps({"frames": len(frames), "fps": 15.0,
                                                "width": 426, "height": 618}))
        for i, f in enumerate(frames):
            z.writestr("drag/%04d.png" % i, f)
    with zipfile.ZipFile(os.path.join(FAKE, "feed.nwp"), "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("metadata.json", json.dumps({"width": 426, "height": 618, "frames": 1}))
        z.writestr("feed/0000.png", frames[0])
    # 空音频
    for name in ("原版笑声.wav", "cry.wav", "dance.mp3"):
        p = os.path.join(FAKE, name)
        if not os.path.exists(p):
            open(p, "wb").write(b"")


def main():
    os.makedirs(OUT, exist_ok=True)
    build_fake_assets()
    from gi.repository import GLib
    sys.path.insert(0, "/mnt/c/Users/LiangzaiGrape/Documents/deepseek-harness/default-workspace/naiwa/linux/naiwa-pet")
    import cairo
    from naiwa.assets import Assets
    from naiwa.motion import Motion
    from naiwa.render import Renderer

    assets = Assets(FAKE)
    print("assets.ok", assets.ok, assets.error, assets.width, assets.height, assets.count)
    r = Renderer(assets)
    now = 100.0
    states = [
        ("idle", lambda m: None),
        ("blink", lambda m: setattr(m, "blink_start", now)),
        ("laugh", lambda m: m.laugh(now)),
        ("walk", lambda m: m.start_walk(now, 1)),
        ("drag", lambda m: m.start_drag(now, 3.0)),
        ("hungry", lambda m: m.start_hungry(now)),
        ("dance", lambda m: m.start_dance(now)),
        ("fat", lambda m: m.start_fat(now)),
        ("sleep", lambda m: m.sleep(now)),
        ("idle5", lambda m: m.start_idle(now, 5, 16000)),
        ("idle6", lambda m: m.start_idle(now, 6, 2000)),
        ("seq1", lambda m: m.start_head_seq(now)),
    ]
    for name, setup in states:
        m = Motion()
        m.update(now, False, assets.duration, 1.0)
        setup(m)
        m.clock = now + 0.3
        m.update(now + 0.3, False, assets.duration, 1.0)
        for scale in (100, 80, 125):
            cw2, ch2, rect, ph2 = r.layout(m, scale, False)
            w, h = max(1, cw2 // 2), max(1, ch2 // 2)
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
            ctx = cairo.Context(surf)
            r.render(ctx, m, scale, False, "自检气泡" if name == "idle" else None, False)
            surf.flush()
            out = os.path.join(OUT, "%s_%d.png" % (name, scale))
            surf.write_to_png(out)
            # 统计非透明像素
            stride = surf.get_stride()
            buf = bytes(surf.get_data())
            nz = 0
            for y in range(0, h, 4):
                row = buf[y * stride:(y + 1) * stride]
                for x in range(0, w, 4):
                    if row[x * 4 + 3] > 8:
                        nz += 1
            print("%-8s %3d%% canvas=%dx%d rect=%s opaque_samples=%d" %
                  (name, scale, w, h, rect, nz))
            assert w > 10 and h > 10
    print("render smoke ok")


if __name__ == "__main__":
    main()
