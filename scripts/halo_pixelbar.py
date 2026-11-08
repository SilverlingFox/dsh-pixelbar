#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HALO PIXELBAR 像素屏操控器（墨漓自制 v2）
=======================================
基于 Seraph310/halo-pixelbar-mcp 实测协议（2026-07-19 真机验证）。

帧格式（64 字节 HID Output Report，接口 usage_page=0xFF14）：
  主机请求: 2E AA ED <cmd> <len-hi> <len-lo> <payload...> <checksum> <00 填充>
  设备响应: 2F BB EC <cmd> <len-hi> <len-lo> <payload...> <checksum> <00 填充>
  校验和: sum(packet[1:]) & 0xFF（从 AA 开始求和，取低 8 位）

命令：
  0xE8 文本:   payload = [0x00, utf8_len, utf8_bytes...]   (文本限 16 字符/48 字节)
  0xEF 像素设置: 9 字节 payload
    布局:   01 R G B 00 02 <scroll> <mode> FF
    场景:   02 R G B 00 01 <scene_id> FF FF
    屏色:   03 R G B 00 00 FF FF FF
  0x6B 氛围灯: [0x13, effect, R, G, B, brightness, speed]（需连发 3 次，间隔 30ms）
  0x66 查询音量 / 0x67 设置音量

用法:
  python halo_pixelbar.py list
  python halo_pixelbar.py text "你好墨漓" --color cyan --layout center
  python halo_pixelbar.py layout scroll_r2l
  python halo_pixelbar.py ui clock
  python halo_pixelbar.py volume 10
  python halo_pixelbar.py light --effect breathing --color #F0B4C8 --brightness high
