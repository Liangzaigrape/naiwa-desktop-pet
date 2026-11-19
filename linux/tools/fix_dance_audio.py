#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把上游那个其实是 MP4 的 dance.mp3 转成真正的 WAV（只取音轨，单声道 22.05k）。

用法：fix_dance_audio.py <src.mp3> <dst.wav>
返回 0 = 生成成功；2 = 没装 ffmpeg；3 = 源文件不存在；1 = 转换失败。
"""
import os
import shutil
import subprocess
import sys


def convert(src, dst):
    if os.path.exists(dst):
        return 0
    if not os.path.exists(src):
        return 3
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return 2
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", src,
           "-vn", "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le", dst]
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if proc.returncode != 0 or not os.path.exists(dst):
        sys.stderr.write(proc.stderr.decode("utf-8", "replace")[-500:])
        return 1
    print("dance.wav: %.2f MB" % (os.path.getsize(dst) / 1048576.0))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(64)
    sys.exit(convert(sys.argv[1], sys.argv[2]))
