#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""系统托盘图标（Gtk.StatusIcon）。

麒麟/UKUI 面板对 XEmbed 托盘图标的支持依赖桌面环境本身，
如果面板没有托盘区，这里会安静地失败，右键奶蛙依然能打开同一个菜单。
"""
import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


class Tray(object):
    def __init__(self, window, icon_path):
        self.window = window
        self.ok = False
        self.icon = None
        if not os.path.exists(icon_path):
            return
        try:
            self.icon = Gtk.StatusIcon.new_from_file(icon_path)
            self.icon.set_tooltip_text("奶蛙 · 右键菜单，双击回来")
            self.icon.connect("popup-menu", self._on_popup)
            self.icon.connect("activate", self._on_activate)
            self.icon.set_visible(True)
            self.ok = True
        except Exception:  # noqa: BLE001
            self.ok = False

    def _on_popup(self, _icon, button, activate_time):
        menu = self.window._build_menu()
        try:
            menu.popup(None, None, Gtk.StatusIcon.position_menu, self.icon,
                       button, activate_time)
        except Exception:  # noqa: BLE001
            pass

    def _on_activate(self, _icon):
        self.window.home()
        self.window._render_now(force=True)

    def set_tooltip(self, text):
        if self.icon is not None:
            try:
                self.icon.set_tooltip_text(text)
            except Exception:  # noqa: BLE001
                pass
