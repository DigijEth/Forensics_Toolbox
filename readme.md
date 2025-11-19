# Android AVD + System Dump Helper

This repository contains a small Python CLI (main.py) that helps you:

- Create emulator AVDs (Samsung-like or Pixel-like).
- Attempt to create a system image dump from a connected device or emulator.
- Assist with setting up Shizuku (installing APK / giving hints to start the service).

Important: This is a helper wrapper around Android SDK tools (sdkmanager, avdmanager, emulator, adb). It does not bypass device security. For many operations you will need a rooted device or to use an emulator.

Usage:
1. Ensure Android SDK command-line tools are installed and available:
   - sdkmanager, avdmanager, emulator, adb must be on PATH or ANDROID_SDK_ROOT / ANDROID_HOME should be set.
2. Python 3.8+ is required.
3. Run:
   ```
   python3 main.py
   ```
4. Use the interactive menu to create devices, dump a system image, or start Shizuku setup steps.

Notes / Next steps:
- The script attempts to install the required system-image package via sdkmanager when creating an AVD. You may be prompted to accept licenses.
- Creating a full block-level system dump from a real device normally requires root. On emulators dd/pull operations are far more likely to succeed.
- Customize DEFAULT_API_LEVEL, DEFAULT_ABI, and DEFAULT_TAG at the top of main.py to match the Android version and ABI you want.
- This is a starting point: you can extend the script to:
  - Auto-detect best device profiles.
  - Create device skins to more closely mimic Samsung hardware.
  - Automatically download Shizuku binaries and run proper start commands.

Security:
- Be careful when running adb shell commands, especially with su -c dd, as they can overwrite device data.
- Always have backups and test on emulators or disposable devices first.

References:
- Android SDK command-line tools: https://developer.android.com/studio/command-line
- Shizuku: https://shizuku.rikka.app/
