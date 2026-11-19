#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""奶蛙桌宠 Linux 版入口。

命令行：
  naiwa-pet                启动桌宠
  naiwa-pet --quit         让正在运行的桌宠退出
  naiwa-pet --hungry       让桌宠饿一点（调试用）
  naiwa-pet --home         把桌宠叫回屏幕右下角
  naiwa-pet --demo KEY     立即播放某个动作
  naiwa-pet --self-test DIR  不显示窗口，跑素材自检并把各状态渲染成 PNG
"""
import errno
import os
import signal
import socket
import sys
import traceback
import zipfile

APP_ID = "naiwa-desktop-pet"
SOCKET_NAME = "control.sock"


def _state_dir():
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    path = os.path.join(base, APP_ID)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def _socket_path():
    return os.path.join(_state_dir(), SOCKET_NAME)


def _send_command(cmd, wait=1.5):
    path = _socket_path()
    if not os.path.exists(path):
        return None
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(wait)
        sock.connect(path)
        sock.sendall((cmd + "\n").encode("utf-8"))
        data = sock.recv(4096)
        sock.close()
        return data.decode("utf-8", "replace").strip()
    except (OSError, socket.timeout):
        return None


def _data_folder():
    env = os.environ.get("NAIWA_PET_DATA")
    if env and os.path.isdir(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    for cand in (
        "/usr/share/naiwa-pet",
        os.path.join(root, "share"),
        os.path.join(root, "assets"),
        root,
        here,
    ):
        if os.path.exists(os.path.join(cand, "素材.nwp")):
            return cand
    return "/usr/share/naiwa-pet"


# --------------------------------------------------------------------- 自检
REQUIRED = [
    "素材.nwp", "walk.nwp", "hold.nwp", "head.nwp", "seq.nwp", "dance.nwp",
    "hunger.nwp", "fat.nwp", "rest.nwp", "rest2.nwp", "sad.nwp", "idle_gif.nwp",
    "drag.nwp", "feed.nwp", "原版笑声.wav", "cry.wav", "dance.mp3",
]


def _inspect_nwp(path):
    """不依赖 GTK 的 .nwp 结构检查。"""
    info = {"path": path, "ok": False}
    try:
        with zipfile.ZipFile(path) as z:
            import json
            meta = json.loads(z.read("metadata.json").decode("utf-8"))
            frames = int(meta.get("frames", 0) or 0)
            names = z.namelist()
            pngs = [n for n in names if n.endswith(".png")]
            info.update({"frames": frames, "pngs": len(pngs),
                         "width": meta.get("width"), "height": meta.get("height"),
                         "fps": meta.get("fps")})
            missing = []
            for i in range(frames):
                if not any(n.endswith("/%04d.png" % i) for n in names):
                    missing.append(i)
                    if len(missing) > 3:
                        break
            info["missing"] = missing
            info["ok"] = frames > 0 and len(pngs) >= frames and not missing
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)
    return info


def self_test(out_dir):
    folder = _data_folder()
    os.makedirs(out_dir, exist_ok=True)
    lines = ["# 奶蛙桌宠 Linux 版自检", "", "素材目录：%s" % folder, ""]
    all_ok = True
    for name in REQUIRED:
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            lines.append("- [缺失] %s" % name)
            all_ok = False
            continue
        size = os.path.getsize(path)
        if name.endswith(".nwp"):
            info = _inspect_nwp(path)
            status = "OK" if info["ok"] else "异常"
            if not info["ok"]:
                all_ok = False
            lines.append("- [%s] %s  %.1f MB  帧数=%s  %sx%s  %sfps"
                         % (status, name, size / 1048576.0, info.get("frames"),
                            info.get("width"), info.get("height"), info.get("fps")))
        else:
            lines.append("- [OK] %s  %.1f MB" % (name, size / 1048576.0))

    try:
        from .assets import Assets
        from .motion import Motion
        from .render import Renderer
        import cairo
        assets = Assets(folder)
        lines.append("")
        lines.append("素材加载：%s" % ("成功" if assets.ok else "失败：%s" % assets.error))
        all_ok = all_ok and assets.ok
        if assets.ok:
            lines.append("本体画布：%dx%d，帧数 %d，%sfps，眼睛 %d 帧，眨眼 %d 帧"
                         % (assets.width, assets.height, assets.count, assets.fps,
                            assets.eyes.eye_count, assets.eyes.blink_count))
            renderer = Renderer(assets)
            motion = Motion()
            now = 100.0
            states = [
                ("idle", lambda: None),
                ("blink", lambda: setattr(motion, "blink_start", now)),
                ("laugh", lambda: motion.laugh(now)),
                ("walk", lambda: motion.start_walk(now, 1)),
                ("drag", lambda: motion.start_drag(now, 3.0)),
                ("hungry", lambda: motion.start_hungry(now)),
                ("dance", lambda: motion.start_dance(now)),
                ("fat", lambda: motion.start_fat(now)),
                ("sleep", lambda: motion.sleep(now)),
                ("idle5", lambda: motion.start_idle(now, 5, 16000)),
                ("idle6", lambda: motion.start_idle(now, 6, 2000)),
                ("seq1", lambda: motion.start_head_seq(now)),
            ]
            for name, setup in states:
                motion.__init__()
                motion.update(now, False, assets.duration, 1.0)
                setup()
                motion.clock = now + 0.3
                motion.update(now + 0.3, False, assets.duration, 1.0)
                for scale in (100, 80):
                    cw2, ch2, _rect, _p = renderer.layout(motion, scale, False)
                    w, h = max(1, cw2 // 2), max(1, ch2 // 2)
                    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
                    ctx = cairo.Context(surf)
                    renderer.render(ctx, motion, scale, False, "自检" if name == "idle" else None, False)
                    surf.flush()
                    out = os.path.join(out_dir, "%s_%d.png" % (name, scale))
                    surf.write_to_png(out)
                    lines.append("  渲染 %-7s %3d%% → %dx%d" % (name, scale, w, h))
            motion.__init__()
            motion.update(now, False, assets.duration, 1.0)
            moved = 0
            t = now
            while t < now + 40.0:
                t += 0.05
                motion.update(t, False, assets.duration, 1.0)
                if motion.blinking or motion.idling or motion.sleeping:
                    moved += 1
            lines.append("状态机 40 秒模拟：眨眼/待机触发 %d 次 %s"
                         % (moved, "OK" if moved else "异常"))
            if not moved:
                all_ok = False
    except Exception as exc:  # noqa: BLE001
        lines.append("渲染自检失败：%s" % exc)
        lines.append(traceback.format_exc())
        all_ok = False

    lines.insert(3, "总体结果：%s\n" % ("通过" if all_ok else "有问题，见下"))
    report = os.path.join(out_dir, "self-test.md")
    with open(report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\n报告：%s" % report)
    return 0 if all_ok else 1


# --------------------------------------------------------------------- 控制通道
class ControlServer(object):
    def __init__(self, window):
        self.window = window
        self.path = _socket_path()
        self.sock = None
        try:
            if os.path.exists(self.path):
                os.unlink(self.path)
        except OSError:
            pass

    def start(self):
        try:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.bind(self.path)
            # 只允许本用户读写这个控制 socket
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
            self.sock.listen(4)
            self.sock.setblocking(False)
            import gi
            gi.require_version("GLib", "2.0")
            from gi.repository import GLib
            GLib.io_add_watch(self.sock, GLib.IO_IN, self._on_readable)
            return True
        except OSError:
            return False

    @staticmethod
    def _peer_uid(conn):
        """取对端 uid；不是本用户就直接拒绝（仅 Linux 有 SO_PEERCRED）。"""
        try:
            import struct
            raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            _pid, uid, _gid = struct.unpack("3i", raw)
            return uid
        except (OSError, AttributeError):
            return os.getuid()

    def _on_readable(self, _fd, _cond):
        try:
            conn, _addr = self.sock.accept()
        except OSError:
            return True
        try:
            if self._peer_uid(conn) != os.getuid():
                return True
            conn.settimeout(0.5)
            data = conn.recv(1024).decode("utf-8", "replace").strip()
            conn.sendall((self._handle(data) + "\n").encode("utf-8"))
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass
        return True

    def _handle(self, cmd):
        import gi
        gi.require_version("GLib", "2.0")
        from gi.repository import GLib
        win = self.window
        if cmd == "quit":
            GLib.idle_add(win.quit_app)
            return "bye"
        if cmd == "hungry":
            GLib.idle_add(win._eat_down)
            return "ok"
        if cmd == "home":
            GLib.idle_add(win.home)
            return "ok"
        if cmd.startswith("demo:"):
            key = cmd.split(":", 1)[1]
            GLib.idle_add(lambda: win._demo_action(key))
            return "ok"
        if cmd == "status":
            return "scale=%d hunger=%d visible=%s" % (
                win.settings.scale, win.settings.hunger, not win.hidden_for_fullscreen)
        return "unknown"

    def close(self):
        try:
            if self.sock is not None:
                self.sock.close()
        except OSError:
            pass
        try:
            if os.path.exists(self.path):
                os.unlink(self.path)
        except OSError:
            pass


# --------------------------------------------------------------------- main
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] == "--self-test":
        out = argv[1] if len(argv) > 1 else os.path.join(os.getcwd(), "self-test")
        return self_test(out)

    if argv and argv[0] in ("--quit", "--hungry", "--home"):
        cmd = {"--quit": "quit", "--hungry": "hungry", "--home": "home"}[argv[0]]
        reply = _send_command(cmd)
        if reply is None:
            sys.stderr.write("奶蛙似乎没有在运行。\n")
            return 1
        return 0

    if argv and argv[0] == "--demo":
        if len(argv) < 2:
            sys.stderr.write("用法：naiwa-pet --demo <动作名>\n")
            return 2
        reply = _send_command("demo:" + argv[1])
        if reply is None:
            sys.stderr.write("奶蛙似乎没有在运行。\n")
            return 1
        return 0

    # 已有实例在跑：把窗口叫回前台然后退出
    reply = _send_command("home")
    if reply is not None:
        return 0

    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    return run_gui()


def run_gui():
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib, Gtk

    folder = _data_folder()
    from .assets import Assets
    from .pet import PetWindow

    if not Gtk.init_check(sys.argv)[0]:
        sys.stderr.write(
            "无法连接图形界面。\n"
            "如果你在 Wayland 桌面上，请设置 GDK_BACKEND=x11 后重试（本程序需要 X11/XWayland 才能做透明异形窗口）。\n")
        return 3

    try:
        assets = Assets(folder)
    except Exception as exc:  # noqa: BLE001
        _report_error(exc, folder)
        return 4
    if not assets.ok:
        _report_error(RuntimeError(assets.error), folder)
        return 4

    window = PetWindow(assets, testing=False)
    server = ControlServer(window)
    server.start()

    def on_term(_signum, _frame):
        GLib.idle_add(window.quit_app)

    try:
        signal.signal(signal.SIGTERM, on_term)
        signal.signal(signal.SIGINT, on_term)
    except (ValueError, OSError):
        pass

    try:
        Gtk.main()
    finally:
        server.close()
    return 0


def _report_error(exc, folder):
    sys.stderr.write("奶蛙没能启动：%s\n素材目录：%s\n" % (exc, folder))
    try:
        path = os.path.join(_state_dir(), "error.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s %s\n%s\n" % (__import__("time").strftime("%F %T"), exc,
                                    traceback.format_exc()))
    except OSError:
        pass
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
        dialog = Gtk.MessageDialog(
            message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK,
            text="奶蛙暂时没能启动")
        dialog.format_secondary_text(
            "请确认素材文件完整（素材.nwp 等）。\n\n错误：%s\n素材目录：%s" % (exc, folder))
        dialog.run()
        dialog.destroy()
    except Exception:  # noqa: BLE001
        pass
