#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""settings.ini 读写（与原 Windows 版键名保持一致，方便迁移配置）。"""
import os

APP_NAME = "naiwa-desktop-pet"


def config_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_NAME)


def data_dir():
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, APP_NAME)


class Settings(object):
    def __init__(self):
        self.scale = 80
        self.x = 0
        self.y = 0
        self.position = False
        self.sound = True
        self.on_top = True
        self.auto_hide = True
        self.volume = 100
        self.alpha = 100
        self.reminder_minutes = 0
        self.mirror = False
        self.chime = False
        self.autorun = False
        self.edge = False
        self.recycle = True
        self.edge_inset = 80
        self.hunger = 5
        self.hunger_stamp = 0

    @property
    def path(self):
        return os.path.join(config_dir(), "settings.ini")

    @classmethod
    def load(cls):
        st = cls()
        try:
            with open(st.path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            return st
        for line in lines:
            line = line.strip()
            if "=" not in line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            try:
                if key == "scale":
                    st.scale = max(50, min(150, int(value)))
                elif key == "x":
                    st.x = int(value)
                    st.position = True
                elif key == "y":
                    st.y = int(value)
                elif key == "sound":
                    st.sound = value == "True"
                elif key == "top":
                    st.on_top = value != "False"
                elif key == "fullscreen":
                    st.auto_hide = value != "False"
                elif key == "alpha":
                    st.alpha = max(40, min(100, int(value)))
                elif key == "mirror":
                    st.mirror = value == "True"
                elif key == "reminder":
                    st.reminder_minutes = int(value)
                elif key == "chime":
                    st.chime = value == "True"
                elif key == "autorun":
                    st.autorun = value == "True"
                elif key == "edge":
                    st.edge = value == "True"
                elif key == "recycle":
                    st.recycle = value != "False"
                elif key == "edgeInset":
                    st.edge_inset = max(0, min(160, int(value)))
                elif key == "volume":
                    st.volume = max(0, min(100, int(value)))
                elif key == "hunger":
                    st.hunger = max(0, min(10, int(value)))
                elif key == "hungerStamp":
                    st.hunger_stamp = int(value)
            except ValueError:
                continue
        return st

    def save(self):
        try:
            os.makedirs(config_dir(), exist_ok=True)
            lines = [
                "scale=%d" % self.scale,
                "x=%d" % self.x,
                "y=%d" % self.y,
                "sound=%s" % ("True" if self.sound else "False"),
                "top=%s" % ("True" if self.on_top else "False"),
                "fullscreen=%s" % ("True" if self.auto_hide else "False"),
                "alpha=%d" % self.alpha,
                "mirror=%s" % ("True" if self.mirror else "False"),
                "reminder=%d" % self.reminder_minutes,
                "chime=%s" % ("True" if self.chime else "False"),
                "autorun=%s" % ("True" if self.autorun else "False"),
                "edge=%s" % ("True" if self.edge else "False"),
                "recycle=%s" % ("True" if self.recycle else "False"),
                "edgeInset=%d" % self.edge_inset,
                "hunger=%d" % self.hunger,
                "hungerStamp=%d" % self.hunger_stamp,
                "volume=%d" % self.volume,
            ]
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            os.replace(tmp, self.path)
            return True
        except OSError:
            return False
