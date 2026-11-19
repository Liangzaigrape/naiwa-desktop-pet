#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""奶蛙桌宠 —— Linux/麒麟 版主窗口。

对应原 Windows 版 PetWindow.cs：
透明异形窗口、鼠标跟随眼睛、拖拽抛掷、重力行走、饥饿喂食、回收站、
右键菜单、托盘、全屏自动隐藏、贴边只露头。
"""
import math
import os
import random
import signal
import subprocess
import sys
import time
import zipfile

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from . import audio, render, settings, trash, xutil  # noqa: E402
from .motion import Motion  # noqa: E402

try:
    import numpy as _np
except ImportError:  # pragma: no cover - 麒麟默认不带 numpy 也能跑（仅牺牲异形点击）
    _np = None

APP_ID = "naiwa-desktop-pet"
SINGLETON_NAME = "naiwa-desktop-pet-singleton"


def _now():
    return time.monotonic()


def _state_dir():
    return settings.data_dir()


def _lock_path():
    return os.path.join(_state_dir(), "instance.pid")


def _read_pid():
    try:
        with open(_lock_path(), "r", encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def _pid_alive(pid):
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _write_pid():
    try:
        os.makedirs(_state_dir(), exist_ok=True)
        with open(_lock_path(), "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass


def _clear_pid():
    try:
        if _read_pid() == os.getpid():
            os.unlink(_lock_path())
    except OSError:
        pass


def _data_folder():
    """素材目录：优先环境变量，其次是打包路径，最后是脚本同级目录。"""
    env = os.environ.get("NAIWA_PET_DATA")
    if env and os.path.isdir(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (
        "/usr/share/naiwa-pet",
        os.path.join(os.path.dirname(here), "share"),
        os.path.join(here, "assets"),
        here,
    ):
        if os.path.exists(os.path.join(cand, "素材.nwp")):
            return cand
    return "/usr/share/naiwa-pet"


MAX_HUNGER = 10
UNIX_EPOCH_OFFSET = 0


class PetWindow(Gtk.Window):
    def __init__(self, assets, testing=False):
        Gtk.Window.__init__(self, type=Gtk.WindowType.TOPLEVEL)
        self.assets = assets
        self.testing = testing
        self.settings = settings.Settings() if testing else settings.Settings.load()
        if self.settings.hunger_stamp <= 0:
            self.settings.hunger_stamp = int(time.time()) + 600
        self.motion = Motion()
        self.motion.auto_look = True
        self.renderer = render.Renderer(assets)
        self.player = audio.Player(self.settings.volume)
        self.player.enabled = self.settings.sound

        self._start = _now()
        self._last_tick = self._start
        self._last_walk_tick = self._start
        self._last_gravity_tick = self._start
        self._next_fullscreen_check = 0.0
        self._fullscreen_timer = 0.0

        self.bubble_text = None
        self.bubble_until = 0.0
        self.last_visual = None
        self.ready = False
        self.menu_open = False
        self.hidden_for_fullscreen = False
        self.edge_right = False

        self.gravity_falling = False
        self.gravity_vy = 0.0
        self.drag_vy = 0.0
        self.drag_vy_peak = 0.0
        self.drag_window = (0, 0)
        self.last_drag_pointer = (0, 0)

        self.next_walk = 8.0
        self.last_hover = -1e9
        self.next_idle = 45.0
        self.next_idle_roll = 60.0
        self.reminder_next = -1.0
        self.last_chime_hour = -1
        self._random = random.Random()

        self._gesture_pressed = False
        self._gesture_dragged = False
        self._gesture_origin = (0, 0)
        self._last_click = -1e9
        self._last_click_point = (0, 0)

        self._mask = None
        self._mask_size = (0, 0)
        self._mask_dirty = True
        self._mask_time = 0.0
        self._surface = None
        self._surface_size = (0, 0)
        self._pos = None
        self._size = (0, 0)

        self._crowd_until = -1.0
        self._crowd_start = 0.0
        self._dance_sound_started = False
        self._laugh_ringing = False
        self._dance_interrupted = False
        self._fat_bubble_shown = False
        self._dance_fading = False

        self._menu = None
        self._tray = None
        self._timeout_id = 0
        self._updating_menu = False
        self._in_shape_update = False

        # ---- 窗口属性
        # Wayland/WSLg 下没有「绝对定位」，无边框 + skip_taskbar 的窗口可能被合成器
        # 直接忽略；NAIWA_PLAIN_WINDOW=1 时改用普通窗口，方便在 WSLg 里试玩。
        plain = os.environ.get("NAIWA_PLAIN_WINDOW") == "1"
        self.set_decorated(plain)
        self.set_title("naiwa-pet")
        self.set_resizable(False)
        self.set_app_paintable(True)
        self.set_skip_taskbar_hint(not plain)
        self.set_skip_pager_hint(not plain)
        self.set_accept_focus(plain)
        self.set_focus_on_map(plain)
        self.set_keep_above(bool(self.settings.on_top) and not plain)
        self.set_type_hint(Gdk.WindowTypeHint.NORMAL if plain else Gdk.WindowTypeHint.UTILITY)
        if not plain:
            self.stick()
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        self._rgba = visual is not None
        if visual is not None:
            self.set_visual(visual)
        self.set_opacity(self.settings.alpha / 100.0)
        self.connect("draw", self._on_draw)
        self.connect("button-press-event", self._on_press)
        self.connect("button-release-event", self._on_release)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("enter-notify-event", self._on_enter)
        self.connect("leave-notify-event", self._on_leave)
        self.connect("destroy", self._on_destroy)
        self.connect("screen-changed", self._on_screen_changed)
        self.connect("scroll-event", self._on_scroll)
        self.connect("drag-data-received", self._on_drag_data)
        self.connect("map-event", self._on_map)
        self.set_events(Gdk.EventMask.BUTTON_PRESS_MASK
                        | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.ENTER_NOTIFY_MASK
                        | Gdk.EventMask.LEAVE_NOTIFY_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK
                        | Gdk.EventMask.SCROLL_MASK)

        self.drag_dest_set(Gtk.DestDefaults.MOTION | Gtk.DestDefaults.DROP,
                           [Gtk.TargetEntry.new("text/uri-list", 0, 0)], Gdk.DragAction.COPY)
        self.connect("drag-motion", self._on_drag_motion)
        self.connect("drag-leave", self._on_drag_leave)
        self.connect("drag-drop", self._on_drag_drop)

        self._setup_position()
        self._apply_size(force=True)
        self.show_all()
        self._apply_size(force=True)
        GLib.idle_add(self._first_ready)

    # ------------------------------------------------------------- 生命周期
    def _first_ready(self):
        self.ready = True
        self.last_chime_hour = time.localtime().tm_hour
        if self.settings.reminder_minutes > 0:
            self.reminder_next = self.now() + self.settings.reminder_minutes * 60
        if not self.testing:
            self._check_fullscreen(immediate=True)
            try:
                from .tray import Tray
                icon = os.path.join(self.assets.folder, "naiwa-pet.png")
                self._tray = Tray(self, icon)
            except Exception:  # noqa: BLE001
                self._tray = None
        self._render_now(force=True)
        self._schedule(16)
        return False

    def now(self):
        return _now() - self._start

    def _on_map(self, *_args):
        if self._pos is not None:
            self.move(self._pos[0], self._pos[1])
        return False

    def _on_screen_changed(self, widget, old_screen):
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)
        self._rgba = visual is not None

    def _on_destroy(self, *_args):
        self._save()
        _clear_pid()
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = 0
        Gtk.main_quit()

    def quit_app(self):
        self.destroy()

    # ------------------------------------------------------------- 位置/尺寸
    def _monitor_workarea(self):
        display = Gdk.Display.get_default()
        try:
            pointer = display.get_default_seat().get_pointer()
            _, x, y = pointer.get_position()
            monitor = display.get_monitor_at_point(x, y)
        except Exception:  # noqa: BLE001
            monitor = display.get_primary_monitor()
        if monitor is None:
            return Gdk.Rectangle(x=0, y=0, width=1280, height=800)
        return monitor.get_workarea()

    def _surface_width_height(self):
        cw2, ch2, _rect, _ph2 = self.renderer.layout(self.motion, self.settings.scale, self.edge_right)
        return max(1, cw2 // 2), max(1, ch2 // 2)

    def _pet_height(self):
        """从窗口顶部到脚底的像素高度（对应原版 PetHeight）。"""
        _c, ch2, _r, _p = self.renderer.layout(self.motion, self.settings.scale, self.edge_right)
        return ch2 // 2

    def _bottom_margin(self):
        """脚底离工作区底边留一点缝，避免贴着屏幕边缘看起来像被切掉。"""
        return max(2, int(6 * self.settings.scale / 100.0))

    def _setup_position(self):
        if self.settings.position and abs(self.settings.x) < 100000:
            self._move_window(self.settings.x, self.settings.y)
            return
        self.home()

    def home(self):
        area = self._monitor_workarea()
        w, h = self._surface_width_height()
        x = area.x + area.width - w - 24
        y = area.y + area.height - h - self._bottom_margin()
        self._move_window(x, y)
        self._keep_visible()

    def _win_pos(self):
        if self._pos is not None:
            return self._pos
        try:
            _ok, x, y = self.get_position()
            self._pos = (int(x), int(y))
            return self._pos
        except Exception:  # noqa: BLE001
            return self.settings.x, self.settings.y

    def _move_window(self, x, y):
        self._pos = (int(x), int(y))
        self.move(int(x), int(y))

    def _keep_visible(self):
        if self.gravity_falling:
            self.gravity_falling = False
            self.motion.falling = False
        area = self._monitor_workarea()
        x, y = self._win_pos()
        w, h = self._surface_width_height()
        if self.settings.edge:
            x = max(area.x, min(x, area.x + area.width - w))
            y = area.y + area.height - 117
        elif self.edge_right:
            x = area.x + area.width - w
            y = max(area.y, min(y, area.y + area.height - h))
        else:
            x = max(area.x, min(x, area.x + area.width - w))
            y = max(area.y, min(y, area.y + area.height - h - self._bottom_margin()))
        self._move_window(x, y)

    def _apply_size(self, force=False):
        w, h = self._surface_width_height()
        old_w, old_h = self._size
        if not force and (old_w, old_h) == (w, h):
            return
        self._size = (w, h)
        x, y = self._win_pos()
        if old_w and old_h and (old_w, old_h) != (w, h):
            x += (old_w - w) // 2
            y += old_h - h
        self.set_size_request(w, h)
        self.resize(w, h)
        self._move_window(x, y)
        self._surface = None
        self.last_visual = None

    def _surface_for(self, w, h):
        if self._surface is None or self._surface_size != (w, h):
            self._surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
            self._surface_size = (w, h)
            self._mask_dirty = True
        return self._surface

    # ------------------------------------------------------------- 绘制
    def _on_draw(self, widget, cr):
        w = self.get_allocated_width()
        h = self.get_allocated_height()
        surf = self._surface_for(w, h)
        sctx = cairo.Context(surf)
        sctx.set_operator(cairo.OPERATOR_CLEAR)
        sctx.paint()
        sctx.set_operator(cairo.OPERATOR_OVER)
        bubble = None
        if self.bubble_text and self.now() < self.bubble_until:
            bubble = self.bubble_text
        elif self.motion.sleeping:
            bubble = "z Z Z"
        try:
            self.renderer.render(sctx, self.motion, self.settings.scale,
                                 self.settings.mirror, bubble, self.edge_right,
                                 crowd=self._crowd_until > 0)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write("render error: %s\n" % exc)
        surf.flush()
        cr.set_source_surface(surf, 0, 0)
        cr.paint()
        if not self.menu_open:
            self._refresh_pixel_alpha()
            if self._mask_dirty:
                self._update_input_shape()
        return True

    # ------------------------------------------------------------- 异形点击区
    def _update_input_shape(self):
        """用当前画面的 alpha 生成 X11 输入形状，透明处鼠标可以点穿。"""
        self._mask_dirty = False
        if not self._rgba or self.menu_open or self._in_shape_update:
            return
        self._in_shape_update = True
        try:
            gdk_window = self.get_window()
            if gdk_window is None:
                return
            w, h = self._surface_size
            if w <= 0 or h <= 0:
                return
            mask = self._alpha_mask(w, h)
            if mask is None:
                return
            region = _region_from_mask(mask, w, h)
            if region is not None:
                gdk_window.input_shape_combine_region(region, 0, 0)
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._in_shape_update = False

    def _alpha_mask(self, w, h):
        surf = self._surface
        if surf is None or _np is None:
            return None
        try:
            stride = surf.get_stride()
            surf.flush()
            buf = surf.get_data()
            arr = _np.frombuffer(buf, dtype=_np.uint8, count=stride * h).reshape(h, stride)
            alpha = _np.ascontiguousarray(arr[:, 3:w * 4:4])
            return alpha > 8
        except Exception:  # noqa: BLE001
            return None

    def _hit_test(self, x, y):
        """窗口坐标 (x,y) 是否落在可见像素上。"""
        if self._np_enabled():
            w, h = self._surface_size
            if 0 <= x < w and 0 <= y < h and self._pixel_alpha is not None:
                try:
                    return bool(self._pixel_alpha[int(y), int(x)])
                except IndexError:
                    return True
        return True

    _pixel_alpha = None

    def _np_enabled(self):
        return _np is not None and self._surface is not None

    def _refresh_pixel_alpha(self):
        if _np is None or self._surface is None:
            self._pixel_alpha = None
            return
        w, h = self._surface_size
        self._pixel_alpha = self._alpha_mask(w, h)

    # ------------------------------------------------------------- 主循环
    def _schedule(self, interval):
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
        self._timeout_id = GLib.timeout_add(interval, self._tick)

    def _tick(self):
        try:
            self._tick_body()
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write("tick error: %s\n" % exc)
        return True

    def _tick_body(self):
        if not self.ready:
            return
        now = self.now()
        dt = min(0.2, max(0.0, now - self._last_tick))
        self._last_tick = now
        m = self.motion

        if now >= self._next_fullscreen_check:
            self._next_fullscreen_check = now + 0.12
            self._check_fullscreen(immediate=False)
        if self.hidden_for_fullscreen:
            self._schedule(150)
            return

        cursor = self._cursor_pos()
        over = False
        if cursor is not None:
            wx, wy = self._win_pos()
            lx, ly = cursor[0] - wx, cursor[1] - wy
            w, h = self._surface_size
            over = (not self.menu_open
                    and 0 <= lx < w and 0 <= ly < h
                    and self._hit_test(lx, ly))

        if m.auto_look and cursor is not None:
            wx, wy = self._win_pos()
            w, h = self._surface_size
            cx = wx + w / 2.0
            cy = wy + h / 2.0
            dx = cursor[0] - cx
            dy = cursor[1] - cy
            dist = max(40.0, math.sqrt(dx * dx + dy * dy))
            m.look_goal = max(0.0, min(1.0, 0.5 + dx / (2.0 * max(180.0, dist))))
            m.look_goal_v = max(0.0, min(1.0, 0.5 - dy / (2.0 * max(180.0, dist))))

        if self.bubble_text and now >= self.bubble_until:
            self.bubble_text = None
            self.last_visual = None

        if over:
            self.last_hover = now
            if m.sleeping:
                m.wake(now)
            if m.walking:
                m.walk_start = -1.0
        else:
            self._maybe_idle(now)
            self._maybe_walk(now)
            self._maybe_idle_roll(now)

        playing_before = m.playing
        m.update(now, over, self.assets.duration,
                 (self.assets.eyes.blink_count / self.assets.eyes.blink_fps)
                 if self.assets.eyes.blink_fps else 1.0)
        if playing_before and not m.playing:
            self._stop_laugh_sound()

        self._update_dance_sound()
        if m.fat and not self._fat_bubble_shown and m.clock - m.fat_start >= 1.2:
            self._fat_bubble_shown = True
            self.show_bubble("我的肚子真是肥嘟嘟的", 5.0)

        self._hunger_tick(now)
        self._head_seq_tick(now)
        self._update_gravity(now)
        self._update_walk_move(now)

        if m.landed_walk_at >= 0.0 and m.walking and now - m.landed_walk_at >= 3.0:
            m.landed_walk_at = -1.0
            m.start_idle(now, 6, 2000)
            self.play_cry()

        if m.dragging and m.clock - m.drag_start >= m.drag_duration:
            m.drag_start = -1.0

        self._apply_size()
        self._maybe_reminder(now)
        self._maybe_chime(now)

        interval = self._pick_interval()
        self._render_now(force=False)
        self._schedule(interval)

    def _pick_interval(self):
        m = self.motion
        if self.hidden_for_fullscreen:
            return 150
        if (m.hover_open or m.playing or m.holding or m.poking or m.has_extra
                or self.gravity_falling or self.bubble_text
                or (m.sleeping and self.assets.packs["rest"].ready
                    and m.clock - m.sleep_start < self.assets.packs["rest"].duration)):
            return 16
        return 300 if m.sleeping else 100

    def _maybe_idle(self, now):
        m = self.motion
        if (self.edge_right or m.sleeping or m.has_extra or m.playing or m.resting
                or m.dragging or m.hover_open or m.feeding or self._gesture_pressed
                or self.menu_open or now < self.next_idle):
            return
        kind = self._random.randrange(4)
        m.start_idle(now, kind, 700 if kind == 3 else (1100 if kind == 0 else 900))
        self.next_idle = now + 45.0 + self._random.random() * 30.0

    def _maybe_walk(self, now):
        m = self.motion
        if (self.edge_right or m.sleeping or m.has_extra or m.playing or m.resting
                or m.dragging or m.hover_open or m.feeding or self._gesture_pressed
                or self.menu_open or self.gravity_falling or now < self.next_walk):
            return
        m.start_walk(now, self._random.randint(0, 1) * 2 - 1)
        self.next_walk = now + 30.0 + self._random.random() * 40.0

    def _maybe_idle_roll(self, now):
        m = self.motion
        if (self.edge_right or m.sleeping or m.has_extra or m.playing or m.resting
                or m.dragging or m.hover_open or m.feeding or m.walking
                or self.gravity_falling or self._gesture_pressed or self.menu_open
                or now - self.last_hover <= 60.0 or now < self.next_idle_roll):
            return
        if self._random.random() < 0.5:
            m.start_idle(now, 5, 16000)
        else:
            m.sleep(now)
        self.next_idle_roll = now + 60.0

    def _hunger_tick(self, now):
        stamp = int(time.time()) + 600
        if self.settings.hunger > 0 and time.time() >= self.settings.hunger_stamp:
            self.settings.hunger -= 1
            self.settings.hunger_stamp = stamp
            if self.settings.hunger < 3:
                self.motion.start_hungry(now)
                self.show_bubble("我好饿…", 10.0)
            self._save()
            if self._menu is not None:
                self._refresh_menu_state()

    def _head_seq_tick(self, now):
        m = self.motion
        crowd = (m.head_sequencing and m.head_seq == 3
                 and m.clock - m.head_seq_start >= 1.0)
        if crowd and self._crowd_until < 0:
            self._crowd_until = now + 6.0
            self._crowd_start = now
            self._start_dance_sound()
            self.last_visual = None
        elif not crowd and self._crowd_until > 0:
            self._crowd_until = -1.0
            self._stop_dance_sound()
            self.last_visual = None

    def _maybe_reminder(self, now):
        if self.settings.reminder_minutes <= 0 or self.reminder_next < 0:
            return
        if now < self.reminder_next:
            return
        self.reminder_next = now + self.settings.reminder_minutes * 60
        if self.motion.sleeping:
            self.motion.wake(now)
        self.motion.celebrate(now)
        self.show_bubble("该休息啦，起来活动一下！", 8.0)

    def _maybe_chime(self, now):
        if not self.settings.chime:
            return
        lt = time.localtime()
        if lt.tm_hour != self.last_chime_hour and lt.tm_min == 0 and lt.tm_sec < 4:
            self.last_chime_hour = lt.tm_hour
            self.motion.celebrate(now)
            self.show_bubble("现在 %02d:%02d 啦" % (lt.tm_hour, lt.tm_min), 5.0)

    # ------------------------------------------------------------- 物理
    def _update_gravity(self, now):
        if not self.gravity_falling:
            return
        dt = min(0.1, max(0.0, now - self._last_gravity_tick))
        self._last_gravity_tick = now
        self.gravity_vy += 1500.0 * dt
        area = self._monitor_workarea()
        h = self._surface_size[1]
        bottom = area.y + area.height - h - self._bottom_margin()
        x, y = self._win_pos()
        ny = y + self.gravity_vy * dt
        if ny <= area.y:
            ny = area.y
            self.gravity_vy = abs(self.gravity_vy) * 0.35
        if ny >= bottom:
            ny = bottom
            self.gravity_vy *= -0.45
            if abs(self.gravity_vy) < 50.0:
                self.gravity_falling = False
                self.motion.falling = False
                self.motion.landing_start = now
                self.motion.start = -1.0
                self.motion.start_walk_landed(now, self._random.randint(0, 1) * 2 - 1)
            else:
                self.motion.landing_start = now
        self._move_window(x, ny)
        self.last_visual = None

    def _update_walk_move(self, now):
        m = self.motion
        if not m.walking or self.gravity_falling or self.edge_right:
            return
        dt = min(0.1, max(0.0, now - self._last_walk_tick))
        self._last_walk_tick = now
        x, y = self._win_pos()
        nx = x + int(round(120.0 * dt * m.walk_dir))
        area = self._monitor_workarea()
        w = self._surface_size[0]
        if nx <= area.x:
            nx = area.x
            m.walk_dir = 1
        elif nx + w >= area.x + area.width:
            nx = area.x + area.width - w
            m.walk_dir = -1
        self._move_window(nx, y)
        self.last_visual = None

    # ------------------------------------------------------------- 渲染节流
    def _visual_key(self):
        m = self.motion
        parts = []
        t = m.clock
        if m.sleeping:
            rest = self.assets.packs["rest"]
            parts.append("S%d" % (int((t - m.sleep_start) * (rest.fps or 10)) if rest.ready else 0))
        if m.dragging:
            parts.append("D%d" % int((t - m.drag_start) * (self.assets.drag.fps or 15)))
        elif m.hover_open:
            parts.append("H%d" % min(18, int((t - m.hover_start) * 15)))
        elif m.feeding:
            parts.append("F")
        elif m.resting:
            parts.append("R")
        elif m.playing:
            parts.append("L%d" % int(m.elapsed * self.assets.fps))
        elif m.head_sequencing:
            parts.append("Q%d" % m.head_seq)
        elif m.dancing:
            parts.append("N%d" % int((t - m.dance_start) * 15))
        elif m.fat:
            parts.append("A%d" % int((t - m.fat_start) * 15))
        elif m.hungry:
            parts.append("G")
        elif m.idling:
            parts.append("I%d%d" % (m.idle_kind, int(t * 15)))
        elif m.blinking:
            parts.append("B%d%d" % (1 if m.look > 0.5 else 0,
                                    int((t - m.blink_start) * self.assets.eyes.blink_fps)))
        else:
            parts.append("E%dV%d" % (int(round(m.look * max(0, self.assets.eyes.eye_count - 1))),
                                     int(round(m.look_v * 30))))
        if (m.poking or m.moving or m.waking or m.celebrating or m.landing
                or m.walking or m.falling):
            parts.append("M%d" % int(t * 60))
        parts.append(str(self.settings.scale))
        parts.append(str(self.settings.alpha))
        parts.append("1" if self.edge_right else "0")
        parts.append("C" if self._crowd_until > 0 else "-")
        parts.append(self.bubble_text or "")
        return "|".join(parts)

    def _render_now(self, force=False):
        if not self.ready or self.hidden_for_fullscreen:
            return
        key = self._visual_key()
        if not force and key == self.last_visual:
            return
        self.last_visual = key
        self.queue_draw()
        self._mask_dirty = True

    def show_bubble(self, text, seconds):
        self.bubble_text = text
        self.bubble_until = self.now() + seconds
        self._render_now(force=True)

    # ------------------------------------------------------------- 声音
    def _audio_on(self):
        return self.settings.sound and self.settings.volume > 0

    def play_laugh(self):
        if not self._audio_on():
            return
        if self.player.play(self.assets.audio_laugh):
            self._laugh_ringing = True

    def _stop_laugh_sound(self):
        if self._laugh_ringing:
            self._laugh_ringing = False
            self.player.stop_all()

    def play_cry(self):
        if self._audio_on():
            self.player.play(self.assets.audio_cry)

    def _start_dance_sound(self):
        if self._audio_on() and not self._dance_sound_started:
            self._dance_sound_started = self.player.play(self.assets.audio_dance, loops=3)

    def _stop_dance_sound(self):
        self._dance_sound_started = False
        self.player.stop_all()

    def _update_dance_sound(self):
        m = self.motion
        if m.dancing and not self._dance_sound_started and not self._dance_fading:
            self._start_dance_sound()
        if self._dance_sound_started and not (m.dancing or self._crowd_until > 0):
            self._stop_dance_sound()

    # ------------------------------------------------------------- 交互
    def _cursor_pos(self):
        try:
            display = Gdk.Display.get_default()
            pointer = display.get_default_seat().get_pointer()
            _screen, x, y = pointer.get_position()
            return int(x), int(y)
        except Exception:  # noqa: BLE001
            return None

    def _on_enter(self, *_args):
        self._on_hover_enter()

    def _on_leave(self, *_args):
        self._on_hover_leave()

    def _on_hover_enter(self):
        m = self.motion
        if self.edge_right or m.hover_open:
            return
        if m.dragging:
            m.drag_start = -1.0
        if m.walking:
            m.walk_start = -1.0
        if m.dancing:
            m.end_dance()
            self._dance_interrupted = True
        if m.sleeping:
            m.wake(self.now())
        m.hover_open = True
        m.hover_start = self.now()
        m.feed_start = -1.0
        self._render_now(force=True)

    def _on_hover_leave(self):
        m = self.motion
        if not m.hover_open:
            return
        m.hover_open = False
        self._dance_interrupted = False
        if not m.dragging and not m.walking and not self.gravity_falling:
            m.clear_effects(self.now())
            m.feed_start = self.now()
        self._render_now(force=True)

    def _on_press(self, widget, event):
        if event.button == 3:
            self._show_menu(event)
            return True
        if event.button == 2:
            self._eat_down()
            return True
        if event.button != 1:
            return False
        if self.edge_right:
            self._set_edge_right(False)
            self._keep_visible()
        if self.settings.edge:
            self.settings.edge = False
            self._refresh_menu_state()
        self._gesture_pressed = True
        self._gesture_dragged = False
        self._gesture_origin = (event.x_root, event.y_root)
        self.last_drag_pointer = self._gesture_origin
        self.drag_window = self._win_pos()
        self.gravity_falling = False
        self.motion.falling = False
        self.drag_vy_peak = 0.0
        self.drag_vy = 0.0
        return True

    def _on_motion(self, widget, event):
        if not self._gesture_pressed:
            return False
        px, py = event.x_root, event.y_root
        ox, oy = self._gesture_origin
        if abs(px - ox) > 5 or abs(py - oy) > 5:
            self._gesture_dragged = True
        if not self._gesture_dragged:
            return True
        m = self.motion
        now = self.now()
        if not m.holding:
            m.begin_drag(now)
            self._stop_laugh_sound()
        self.drag_vy = (py - self.last_drag_pointer[1]) * 150
        if self.drag_vy < self.drag_vy_peak:
            self.drag_vy_peak = self.drag_vy
        m.drag(now, px - self.last_drag_pointer[0])
        self.last_drag_pointer = (px, py)
        wx, wy = self.drag_window
        self._move_window(wx + px - ox, wy + py - oy)
        self.last_visual = None
        self._render_now(force=True)
        return True

    def _on_release(self, widget, event):
        if event.button != 1 or not self._gesture_pressed:
            return False
        self._gesture_pressed = False
        now = self.now()
        dragged = self._gesture_dragged
        double = self._is_double_click(event.x_root, event.y_root, now)
        if dragged:
            self.motion.end_drag(now)
            area = self._monitor_workarea()
            x, y = self._win_pos()
            w = self._surface_size[0]
            if not self.settings.edge and x + w >= area.x + area.width - 24:
                self._set_edge_right(True)
            else:
                self._keep_visible()
                self.gravity_falling = True
                self.motion.falling = True
                self.gravity_vy = (max(-1000.0, self.drag_vy_peak)
                                   if self.drag_vy_peak < -120.0 else 0.0)
                self.drag_vy_peak = 0.0
                self._last_gravity_tick = now
            self._render_now(force=True)
            self._save()
            return True
        if self.edge_right:
            return True
        if double:
            self._on_click(event.x, event.y)
        return True

    def _is_double_click(self, x, y, now):
        last = self._last_click
        lx, ly = self._last_click_point
        is_double = (now - last <= 0.45 and abs(x - lx) <= 6 and abs(y - ly) <= 6)
        if is_double:
            self._last_click = -1e9
        else:
            self._last_click = now
            self._last_click_point = (x, y)
        return is_double

    def _pet_x(self, wx):
        v = wx * 100.0 / self.settings.scale
        return self.assets.width - v if self.settings.mirror else v

    def _pet_y(self, wy):
        return (wy - 58) * 100.0 / self.settings.scale

    def _on_click(self, ex, ey):
        m = self.motion
        px = self._pet_x(ex)
        py = self._pet_y(ey)
        if m.head_sequencing:
            return
        if m.in_belly(px, py):
            self.laugh()
        elif m.in_head(px, py):
            m.start_head_seq(self.now())
            self._render_now(force=True)
        elif m.resting:
            m.stand(self.now())
            self._render_now(force=True)

    def laugh(self):
        now = self.now()
        if self.motion.laugh(now):
            self.play_laugh()
            self._render_now(force=True)
            return True
        return False

    def _eat_down(self):
        if self.settings.hunger > 0:
            self.settings.hunger -= 1
        if self.settings.hunger < 3 and not self.motion.hungry:
            self.motion.start_hungry(self.now())
            self.show_bubble("我好饿…", 10.0)
        self._save()
        self._render_now(force=True)

    # ------------------------------------------------------------- 拖入文件
    def _uri_paths(self, selection):
        uris = selection.get_uris() or []
        paths = []
        for uri in uris:
            try:
                path = GLib.filename_from_uri(uri)[0]
                if path:
                    paths.append(path)
            except Exception:  # noqa: BLE001
                continue
        return paths

    def _on_drag_motion(self, widget, context, x, y, time_):
        Gdk.drag_status(context, Gdk.DragAction.COPY, time_)
        if self._hit_test(x, y):
            self._on_hover_enter()
        return True

    def _on_drag_leave(self, widget, context, time_):
        self._on_hover_leave()
        return True

    def _on_drag_drop(self, widget, context, x, y, time_):
        if not self._hit_test(x, y):
            self._on_hover_leave()
            return False
        targets = []
        try:
            targets = context.list_targets()
        except Exception:  # noqa: BLE001
            pass
        for target in targets or []:
            name = target.name() if hasattr(target, "name") else str(target)
            if name == "text/uri-list":
                widget.drag_get_data(context, target, time_)
                return True
        try:
            widget.drag_get_data(context, Gdk.Atom.intern("text/uri-list", False), time_)
        except Exception:  # noqa: BLE001
            return False
        return True

    def _on_drag_data(self, widget, context, x, y, data, info, time_):
        paths = self._uri_paths(data) if data is not None else []
        widget.drag_finish(context, bool(paths), False, time_)
        if paths:
            self._on_file_drop(paths)
        return True

    def _on_file_drop(self, paths):
        m = self.motion
        if self.edge_right or not paths:
            return
        now = self.now()
        if m.sleeping:
            m.wake(now)
        drag = self.assets.drag
        m.start_drag(now, drag.duration if drag.ready else 6.0)
        moved = trash.move_all(paths) if self.settings.recycle else 0
        if moved > 0:
            if self.settings.hunger < MAX_HUNGER:
                self.settings.hunger += 1
            self.settings.hunger_stamp = int(time.time()) + 600
            if m.hungry:
                m.end_hungry()
            if self.settings.hunger >= MAX_HUNGER:
                m.drag_duration = min(m.drag_duration, 1.4)
                m.start_fat(now)
                self._fat_bubble_shown = False
            else:
                if not self._dance_interrupted:
                    m.start_dance(now)
                self.show_bubble("谢谢你！！", 4.0)
            self._dance_interrupted = False
            self._save()
            self._refresh_menu_state()
        elif self.settings.recycle:
            self.show_bubble("回收失败（文件被占用？）已保留", 4.0)
        else:
            self.show_bubble("收到 %d 个文件（回收已关闭）" % len(paths), 3.0)
        self._render_now(force=True)

    # ------------------------------------------------------------- 全屏检测
    def _check_fullscreen(self, immediate):
        if not (self.ready and not self.menu_open and not self._gesture_pressed):
            return
        want = False
        if self.settings.auto_hide:
            now = self.now()
            if immediate or now - self._fullscreen_timer > 0.3:
                self._fullscreen_timer = now
                try:
                    want = xutil.x11().active_is_fullscreen()
                except Exception:  # noqa: BLE001
                    want = False
        if immediate:
            self._apply_fullscreen(want)
        elif want != self.hidden_for_fullscreen:
            # 防抖：连续两次一致才切换
            self._fs_pending = getattr(self, "_fs_pending", 0) + 1
            if self._fs_pending >= 2:
                self._fs_pending = 0
                self._apply_fullscreen(want)
        else:
            self._fs_pending = 0

    def _apply_fullscreen(self, hidden):
        if hidden == self.hidden_for_fullscreen:
            return
        self.hidden_for_fullscreen = hidden
        if hidden:
            self._gesture_pressed = False
            self.motion.suspend(self.now())
            self._stop_laugh_sound()
            self.hide()
        else:
            self.motion.suspend(self.now())
            self.show_all()
            self._render_now(force=True)

    # ------------------------------------------------------------- 贴边露头
    def _set_edge_right(self, value):
        self.edge_right = value
        if value:
            self.motion.clear_effects(self.now())
            self._apply_size(force=True)
            area = self._monitor_workarea()
            w, h = self._surface_width_height()
            _x, y = self._win_pos()
            self._move_window(area.x + area.width - w,
                              max(area.y, min(y, area.y + area.height - h)))
        else:
            self._apply_size(force=True)
            self._keep_visible()
        self.last_visual = None
        self._render_now(force=True)

    # ------------------------------------------------------------- 菜单
    def _show_menu(self, event):
        self.motion.end_drag(self.now())
        self._gesture_pressed = False
        menu = self._build_menu()
        self.menu_open = True
        try:
            menu.popup_at_pointer(event)
        except Exception:  # noqa: BLE001
            menu.popup(None, None, None, None, event.button, event.time)

    def _menu_closed(self, *_args):
        self.menu_open = False
        self._mask_dirty = True
        self._render_now(force=True)

    def _refresh_menu_state(self):
        if self._menu is not None:
            self._update_menu_checks(self._menu)

    def _build_menu(self):
        if self._menu is not None:
            self._update_menu_checks(self._menu)
            return self._menu
        menu = Gtk.Menu()
        menu.connect("selection-done", self._menu_closed)

        hunger = Gtk.MenuItem(label=self._hunger_label())
        hunger.set_sensitive(False)
        menu.append(hunger)
        self._hunger_item = hunger

        help_item = Gtk.MenuItem(label="使用说明书")
        help_item.connect("activate", self._open_help)
        menu.append(help_item)
        menu.append(Gtk.SeparatorMenuItem())

        settings_item = Gtk.MenuItem(label="设置")
        sub = Gtk.Menu()

        demo_item = Gtk.MenuItem(label="查看动作")
        demo_menu = Gtk.Menu()
        actions = [
            ("大笑", "laugh"), ("小动作", "idle"), ("转手舞", "idle5"),
            ("哭泣（上抛后）", "idle6"), ("行走", "walk"), ("起势（第1阶段）", "seq1"),
            ("愤怒（第2阶段）", "seq2"), ("打电话·炸开舞群", "seq3"),
            ("喂食庆祝舞蹈", "dance"), ("饥饿乞讨", "hungry"),
            ("吃饱变袋鼠", "fat"), ("睡觉", "sleep"),
        ]
        for label, key in actions:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _w, k=key: self._demo_action(k))
            demo_menu.append(item)
        demo_item.set_submenu(demo_menu)
        sub.append(demo_item)

        size_item = Gtk.MenuItem(label="大小")
        size_menu = Gtk.Menu()
        self._size_items = []
        for pct, label in ((50, "很小(50%)"), (65, "小号(65%)"), (80, "中号(80%)"),
                           (95, "标准(95%)"), (110, "大号(110%)"), (125, "加大(125%)"),
                           (140, "特大(140%)"), (150, "最大(150%)")):
            item = Gtk.CheckMenuItem(label=label)
            item.connect("activate", lambda _w, p=pct: self.set_size(p))
            size_menu.append(item)
            self._size_items.append((pct, item))
        size_menu.append(Gtk.SeparatorMenuItem())
        for label, delta in (("放大 5%", 5), ("缩小 5%", -5)):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _w, d=delta: self.set_size(self.settings.scale + d))
            size_menu.append(item)
        size_item.set_submenu(size_menu)
        sub.append(size_item)

        self._sound_item = Gtk.CheckMenuItem(label="声音")
        self._sound_item.connect("toggled", self._on_toggle_sound)
        sub.append(self._sound_item)

        volume_item = Gtk.MenuItem(label="音量")
        volume_menu = Gtk.Menu()
        self._volume_label_item = Gtk.MenuItem(label="音量：%d%%" % self.settings.volume)
        self._volume_label_item.set_sensitive(False)
        volume_menu.append(self._volume_label_item)
        scale_item = Gtk.MenuItem()
        self._volume_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        self._volume_scale.set_draw_value(False)
        self._volume_scale.set_size_request(200, -1)
        self._volume_scale.set_value(self.settings.volume)
        self._volume_scale.connect("value-changed",
                                   lambda w: self.set_volume(int(w.get_value())))
        scale_item.add(self._volume_scale)
        volume_menu.append(scale_item)
        volume_menu.append(Gtk.SeparatorMenuItem())
        for label, delta in (("调大 5%", 5), ("调小 5%", -5)):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _w, d=delta: self.set_volume(self.settings.volume + d))
            volume_menu.append(item)
        self._mute_item = Gtk.MenuItem(label="静音")
        self._mute_item.connect("activate", lambda _w: self.toggle_mute())
        volume_menu.append(self._mute_item)
        volume_menu.append(Gtk.SeparatorMenuItem())
        for pct in (100, 80, 60, 40, 20):
            item = Gtk.MenuItem(label="%d%%" % pct)
            item.connect("activate", lambda _w, p=pct: self.set_volume(p))
            volume_menu.append(item)
        volume_item.set_submenu(volume_menu)
        sub.append(volume_item)
        sub.append(Gtk.SeparatorMenuItem())

        self._autorun_item = Gtk.CheckMenuItem(label="开机自启动")
        self._autorun_item.connect("toggled", self._on_toggle_autorun)
        sub.append(self._autorun_item)

        self._autohide_item = Gtk.CheckMenuItem(label="全屏时自动隐藏")
        self._autohide_item.connect("toggled", self._on_toggle_autohide)
        sub.append(self._autohide_item)

        self._edge_item = Gtk.CheckMenuItem(label="贴边只露头")
        self._edge_item.connect("toggled", self._on_toggle_edge)
        sub.append(self._edge_item)

        sub.append(Gtk.SeparatorMenuItem())
        quit_item = Gtk.MenuItem(label="退出奶蛙")
        quit_item.connect("activate", lambda _w: self.quit_app())
        sub.append(quit_item)

        settings_item.set_submenu(sub)
        menu.append(settings_item)
        menu.show_all()
        self._menu = menu
        self._update_menu_checks(menu)
        return menu

    def _hunger_label(self):
        filled = "▓" * self.settings.hunger + "░" * (MAX_HUNGER - self.settings.hunger)
        return "饥饿 %s %d/%d" % (filled, self.settings.hunger, MAX_HUNGER)

    def _on_toggle_sound(self, item):
        if not self._updating_menu:
            self.set_sound(item.get_active())

    def _on_toggle_autorun(self, item):
        if not self._updating_menu:
            self.set_autorun(item.get_active())

    def _on_toggle_autohide(self, item):
        if not self._updating_menu:
            self.set_autohide(item.get_active())

    def _on_toggle_edge(self, item):
        if not self._updating_menu:
            self.set_edge(item.get_active())

    def _update_menu_checks(self, menu):
        if self._updating_menu:
            return
        self._updating_menu = True
        try:
            if hasattr(self, "_hunger_item"):
                self._hunger_item.set_label(self._hunger_label())
            if hasattr(self, "_sound_item"):
                self._sound_item.set_active(self.settings.sound)
            if hasattr(self, "_volume_label_item"):
                self._volume_label_item.set_label("音量：%d%%" % self.settings.volume)
            if hasattr(self, "_mute_item"):
                self._mute_item.set_label("取消静音" if self.settings.volume <= 0 else "静音")
            if hasattr(self, "_autorun_item"):
                self._autorun_item.set_active(self.settings.autorun)
            if hasattr(self, "_autohide_item"):
                self._autohide_item.set_active(self.settings.auto_hide)
            if hasattr(self, "_edge_item"):
                self._edge_item.set_active(self.settings.edge)
            for pct, item in getattr(self, "_size_items", []):
                item.set_active(pct == self.settings.scale)
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._updating_menu = False

    def _open_help(self, *_args):
        for cand in (os.path.join(self.assets.folder, "使用说明.txt"),
                     "/usr/share/naiwa-pet/使用说明.txt"):
            if os.path.exists(cand):
                try:
                    subprocess.Popen(["xdg-open", cand],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except OSError:
                    break
        self.show_bubble("说明书文件没找到", 3.0)

    def _demo_action(self, name):
        now = self.now()
        m = self.motion
        if name == "laugh":
            self.laugh()
            return
        if name == "idle":
            m.start_idle(now, self._random.randrange(4), 1400)
        elif name == "idle5":
            m.start_idle(now, 5, 16000)
        elif name == "idle6":
            m.start_idle(now, 6, 2000)
        elif name == "walk":
            m.start_walk(now, 1)
        elif name == "seq1":
            m.start_head_seq(now)
        elif name == "seq2":
            m.start_head_seq(now)
            m.start_head_seq(now)
        elif name == "seq3":
            m.start_head_seq(now)
            m.start_head_seq(now)
            m.start_head_seq(now)
        elif name == "dance":
            m.start_dance(now)
        elif name == "hungry":
            m.start_hungry(now)
            self.show_bubble("我好饿…", 10.0)
        elif name == "fat":
            m.start_fat(now)
            self._fat_bubble_shown = False
        elif name == "sleep":
            m.sleep(now)
        self._render_now(force=True)

    # ------------------------------------------------------------- 设置项
    def set_size(self, scale):
        self.settings.scale = max(50, min(150, int(scale)))
        self._surface = None
        self._apply_size(force=True)
        self._keep_visible()
        self._render_now(force=True)
        self._save()
        self._refresh_menu_state()

    def set_sound(self, enabled):
        self.settings.sound = bool(enabled)
        self.player.enabled = self.settings.sound
        if not self.settings.sound:
            self.player.stop_all()
        self._save()
        self._refresh_menu_state()

    def set_volume(self, value):
        self.settings.volume = max(0, min(100, int(value)))
        self.player.set_volume(self.settings.volume)
        if hasattr(self, "_volume_scale"):
            try:
                if abs(self._volume_scale.get_value() - self.settings.volume) > 0.5:
                    self._volume_scale.set_value(self.settings.volume)
            except Exception:  # noqa: BLE001
                pass
        self._save()
        self._refresh_menu_state()

    def toggle_mute(self):
        if self.settings.volume > 0:
            self._mute_back = self.settings.volume
            self.set_volume(0)
        else:
            self.set_volume(getattr(self, "_mute_back", 100) or 100)

    def set_autorun(self, enabled):
        self.settings.autorun = bool(enabled)
        _write_autostart(self.settings.autorun)
        self._save()
        self._refresh_menu_state()

    def set_autohide(self, enabled):
        self.settings.auto_hide = bool(enabled)
        if not self.settings.auto_hide:
            self._apply_fullscreen(False)
        self._save()
        self._refresh_menu_state()

    def set_edge(self, enabled):
        self.settings.edge = bool(enabled)
        self.edge_right = False
        if self.settings.edge:
            area = self._monitor_workarea()
            x, _y = self._win_pos()
            w = self._surface_size[0]
            self._move_window(max(area.x, min(x, area.x + area.width - w)),
                              area.y + area.height - 117)
            self._keep_visible()
        else:
            self.home()
        self._save()
        self._refresh_menu_state()
        self._render_now(force=True)

    def _on_scroll(self, widget, event):
        if event.direction == Gdk.ScrollDirection.UP:
            self.set_volume(self.settings.volume + 5)
            return True
        if event.direction == Gdk.ScrollDirection.DOWN:
            self.set_volume(self.settings.volume - 5)
            return True
        return False

    def _save(self):
        if self.testing:
            return
        try:
            x, y = self._win_pos()
            self.settings.x = int(x)
            self.settings.y = int(y)
            self.settings.save()
        except Exception:  # noqa: BLE001
            pass


def _region_from_mask(mask, w, h):
    """bool ndarray → cairo.Region（按位图 1bpp 生成）。"""
    if _np is None:
        return None
    try:
        data = _np.packbits(mask, axis=1)
        stride = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_A1, w)
        if data.shape[1] > stride:
            data = data[:, :stride]
        elif data.shape[1] < stride:
            pad = _np.zeros((h, stride - data.shape[1]), dtype=_np.uint8)
            data = _np.concatenate([data, pad], axis=1)
        buf = bytearray(data.tobytes())
        surf = cairo.ImageSurface.create_for_data(buf, cairo.FORMAT_A1, w, h, stride)
        region = cairo.Region.create_from_surface(surf)
        surf.finish()
        return region
    except Exception:  # noqa: BLE001
        return None


def _write_autostart(enabled):
    path = os.path.join(settings.config_dir(), "autostart")
    desktop = os.path.join(os.path.expanduser("~"), ".config", "autostart", "naiwa-pet.desktop")
    try:
        if enabled:
            os.makedirs(os.path.dirname(desktop), exist_ok=True)
            with open(desktop, "w", encoding="utf-8") as f:
                f.write("[Desktop Entry]\nType=Application\nName=奶蛙桌宠\n"
                        "Exec=naiwa-pet\nIcon=naiwa-pet\nTerminal=false\n"
                        "X-GNOME-Autostart-enabled=true\n")
        else:
            if os.path.exists(desktop):
                os.unlink(desktop)
    except OSError:
        pass
    _ = path
