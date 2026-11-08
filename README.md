# dsh-pixelbar

把「花再 Halo PixelBar」桌面像素屏变成 DSH 里可直呼的工具——推一行字、切场景、改屏色、调氛围灯、控音量，全部一句话搞定。

聊天里不用再记命令、也不用先翻文档：在 DSH 里直接说「像素屏推个『在』」，`pixelbar` 工具就发过去了。

> DSH 插件外壳 + 独立可用的 Python HID 脚本，两层都能单独跑。

## 特性

| 能力 | 说明 |
| --- | --- |
| 推文字 | 16 字符 / 48 字节上限，7 种颜色、6 种布局（含左右滚动） |
| 自动回时钟 | 推完默认 15 秒切回时钟界面，避免通知一直挂在屏上 |
| 场景切换 | clock / game / work / read / cats / dogs / memes / cyber / waves |
| 屏主题色 | 带颜色校准表，补偿这块屏的 R 偏弱、B 偏强的色偏 |
| 氛围灯 | 6 种灯效 + 颜色 + 亮度 + 速度 |
| 硬件音量 | 查询 / 设置 0–16 |
| 状态检查 | 查控制接口是否在线 |

实测延迟（Windows 11 + Python 3.13）：`status` 约 137 ms，`text` 推送约 73 ms。每次调用起一个短命 python 进程，没引入长驻桥。

## 环境要求

- Windows（脚本用 `windowsHide` + `pythonw.exe` 规避黑框闪烁，其他平台未验证）
- 花再 Halo PixelBar 设备，USB 连接
- Python 3.8+
- `hidapi`：

  ```powershell
  python -m pip install hidapi
  ```

- Node.js 18+（仅 DSH 插件外壳需要）

> 设备标识：`VID 0x2D99 / PID 0xA106`，控制接口 `interface=4`、`usage_page=0xFF14`、`usage=0x01`。其它型号未经实测，协议可能不同。

## 安装（DSH 插件）

1. 双击 `apply.bat`（或 `pwsh -File apply.ps1`）

   脚本会：探测 `%USERPROFILE%\.dsh\profiles\desktop`（找不到就取唯一候选，或用 `DSH_PROFILE_DIR` 指定）→ 复制 `index.js / package.json / cordis.patch.yml / scripts/` 到 profile 的 `node_modules\dsh-pixelbar` → 把 `dsh-pixelbar` 登记进 `dsh.profile.bundles`。原 `package.json` 会备份成 `package.json.pixelbar.bak`。

2. 重启 DSH，新会话里让助手推一句到像素屏验证。

卸载：`rollback.bat`，再重启 DSH。

> 插件目录被复制进 `node_modules`，所以 `pnpm install` 之类操作后可能需要重跑 `apply.ps1`。

## 在 DSH 里用

插件注册单个工具 `pixelbar`：

| 参数 | 值 |
| --- | --- |
| `action` | `text`（默认）/ `scene` / `screen` / `light` / `volume` / `clock` / `status` |
| `text` | 要显示的文字，超过 16 字符自动截断 |
| `color` | `white` `red` `green` `blue` `yellow` `cyan` `magenta`，默认 `magenta` |
| `layout` | `left` `center` `right` `stretch` `scroll_left_to_right` `scroll_right_to_left` |
| `scene` | 见上方场景列表 |
| `hex` | `#F0B4C8` 这种六位十六进制，用于 `screen` / `light` |
| `effect` | `breathing` `color_tide` `static` `ripple` `flow` `dynamic` |
| `brightness` | `low` `medium` `high` |
| `speed` | `light` 速度 1–10 |
| `volume` | 0–16；不填 = 查询 |
| `clock_restore` | 推完多少秒回时钟，默认 15；`0` = 不回 |

例：

- `pixelbar { "text": "在", "color": "cyan" }`
- `pixelbar { "action": "scene", "scene": "work" }`
- `pixelbar { "action": "light", "effect": "breathing", "hex": "#F0B4C8", "brightness": "high" }`

## 配置

默认值在 `cordis.patch.yml` 的 `config` 里，工程里对应 `index.js` 的 `DEFAULTS`：

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `python` | 空 | 留空自动探测：环境变量 `DSH_PIXELBAR_PYTHON` → PATH 上的 `python3` / `python` |
| `script` | `scripts/halo_pixelbar.py` | 相对路径相对于插件目录；也可写绝对路径 |
| `clockScript` | `scripts/clock_restore.py` | 同上 |
| `defaultColor` | `magenta` | 默认文字色 |
| `restoreSeconds` | `15` | 默认回时钟秒数 |

