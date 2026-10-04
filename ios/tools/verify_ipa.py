"""校验一个 IPA 是否真的能拿去侧载。

CI 产出的是「未签名」IPA——但签名状态、架构、Info.plist 里那几项权限声明，
都要真的打开包看才算数。这个脚本就是干这个的，避免靠文件名猜。

    python tools/verify_ipa.py ..\\..\\..\\Desktop\\生活助手.ipa
    python tools/verify_ipa.py 生活助手.ipa --expect-permissions
"""

from __future__ import annotations

import argparse
import plistlib
import struct
import sys
import zipfile
from pathlib import Path

# 需求里点名要有的五项权限（缺任何一项，对应功能会直接闪退）
REQUIRED_PERMISSIONS = {
    "NSLocationWhenInUseUsageDescription": "定位",
    "NSCameraUsageDescription": "相机",
    "NSPhotoLibraryUsageDescription": "相册",
    "NSMicrophoneUsageDescription": "麦克风",
    "NSSpeechRecognitionUsageDescription": "语音识别",
}

_CPU_NAMES = {0x0100000C: "arm64", 0x01000007: "x86_64", 7: "i386", 12: "arm"}


def macho_archs(data: bytes) -> list[str]:
    """从 Mach-O 头部读架构（含 fat 二进制的多个切片）。"""
    if len(data) < 8:
        return []
    magic = struct.unpack(">I", data[:4])[0]
    if magic in (0xCAFEBABE, 0xCAFEBABF):  # fat
        count = struct.unpack(">I", data[4:8])[0]
        archs = []
        for i in range(count):
            off = 8 + i * 20
            if off + 4 > len(data):
                break
            cpu = struct.unpack(">I", data[off:off + 4])[0]
            archs.append(_CPU_NAMES.get(cpu, f"cpu=0x{cpu:x}"))
        return archs
    if magic in (0xFEEDFACE, 0xFEEDFACF):  # 大端（理论值）
        cpu = struct.unpack(">I", data[4:8])[0]
        return [_CPU_NAMES.get(cpu, f"cpu=0x{cpu:x}")]
    little = struct.unpack("<I", data[:4])[0]
    if little in (0xFEEDFACE, 0xFEEDFACF):  # 小端（iPhone 上就是这个）
        cpu = struct.unpack("<I", data[4:8])[0]
        return [_CPU_NAMES.get(cpu, f"cpu=0x{cpu:x}")]
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description="校验 IPA 是否可直接侧载")
    ap.add_argument("ipa", type=Path)
    ap.add_argument("--expect-permissions", action="store_true",
                    help="要求 Info.plist 里包含生活助手需要的五项权限说明")
    args = ap.parse_args()

    ok = True

    def check(label: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        if not passed:
            ok = False
        print(f"  {'✓' if passed else '✗'} {label}" + (f"  — {detail}" if detail else ""))

    if not args.ipa.is_file():
        print(f"找不到文件：{args.ipa}")
        return 2
    size_mb = args.ipa.stat().st_size / 1024 / 1024
    print(f"校验 {args.ipa}\n大小 {size_mb:.2f} MB\n")

    with zipfile.ZipFile(args.ipa) as z:
        names = z.namelist()

        apps = sorted({n.split("/")[1] for n in names if n.startswith("Payload/") and n.count("/") > 1})
        check("包含 Payload/<App>.app 结构", len(apps) == 1, ", ".join(apps) or "没有 Payload 目录")
        if len(apps) != 1:
            return 1

        app_dir = f"Payload/{apps[0]}"
        info_path = f"{app_dir}/Info.plist"
        check("有 Info.plist", info_path in names)
        if info_path not in names:
            return 1

        info = plistlib.loads(z.read(info_path))

        # ---- 未签名状态：这两个残留会让爱思助手重签时报错 ----
        leftovers = [n for n in names if "_CodeSignature" in n or n.endswith("embedded.mobileprovision")]
        check("没有残留签名（未签名包）", not leftovers,
              f"{len(leftovers)} 条：{leftovers[:3]}" if leftovers else "")

        # ---- 可执行文件与架构 ----
        exe_name = info.get("CFBundleExecutable", "")
        exe_path = f"{app_dir}/{exe_name}"
        if exe_path in names:
            archs = macho_archs(z.read(exe_path))
            check("可执行文件是真机架构（需要 arm64）", "arm64" in archs, ", ".join(archs) or "认不出 Mach-O")
        else:
            check("可执行文件存在", False, exe_path)

        # ---- 部署目标 ----
        min_os = str(info.get("MinimumOSVersion", ""))
        check("MinimumOSVersion >= 18.0（iPhone 16 Pro Max / iOS 18.7）",
              bool(min_os) and float(min_os.split(".")[0]) >= 18, min_os or "未声明")

        # ---- 权限说明 ----
        if args.expect_permissions:
            missing = [f"{k}（{v}）" for k, v in REQUIRED_PERMISSIONS.items() if not info.get(k)]
            check("五项权限说明齐全", not missing, "缺：" + "、".join(missing) if missing else "")

        # ---- 网络：调试期明文 HTTP ----
        ats = info.get("NSAppTransportSecurity") or {}
        check("允许明文 HTTP（连局域网后端必需）",
              bool(ats.get("NSAllowsArbitraryLoads") or ats.get("NSAllowsLocalNetworking")),
              str(ats) if ats else "没有 NSAppTransportSecurity")

        print("\n  Bundle 信息")
        print(f"    Identifier   {info.get('CFBundleIdentifier')}")
        print(f"    DisplayName  {info.get('CFBundleDisplayName')}")
        print(f"    Version      {info.get('CFBundleShortVersionString')} ({info.get('CFBundleVersion')})")
        print(f"    包内条目     {len(names)} 个")

    print()
    if ok:
        print("结论：可以直接拖进爱思助手签名安装。")
        return 0
    print("结论：上面有 ✗，先修掉再装。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
