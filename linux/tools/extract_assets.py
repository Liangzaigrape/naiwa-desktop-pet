#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从上游 portable.zip 里解出素材，并修正常见的中文文件名乱码。

Info-ZIP 的 unzip 在 zip 没打 UTF-8 标记时会把中文名按 CP437 解出来，
变成 "ч┤ацЭР.nwp" 这种乱码；这里用「名字的 CP437 字节再按 UTF-8 解码」还原。

用法：extract_assets.py <portable.zip> <输出目录>
"""
import os
import sys
import zipfile


def fixed_name(info):
    name = info.filename
    if info.flag_bits & 0x800:
        return name
    try:
        raw = name.encode("cp437")
    except UnicodeEncodeError:
        return name
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return name


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    with zipfile.ZipFile(src) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = os.path.basename(fixed_name(info))
            if not name:
                continue
            target = os.path.join(out, name)
            with z.open(info) as fin, open(target, "wb") as fout:
                while True:
                    chunk = fin.read(1 << 20)
                    if not chunk:
                        break
                    fout.write(chunk)
            print("%-28s %8.1f MB" % (name, os.path.getsize(target) / 1048576.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
