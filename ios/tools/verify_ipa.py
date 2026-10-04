"""校验一个 IPA 是否真的能拿去侧载 / 是否已经签好。

CI 产出的是「未签名」IPA，爱思助手签完之后是「已签名」IPA——这两种状态要看的
东西不一样，所以这个脚本自己判断，并且不靠文件名猜：

  未签名包：不能有 _CodeSignature / embedded.mobileprovision（残留会让重签报错）
  已签名包：解析 embedded.mobileprovision，看有效期、Team、App ID、登记设备数

    python tools/verify_ipa.py 生活助手.ipa
    python tools/verify_ipa.py "..\\..\\..\\Desktop\\生活助手.ipa" --expect-permissions
    python tools/verify_ipa.py signed.ipa --require signed
"""

from __future__ import annotations

import argparse
import plistlib
import struct
import sys
import zipfile
from datetime import datetime, timezone
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
    """从 Mach-O 头部读架构（fat 二进制会有多个切片）。"""
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
    for fmt, big in ((">I", True), ("<I", False)):
        val = struct.unpack(fmt, data[:4])[0]
        if val in (0xFEEDFACE, 0xFEEDFACF):
            cpu = struct.unpack(fmt, data[4:8])[0]
            return [_CPU_NAMES.get(cpu, f"cpu=0x{cpu:x}")]
    return []


def parse_profile(blob: bytes) -> dict:
    """embedded.mobileprovision 是 CMS 签名块，但里面的 plist 是明文。

    直接从字节流里切出 <?xml ... </plist> 就能解析，不需要验签。
    """
    start = blob.find(b"<?xml")
    end = blob.find(b"</plist>")
    if start < 0 or end < 0:
        return {}
    try:
        return plistlib.loads(blob[start:end + len(b"</plist>")])
    except Exception:
        return {}


def report_profile(profile: dict) -> bool:
    """打印 profile 关键信息，返回它是否仍然有效。"""
    if not profile:
        print("  ! 有 embedded.mobileprovision 但解析不出 plist")
        return False

    exp = profile.get("ExpirationDate")
    ents = profile.get("Entitlements") or {}
    devices = profile.get("ProvisionedDevices") or []

    print("\n  签名信息")
    print(f"    Profile      {profile.get('Name', '')}")
    print(f"    Team         {profile.get('TeamName') or profile.get('TeamIdentifier') or ''}")
    print(f"    App ID       {ents.get('application-identifier', '')}")
    print(f"    有效期至     {exp}")

    valid = True
    if isinstance(exp, datetime):
        now = datetime.now(exp.tzinfo) if exp.tzinfo else datetime.now()
        days = (exp - now).days
        if days < 0:
            print(f"  ✗ profile 已过期 {abs(days)} 天，装不上了")
            valid = False
        elif days <= 1:
            print(f"  ! 只剩不到 {max(days, 0)} 天就过期，尽快装")
        else:
            print(f"    剩余        约 {days} 天")
    if devices:
        print(f"    已登记设备   {len(devices)} 台（侧载只认这一台，装到别的设备会失败）")
    return valid


def main() -> int:
    ap = argparse.ArgumentParser(description="校验 IPA 状态")
    ap.add_argument("ipa", type=Path)
    ap.add_argument("--expect-permissions", action="store_true",
                    help="要求 Info.plist 里包含生活助手需要的五项权限说明")
    ap.add_argument("--require", choices=["signed", "unsigned"],
                    help="强制要求处于某个签名状态；不指定则只报告不判定")
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
    print(f"校验 {args.ipa}\n大小 {args.ipa.stat().st_size / 1024 / 1024:.2f} MB\n")

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

        # ---- 签名状态：已签还是未签，由包内实际内容决定 ----
        has_sig = any(n.startswith(f"{app_dir}/_CodeSignature/") for n in names)
        prof_path = f"{app_dir}/embedded.mobileprovision"
        has_prof = prof_path in names
        signed = has_sig and has_prof
        state = "已签名" if signed else ("未签名" if not has_sig and not has_prof else "签名不完整")
        if signed:
            print(f"  签名状态     {state}（可交给爱思助手/侧载工具直接安装）")
        else:
            print(f"  签名状态     {state}（未签名包由爱思助手用 Apple ID 现场签）")

        if args.require == "signed":
            check("要求已签名", signed, state)
        elif args.require == "unsigned":
            check("要求未签名", not has_sig and not has_prof, state)

        if has_prof and not report_profile(parse_profile(z.read(prof_path))):
            ok = False

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

        if args.expect_permissions:
            missing = [f"{k}（{v}）" for k, v in REQUIRED_PERMISSIONS.items() if not info.get(k)]
            check("五项权限说明齐全", not missing, "缺：" + "、".join(missing) if missing else "")

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
        print("结论：可以直接安装。" if signed else "结论：未签名包，交给爱思助手签名后安装。")
        return 0
    print("结论：上面有 ✗，先修掉再装。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