"""

import sys
import time
import argparse
from enum import IntEnum

try:
    import hid
    HAS_HID = True
except ImportError:
    HAS_HID = False

VENDOR_ID = 0x2D99
PRODUCT_ID = 0xA106
INTERFACE_NUMBER = 4
CONTROL_USAGE_PAGE = 0xFF14
CONTROL_USAGE = 0x01
PACKET_LEN = 64
FRAME_TYPE = 0xED  # 帧类型字节（MCP 实测）
LIGHTING_WRITE_REPETITIONS = 3
LIGHTING_WRITE_DELAY = 0.03


class TextColor(IntEnum):
    WHITE = 0
    RED = 1
    GREEN = 2
    BLUE = 3
    YELLOW = 4
    CYAN = 5
    MAGENTA = 6


SCENES = {
    "clock": 0, "game": 1, "work": 2, "read": 3,
    "cats": 4, "dogs": 5, "memes": 6, "cyber": 7, "waves": 8,
}

LAYOUTS = {
    "left": (0, 0), "center": (0, 1), "right": (0, 2),
    "stretch": (0, 3),
    "scroll_left_to_right": (1, 0), "scroll_right_to_left": (1, 1),
}

EFFECTS = {"breathing": 1, "color_tide": 2, "static": 3, "ripple": 4, "flow": 5, "dynamic": 6}
BRIGHTNESS = {"low": 0x14, "medium": 0x28, "high": 0x3C}

DEFAULT_RGB = (0xF0, 0xB4, 0xC8)  # 默认粉紫

# ============================================================
# 颜色校准表（2026-08-01 君辞目测校准）
# 屏幕特性：R 通道增益低、G 居中、B 偏强 → 含红颜色偏青/偏紫
# 格式: 目标色(大写hex) -> 补偿色(发到屏幕的值)
# ============================================================
CALIBRATION = {
    "#FF0000": "#FF0303",  # 红: 偏深 → 微提亮
    "#00FF00": "#03FF03",  # 绿: 偏深 → 微提亮
    "#0000FF": "#0000FF",  # 蓝: 准
    # 白 #FFFFFF 跳过（君辞不用白色）
    "#00FFFF": "#00FFD0",  # 青: 偏蓝 → 减B
    "#FFFF00": "#FF8800",  # 黄: 君辞钦定（#FF8800 显示效果最像目标黄）
    "#FF00FF": "#FF00D0",  # 品红: 偏紫 → 减B
    "#F0B4C8": "#FF6080",  # 默认粉: 偏青 → R拉满压G/B（接近屏极限）
    "#FF8800": "#FF6000",  # 橙: 偏黄 → 减G
    "#66AFFF": "#80C0FF",  # 天蓝: 偏深 → 提亮
}


def apply_calibration(color_hex: str) -> str:
    """应用颜色校准（精确匹配目标色，无匹配则原样返回）"""
    key = color_hex.strip().upper()
    if not key.startswith("#"):
        key = "#" + key
    return CALIBRATION.get(key, color_hex)


def _calibrate_rgb(rgb: tuple) -> tuple:
    """把 RGB tuple 应用校准后转回 tuple"""
    h = "#%02X%02X%02X" % tuple(rgb)
    h = apply_calibration(h)
    c = h.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _pad(data) -> bytes:
    packet = bytes(data)
    if len(packet) > PACKET_LEN:
        return packet[:PACKET_LEN]
    return packet + bytes(PACKET_LEN - len(packet))


def _edifier_packet(command: int, payload) -> bytes:
    """MCP 实测帧格式: 2E AA ED <cmd> <len-be> <payload> <sum(packet[1:])&0xFF>"""
    body = bytes(payload)
    packet = bytearray([0x2E, 0xAA, FRAME_TYPE, command,
                        (len(body) >> 8) & 0xFF, len(body) & 0xFF])
    packet.extend(body)
    packet.append(sum(packet[1:]) & 0xFF)
    return _pad(packet)


def build_text_packet(text: str, color: TextColor = TextColor.WHITE) -> bytes:
    """文本包: 0xE8, payload = [0x00, utf8_len, utf8_bytes...]（限 16 字符/48 字节）"""
    text = text.strip()[:16]
    tb = text.encode("utf-8")
    while len(tb) > 48:
        text = text[:-1]
        tb = text.encode("utf-8")
    return _edifier_packet(0xE8, [0x00, len(tb), *tb])


def build_layout_packet(layout: str, rgb: tuple = DEFAULT_RGB) -> bytes:
    """布局包: 0xEF, payload = [01 R G B 00 02 scroll mode FF]（RGB 自动校准）"""
    scroll, mode = LAYOUTS[layout]
    r, g, b = _calibrate_rgb(rgb)
    return _edifier_packet(0xEF, [0x01, r, g, b, 0x00, 0x02, scroll, mode, 0xFF])


def build_scene_packet(scene: str, rgb: tuple = DEFAULT_RGB) -> bytes:
    """场景包: 0xEF, payload = [02 R G B 00 01 scene_id FF FF]（RGB 自动校准）"""
    scene_id = SCENES[scene]
    r, g, b = _calibrate_rgb(rgb)
    return _edifier_packet(0xEF, [0x02, r, g, b, 0x00, 0x01, scene_id, 0xFF, 0xFF])


def build_screen_color_packet(color_hex: str) -> bytes:
    """像素屏主题色: 0xEF, payload = [03 R G B 00 00 FF FF FF]（自动应用校准）"""
    color_hex = apply_calibration(color_hex)
    c = color_hex.strip().lstrip("#")
    rgb = tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    return _edifier_packet(0xEF, [0x03, *rgb, 0x00, 0x00, 0xFF, 0xFF, 0xFF])


def build_ambient_packet(effect: str, color_hex: str, brightness: str, speed: int) -> bytes:
    """氛围灯: 0x6B, payload = [13 effect R G B brightness speed]"""
    c = color_hex.strip().lstrip("#")
    rgb = tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    return _edifier_packet(0x6B, [0x13, EFFECTS[effect], *rgb, BRIGHTNESS[brightness], speed])


def build_ambient_power_packet(enabled: bool) -> bytes:
    return _edifier_packet(0x6B, [0x00, 0x00, 0x00, 0x00, int(enabled), 0xFF, 0xFF])


def build_volume_query_packet() -> bytes:
    return _edifier_packet(0x66, [])


def build_volume_set_packet(volume: int) -> bytes:
    return _edifier_packet(0x67, [max(0, min(16, volume))])


def find_devices():
    """查找 Halo PixelBar 像素屏控制接口（interface=4, usage_page=FF14）"""
    found = []
    for d in hid.enumerate(VENDOR_ID, PRODUCT_ID):
        if int(d.get("interface_number", -1)) != INTERFACE_NUMBER:
            continue
        if int(d.get("usage_page", 0)) != CONTROL_USAGE_PAGE:
            continue
        if int(d.get("usage", 0)) != CONTROL_USAGE:
            continue
        found.append(d)
    return found


class HaloPixelBar:
    def __init__(self):
        self.dev = None
        self.device_info = None

    def connect(self):
        devs = find_devices()
        if not devs:
            raise RuntimeError("未找到 Halo PixelBar 控制接口（检查 USB 连接）")
        last_err = ""
        for attempt in range(5):
            for d in devs:
                dev = hid.device()
                try:
                    dev.open_path(d["path"])
                    r = dev.write(build_text_packet(""))
                    if r >= 0:
                        self.dev = dev
                        self.device_info = d
                        return d
                    dev.close()
                except Exception as e:
                    last_err = str(e)
                    try:
                        dev.close()
                    except Exception:
                        pass
            time.sleep(0.6)
        raise RuntimeError(f"连接失败: {last_err}")

    def send(self, packet: bytes, consume_response: bool = True) -> int:
        """发送数据包；写入后尝试读取设备响应（避免响应队列堵塞）"""
        if not self.dev:
            raise RuntimeError("未连接")
        r = self.dev.write(packet)
        if r < 0:
            return r
        if consume_response:
            try:
                self.dev.read(64, timeout_ms=100)
            except Exception:
                pass
        return r

    def send_text(self, text: str, color: TextColor = TextColor.WHITE, layout: str = None):
        if layout is not None:
            self.send(build_layout_packet(layout))
            time.sleep(0.05)
        return self.send(build_text_packet(text))

    def set_layout(self, layout: str):
        return self.send(build_layout_packet(layout))

    def set_scene(self, scene: str):
        return self.send(build_scene_packet(scene))

    def set_screen_color(self, color_hex: str):
        return self.send(build_screen_color_packet(color_hex))

    def set_light(self, effect: str, color_hex: str, brightness: str, speed: int):
        pkt = build_ambient_packet(effect, color_hex, brightness, speed)
        # 灯光命令需连发 3 次（间隔 30ms）才生效
        last = -1
        for i in range(LIGHTING_WRITE_REPETITIONS):
            last = self.send(pkt, consume_response=False)
            if last < 0:
                break
            if i + 1 < LIGHTING_WRITE_REPETITIONS:
                time.sleep(LIGHTING_WRITE_DELAY)
        return last

    def set_light_power(self, enabled: bool):
        return self.send(build_ambient_power_packet(enabled))

    def get_volume(self) -> dict:
        self.send(build_volume_query_packet(), consume_response=False)
        try:
            resp = self.dev.read(64, timeout_ms=1000)
        except Exception:
            return {}
        if resp and bytes(resp[:4]) == bytes([0x2F, 0xBB, 0xEC, 0x66]):
            payload = bytes(resp[6:6 + ((resp[4] << 8) | resp[5])])
            if len(payload) >= 2:
                return {"maximum": payload[0], "current": payload[1]}
        return {}

    def set_volume(self, volume: int):
        return self.send(build_volume_set_packet(volume))

    def close(self):
        if self.dev:
            try:
                self.dev.close()
            except Exception:
                pass
            self.dev = None


def main():
    if not HAS_HID:
        if "--quiet" in sys.argv:
            return 0
        print("[!] 需要 hid 库: pip install hidapi", file=sys.stderr)
        return 1

    ap = argparse.ArgumentParser(description="Halo PixelBar 像素屏操控器 v2")
    ap.add_argument("--quiet", action="store_true", help="device offline: skip silently")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("list", help="列出控制接口")
    p_text = sub.add_parser("text", help="显示文字")
    p_text.add_argument("text", nargs="+")
    p_text.add_argument("--color", default="white", help="white/red/green/blue/yellow/cyan/magenta")
    p_text.add_argument("--layout", default=None, help="left/center/right/stretch/scroll_left_to_right/scroll_right_to_left")
    p_layout = sub.add_parser("layout", help="设置布局")
    p_layout.add_argument("layout", choices=list(LAYOUTS.keys()))
    p_ui = sub.add_parser("ui", help="切换场景模式")
    p_ui.add_argument("model", choices=list(SCENES.keys()))
    p_color = sub.add_parser("color", help="设置像素屏主题色（自动应用校准）")
    p_color.add_argument("hex", help="如 #F0B4C8")
    p_color.add_argument("--raw", action="store_true", help="跳过校准，直接发原始值")
    p_vol = sub.add_parser("volume", help="查询/设置硬件音量")
    p_vol.add_argument("value", nargs="?", type=int, help="0-16，不填则查询")
    p_light = sub.add_parser("light", help="氛围灯")
    p_light.add_argument("--effect", default="breathing", choices=list(EFFECTS.keys()))
    p_light.add_argument("--color", default="#F0B4C8")
    p_light.add_argument("--brightness", default="medium", choices=list(BRIGHTNESS.keys()))
    p_light.add_argument("--speed", type=int, default=5)
    p_power = sub.add_parser("lightpower", help="氛围灯开关")
    p_power.add_argument("on", choices=["on", "off"])

    args = ap.parse_args()
    quiet = getattr(args, "quiet", False) or "--quiet" in sys.argv
    if not args.cmd:
        ap.print_help()
        return 1

    if args.cmd == "list":
        try:
            devs = find_devices()
        except Exception as e:
            if quiet:
                return 0
            print(f"[FAIL] {e}")
            return 1
        if not devs:
            if quiet:
                return 0
            print("未找到控制接口（检查 USB 连接）")
            return 1
        for d in devs:
            print(f"  interface={d.get('interface_number')} usage_page={d['usage_page']:04X} "
                  f"usage={d['usage']:02X} {d.get('product_string','')}")
        return 0

    bar = None
    try:
        bar = HaloPixelBar()
        info = bar.connect()
        print(f"[OK] 已连接: {info.get('product_string','')}")

        if args.cmd == "text":
            r = bar.send_text(" ".join(args.text), TextColor[args.color.upper()], args.layout)
            print(f"[OK] 显示: {' '.join(args.text)!r} 颜色={args.color} 布局={args.layout or '保持'}")
        elif args.cmd == "layout":
            r = bar.set_layout(args.layout)
            print(f"[OK] 布局: {args.layout}")
        elif args.cmd == "ui":
            r = bar.set_scene(args.model)
            print(f"[OK] 场景: {args.model}")
        elif args.cmd == "color":
            sent = args.hex
            if not args.raw:
                cal = apply_calibration(args.hex)
                if cal != args.hex:
                    print(f"[校准] {args.hex} -> {cal}")
                sent = cal
            r = bar.set_screen_color(sent)
            print(f"[OK] 屏色: {sent}")
        elif args.cmd == "volume":
            if args.value is None:
                v = bar.get_volume()
                print(f"[OK] 音量: {v.get('current','?')}/{v.get('maximum','?')}")
            else:
                r = bar.set_volume(args.value)
                time.sleep(0.3)
                v = bar.get_volume()
                print(f"[OK] 设置音量 {args.value} -> 当前 {v.get('current','?')}")
        elif args.cmd == "light":
            r = bar.set_light(args.effect, args.color, args.brightness, args.speed)
            print(f"[OK] 氛围灯: {args.effect} {args.color}")
        elif args.cmd == "lightpower":
            r = bar.set_light_power(args.on == "on")
            print(f"[OK] 氛围灯: {'开' if args.on == 'on' else '关'}")
        return 0
    except Exception as e:
        if quiet:
            return 0
        print(f"[FAIL] {e}")
        return 1
    finally:
        if bar is not None:
            try:
                bar.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
