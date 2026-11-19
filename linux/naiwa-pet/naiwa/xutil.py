#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""少量 X11 辅助：全屏检测。

不依赖 python3-xlib，直接用 ctypes 调 libX11。
Wayland 会话下这些函数会安静地返回 False（视为「没有全屏窗口」）。
"""
import ctypes
import ctypes.util

NET_WM_STATE = "_NET_WM_STATE"
NET_WM_STATE_FULLSCREEN = "_NET_WM_STATE_FULLSCREEN"
NET_ACTIVE_WINDOW = "_NET_ACTIVE_WINDOW"


class _X11(object):
    def __init__(self):
        self.ok = False
        self.lib = None
        self.dpy = None
        self.root = 0
        try:
            name = ctypes.util.find_library("X11")
            if not name:
                return
            self.lib = ctypes.CDLL(name)
            self.lib.XOpenDisplay.restype = ctypes.c_void_p
            self.lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
            self.lib.XDefaultRootWindow.restype = ctypes.c_ulong
            self.lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            self.lib.XInternAtom.restype = ctypes.c_ulong
            self.lib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
            self.lib.XGetWindowProperty.restype = ctypes.c_int
            self.lib.XGetWindowProperty.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long,
                ctypes.c_long, ctypes.c_int, ctypes.c_ulong,
                ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.c_void_p),
            ]
            self.lib.XFree.argtypes = [ctypes.c_void_p]
            dpy = self.lib.XOpenDisplay(None)
            if not dpy:
                return
            self.dpy = ctypes.c_void_p(dpy)
            self.root = self.lib.XDefaultRootWindow(self.dpy)
            self.atom_state = self.lib.XInternAtom(self.dpy, NET_WM_STATE.encode(), 0)
            self.atom_fullscreen = self.lib.XInternAtom(
                self.dpy, NET_WM_STATE_FULLSCREEN.encode(), 0)
            self.atom_active = self.lib.XInternAtom(self.dpy, NET_ACTIVE_WINDOW.encode(), 0)
            self.ok = True
        except (OSError, AttributeError):
            self.ok = False

    def _prop(self, win, atom, max_items=32):
        actual_type = ctypes.c_ulong()
        actual_format = ctypes.c_int()
        nitems = ctypes.c_ulong()
        bytes_after = ctypes.c_ulong()
        prop = ctypes.c_void_p()
        status = self.lib.XGetWindowProperty(
            self.dpy, win, atom, 0, max_items, 0, 0,
            ctypes.byref(actual_type), ctypes.byref(actual_format),
            ctypes.byref(nitems), ctypes.byref(bytes_after), ctypes.byref(prop))
        if status != 0 or not prop.value:
            return []
        try:
            count = int(nitems.value)
            if actual_format.value == 32:
                arr = ctypes.cast(prop, ctypes.POINTER(ctypes.c_ulong))
                return [int(arr[i]) for i in range(count)]
            return []
        finally:
            self.lib.XFree(prop)

    def active_window(self):
        if not self.ok:
            return 0
        vals = self._prop(self.root, self.atom_active, 1)
        return vals[0] if vals else 0

    def is_fullscreen(self, win):
        if not self.ok or not win:
            return False
        states = self._prop(win, self.atom_state, 32)
        return self.atom_fullscreen in states

    def active_is_fullscreen(self):
        if not self.ok:
            return False
        win = self.active_window()
        if not win:
            return False
        try:
            import gi
            gi.require_version("Gdk", "3.0")
            from gi.repository import Gdk
            gdk_win = Gdk.X11.Window.foreign_new_for_display(
                Gdk.Display.get_default(), win) if hasattr(Gdk, "X11") else None
            if gdk_win is not None:
                state = gdk_win.get_state()
                if state & Gdk.WindowState.FULLSCREEN:
                    return True
        except Exception:  # noqa: BLE001
            pass
        return self.is_fullscreen(win)


_X = None


def x11():
    global _X
    if _X is None:
        _X = _X11()
    return _X
