#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""奶蛙状态机 —— 由原 C# 版 Motion.cs 逐项移植。

所有时间都以「程序启动后经过的秒数」为单位（float），
外部只调用 update()，然后读属性决定画面。
"""
import math
import random


class Motion(object):
    POKE_DURATION = 0.95

    def __init__(self):
        self.look = 0.5
        self.look_v = 0.5
        self.look_goal = 0.5
        self.look_goal_v = 0.5
        self.auto_look = True

        self.start = -1.0          # 大笑等主播放
        self.elapsed = 0.0
        self.clock = 0.0
        self.blink_start = -1.0
        self.next_blink = 4.0
        self.wake_start = -1.0
        self.poke_start = -1.0
        self.poke_x = 144.0
        self.poke_y = 205.0
        self.landing_start = -1.0
        self.drag_angle = 0.0
        self.walk_start = -1.0
        self.walk_dir = 1
        self.resting = False
        self.holding = False
        self.play_count = 0

        self.drag_start = -1.0
        self.drag_duration = 8.0
        self.hover_open = False
        self.hover_start = -1.0
        self.feed_start = -1.0
        self.hungry_start = -1.0
        self.dance_start = -1.0
        self.fat_start = -1.0
        self.falling = False
        self.idle_start = -1.0
        self.idle_end = 0.0
        self.idle_kind = -1
        self.sleep_start = -1.0
        self.head_start = -1.0
        self.celebrate_start = -1.0
        self.head_seq_start = -1.0
        self.head_seq = 0
        self.landed_walk_at = -1.0

        self._previous = -1.0
        self._drag_target = 0.0
        self._drag_velocity = 0.0
        self._last_drag_time = -1.0
        self._random = random.Random()

    # ------------------------------------------------------------------ 查询
    @property
    def playing(self):
        return self.start >= 0.0

    @property
    def blinking(self):
        return self.blink_start >= 0.0

    @property
    def poking(self):
        return self.poke_start >= 0.0

    @property
    def landing(self):
        return self.landing_start >= 0.0

    @property
    def waking(self):
        return self.wake_start >= 0.0

    @property
    def dragging(self):
        return self.drag_start >= 0.0

    @property
    def feeding(self):
        return self.feed_start >= 0.0

    @property
    def hungry(self):
        return self.hungry_start >= 0.0

    @property
    def dancing(self):
        return self.dance_start >= 0.0

    @property
    def fat(self):
        return self.fat_start >= 0.0

    @property
    def sleeping(self):
        return self.sleep_start >= 0.0

    @property
    def idling(self):
        return self.idle_start >= 0.0

    @property
    def head_poking(self):
        return self.head_start >= 0.0

    @property
    def celebrating(self):
        return self.celebrate_start >= 0.0

    @property
    def head_sequencing(self):
        return self.head_seq_start >= 0.0

    @property
    def walking(self):
        return self.walk_start >= 0.0 and not self.holding

    @property
    def has_extra(self):
        return any([
            self.idle_start >= 0.0, self.sleep_start >= 0.0, self.head_start >= 0.0,
            self.celebrate_start >= 0.0, self.walk_start >= 0.0, self.head_seq_start >= 0.0,
            self.dance_start >= 0.0, self.fat_start >= 0.0,
        ])

    @property
    def moving(self):
        if not self.holding and not self.landing:
            return abs(self.drag_angle) > 0.02
        return True

    @property
    def poke_amount(self):
        num = self.clock - self.poke_start
        if not self.poking or num < 0.0 or num >= self.POKE_DURATION:
            return 0.0
        if num < 0.12:
            return 0.85 * math.sin(num / 0.12 * math.pi / 2.0)
        return 0.85 * math.exp(-4.8 * (num - 0.12)) * math.cos(18.0 * (num - 0.12))

    @property
    def squash(self):
        num = self.clock - self.landing_start
        if not self.landing or num < 0.0:
            return 0.0
        return 0.055 * math.exp(-6.0 * num) * math.sin(19.0 * num)

    # ------------------------------------------------------------------ 状态切换
    def start_hungry(self, now):
        self.clear_effects(now)
        self.walk_start = -1.0
        self.hungry_start = now

    def end_hungry(self):
        self.hungry_start = -1.0

    def start_dance(self, now):
        self.clear_effects(now)
        self.walk_start = -1.0
        self.dance_start = now

    def end_dance(self):
        self.dance_start = -1.0

    def start_fat(self, now):
        self.clear_effects(now)
        self.walk_start = -1.0
        self.dance_start = -1.0
        self.fat_start = now

    def end_fat(self):
        self.fat_start = -1.0

    def start_drag(self, now, duration):
        self.drag_start = now
        self.drag_duration = max(0.5, duration)
        self.look = 0.0
        self.look_v = 0.5
        self.hover_open = False
        self.feed_start = -1.0
        self.clear_effects(now)

    def start_walk(self, now, direction):
        self.clear_all(now)
        self.walk_start = now
        self.walk_dir = 1 if direction > 0 else -1
        self.landed_walk_at = -1.0

    def start_walk_landed(self, now, direction):
        self.start_walk(now, direction)
        self.landed_walk_at = now

    def start_head_seq(self, now):
        if (not self.playing and not self.resting and not self.holding and not self.sleeping
                and not self.dragging and not self.hover_open and not self.feeding
                and self.head_seq < 3):
            self.head_seq = self.head_seq + 1 if self.head_seq < 3 else 1
            self.clear_all(now)
            self.head_seq_start = now

    def end_head_seq(self):
        self.head_seq_start = -1.0
        self.head_seq = 0

    def clear_effects(self, now):
        self.clock = now
        self.blink_start = -1.0
        self.poke_start = -1.0
        self.wake_start = -1.0
        self.landing_start = -1.0
        self.idle_start = -1.0
        self.sleep_start = -1.0
        self.head_start = -1.0
        self.celebrate_start = -1.0
        self.hungry_start = -1.0
        self.dance_start = -1.0
        self.fat_start = -1.0
        self.holding = False
        self.drag_angle = 0.0
        self._drag_target = 0.0
        self._drag_velocity = 0.0
        self.schedule_blink(now)

    def clear_all(self, now):
        self.drag_start = -1.0
        self.hover_open = False
        self.feed_start = -1.0
        self.walk_start = -1.0
        self.head_seq_start = -1.0
        self.head_seq = 0
        self.clear_effects(now)

    def schedule_blink(self, now):
        self.next_blink = now + 4.0 + self._random.random() * 4.0

    def laugh(self, now):
        if self.playing:
            return False
        self.clear_all(now)
        self.resting = False
        self.start = now
        self.elapsed = 0.0
        self.play_count += 1
        return True

    def stop(self):
        self.start = -1.0
        self.elapsed = 0.0
        self.resting = False
        self.clear_effects(self.clock)

    def stand(self, now):
        if self.resting:
            self.resting = False
            self.clear_all(now)
            self.wake_start = now

    def poke(self, now, x, y):
        if self.playing or self.resting or self.holding or not self.in_belly(x, y):
            return False
        self.clear_all(now)
        self.poke_start = now
        self.poke_x = x
        self.poke_y = y
        return True

    def begin_drag(self, now):
        self.start = -1.0
        self.elapsed = 0.0
        self.clear_all(now)
        self.holding = True
        self.walk_start = now
        self._last_drag_time = now

    def drag(self, now, dx):
        if not self.holding:
            self.begin_drag(now)
        num = max(1.0 / 120.0, now - self._last_drag_time)
        self._last_drag_time = now
        self._drag_target = max(-7.0, min(7.0, dx / num * 0.013))
        self.clock = now

    def end_drag(self, now):
        if self.holding:
            self.holding = False
            self._drag_target = 0.0
            self.clock = now
            self.landing_start = now
            self.schedule_blink(now)

    def suspend(self, now):
        self.start = -1.0
        self.elapsed = 0.0
        self.look = 0.0
        self.look_v = 0.5
        self.drag_start = -1.0
        self.hover_open = False
        self.feed_start = -1.0
        self.clear_effects(now)

    def start_idle(self, now, kind, duration_ms):
        self.clear_all(now)
        self.idle_start = now
        self.idle_end = now + duration_ms / 1000.0
        self.idle_kind = kind

    def sleep(self, now):
        if (self.playing or self.resting or self.holding or self.poking or self.head_poking
                or self.celebrating or self.dragging or self.hover_open or self.feeding):
            return False
        self.clear_all(now)
        self.sleep_start = now
        return True

    def wake(self, now):
        if not self.sleeping:
            return False
        self.sleep_start = -1.0
        self.blink_start = now
        self.schedule_blink(now)
        return True

    def head_poke(self, now):
        if (self.playing or self.resting or self.holding or self.sleeping or self.celebrating
                or self.dragging or self.hover_open or self.feeding):
            return False
        self.clear_all(now)
        self.head_start = now
        return True

    def celebrate(self, now):
        self.clear_all(now)
        self.celebrate_start = now
        self.resting = False

    # ------------------------------------------------------------------ 每帧推进
    def update(self, now, over, duration, blink_duration):
        self.clock = now
        dt = 0.0 if self._previous < 0.0 else min(0.05, max(0.0, now - self._previous))
        self._previous = now

        target = self.look_goal if self.auto_look else (1.0 if over else 0.0)
        step = dt / 0.18
        self.look += max(0.0 - step, min(step, target - self.look))
        target_v = self.look_goal_v if self.auto_look else 0.5
        self.look_v += max(0.0 - step, min(step, target_v - self.look_v))

        if self.playing:
            self.elapsed = max(0.0, now - self.start)
            if self.elapsed >= duration:
                self.start = -1.0
                self.elapsed = duration
                self.resting = False

        if self.waking and now - self.wake_start >= 0.24:
            self.wake_start = -1.0
        if self.poking and now - self.poke_start >= self.POKE_DURATION:
            self.poke_start = -1.0
        if self.landing and now - self.landing_start >= 0.9:
            self.landing_start = -1.0
        if self.blinking and now - self.blink_start >= blink_duration:
            self.blink_start = -1.0
            self.schedule_blink(now)
        if self.idling and now >= self.idle_end:
            self.idle_start = -1.0
        if self.sleeping and now - self.sleep_start >= 600.0:
            self.sleep_start = -1.0
        if self.head_poking and now - self.head_start >= 1.0:
            self.head_start = -1.0
        if self.celebrating and now - self.celebrate_start >= 2.8:
            self.celebrate_start = -1.0
        if self.feeding and now - self.feed_start >= 1.0:
            self.feed_start = -1.0
        if self.hungry and now - self.hungry_start >= 10.0:
            self.hungry_start = -1.0
        if self.dancing and now - self.dance_start >= 8.7:
            self.dance_start = -1.0
        if self.fat and now - self.fat_start >= 6.0:
            self.fat_start = -1.0
        if self.walking and now - self.walk_start >= 4.0:
            self.walk_start = -1.0
            self.landed_walk_at = -1.0
        if not self.walking and self.landed_walk_at >= 0.0:
            self.landed_walk_at = -1.0
        if self.head_sequencing and now - self.head_seq_start >= 8.0:
            self.end_head_seq()
        if (not self.playing and not self.resting and not self.holding and not self.landing
                and not self.poking and not self.waking and not self.blinking
                and not self.has_extra and now >= self.next_blink):
            self.blink_start = now

        if not self.holding or now - self._last_drag_time > 0.1:
            self._drag_target = 0.0
        steps = max(1, int(math.ceil(dt / 0.008)))
        sub = dt / steps
        for _ in range(steps):
            self._drag_velocity += (160.0 * (self._drag_target - self.drag_angle)
                                    - 25.0 * self._drag_velocity) * sub
            self.drag_angle += self._drag_velocity * sub
        self.drag_angle = max(-7.0, min(7.0, self.drag_angle))
        if not self.holding and abs(self.drag_angle) < 0.02 and abs(self._drag_velocity) < 0.05:
            self.drag_angle = 0.0
            self._drag_velocity = 0.0

    # ------------------------------------------------------------------ 命中区
    @staticmethod
    def in_eye(x, y):
        nx = (x - 145.0) / 60.0
        ny = (y - 95.0) / 45.0
        return nx * nx + ny * ny <= 1.0 and y >= 55.0

    @staticmethod
    def in_belly(x, y):
        nx = (x - 107.0) / 75.0
        ny = (y - 211.0) / 75.0
        return nx * nx + ny * ny <= 1.0

    @staticmethod
    def in_head(x, y):
        nx = (x - 145.0) / 56.0
        ny = (y - 62.0) / 52.0
        return nx * nx + ny * ny <= 1.0 and y >= 10.0
