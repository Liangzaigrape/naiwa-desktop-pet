#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""声音播放：按文件格式挑播放器，缺什么就静音不报错。

注意：上游 release 里的 `dance.mp3` 其实是 **MP4 容器**（HEVC 视频 + AAC 音频，
手机录屏改名而来），paplay / aplay / mpg123 都放不了它，只有 ffplay / vlc 能放。
所以打包时会把它的音轨转成真正的 `dance.wav`，运行时优先用 wav。
"""
import os
import shutil
import subprocess

_KINDS = {
    "paplay": "volume",
    "aplay": "aplay",
    "mpg123": "mpg123",
    "ffplay": "ffplay",
    "cvlc": "none",
}

# 每种格式的播放器优先级（先找谁先试谁）
_ORDER = {
    ".wav": ["paplay", "aplay", "ffplay", "cvlc"],
    ".mp3": ["mpg123", "ffplay", "cvlc", "paplay"],
    ".ogg": ["paplay", "ffplay", "cvlc"],
    ".flac": ["paplay", "ffplay", "cvlc"],
    ".m4a": ["ffplay", "cvlc"],
    ".mp4": ["ffplay", "cvlc"],
}


def _pick(path):
    fmt = os.path.splitext(path)[1].lower()
    for prog in _ORDER.get(fmt, ["ffplay", "cvlc"]):
        found = shutil.which(prog)
        if found:
            return found, _KINDS[prog]
    return None, None


def _any_player():
    for progs in _ORDER.values():
        for prog in progs:
            if shutil.which(prog):
                return prog
    return None


class Player(object):
    def __init__(self, volume=100):
        self.volume = max(0, min(100, volume))
        self.enabled = True
        self._procs = []

    def set_volume(self, volume):
        self.volume = max(0, min(100, volume))

    def _args(self, path, kind):
        if kind == "volume":
            # paplay: 65536 == 100%
            return [path, "--volume=%d" % int(self.volume * 655.36)]
        if kind == "aplay":
            # aplay 没有音量参数（softvol 需要插件配置），靠系统音量
            return [path, "-q"]
        if kind == "mpg123":
            return [path, "-q", "-f", str(int(self.volume * 327.67))]
        if kind == "ffplay":
            return [path, "-nodisp", "-autoexit", "-loglevel", "quiet",
                    "-volume", str(int(self.volume))]
        return [path, "--play-and-exit", "--quiet"]

    def play(self, filepath, loops=0):
        if not self.enabled or self.volume <= 0 or not filepath:
            return False
        if not os.path.exists(filepath):
            return False
        path, kind = _pick(filepath)
        if not path:
            return False
        args = self._args(path, kind)
        if loops:
            if kind == "mpg123":
                args.insert(1, "--loop")
                args.insert(2, str(loops))
            elif kind == "ffplay":
                args.insert(1, "-loop")
                args.insert(2, str(loops))
            elif kind == "none":
                args.insert(1, "--loop")
                args.append(str(loops))
        args.append(filepath)
        try:
            proc = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    start_new_session=True)
            self._procs.append(proc)
            self._reap()
            return True
        except OSError:
            return False

    def stop_all(self):
        for proc in self._procs:
            try:
                proc.terminate()
            except OSError:
                pass
        self._procs = []

    def _reap(self):
        alive = []
        for proc in self._procs:
            if proc.poll() is None:
                alive.append(proc)
        self._procs = alive[-8:]

    @staticmethod
    def available():
        return _any_player() is not None
