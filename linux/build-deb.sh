#!/bin/bash
# 奶蛙桌宠 Linux/麒麟 版打包脚本
#
# 用法：./build-deb.sh [素材目录]
#   素材目录默认用仓库根目录（即包含 素材.nwp / walk.nwp / idle_gif.nwp 的目录）。
#   大素材（素材.nwp、idle_gif.nwp、drag.nwp、dance.mp3）不入库，
#   需要从上游 Release 的 portable.zip 里解出来放到素材目录。
#
# 产物：dist/naiwa-pet_<版本>_all.deb      可安装的 deb（架构无关）
#       dist/naiwa-pet_<版本>_portable.tar.gz  免安装版（解压即用）
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
ASSETS="${1:-$ROOT}"
VERSION="${VERSION:-2.5.1}"
REVISION="${REVISION:-linux.1}"
PKGVER="${VERSION}-${REVISION}"
DIST="$HERE/dist"
BUILD="$HERE/.build"
STAGE="$BUILD/stage"

REQUIRED="素材.nwp walk.nwp hold.nwp head.nwp seq.nwp dance.nwp hunger.nwp fat.nwp rest.nwp rest2.nwp sad.nwp idle_gif.nwp drag.nwp feed.nwp 原版笑声.wav cry.wav dance.mp3"

die() { echo "错误：$*" >&2; exit 1; }

echo "== 检查素材 ($ASSETS) =="
missing=""
for f in $REQUIRED; do
    [ -f "$ASSETS/$f" ] || missing="$missing $f"
done
[ -z "$missing" ] || die "缺少素材:$missing
请先从上游 Release 的 naiwa-pet-v${VERSION}-portable.zip 里把这些文件解出来（见 linux/README-linux.md）。"

echo "== 清理 =="
rm -rf "$BUILD" "$DIST"
mkdir -p "$STAGE" "$DIST"

