#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI 逻辑自测：在 Xvfb 里建真实窗口，逐个触发菜单项与设置项，确认不炸。"""
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.environ.get(
    "NAIWA_APP", "/usr/lib/naiwa-pet"))

import gi  # noqa: E402
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from naiwa.assets import Assets  # noqa: E402
from naiwa.pet import PetWindow  # noqa: E402

FOLDER = os.environ["NAIWA_PET_DATA"]
failures = []


def check(name, fn):
    try:
        fn()
        print("  ok   %s" % name)
    except Exception as exc:  # noqa: BLE001
        failures.append((name, exc))
        print("  FAIL %s: %s" % (name, exc))
        traceback.print_exc()


def main():
    assets = Assets(FOLDER)
    if not assets.ok:
        print("素材加载失败:", assets.error)
        return 1
    win = PetWindow(assets, testing=False)
    win.show_all()

    def run():
        menu = win._build_menu()
        win._update_menu_checks(menu)
        check("菜单构建", lambda: menu.get_children())
        check("声音开关", lambda: (win.set_sound(False), win.set_sound(True)))
        check("音量", lambda: (win.set_volume(40), win.set_volume(100)))
        check("静音", lambda: (win.toggle_mute(), win.toggle_mute()))
        for pct in (50, 65, 80, 110, 150):
            check("大小 %d%%" % pct, lambda p=pct: win.set_size(p))
        check("重绘", lambda: win._render_now(force=True))
        check("全屏隐藏开关", lambda: (win.set_autohide(False), win.set_autohide(True)))
        check("贴边", lambda: (win.set_edge(True), win.set_edge(False)))
        check("回到原位", win.home)
        check("气泡", lambda: win.show_bubble("测试气泡", 3))
        check("饥饿-1", win._eat_down)
        check("大笑", win.laugh)
        check("动作-行走", lambda: win._demo_action("walk"))
        check("动作-转手舞", lambda: win._demo_action("idle5"))
        check("动作-睡觉", lambda: win._demo_action("sleep"))
        check("动作-炸开舞群", lambda: win._demo_action("seq3"))
        # 用临时文件测试「拖进来回收」，别把脚本自己删了
        fd, tmp = tempfile.mkstemp(prefix="naiwa-drop-", suffix=".txt")
        os.close(fd)
        check("拖文件回收", lambda: win._on_file_drop([tmp]))
        check("右键菜单复用", lambda: win._build_menu())
        check("尺寸计算", lambda: (win._surface_width_height(), win._pet_height()))
        Gtk.main_quit()
        return False

    GLib.timeout_add(800, run)
    GLib.timeout_add(8000, Gtk.main_quit)
    Gtk.main()
    print("\n失败 %d 项" % len(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
