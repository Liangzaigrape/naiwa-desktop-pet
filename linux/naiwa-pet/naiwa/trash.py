#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把文件移入回收站 —— 按 freedesktop.org Trash 规范实现。

只依赖 Python 标准库，不需要 gio / gvfs，麒麟、Ubuntu 都能用。
"""
import os
import shutil
import time
import urllib.parse

TRASH_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", "Trash")
FILES_DIR = os.path.join(TRASH_DIR, "files")
INFO_DIR = os.path.join(TRASH_DIR, "info")

_HOME = os.path.expanduser("~")


def _ensure_dirs():
    for d in (TRASH_DIR, FILES_DIR, INFO_DIR):
        os.makedirs(d, exist_ok=True)


def _unique_name(name):
    candidate = name
    stem, ext = os.path.splitext(name)
    n = 1
    while os.path.exists(os.path.join(FILES_DIR, candidate)):
        candidate = "%s.%d%s" % (stem, n, ext)
        n += 1
    return candidate


def _path_for_url(path):
    """文件在原目录里的删除时间戳，用于恢复时的原名。"""
    return "file://" + urllib.parse.quote(os.path.abspath(path))


def move_to_trash(path):
    """把 path 移入回收站；成功返回 True。"""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return False
    if os.path.abspath(path).startswith(TRASH_DIR + os.sep):
        return False
    _ensure_dirs()
    name = os.path.basename(path.rstrip(os.sep)) or "item"
    target_name = _unique_name(name)
    target = os.path.join(FILES_DIR, target_name)
    info_path = os.path.join(INFO_DIR, target_name + ".trashinfo")
    try:
        shutil.move(path, target)
    except (OSError, shutil.Error):
        return False
    try:
        del_time = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        with open(info_path, "w", encoding="utf-8") as f:
            f.write("[Trash Info]\n")
            f.write("Path=%s\n" % urllib.parse.quote(os.path.abspath(path)))
            f.write("DeletionDate=%s\n" % del_time)
    except OSError:
        pass
    return True


def move_all(paths):
    ok = 0
    for p in paths:
        if move_to_trash(p):
            ok += 1
    return ok
