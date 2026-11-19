# 奶蛙桌宠 · Linux / 麒麟 移植版

把原 Windows C#（.NET Framework + WinForms + `UpdateLayeredWindow`）版本移植到
**Python 3 + GTK3**，在银河麒麟 V10（x86_64 / ARM64，X11 会话）与 Ubuntu / Debian
一类桌面上运行。**素材格式完全兼容**：原版的 `素材.nwp`、`walk.nwp`、`dance.mp3` 等
直接可用，无需转换。

> 上游项目：[LIN4RUN/naiwa-desktop-pet](https://github.com/LIN4RUN/naiwa-desktop-pet)（MIT）
> 移植仓库：[Liangzaigrape/naiwa-desktop-pet](https://github.com/Liangzaigrape/naiwa-desktop-pet)

---

## 1. 装哪个包

| 文件 | 适用场景 |
|---|---|
| `naiwa-pet_2.5.1_linux.2_all.deb` | **推荐**。`sudo dpkg -i` 装上，应用菜单里出现「奶蛙桌宠」 |
| `naiwa-pet_2.5.1_linux.2_portable.tar.gz` | 单位电脑没有 sudo 权限时用：解压到自己的家目录直接运行 |

deb 是 **Architecture: all**（纯 Python，无编译产物），x86_64 和 ARM64 的麒麟都能装；
**安装包约 40 MB**。素材为了压体积做了降采样（0.45 倍 + 192 色，alpha 保持 8 位），
默认 80% 大小下与原画质几乎无差别；要全画质就 `SLIM=0 bash linux/build-deb.sh` 自己打。

### 1.1 安装 deb

```bash
sudo dpkg -i naiwa-pet_2.5.1_linux.2_all.deb
# 若提示缺依赖（极少数精简系统）：
sudo apt-get -f install
```

安装后：

* 应用菜单 → 「奶蛙桌宠」（分类：附件/娱乐）
* 或终端执行 `naiwa-pet`

依赖：`python3 (>=3.6)`、`python3-gi`、`gir1.2-gtk-3.0`、`python3-cairo`。
麒麟 V10 桌面版默认就带这些（UKUI 本身就是 GTK3 写的）。
声音另需 `pulseaudio-utils`（`paplay`）或 `alsa-utils`（`aplay`）；`dance.mp3` 建议装
`mpg123`，没装则跳舞时静音，不影响画面。

### 1.2 免安装版

```bash
tar xzf naiwa-pet_2.5.1_linux.2_portable.tar.gz -C ~/
~/naiwa-pet/naiwa-pet        # 直接运行
```

删掉目录即卸载。桌面图标：把 `naiwa-pet.desktop` 里的 `Exec=` 改成你的实际路径，
再复制到 `~/桌面` 或 `~/.local/share/applications/`。

### 1.3 卸载

```bash
sudo dpkg -r naiwa-pet        # 配置和回收站里的文件保留
# 彻底清理：
sudo dpkg -P naiwa-pet
rm -rf ~/.config/naiwa-desktop-pet ~/.local/share/naiwa-desktop-pet
```

---

## 2. 怎么玩

| 操作 | 效果 |
|---|---|
| 鼠标悬停在身上 | 张嘴（准备吃东西） |
| **双击肚子** | 大笑（配音效） |
| **单击 / 拖动** | 把奶蛙举起来，松手会掉下去；快速往上甩会抛起来，落地摔哭 |
| **双击头部** | 三阶段表演：起势 → 愤怒 → 打电话（炸开 6 只小奶蛙跳舞） |
| **把文件拖到嘴上** | 张嘴吃掉 → 文件进回收站（可恢复），饥饿 +1 |
| **中键点奶蛙** | 饿一点（调试用） |
| **右键** | 菜单：饥饿条 / 使用说明书 / 设置（动作预览、大小、声音、音量、自启、全屏隐藏、贴边、退出） |
| 拖到屏幕右缘 | 只露一个头挂边上，点一下回来 |
| 闲置 45s+ | 自己走两步、做小动作；闲置 60s 可能转手舞或睡着 |
| 全屏看视频/PPT | 自动隐藏，退出全屏再出现（可在设置里关） |

饥饿：初始 5/10，每 10 分钟 -1，低于 3 会开始乞讨；喂满 10 点会冒烟变成胖袋鼠。
配置写在 `~/.config/naiwa-desktop-pet/settings.ini`，键名与 Windows 版完全一致，
可以从 Windows 版直接拷过来。

---

## 3. 麒麟系统注意事项

1. **必须是 X11 会话**（麒麟 V10 默认就是）。如果登录的是 Wayland 会话，
   启动脚本会自动设 `GDK_BACKEND=x11` 走 XWayland，透明/穿透仍然有效（少数
   Wayland 合成器对「点穿」支持不完整，此时只有异形外观、没有点击穿透）。
2. **需要开启桌面合成（compositing）**。UKUI / MATE / GNOME / KDE 默认开启；
   如果你装了很精简的窗口管理器（如 openbox 且无 compositor），奶蛙周围会出现
   黑底方块 —— 这是没有合成器的原因，装个 `picom` / `xcompmgr` 就好。
3. **托盘图标**：UKUI 面板如果没有「系统托盘」插件，图标不显示，但右键奶蛙
   的菜单功能完全一样，不影响使用。
4. **单位电脑不能联网**时，deb 的依赖（`python3-gi` 等）通常已经预装；
   若确实缺包，可用同版本麒麟的 ISO 做本地源，或改用免安装版
   （免安装版只依赖系统自带的 python3-gi）。

---

## 4. 从源码构建

```bash
# 1) 取代码
git clone https://github.com/Liangzaigrape/naiwa-desktop-pet.git
cd naiwa-desktop-pet

# 2) 取大素材（不入库）：从上游 Release 下载 portable.zip 后解出
curl -L -o /tmp/portable.zip \
  https://github.com/LIN4RUN/naiwa-desktop-pet/releases/download/v2.5.1/naiwa-pet-v2.5.1-portable.zip
python3 linux/tools/extract_assets.py /tmp/portable.zip ~/naiwa-assets
#    把仓库自带的素材也复制过去，凑成完整的一套
cp -n *.nwp *.wav ~/naiwa-assets/

# 3) 打包（需要 dpkg-deb、python3-gi、pillow；图标用 GdkPixbuf 现场生成）
#    默认会做素材瘦身（0.45 倍 + 192 色），并调用 ffmpeg 把舞曲转成 wav
bash linux/build-deb.sh ~/naiwa-assets
# 想打全画质包（体积回到 ~180 MB）：
#   SLIM=0 bash linux/build-deb.sh ~/naiwa-assets
# 产物：linux/dist/naiwa-pet_2.5.1_linux.2_all.deb
#       linux/dist/naiwa-pet_2.5.1_linux.2_portable.tar.gz
```

构建脚本做三件事：把 `linux/naiwa-pet/` 装到 `/usr/lib/naiwa-pet/`、素材装到
`/usr/share/naiwa-pet/`、生成 desktop 文件 + 256×256 图标 + `DEBIAN/control`，
最后用 `dpkg-deb --root-owner-group` 打包（不依赖 `fakeroot`）。

### 开发与自测

```bash
# 不显示窗口，只校验素材并渲染各状态到 PNG
NAIWA_PET_DATA=~/naiwa-assets python3 -m naiwa --self-test /tmp/selftest
# 在 Xvfb 里跑真实窗口 + 截图的端到端测试
bash linux/tools/e2e.sh ~/naiwa-assets /tmp/e2e
# 逐个触发菜单/设置项的 UI 自测
bash linux/tools/ui_selftest.sh
```

---

## 5. 代码结构

```
linux/
├── build-deb.sh                 # 一键打包 deb + 免安装包
├── package/                     # deb 里与代码无关的固定文件
│   ├── usr/bin/naiwa-pet        # 启动脚本（设 GDK_BACKEND / PYTHONPATH）
│   ├── usr/share/applications/naiwa-pet.desktop
├── tools/
│   ├── extract_assets.py        # 解 portable.zip 并修正中文名乱码
│   ├── make_icon.sh             # 从素材.nwp 生成图标
│   ├── e2e.sh / ui_selftest.sh  # 自动化测试
│   └── smoke_render.py          # 无素材时的渲染冒烟测试
└── naiwa-pet/naiwa/
    ├── app.py                   # 入口、命令行、单实例、控制通道、--self-test
    ├── pet.py                   # 主窗口：事件、物理、菜单、拖放、全屏、贴边
    ├── motion.py                # 状态机（逐项移植自 Motion.cs）
    ├── render.py                # cairo 合成（2 倍绘制 + 降采样，移植自 Renderer.cs）
    ├── assets.py                # .nwp（zip + PNG 帧）按需解码 + LRU 缓存
    ├── settings.py              # settings.ini（键名与 Windows 版一致）
    ├── audio.py                 # paplay/aplay/mpg123/ffplay 播放与音量
    ├── trash.py                 # freedesktop.org 回收站（纯标准库）
    ├── tray.py                  # Gtk.StatusIcon 托盘
    └── xutil.py                 # ctypes 调 libX11 做全屏检测
```

### 与 Windows 版的对应关系

| Windows (C#) | Linux (Python) | 说明 |
|---|---|---|
| `UpdateLayeredWindow` 分层窗口 | GTK3 RGBA visual + cairo | 逐像素 alpha，效果等价 |
| 按像素命中 (`WM_NCHITTEST` + 蒙版) | `input_shape_combine_region` | 透明处点击直接穿透到桌面 |
| `GDI+` 绘制 + 2 倍降采样 | cairo + 2 倍画布 | 同样的抗锯齿策略 |
| `WMPlayer.OCX` | `paplay` / `aplay` / `mpg123` | 音量、静音、渐隐对应实现 |
| `SHFileOperation` 回收站 | freedesktop Trash 规范 | 纯标准库实现，可恢复 |
| 注册表 `Run` 自启 | `~/.config/autostart/*.desktop` | 菜单里同样能开关 |
| `NotifyIcon` 托盘 | `Gtk.StatusIcon` | 面板无托盘区时静默跳过 |
| `GetForegroundWindow` 全屏检测 | `_NET_WM_STATE_FULLSCREEN` | 走 X11 属性 |
| `--self-test/--demo/--probe` | `--self-test/--demo` + 控制 socket | 见 `naiwa-pet --help` |

### 已知差异

* 眼珠跟随用的是原版 `look/*.png` 11 帧贴图（与原版一致），`eye_art.nwp` 未使用
  （Windows 版同样没用到，属于遗留素材）。
* 托盘菜单与奶蛙右键菜单是同一个 `Gtk.Menu`；Windows 版的「音量滑条」在 Linux 版
  里是菜单内嵌 `Gtk.Scale`，另外加了滚轮直接调音量。
* 全屏隐藏的判定依赖 `_NET_WM_STATE_FULLSCREEN`，个别用 `override-redirect`
  做全屏的播放器可能检测不到。
* **舞曲 `dance.mp3` 其实是 MP4**（手机录屏改名，HEVC 视频 + AAC 音频）。
  `paplay` / `aplay` / `mpg123` 都放不了它，所以打包时用 `ffmpeg` 把音轨转成
  `dance.wav` 一起装（运行时优先用 wav）。没装 ffmpeg 打出来的包跳舞会静音，
  但不影响画面和其它音效。

---

## 6. 常见问题

**启动没反应 / 一闪就退**：终端里执行 `naiwa-pet` 看报错；日志在
`~/.local/share/naiwa-desktop-pet/error.log`。

**提示 `Namespace Gtk not available`**：装依赖
`sudo apt install python3-gi gir1.2-gtk-3.0 python3-cairo`。

**奶蛙周围有黑框**：桌面没有合成器，见第 3 节第 2 条。

**点击穿透不生效（点到透明处也算点奶蛙）**：说明 `numpy` 不在（用于快速生成
点击蒙版），装 `sudo apt install python3-numpy` 即可；没有它也能用，只是异形点击区
退化成整个窗口矩形。

**没有声音**：`command -v paplay aplay mpg123` 看有没有播放器；装了但没声音，检查
`pavucontrol` 里奶蛙的输出设备。菜单 → 设置 → 声音 / 音量 里也能调。

**开机自启**：右键 → 设置 → 开机自启动，会在
`~/.config/autostart/naiwa-pet.desktop` 写一条；不需要时再点一次取消。