echo "== 复制程序 =="
install -d "$STAGE/usr/lib/naiwa-pet/naiwa"
cp -f "$HERE"/naiwa-pet/naiwa/*.py "$STAGE/usr/lib/naiwa-pet/naiwa/"
install -d "$STAGE/usr/bin"
install -m 0755 "$HERE/package/usr/bin/naiwa-pet" "$STAGE/usr/bin/naiwa-pet"

echo "== 复制素材 =="
install -d "$STAGE/usr/share/naiwa-pet"
for f in $REQUIRED; do
    install -m 0644 "$ASSETS/$f" "$STAGE/usr/share/naiwa-pet/$f"
done

echo "== 桌面文件 / 图标 =="
install -d "$STAGE/usr/share/applications"
install -m 0644 "$HERE/package/usr/share/applications/naiwa-pet.desktop" \
    "$STAGE/usr/share/applications/naiwa-pet.desktop"
install -d "$STAGE/usr/share/icons/hicolor/256x256/apps"
bash "$HERE/tools/make_icon.sh" "$ASSETS" "$STAGE/usr/share/icons/hicolor/256x256/apps/naiwa-pet.png"
cp -f "$STAGE/usr/share/icons/hicolor/256x256/apps/naiwa-pet.png" "$STAGE/usr/share/naiwa-pet/naiwa-pet.png"

echo "== 文档 =="
install -d "$STAGE/usr/share/doc/naiwa-pet"
[ -f "$ROOT/LICENSE" ] && install -m 0644 "$ROOT/LICENSE" "$STAGE/usr/share/doc/naiwa-pet/copyright"
install -m 0644 "$HERE/README-linux.md" "$STAGE/usr/share/doc/naiwa-pet/README-linux.md"
if [ -f "$ROOT/使用说明.txt" ]; then
    install -m 0644 "$ROOT/使用说明.txt" "$STAGE/usr/share/naiwa-pet/使用说明.txt"
fi
cat > "$STAGE/usr/share/doc/naiwa-pet/changelog" <<EOF
naiwa-pet ($PKGVER) unstable; urgency=medium

  * 首个 Linux/麒麟 移植版：Python 3 + GTK3 重写窗口层与交互，
    沿用原版 .nwp 素材与状态机参数。

 -- Liangzaigrape <2817680489@qq.com>  $(date -R)
EOF
gzip -9nf "$STAGE/usr/share/doc/naiwa-pet/changelog"
[ -f "$STAGE/usr/share/doc/naiwa-pet/copyright" ] || \
    printf 'MIT License\nhttps://github.com/LIN4RUN/naiwa-desktop-pet\n' \
        > "$STAGE/usr/share/doc/naiwa-pet/copyright"

echo "== DEBIAN 控制信息 =="
install -d "$STAGE/DEBIAN"
SIZE=$(du -sk "$STAGE/usr" | cut -f1)
cat > "$STAGE/DEBIAN/control" <<EOF
Package: naiwa-pet
Version: $PKGVER
Section: graphics
Priority: optional
Architecture: all
Installed-Size: $SIZE
Depends: python3 (>= 3.6), python3-gi, gir1.2-gtk-3.0, python3-cairo
Recommends: pulseaudio-utils | alsa-utils, mpg123
Maintainer: Liangzaigrape <2817680489@qq.com>
Homepage: https://github.com/Liangzaigrape/naiwa-desktop-pet
Description: 奶蛙桌宠（Linux/麒麟 移植版）
 透明异形窗口的桌面宠物：眼睛跟着鼠标转、可以拖着抛着玩、会自己走路睡觉，
 会饿会撒娇，把文件拖到它嘴上就吃掉（移入回收站）。
 .
 由原 Windows C# 版（LIN4RUN/naiwa-desktop-pet）移植，改用 Python 3 + GTK3，
 素材格式（.nwp）与原版完全一致，原版的素材包可直接使用。
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
fi
exit 0
EOF
cat > "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
fi
exit 0
EOF
chmod 0755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

echo "== md5sums =="
( cd "$STAGE" && find usr -type f -print0 | sort -z | xargs -0 md5sum > DEBIAN/md5sums )

echo "== 构建 deb =="
chmod 0644 "$STAGE/DEBIAN/control" "$STAGE/DEBIAN/md5sums"
find "$STAGE" -type d -exec chmod 0755 {} +
DEB="$DIST/naiwa-pet_${VERSION}_linux.1_all.deb"
# 素材是已压缩的 PNG，xz 收益极小但很慢，所以用 gzip
dpkg-deb --root-owner-group -Zgzip -z9 --build "$STAGE" "$DEB"
echo "deb -> $DEB"

echo "== 构建免安装包 =="
PORT="$BUILD/portable/naiwa-pet"
mkdir -p "$PORT/naiwa" "$PORT/share"
cp -f "$HERE"/naiwa-pet/naiwa/*.py "$PORT/naiwa/"
for f in $REQUIRED; do
    cp -f "$ASSETS/$f" "$PORT/share/$f"
done
cp -f "$STAGE/usr/share/naiwa-pet/使用说明.txt" "$PORT/share/" 2>/dev/null || true
cp -f "$STAGE/usr/share/icons/hicolor/256x256/apps/naiwa-pet.png" "$PORT/share/naiwa-pet.png"
cat > "$PORT/naiwa-pet" <<'EOF'
#!/bin/sh
HERE="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
export NAIWA_PET_DATA="$HERE/share"
[ "${NAIWA_BACKEND:-x11}" = "x11" ] && export GDK_BACKEND=x11
exec python3 -m naiwa "$@"
EOF
chmod 0755 "$PORT/naiwa-pet"
cat > "$PORT/README.txt" <<'EOF'
奶蛙桌宠 免安装版
----------------
1. 把整个 naiwa-pet 目录放到你有权限的位置，例如 ~/naiwa-pet
2. 终端里执行：  ~/naiwa-pet/naiwa-pet
   桌面快捷方式： 编辑 naiwa-pet.desktop 里的路径后双击
3. 需要系统自带 python3、python3-gi、gir1.2-gtk-3.0
   （麒麟 V10 桌面默认就有；若提示缺 gi，执行：
     sudo apt install python3-gi gir1.2-gtk-3.0 python3-cairo）
4. 卸载：直接删掉整个目录。
EOF
sed "s#Exec=naiwa-pet#Exec=$PORT/naiwa-pet#" \
    "$HERE/package/usr/share/applications/naiwa-pet.desktop" > "$PORT/naiwa-pet.desktop"
TAR="$DIST/naiwa-pet_${VERSION}_linux.1_portable.tar.gz"
tar -C "$BUILD/portable" -czf "$TAR" naiwa-pet
echo "portable -> $TAR"

echo
echo "完成："
ls -lh "$DIST"
