#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""声音播放：优先 PulseAudio/ALSA，缺什么就静音不报错。"""
import os
import shutil
import subprocess

_PROGRAMS = [
    # (命令, 是否支持音量参数, 构造参数)
    ("paplay", "volume"),
    ("aplay", "aplay"),
    ("mpg123", "mpg123"),
    ("ffplay", "ffplay"),
    ("cvlc", "none"),
]


def _which(programs):
    for prog, kind in programs:
        path = shutil.which(prog)
        if path:
            return path, kind
    return None, None


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
            # aplay 没有音量选项，用 softvol 会报错；仅当非 100% 时提示不可控
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
        path, kind = _which(_PROGRAMS)
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
        path, _ = _which(_PROGRAMS)
        return path is not None
