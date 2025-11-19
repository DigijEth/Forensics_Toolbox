#!/usr/bin/env python3
"""
avd-manager.py

A simple CLI tool to provision Android emulators (Samsung/Pixel-ish) and to
create a system image dump from a connected device. Also contains a helper
to prepare Shizuku (install / start) via adb.

This script wraps Android SDK tools (sdkmanager, avdmanager, emulator, adb).
It does not attempt to bypass device protections — for creating a full block
dump it will prompt and attempt commands that require a rooted device or an
emulator (emulators are usually rootable).

Requirements:
- Python 3.8+
- Android SDK tools on PATH (sdkmanager, avdmanager, emulator, adb), or ANDROID_SDK_ROOT/ANDROID_HOME set.
- Java installed (for some sdk tools)
- For system dumps from a real device: device must be rooted or allow the operations attempted.

This is a starting skeleton. Each operation prints the commands it runs and runs
them with subprocess so you can see and tweak behaviour easily.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from typing import Optional, List

# Configurable defaults
DEFAULT_API_LEVEL = "31"  # change as desired
DEFAULT_ABI = "x86_64"
DEFAULT_TAG = "google_apis"  # or google_apis_playstore, default tag
EMULATOR_TIMEOUT = 10  # seconds to wait after starting emulator (used minimally)

TOOLS = ["sdkmanager", "avdmanager", "emulator", "adb"]


def which_or_env(tool_name: str) -> Optional[str]:
    # Try PATH first
    p = shutil.which(tool_name)
    if p:
        return p
    # fallback to ANDROID_SDK_ROOT / ANDROID_HOME
    sdk_root = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if not sdk_root:
        return None
    # common path
    possible = [
        os.path.join(sdk_root, "tools", "bin", tool_name),
        os.path.join(sdk_root, "cmdline-tools", "latest", "bin", tool_name),
        os.path.join(sdk_root, "cmdline-tools", "bin", tool_name),
        os.path.join(sdk_root, "platform-tools", tool_name),
    ]
    for pp in possible:
        if os.path.exists(pp):
            return pp
    return None


def ensure_tools():
    missing = []
    found = {}
    for t in TOOLS:
        p = which_or_env(t)
        if not p:
            missing.append(t)
        else:
            found[t] = p
    if missing:
        print("Warning: Some Android SDK tools were not found:", ", ".join(missing))
        print("Make sure ANDROID_SDK_ROOT or ANDROID_HOME is set and sdk commandline tools are installed.")
    return found


def run(cmd: List[str], check=True, capture_output=False, env=None):
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=check, capture_output=capture_output, env=env)


def list_avd_devices(avdmanager_path: Optional[str]) -> List[dict]:
    # Parse "avdmanager list device" to find device ids and names.
    devices = []
    if not avdmanager_path:
        return devices
    try:
        res = subprocess.run([avdmanager_path, "list", "device"], check=True, capture_output=True, text=True)
        out = res.stdout.splitlines()
        # Very small parser: lines like "id: 23 or \"pixel_5\""
        current = {}
        for line in out:
            line = line.strip()
            if not line:
                continue
            if line.startswith("id:"):
                current = {"id": line.split(":", 1)[1].strip()}
                devices.append(current)
            elif line.startswith("name:") and current is not None:
                current["name"] = line.split(":", 1)[1].strip()
    except Exception:
        pass
    return devices


def ensure_system_image(sdkmanager_path: Optional[str], api: str = DEFAULT_API_LEVEL, tag: str = DEFAULT_TAG, abi: str = DEFAULT_ABI):
    """
    Ensure the system image package is installed via sdkmanager. This will prompt to accept licenses.
    """
    if not sdkmanager_path:
        print("sdkmanager not found; cannot install system images automatically.")
        return
    pkg = f"system-images;android-{api};{tag};{abi}"
    print(f"Ensuring system image package is installed: {pkg}")
    try:
        run([sdkmanager_path, pkg])
    except subprocess.CalledProcessError as e:
        print("sdkmanager failed. You may need to run the command manually with correct SDK tools installed.")
        print(e)


def create_avd(avdmanager_path: Optional[str], sdkmanager_path: Optional[str], name: str, device_profile: Optional[str] = None, api: str = DEFAULT_API_LEVEL):
    """
    Create an AVD with given name and a device profile (if available). This attempts to
    install the required system image and call avdmanager create avd.
    """
    # Ensure system image
    ensure_system_image(sdkmanager_path, api=api)

    # Compose package id
    pkg = f"system-images;android-{api};{DEFAULT_TAG};{DEFAULT_ABI}"

    if not avdmanager_path:
        print("avdmanager not found. Install Android command-line tools and ensure avdmanager is on PATH.")
        return

    cmd = [avdmanager_path, "create", "avd", "--name", name, "--package", pkg, "--force"]
    if device_profile:
        cmd += ["--device", device_profile]

    print(f"Creating AVD '{name}' (device profile: {device_profile or 'default'})")
    try:
        # avdmanager may prompt for "Do you wish to create a custom hardware profile [no]:" -- we pass --force to avoid; still user input may be required
        run(cmd)
        print(f"AVD '{name}' created.")
    except subprocess.CalledProcessError as e:
        print("Failed to create AVD. Output:")
        if e.stdout:
            print(e.stdout.decode() if isinstance(e.stdout, bytes) else e.stdout)
        if e.stderr:
            print(e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr)


def start_emulator(emulator_path: Optional[str], avd_name: str, no_window: bool = False):
    if not emulator_path:
        print("emulator binary not found.")
        return None
    cmd = [emulator_path, "-avd", avd_name]
    if no_window:
        cmd.append("-no-window")
    # Start emulator in background
    print("Starting emulator:", " ".join(cmd))
    # Using Popen so we don't block the script; user can CTRL-C to stop.
    proc = subprocess.Popen(cmd)
    return proc


def create_samsung_device(found_tools):
    """
    Attempt to create an AVD configured to emulate a Samsung-like device.
    Note: avdmanager doesn't ship official Samsung profiles. We try to pick a
    large-screen device profile if available or fallback to a Nexus/Pixel profile.
    """
    avdmanager_path = found_tools.get("avdmanager")
    sdkmanager_path = found_tools.get("sdkmanager")

    devices = list_avd_devices(avdmanager_path)
    # Prefer a large device profile; try to match names
    preferred = None
    for d in devices:
        name = d.get("name", "").lower()
        if "galaxy" in name or "samsung" in name or "large" in name or "xlarge" in name:
            preferred = d["id"]
            break
    if not preferred:
        # fallbacks
        for fallback in ("pixel_6", "pixel_5", "Nexus 6", "Nexus 5X"):
            for d in devices:
                if fallback.lower() in d.get("name", "").lower() or fallback.lower() in d.get("id", "").lower():
                    preferred = d["id"]
                    break
            if preferred:
                break

    avd_name = "Samsung_Device_AVD"
    create_avd(avdmanager_path, sdkmanager_path, avd_name, device_profile=preferred)
    print("You can start the emulator with option to run headless or with window.")


def create_pixel_device(found_tools):
    avdmanager_path = found_tools.get("avdmanager")
    sdkmanager_path = found_tools.get("sdkmanager")

    devices = list_avd_devices(avdmanager_path)
    preferred = None
    for d in devices:
        # try to match available Pixel device ids/names
        name = d.get("name", "").lower()
        if "pixel" in name or "pixel_6" in d.get("id", "").lower() or "pixel_3" in d.get("id", "").lower():
            preferred = d["id"]
            break

    avd_name = "Pixel_Device_AVD"
    create_avd(avdmanager_path, sdkmanager_path, avd_name, device_profile=preferred)
    print("Pixel-like AVD created.")


def choose_connected_device(adb_path: Optional[str]) -> Optional[str]:
    if not adb_path:
        print("adb not found.")
        return None
    try:
        res = subprocess.run([adb_path, "devices"], check=True, capture_output=True, text=True)
        lines = res.stdout.strip().splitlines()
        # lines: first line "List of devices attached"
        devices = []
        for l in lines[1:]:
            if not l.strip():
                continue
            parts = l.split()
            if len(parts) >= 2:
                devices.append((parts[0], parts[1]))
        if not devices:
            print("No devices/emulators attached.")
            return None
        print("Connected devices/emulators:")
        for idx, (serial, state) in enumerate(devices, 1):
            print(f"{idx}) {serial} ({state})")
        choice = input("Pick device number (default 1): ").strip()
        if not choice:
            choice = "1"
        try:
            i = int(choice) - 1
            return devices[i][0]
        except Exception:
            print("Invalid choice.")
            return None
    except subprocess.CalledProcessError:
        print("adb devices failed.")
        return None


def create_system_image_dump(found_tools):
    """
    Try to dump a system image from a connected device.

    Strategy:
    - List devices via adb.
    - Ask user if they want to attempt a 'dd' from a block device (requires root) -> adb shell su -c 'dd if=... of=/sdcard/system.img'
    - If root not available, attempt to pull /system directory.
    - Pull the created image to local machine.
    """
    adb_path = found_tools.get("adb")
    if not adb_path:
        print("adb not found. Cannot continue.")
        return

    serial = choose_connected_device(adb_path)
    if not serial:
        return

    print("NOTE: Creating a system image typically requires root on the target device or running an emulator.")
    print("Options:")
    print("1) Attempt a block-level dd (requires root).")
    print("2) Try a recursive pull of /system (may be limited by permissions).")
    choice = input("Choose method (1 or 2) [1]: ").strip() or "1"

    if choice == "1":
        # Need to find system partition. Common path: /dev/block/by-name/system
        remote_img = "/sdcard/system.img"
        dd_cmd = f"su -c 'dd if=/dev/block/by-name/system of={remote_img} bs=4096 || dd if=/dev/block/platform/*/by-name/system of={remote_img} bs=4096'"
        print("Attempting dd on device (this will likely fail on unrooted devices).")
        try:
            run([adb_path, "-s", serial, "shell", dd_cmd])
            # Pull image
            local_name = f"{serial}_system.img"
            run([adb_path, "-s", serial, "pull", remote_img, local_name])
            print(f"Pulled image to {local_name}")
            print(f"Cleaning remote image {remote_img}")
            run([adb_path, "-s", serial, "shell", f"rm {remote_img}"])
        except subprocess.CalledProcessError:
            print("Failed to dd/pull system image. Check if the device is rooted or try method 2 (pull /system).")

    else:
        # Method 2: pull /system
        local_dir = f"{serial}_system"
        print(f"Attempting to pull /system -> {local_dir} (may be restricted on modern devices).")
        try:
            run([adb_path, "-s", serial, "pull", "/system", local_dir])
            print(f"/system pulled to local directory: {local_dir}")
        except subprocess.CalledProcessError:
            print("Recursive pull failed. Consider using a rooted device or an emulator to perform a full dump.")


def setup_shizuku(found_tools):
    """
    Install / start Shizuku via adb.

    Common steps:
    - Install Shizuku APK (user should supply path), or direct user to Play Store.
    - Start the shizuku server via 'adb shell sh /data/local/tmp/shizuku' if appropriate, or by sending the adb command that the maintainer recommends.
    - For devs, Shizuku provides a "shizuku-server" binary; this script only assists with the common pattern.
    """
    adb_path = found_tools.get("adb")
    if not adb_path:
        print("adb not found.")
        return

    print("Shizuku setup helper.")
    apk_path = input("Path to Shizuku APK to install (leave empty to skip install): ").strip()
    if apk_path:
        if not os.path.exists(apk_path):
            print("APK path does not exist.")
        else:
            try:
                run([adb_path, "install", "-r", apk_path])
                print("APK installed (or reinstalled).")
            except subprocess.CalledProcessError:
                print("Failed to install APK via adb.")
    print("You can start the Shizuku server on a rooted device with a command like:")
    print("  adb shell su -c 'sh /data/local/tmp/shizuku_start.sh'  # if you have the script on device")
    print("Or on emulator you can run the server binary and then grant permissions via the app UI.")
    print("For non-rooted devices, Shizuku supports ADB mode using 'adb shell sh /data/local/tmp/start.sh' but it requires manual steps.")
    print("Refer to Shizuku docs: https://shizuku.rikka.app/")


def main_menu():
    found_tools = ensure_tools()
    print("Simple Android AVD + Dump helper")
    while True:
        print("\nMain Menu")
        print("1) Create Samsung device")
        print("2) Create a Pixel Device")
        print("3) Create System Image dump")
        print("4) Setup Shizuku")
        print("q) Quit")
        choice = input("Choose an option: ").strip().lower()
        if choice in ("q", "quit", "exit"):
            print("Exiting.")
            break
        if choice == "1":
            create_samsung_device(found_tools)
        elif choice == "2":
            create_pixel_device(found_tools)
        elif choice == "3":
            create_system_image_dump(found_tools)
        elif choice == "4":
            setup_shizuku(found_tools)
        else:
            print("Unknown choice.")


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\nInterrupted. Exiting.")
        sys.exit(0)
