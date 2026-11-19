#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""".nwp 素材包结构自检：条目类型 / 路径穿越 / 尾随数据 / PNG magic / CRC。

用法：python3 linux/tools/audit_nwp.py [素材目录]
默认检查 /usr/share/naiwa-pet（安装后）或仓库根目录。
"""
import glob
import os
import struct
import sys
import zipfile


def default_root():
    for cand in ("/usr/share/naiwa-pet", os.path.join(os.path.dirname(__file__), "..", "..")):
        if glob.glob(os.path.join(cand, "*.nwp")):
            return cand
    return "."


def check(root):
    total = 0
    bad = []
    for path in sorted(glob.glob(os.path.join(root, "*.nwp"))):
        size = os.path.getsize(path)
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            total += len(infos)
            odd = [i.filename for i in infos
                   if not (i.filename.endswith(".png") or i.filename == "metadata.json")]
            traversal = [i.filename for i in infos
                         if i.filename.startswith("/") or ".." in i.filename]
            with open(path, "rb") as f:
                data = f.read()
            eocd = data.rfind(b"PK\x05\x06")
            eocd_len = 22 + struct.unpack("<H", data[eocd + 20:eocd + 22])[0] if eocd >= 0 else 0
            trailing = size - (eocd + eocd_len) if eocd >= 0 else -1
            magic_ok = True
            for info in infos[:5] + infos[-3:]:
                if info.filename.endswith(".png") and not z.read(info.filename)[:8].startswith(b"\x89PNG"):
                    magic_ok = False
            try:
                crc_ok = z.testzip() is None
            except Exception:  # noqa: BLE001
                crc_ok = False
        ok = not (odd or traversal or trailing != 0 or not magic_ok or not crc_ok)
        if not ok:
            bad.append((os.path.basename(path), odd, traversal, trailing, magic_ok, crc_ok))
        print("%-16s %9d  entries=%-4d odd=%-2d traversal=%-2d trailing=%-3d png=%-5s crc=%-5s %s"
              % (os.path.basename(path), size, len(infos), len(odd), len(traversal),
                 trailing, magic_ok, crc_ok, "OK" if ok else "异常"))
    print("\n总条目数:", total)
    print("异常文件:", bad if bad else "无")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(check(sys.argv[1] if len(sys.argv) > 1 else default_root()))
