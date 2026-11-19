#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""奶蛙素材包 (.nwp) 读取。

.nwp 是 zip 容器：metadata.json + 若干 PNG 帧。
本模块只做「按需解码 + LRU 缓存」，不解码全部帧，避免启动时吃掉几百 MB 内存。
"""
import io
import json
import os
import zipfile
from collections import OrderedDict

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf  # noqa: E402

PNG_MAGIC = b"\x89PNG"


def decode_png(data):
    """把 PNG 字节解码成 GdkPixbuf（保留 alpha）。"""
    loader = GdkPixbuf.PixbufLoader.new_with_type("png")
    loader.write(data)
    loader.close()
    pix = loader.get_pixbuf()
    if pix is None:
        raise ValueError("PNG 解码失败")
    return pix


class FramePack(object):
    """zip 里的帧序列。frames 从 1 开始按 0000.png 命名。"""

    def __init__(self, path, prefix, cache_size=24):
        self.path = path
        self.prefix = prefix
        self.entries = []
        self.width = 0
        self.height = 0
        self.fps = 15.0
        self.meta = {}
        self._cache = OrderedDict()
        self._cache_size = cache_size
        self._data = {}
        if not os.path.exists(path):
            return
        with zipfile.ZipFile(path) as z:
            try:
                self.meta = json.loads(z.read("metadata.json").decode("utf-8"))
            except KeyError:
                self.meta = {}
            self.width = int(self.meta.get("width", 0) or 0) // 2
            self.height = int(self.meta.get("height", 0) or 0) // 2
            self.fps = float(self.meta.get("fps", 15.0) or 15.0)
            count = int(self.meta.get("frames", 0) or 0)
            names = set(z.namelist())
            for i in range(count):
                name = "%s/%04d.png" % (prefix, i)
                if name in names:
                    self.entries.append(name)
            if not self.entries:
                # 允许 frames 与实际文件数不一致
                self.entries = sorted(
                    n for n in names
                    if n.startswith(prefix + "/") and n.endswith(".png")
                )

    @property
    def count(self):
        return len(self.entries)

    @property
    def ready(self):
        return bool(self.entries)

    @property
    def duration(self):
        return self.count / self.fps if self.fps else 0.0

    def frame(self, index):
        if not self.entries:
            return None
        index = max(0, min(self.count - 1, int(index)))
        pix = self._cache.get(index)
        if pix is not None:
            self._cache.move_to_end(index)
            return pix
        if self.path not in self._data:
            with open(self.path, "rb") as f:
                raw = f.read()
            self._data[self.path] = zipfile.ZipFile(io.BytesIO(raw))
        z = self._data[self.path]
        pix = decode_png(z.read(self.entries[index]))
        self._cache[index] = pix
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return pix

    def close(self):
        for z in self._data.values():
            try:
                z.close()
            except Exception:
                pass
        self._data.clear()
        self._cache.clear()


class EyeArt(object):
    """眼睛贴图：look/00..NN.png 与 blink/{0,1}/00..NN.png。"""

    def __init__(self, folder, cache_size=8):
        self.eyes = []
        self.blinks = ([], [])
        self.eye_count = 0
        self.blink_count = 0
        self.blink_fps = 10.0
        self._path = os.path.join(folder, "素材.nwp")
        self._cache = OrderedDict()
        self._cache_size = cache_size
        self._zip = None
        self._data = {}
        if not os.path.exists(self._path):
            return
        with zipfile.ZipFile(self._path) as z:
            meta = json.loads(z.read("metadata.json").decode("utf-8"))
            self.meta = meta
            self.eye_count = int(meta.get("eyeFrames", 0) or 0)
            self.blink_count = int(meta.get("blinkFrames", 0) or 0)
            self.blink_fps = float(meta.get("blinkFps", 10.0) or 10.0)
            self.eyes = ["look/%02d.png" % i for i in range(self.eye_count)]
            self.blinks = (
                ["blink/0/%02d.png" % i for i in range(self.blink_count)],
                ["blink/1/%02d.png" % i for i in range(self.blink_count)],
            )
            existing = set(z.namelist())
            self.eyes = [n for n in self.eyes if n in existing]
            self.blinks = (
                [n for n in self.blinks[0] if n in existing],
                [n for n in self.blinks[1] if n in existing],
            )
        self.eye_count = len(self.eyes)
        self.blink_count = len(self.blinks[0])

    def _get(self, key):
        pix = self._cache.get(key)
        if pix is not None:
            self._cache.move_to_end(key)
            return pix
        if not key:
            return None
        if self._zip is None:
            with open(self._path, "rb") as f:
                raw = f.read()
            self._zip = zipfile.ZipFile(io.BytesIO(raw))
        pix = decode_png(self._zip.read(key))
        self._cache[key] = pix
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return pix

    def eye(self, value):
        if not self.eyes:
            return None
        idx = int(round(max(0.0, min(1.0, value)) * (self.eye_count - 1)))
        return self._get(self.eyes[idx])

    def blink(self, look, frame):
        if not self.blink_count:
            return None
        row = self.blinks[1] if look > 0.5 else self.blinks[0]
        if not row:
            return None
        idx = max(0, min(len(row) - 1, int(frame)))
        return self._get(row[idx])


class SingleArt(object):
    """.nwp 里只有一张图（feed.nwp / eye_art.nwp 之类）。"""

    def __init__(self, folder, name, member):
        self.path = os.path.join(folder, name)
        self.member = member
        self.width = 0
        self.height = 0
        self.meta = {}
        self._pix = None
        self._zip = None
        if not os.path.exists(self.path):
            return
        with zipfile.ZipFile(self.path) as z:
            self.meta = json.loads(z.read("metadata.json").decode("utf-8"))
            self.width = int(self.meta.get("width", 0) or 0) // 2
            self.height = int(self.meta.get("height", 0) or 0) // 2

    @property
    def ready(self):
        return os.path.exists(self.path)

    def frame(self):
        if self._pix is None and self.ready:
            if self._zip is None:
                self._zip = zipfile.ZipFile(self.path)
            self._pix = decode_png(self._zip.read(self.member))
        return self._pix


class Assets(object):
    """全部素材的统一入口。"""

    NPW_FILES = {
        "walk": "walk.nwp",
        "hold": "hold.nwp",
        "head": "head.nwp",
        "seq": "seq.nwp",
        "dance": "dance.nwp",
        "hunger": "hunger.nwp",
        "fat": "fat.nwp",
        "rest": "rest.nwp",
        "rest2": "rest2.nwp",
        "sad": "sad.nwp",
        "idle_gif": "idle_gif.nwp",
    }

    def __init__(self, folder):
        self.folder = folder
        self.ok = False
        self.error = ""
        self.width = 0
        self.height = 0
        self.count = 0
        self.fps = 12.0
        self.duration = 1.0
        self.main = None
        self.eyes = EyeArt(folder)
        self.drag = FramePack(os.path.join(folder, "drag.nwp"), "drag", cache_size=32)
        self.feed = SingleArt(folder, "feed.nwp", "feed/0000.png")
        self.packs = {}
        for key, name in self.NPW_FILES.items():
            self.packs[key] = FramePack(os.path.join(folder, name), key, cache_size=16)
        self.audio_laugh = os.path.join(folder, "原版笑声.wav")
        self.audio_cry = os.path.join(folder, "cry.wav")
        # 上游的 dance.mp3 其实是 MP4（手机录屏改名），打包时转出的 dance.wav 优先
        self.audio_dance = os.path.join(folder, "dance.wav")
        if not os.path.exists(self.audio_dance):
            self.audio_dance = os.path.join(folder, "dance.mp3")
        self._main_zip = None
        self._main_cache = OrderedDict()
        self._main_cache_size = 16
        self._load_main()

    def _load_main(self):
        path = os.path.join(self.folder, "素材.nwp")
        if not os.path.exists(path):
            self.error = "缺少素材.nwp"
            return
        try:
            with zipfile.ZipFile(path) as z:
                meta = json.loads(z.read("metadata.json").decode("utf-8"))
                self.width = int(meta["width"]) // 2
                self.height = int(meta["height"]) // 2
                self.count = int(meta["frames"])
                self.fps = float(meta["fps"])
                self.duration = self.count / self.fps if self.fps else 1.0
                names = z.namelist()
                self._main_names = ["laugh/%04d.png" % i for i in range(self.count)]
                missing = [n for n in self._main_names if n not in set(names)]
                if missing:
                    raise ValueError("缺少大笑帧：%s" % missing[0])
            self.ok = True
        except Exception as exc:  # noqa: BLE001
            self.error = "素材.nwp 无效：%s" % exc

    def _main_frame(self, index):
        index = max(0, min(self.count - 1, int(index)))
        pix = self._main_cache.get(index)
        if pix is not None:
            self._main_cache.move_to_end(index)
            return pix
        if self._main_zip is None:
            self._main_zip = zipfile.ZipFile(os.path.join(self.folder, "素材.nwp"))
        pix = decode_png(self._main_zip.read(self._main_names[index]))
        self._main_cache[index] = pix
        while len(self._main_cache) > self._main_cache_size:
            self._main_cache.popitem(last=False)
        return pix

    def pack(self, key):
        return self.packs.get(key)

    def frame(self, index):
        return self._main_frame(index)

    def eye(self, value):
        return self.eyes.eye(value)

    def blink(self, look, frame):
        return self.eyes.blink(look, frame)

    def close(self):
        for p in self.packs.values():
            p.close()
        self.drag.close()
        if self._main_zip is not None:
            self._main_zip.close()
            self._main_zip = None
        self._main_cache.clear()
