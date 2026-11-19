#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""奶蛙绘制层：把状态机 + 素材合成成一帧画面（cairo）。

原版是 2 倍素材 → 2 倍画布绘制 → 最后降采样，这里保持同样的做法，
保证 50%~150% 任意缩放下边缘都不糊。

性能：同一帧的「缩放后贴图」会缓存，切换缩放比例时整体失效。
"""
import math

import cairo
import gi

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GdkPixbuf, Pango, PangoCairo  # noqa: E402

BUBBLE_HEIGHT = 58
FONT_FAMILY = "Noto Sans CJK SC, WenQuanYi Micro Hei, Microsoft YaHei, Sans"


def _surface_of(pix):
    """pixbuf → (缓存的) cairo surface。"""
    surf = getattr(pix, "_naiwa_surface", None)
    if surf is None:
        surf = Gdk.cairo_surface_create_from_pixbuf(pix, 0, None)
        try:
            pix._naiwa_surface = surf
        except (AttributeError, TypeError):
            pass
    return surf


def draw_pixbuf(cr, pix, x, y, w, h, alpha=1.0):
    if pix is None or w <= 0 or h <= 0 or alpha <= 0.0:
        return
    surf = _surface_of(pix)
    cr.save()
    cr.translate(x, y)
    cr.scale(w / float(pix.get_width()), h / float(pix.get_height()))
    cr.set_source_surface(surf, 0, 0)
    cr.get_source().set_filter(cairo.FILTER_BILINEAR)
    if alpha >= 1.0:
        cr.paint()
    else:
        cr.paint_with_alpha(max(0.0, min(1.0, alpha)))
    cr.restore()


def _rounded_rect(cr, x, y, w, h, r):
    r = min(r, w / 2.0, h / 2.0)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.arc(x + w - r, y + r, r, 1.5 * math.pi, 2 * math.pi)
    cr.arc(x + w - r, y + h - r, r, 0, 0.5 * math.pi)
    cr.arc(x + r, y + h - r, r, 0.5 * math.pi, math.pi)
    cr.close_path()


class Renderer(object):
    def __init__(self, assets):
        self.assets = assets
        self._scaled = {}
        self._scaled_scale = None

    # ------------------------------------------------------------ 缩放缓存
    def _reset_scale(self, scale_pct):
        if scale_pct != self._scaled_scale:
            self._scaled = {}
            self._scaled_scale = scale_pct

    def _pix(self, tag, index, pix):
        if pix is None or self._scaled_scale == 100:
            return pix
        key = (tag, index)
        got = self._scaled.get(key)
        if got is not None:
            return got
        s = self._scaled_scale / 100.0
        w = max(1, int(round(pix.get_width() * s)))
        h = max(1, int(round(pix.get_height() * s)))
        out = pix.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR) or pix
        self._scaled[key] = out
        if len(self._scaled) > 24:
            self._scaled.pop(next(iter(self._scaled)))
        return out

    # ------------------------------------------------------------ 布局
    def layout(self, m, scale_pct, edge_right):
        """返回 (cw, ch, pet_rect(dx,dy,w,h), pet_h)，尺寸均为 2 倍画布像素。"""
        s2 = scale_pct * 2
        a = self.assets
        if edge_right:
            k = s2 / 100.0
            return int(433 * k), int(374 * k), (0, 0, int(433 * k), int(374 * k)), int(374 * k)

        cw = a.width
        if m.sleeping:
            for key in ("rest", "rest2"):
                pack = a.packs[key]
                if pack.ready and pack.width > cw:
                    cw = pack.width
        cw2 = cw * s2 // 100
        ph2 = a.height * s2 // 100
        ch2 = ph2
        if m.dragging or m.hover_open:
            ch2 = max(ch2, a.drag.height * s2 // 100)
        if m.feeding and a.feed.height:
            ch2 = max(ch2, a.feed.height * s2 // 100)
        ch2 += 116
        return cw2, ch2, (0, ch2 - ph2, cw2, ph2), ph2

    # ------------------------------------------------------------ 主绘制
    def render(self, cr, m, scale_pct, mirror, bubble, edge_right, crowd=False):
        """把当前状态画到 cairo 目标上；目标尺寸应等于 layout() 的一半。"""
        self._reset_scale(scale_pct)
        cw2, ch2, rect, ph2 = self.layout(m, scale_pct, edge_right)
        cr.save()
        cr.scale(0.5, 0.5)
        if not edge_right:
            cr.translate(0, 116)
        if crowd:
            self._draw_crowd(cr, m, cw2, rect, scale_pct * 2 / 100.0)
        else:
            self._draw_scene(cr, m, scale_pct, mirror, bubble, edge_right, cw2, ch2, rect, ph2)
        cr.restore()

    # ------------------------------------------------------------ 场景
    def _draw_scene(self, cr, m, scale_pct, mirror, bubble, edge_right, cw2, ch2, rect, ph2):
        a = self.assets
        s2 = scale_pct * 2
        k = s2 / 100.0

        if edge_right:
            head = a.packs["head"]
            pix = head.frame(0) if head.ready else None
            if pix is not None:
                w = (head.width or a.width) * k
                h = (head.height or a.height) * k
                cr.save()
                cr.translate(-76 * k, 45 * k)
                cr.translate(106 * k, 60 * k)
                cr.rotate(math.radians(-30))
                cr.translate(-106 * k, -60 * k)
                draw_pixbuf(cr, pix, 0, 0, w, h)
                cr.restore()
            return

        flip = bool(mirror)
        if m.holding and m.drag_angle < -0.5:
            flip = not flip
        if m.walking and m.walk_dir > 0:
            flip = not flip

        cr.save()
        if flip:
            cr.translate(cw2, 0)
            cr.scale(-1, 1)

        self._apply_transform(cr, m, cw2, ph2, s2)

        rx, ry, rw, rh = rect
        drag_rect = (rx, ry, rw, rh)
        if a.drag.width:
            drag_rect = (int((cw2 - a.drag.width * k) / 2.0),
                         int(ry + rh - a.drag.height * k),
                         int(a.drag.width * k), int(a.drag.height * k))

        look = (1.0 - m.look) if mirror else m.look

        if m.holding or m.falling:
            pack = a.packs["hold"]
            if pack.ready:
                draw_pixbuf(cr, pack.frame(0), (cw2 - pack.width * k) / 2.0,
                            ry + rh - pack.height * k, pack.width * k, pack.height * k)
        elif m.dragging:
            d = a.drag
            if d.ready:
                idx = int((m.clock - m.drag_start) * d.fps)
                draw_pixbuf(cr, d.frame(idx), drag_rect[0], drag_rect[1], drag_rect[2], drag_rect[3])
        elif m.walking:
            pack = a.packs["walk"]
            if pack.ready:
                idx = int((m.clock - m.walk_start) * 12.0) % pack.count
                draw_pixbuf(cr, pack.frame(idx), rx, ry, rw, rh)
        elif m.hover_open:
            d = a.drag
            if d.ready:
                n = min(18, int((m.clock - m.hover_start) * 15.0))
                draw_pixbuf(cr, d.frame(min(d.count - 1, 1 + n)),
                            drag_rect[0], drag_rect[1], drag_rect[2], drag_rect[3])
        elif m.feeding:
            if a.feed.ready:
                draw_pixbuf(cr, a.feed.frame(), drag_rect[0], drag_rect[1], drag_rect[2], drag_rect[3])
        elif m.hungry:
            pack = a.packs["hunger"]
            if pack.ready:
                draw_pixbuf(cr, pack.frame(0), (cw2 - pack.width * k) / 2.0,
                            ry + rh - pack.height * k, pack.width * k, pack.height * k)
        elif m.dancing:
            pack = a.packs["dance"]
            if pack.ready:
                h = a.height * k
                w = pack.width * h / float(pack.height or 1)
                idx = int((m.clock - m.dance_start) * 15.0) % pack.count
                draw_pixbuf(cr, pack.frame(idx), (cw2 - w) / 2.0, ry + rh - h, w, h)
        elif m.fat:
            self._draw_fat(cr, m, cw2, rx, ry, rw, rh, k)
        elif m.head_sequencing:
            self._draw_head_seq(cr, m, cw2, rx, ry, rw, rh, k)
        elif m.resting:
            draw_pixbuf(cr, a.frame(a.count - 1), rx, ry, rw, rh)
        elif m.waking:
            t = min(1.0, (m.clock - m.wake_start) / 0.24)
            draw_pixbuf(cr, a.frame(a.count - 1), rx, ry, rw, rh, 1.0 - t)
            draw_pixbuf(cr, a.eye(look), rx, ry, rw, rh, t)
        elif m.sleeping:
            self._draw_sleep(cr, m, cw2, rx, ry, rw, rh, k)
        elif m.idling and m.idle_kind == 5:
            self._draw_idle_gif(cr, m, cw2, ry, rh, k)
        elif m.idling and m.idle_kind == 6:
            pack = a.packs["sad"]
            if pack.ready:
                h = a.height * k
                w = pack.width * h / float(pack.height or 1)
                draw_pixbuf(cr, pack.frame(0), (cw2 - w) / 2.0, ry + rh - h, w, h)
        elif not m.playing:
            if m.blinking:
                img = a.blink(look, int((m.clock - m.blink_start) * a.eyes.blink_fps))
            else:
                img = a.eye(look)
            draw_pixbuf(cr, img, rx, ry, rw, rh)
        elif m.elapsed < 0.1:
            draw_pixbuf(cr, a.eye(look), rx, ry, rw, rh)
            draw_pixbuf(cr, a.frame(int(m.elapsed * a.fps)), rx, ry, rw, rh, m.elapsed / 0.1)
        else:
            draw_pixbuf(cr, a.frame(int(m.elapsed * a.fps)), rx, ry, rw, rh)

        cr.restore()

        if bubble:
            self._draw_bubble(cr, bubble, cw2, k)

    def _apply_transform(self, cr, m, cw2, ph2, s2):
        k = s2 / 100.0
        if m.moving:
            pvx = cw2 * 0.5
            pvy = ph2 * (0.56 if m.holding else 0.9565)
            cr.translate(pvx, pvy - (2.0 * k if m.holding else 0.0))
            cr.rotate(math.radians(m.drag_angle))
            if m.holding:
                cr.scale(1.008, 1.018)
            else:
                cr.scale(1.0 + m.squash, 1.0 - m.squash)
            cr.translate(-pvx, -pvy)
        elif m.idling and m.idle_kind not in (5, 6):
            t = max(0.0, min(1.0, (m.clock - m.idle_start) / max(0.001, m.idle_end - m.idle_start)))
            cx, cy = cw2 * 0.5, ph2 * 0.5
            cr.translate(cx, cy)
            if m.idle_kind == 0:
                cr.rotate(math.radians(10.0 * math.sin(math.pi * t)))
            elif m.idle_kind == 1:
                cr.translate(0, -26.0 * math.sin(math.pi * t) * k)
            elif m.idle_kind == 2:
                cr.translate(14.0 * math.sin(2 * math.pi * t) * k, -4.0 * math.sin(math.pi * t) * k)
            elif m.idle_kind == 3:
                cr.translate(3.0 * math.sin(30.0 * t) * k, 0)
            elif m.idle_kind == 4:
                cr.scale(1.0, 1.0 - 0.06 * math.sin(math.pi * t))
            cr.translate(-cx, -cy)
        elif m.head_poking:
            t = max(0.0, min(1.0, (m.clock - m.head_start) / 1.0))
            cx, cy = cw2 * 0.5, ph2 * 0.35
            cr.translate(cx, cy)
            cr.rotate(math.radians(4.0 * math.sin(math.pi * t)))
            cr.scale(1.0, 1.0 - 0.08 * math.sin(math.pi * t))
            cr.translate(-cx, -cy)
        elif m.celebrating:
            t = m.clock - m.celebrate_start
            cx, cy = cw2 * 0.5, ph2 * 0.5
            cr.translate(cx, cy)
            cr.translate(0, -26.0 * abs(math.sin(math.pi * t * 2.0)) * k)
            cr.rotate(math.radians(2.0 * math.sin(math.pi * t * 2.0)))
            cr.translate(-cx, -cy)

    # ------------------------------------------------------------ 炸开舞群
    def _draw_crowd(self, cr, m, cw2, rect, k):
        """头槌第三阶段：6 只小奶蛙落地跳舞（对应原版 CrowdWindow 的整体效果）。"""
        a = self.assets
        rx, ry, rw, rh = rect
        t = m.clock - m.head_seq_start
        base = a.frame(0)
        dance = a.packs["dance"]
        small = 0.6
        bw = a.width * k * small
        bh = a.height * k * small
        dance_t = max(0.0, t - 1.05)
        for i in range(6):
            col = i % 3
            row = i // 3
            tx = cw2 * (0.5 + (col - 1) * 0.29)
            ty = ry + rh - row * bh * 0.95 - bh
            if t < 0.55:
                p = t / 0.55
                ease = 1.0 - (1.0 - p) ** 3
                x = cw2 * 0.5 + (tx - cw2 * 0.5) * ease + math.sin(t * 1.6 + i) * 6.0
                y = ry + rh - bh - (rh * 0.35) * math.sin(p * math.pi) + (ty - (ry + rh - bh)) * ease
            else:
                x = tx + math.sin(t * 1.6 + i) * 6.0 * k / 2.0
                y = ty
                bounce = (t - 0.55) % 1.2
                if bounce < 0.35:
                    y -= abs(math.sin(bounce / 0.35 * math.pi)) * 26.0 * k / 2.0
            pix = base
            if dance_t > 0 and dance.ready:
                idx = (int(dance_t * 15.0) + i * 7) % dance.count
                pix = dance.frame(idx)
            draw_pixbuf(cr, pix, x - bw / 2.0, y, bw, bh)


    def _draw_fat(self, cr, m, cw2, rx, ry, rw, rh, k):
        a = self.assets
        t = m.clock - m.fat_start
        if t < 1.2:
            draw_pixbuf(cr, a.frame(0), rx, ry, rw, rh)
            for i in range(3):
                n = t + i * 0.4
                if n > 1.2:
                    n -= 1.2
                p = n / 1.2
                x = cw2 / 2.0 + (p * 24.0 + i * 18 - 27.0) * k
                y = (ry - 36 * k) - p * 58.0 * k
                r = (6.0 + p * 15.0) * k
                cr.save()
                cr.set_source_rgba(132 / 255.0, 132 / 255.0, 132 / 255.0,
                                   max(0.0, 215.0 * (1.0 - p)) / 255.0)
                cr.arc(x, y, r, 0, 2 * math.pi)
                cr.fill()
                cr.restore()
        else:
            pack = a.packs["fat"]
            if pack.ready:
                draw_pixbuf(cr, pack.frame(0), (cw2 - pack.width * k) / 2.0,
                            ry + rh - pack.height * k, pack.width * k, pack.height * k)

    def _draw_head_seq(self, cr, m, cw2, rx, ry, rw, rh, k):
        a = self.assets
        pack = a.packs["seq"]
        if not pack.ready:
            return
        t = m.clock - m.head_seq_start
        x = (cw2 - pack.width * k) / 2.0
        y = ry + rh - pack.height * k
        if m.head_seq != 3 or t < 1.0:
            idx = max(0, min(pack.count - 1, m.head_seq - 1))
            draw_pixbuf(cr, pack.frame(idx), x, y, pack.width * k, pack.height * k)
        else:
            draw_pixbuf(cr, a.frame(0), rx, ry, rw, rh)

    def _draw_sleep(self, cr, m, cw2, rx, ry, rw, rh, k):
        a = self.assets
        rest = a.packs["rest"]
        rest2 = a.packs["rest2"]
        t = m.clock - m.sleep_start
        if rest.ready and (rest.duration <= 0 or t < rest.duration):
            idx = min(rest.count - 1, int(t * rest.fps))
            draw_pixbuf(cr, rest.frame(idx), (cw2 - rest.width * k) / 2.0,
                        ry + rh - rest.height * k, rest.width * k, rest.height * k)
        elif rest2.ready:
            draw_pixbuf(cr, rest2.frame(0), (cw2 - rest2.width * k) / 2.0,
                        ry + rh - rest2.height * k, rest2.width * k, rest2.height * k)
        else:
            draw_pixbuf(cr, a.blink(0.0, a.eyes.blink_count - 1), rx, ry, rw, rh)

    def _draw_idle_gif(self, cr, m, cw2, ry, rh, k):
        a = self.assets
        pack = a.packs["idle_gif"]
        if not pack.ready:
            return
        h = a.height * k
        w = pack.width * h / float(pack.height or 1)
        idx = int((m.clock - m.idle_start) * pack.fps) % pack.count
        draw_pixbuf(cr, pack.frame(idx), (cw2 - w) / 2.0, ry + rh - h, w, h)

    # ------------------------------------------------------------ 气泡
    def _draw_bubble(self, cr, text, cw2, k):
        font = Pango.FontDescription(FONT_FAMILY)
        font.set_size(int(11 * k * Pango.SCALE))
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(font)
        layout.set_text(text, -1)
        tw, th = layout.get_pixel_size()
        max_w = cw2 - 16 * k
        while tw + 28 * k > max_w and font.get_size() > int(6.5 * k * Pango.SCALE):
            font.set_size(font.get_size() - int(0.8 * k * Pango.SCALE))
            layout.set_font_description(font)
            tw, th = layout.get_pixel_size()
        bw = min(max_w, tw + 28 * k)
        bh = 40 * k
        bx = (cw2 - bw) / 2.0
        by = 6 * k
        r = 10 * k
        cr.save()
        cr.new_path()
        _rounded_rect(cr, bx, by, bw, bh, r)
        cr.set_source_rgba(1, 1, 1, 216 / 255.0)
        cr.fill_preserve()
        cr.set_source_rgba(90 / 255.0, 90 / 255.0, 90 / 255.0, 140 / 255.0)
        cr.set_line_width(max(1.0, 1.0 * k))
        cr.stroke()
        cr.new_path()
        cx = bx + bw / 2.0
        cr.move_to(cx - 7 * k, by + bh)
        cr.line_to(cx + 7 * k, by + bh)
        cr.line_to(cx, by + bh + 11 * k)
        cr.close_path()
        cr.set_source_rgba(1, 1, 1, 216 / 255.0)
        cr.fill()
        cr.move_to((cw2 - tw) / 2.0, by + (bh - th) / 2.0)
        cr.set_source_rgba(45 / 255.0, 45 / 255.0, 45 / 255.0, 235 / 255.0)
        PangoCairo.show_layout(cr, layout)
        cr.restore()