## 独立使用（不经 DSH）

脚本不依赖 DSH，可以单独当命令行工具用：

```powershell
cd scripts

python halo_pixelbar.py list                  # 列出控制接口
python halo_pixelbar.py text "在" --color cyan --layout center
python halo_pixelbar.py ui work               # 切场景
python halo_pixelbar.py color "#F0B4C8"       # 屏主题色（自动校准）
python halo_pixelbar.py color "#FF0000" --raw # 跳过校准
python halo_pixelbar.py light --effect breathing --color "#F0B4C8" --brightness high --speed 5
python halo_pixelbar.py lightpower off
python halo_pixelbar.py volume                # 查询
python halo_pixelbar.py volume 10

python clock_restore.py 20                    # 20 秒后回时钟
python color_calib.py                         # 色卡，用于目测校准
```

## HID 协议

真机实测的帧格式（64 字节 HID Output Report）：

```text
主机请求: 2E AA ED <cmd> <len-hi> <len-lo> <payload...> <checksum> <00 填充>
设备响应: 2F BB EC <cmd> <len-hi> <len-lo> <payload...> <checksum> <00 填充>
校验和:   sum(packet[1:]) & 0xFF      # 从 AA 开始求和取低 8 位
```

| 命令 | 用途 | payload |
| --- | --- | --- |
| `0xE8` | 文字 | `00 utf8_len utf8_bytes...` |
| `0xEF` | 布局 | `01 R G B 00 02 <scroll> <mode> FF` |
| `0xEF` | 场景 | `02 R G B 00 01 <scene_id> FF FF` |
| `0xEF` | 屏色 | `03 R G B 00 00 FF FF FF` |
| `0x6B` | 氛围灯 | `13 <effect> R G B <brightness> <speed>`，**需连发 3 次、间隔 30 ms** |
| `0x66` | 查询音量 | 空 |
| `0x67` | 设置音量 | `volume` |

枚举值：

- 场景：`clock=0 game=1 work=2 read=3 cats=4 dogs=5 memes=6 cyber=7 waves=8`
- 布局 `(scroll, mode)`：`left=(0,0) center=(0,1) right=(0,2) stretch=(0,3) scroll_left_to_right=(1,0) scroll_right_to_left=(1,1)`
- 灯效：`breathing=1 color_tide=2 static=3 ripple=4 flow=5 dynamic=6`
- 亮度：`low=0x14 medium=0x28 high=0x3C`
- 文字颜色：`white=0 red=1 green=2 blue=3 yellow=4 cyan=5 magenta=6`

## 颜色校准

这块屏的 R 通道增益偏低、B 偏强，直接发 sRGB 值会偏青/偏紫。`halo_pixelbar.py` 里内置一张目测校准表（`CALIBRATION`），屏色和布局 RGB 会自动查表替换；文字颜色走硬件枚举，不受影响。

`docs/color-card.html` 是配套的色卡页面：在电脑屏幕上显示标准色，和音箱屏对比，看出偏差后改 `CALIBRATION` 里的映射。

## 已知限制

- 屏幕只有 16 字符 / 48 字节位宽，emoji 不显示，颜文字 `^_^ QAQ (T_T)` 可用。
- 每次调用新起 python 进程（约 40 ms 启动 + HID 打开），高频推送不建议。
- 场景 ID、灯效 ID 来自单台设备实测，固件不同可能错位。
- 只会用 `pythonw.exe` 规避 Windows 控制台闪窗；Linux / macOS 未做适配。

## 排错

| 现象 | 处理 |
| --- | --- |
| `未找到 Halo PixelBar 控制接口` | 检查 USB 连接；`python scripts\halo_pixelbar.py list` 看接口是否枚举出来 |
| `[!] 需要 hid 库` | `python -m pip install hidapi` |
| 推送成功但屏上没变 | 设备可能处于音乐律动等抢占模式，先切回 `clock` 场景 |
| 插件加载了但工具报找不到脚本 | 重跑 `apply.ps1`，确认 `node_modules\dsh-pixelbar\scripts\` 存在 |

## 致谢

HID 帧格式最初参考 [Seraph310/halo-pixelbar-mcp](https://github.com/Seraph310/halo-pixelbar-mcp) 的实测结论，后续在本机逐条验证并整理。

## License

[MIT](LICENSE)
