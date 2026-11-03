#!/usr/bin/env python3
"""
macbook-als: Ambient Light Sensor (ALS) Auto-Brightness Daemon for MacBooks running Linux.
Zero external dependencies (pure Python 3 standard library).
"""

import os
import sys
import time
import glob
import math
import signal
import shutil
import argparse
import subprocess
import configparser

PAUSE_FILE = "/tmp/macbook-als.paused"

DEFAULT_CONFIG_PATHS = [
    "/etc/macbook-als.conf",
    os.path.expanduser("~/.config/macbook-als.conf"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "macbook-als.conf")
]

class HardwareDetector:
    @staticmethod
    def find_als():
        """Locates Apple SMC or IIO Ambient Light Sensor."""
        # 1. Apple SMC (Intel MacBooks)
        applesmc_light = "/sys/devices/platform/applesmc.768/light"
        if os.path.exists(applesmc_light):
            return {"type": "applesmc", "path": applesmc_light}

        # 2. Linux IIO subsystem (T2 / Apple Silicon / standard ACPI ALS)
        iio_devices = glob.glob("/sys/bus/iio/devices/iio:device*")
        for dev in iio_devices:
            for node in ["in_illuminance_raw", "in_illuminance_input", "in_illuminance"]:
                full_path = os.path.join(dev, node)
                if os.path.exists(full_path):
                    return {"type": "iio", "path": full_path}

        # 3. ACPI ALS
        acpi_als = glob.glob("/sys/bus/acpi/devices/ACPI0008:*/ali")
        if acpi_als and os.path.exists(acpi_als[0]):
            return {"type": "acpi", "path": acpi_als[0]}

        return None

    @staticmethod
    def find_backlight():
        """Locates the primary display backlight controller."""
        candidates = glob.glob("/sys/class/backlight/*")
        priority = ["gmux_backlight", "intel_backlight", "apple_backlight", "appledrm_backlight", "amdgpu_bl"]
        sorted_candidates = sorted(
            candidates,
            key=lambda c: next((i for i, p in enumerate(priority) if p in os.path.basename(c)), 99)
        )
        for dev in sorted_candidates:
            b_path = os.path.join(dev, "brightness")
            m_path = os.path.join(dev, "max_brightness")
            if os.path.exists(b_path) and os.path.exists(m_path):
                try:
                    with open(m_path, "r") as f:
                        max_b = int(f.read().strip())
                    return {"name": os.path.basename(dev), "path": b_path, "max": max_b}
                except Exception:
                    continue
        return None

    @staticmethod
    def find_kbd_backlight():
        """Locates the keyboard backlight controller."""
        candidates = (
            glob.glob("/sys/class/leds/*kbd_backlight*") +
            glob.glob("/sys/class/leds/smc::kbd_backlight*") +
            glob.glob("/sys/class/leds/apple::kbd_backlight*")
        )
        for dev in candidates:
            b_path = os.path.join(dev, "brightness")
            m_path = os.path.join(dev, "max_brightness")
            if os.path.exists(b_path) and os.path.exists(m_path):
                try:
                    with open(m_path, "r") as f:
                        max_b = int(f.read().strip())
                    return {"name": os.path.basename(dev), "path": b_path, "max": max_b}
                except Exception:
                    continue
        return None


def send_notification(summary, body):
    """Sends desktop notification if notify-send is installed (fails silently)."""
    if shutil.which("notify-send"):
        try:
            subprocess.run(
                ["notify-send", "-a", "macbook-als", "-i", "display-brightness-symbolic", summary, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1.0
            )
        except Exception:
            pass


def is_service_active():
    """Checks if macbook-als systemd service is active."""
    if shutil.which("systemctl"):
        try:
            res = subprocess.run(
                ["systemctl", "is-active", "--quiet", "macbook-als.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return res.returncode == 0
        except Exception:
            return False
    return False


def set_paused_state(pause=True):
    """Creates or removes the pause marker file without requiring sudo."""
    if pause:
        try:
            with open(PAUSE_FILE, "w") as f:
                f.write(str(time.time()))
            # Ensure file is writable by anyone so any user can toggle it
            try:
                os.chmod(PAUSE_FILE, 0o666)
            except Exception:
                pass
            print("[macbook-als] Auto-brightness PAUSED.")
            send_notification("Auto-Brightness Paused", "Automatic light sensor adjustments are suspended.")
            return True
        except Exception as e:
            print(f"[!] Failed to create pause marker: {e}", file=sys.stderr)
            return False
    else:
        try:
            if os.path.exists(PAUSE_FILE):
                os.remove(PAUSE_FILE)
            print("[macbook-als] Auto-brightness RESUMED.")
            send_notification("Auto-Brightness Resumed", "Automatic light sensor adjustments are active.")
            return True
        except Exception as e:
            print(f"[!] Failed to remove pause marker: {e}", file=sys.stderr)
            return False


def toggle_state():
    """Toggles paused/resumed state."""
    currently_paused = os.path.exists(PAUSE_FILE)
    set_paused_state(not currently_paused)

    # Remind the user if service isn't active
    if not is_service_active():
        print("Note: The macbook-als systemd service is not currently running.")
        print("      To start it: sudo systemctl start macbook-als")


def show_status():
    """Prints current status (service active, paused, hardware)."""
    service_active = is_service_active()
    is_paused = os.path.exists(PAUSE_FILE)

    print("========================================")
    print("        macbook-als Status             ")
    print("========================================")
    print(f"systemd service: {'Active (running)' if service_active else 'Inactive / Not running'}")
    print(f"Auto-brightness: {'PAUSED' if is_paused else 'ACTIVE'}")
    if is_paused:
        print(f"Pause flag file: {PAUSE_FILE}")
    print("----------------------------------------")
    print("Use 'macbook-als --toggle' to pause or resume instantly.")


def read_sensor_lux(sensor_info):
    """Reads raw sensor value and converts to float lux representation."""
    if not sensor_info or not os.path.exists(sensor_info["path"]):
        return 0.0

    try:
        with open(sensor_info["path"], "r") as f:
            content = f.read().strip()

        # Apple SMC often outputs '(left,right)', e.g. '(15,16)'
        if sensor_info["type"] == "applesmc" and "(" in content:
            cleaned = content.replace("(", "").replace(")", "").replace(" ", "")
            parts = [float(p) for p in cleaned.split(",") if p]
            return sum(parts) / len(parts) if parts else 0.0

        return float(content)
    except Exception:
        return 0.0


def load_config():
    """Loads configuration with fallback defaults."""
    defaults = {
        "poll_interval": 1.0,
        "smoothing_factor": 0.25,
        "min_screen_percent": 5,
        "max_screen_percent": 100,
        "max_expected_lux": 1000.0,
        "kbd_control_enabled": True,
        "kbd_threshold_lux": 150.0,
        "kbd_max_percent": 80,
    }

    config = configparser.ConfigParser()
    found_file = None
    for p in DEFAULT_CONFIG_PATHS:
        if os.path.isfile(p):
            config.read(p)
            found_file = p
            break

    settings = dict(defaults)
    if found_file and "General" in config:
        gen = config["General"]
        settings["poll_interval"] = gen.getfloat("poll_interval", defaults["poll_interval"])
        settings["smoothing_factor"] = gen.getfloat("smoothing_factor", defaults["smoothing_factor"])
        settings["max_expected_lux"] = gen.getfloat("max_expected_lux", defaults["max_expected_lux"])

    if found_file and "Screen" in config:
        sc = config["Screen"]
        settings["min_screen_percent"] = sc.getint("min_screen_percent", defaults["min_screen_percent"])
        settings["max_screen_percent"] = sc.getint("max_screen_percent", defaults["max_screen_percent"])

    if found_file and "Keyboard" in config:
        kb = config["Keyboard"]
        settings["kbd_control_enabled"] = kb.getboolean("enabled", defaults["kbd_control_enabled"])
        settings["kbd_threshold_lux"] = kb.getfloat("threshold_lux", defaults["kbd_threshold_lux"])
        settings["kbd_max_percent"] = kb.getint("max_percent", defaults["kbd_max_percent"])

    return settings, found_file


def calculate_screen_brightness(lux, settings, max_hardware):
    """Maps lux logarithmically (human eye perception curve) to hardware brightness."""
    clamped_lux = max(0.0, min(lux, settings["max_expected_lux"]))
    ratio = math.log10(clamped_lux + 1.0) / math.log10(settings["max_expected_lux"] + 1.0)

    min_pct = settings["min_screen_percent"] / 100.0
    max_pct = settings["max_screen_percent"] / 100.0
    target_pct = min_pct + (max_pct - min_pct) * ratio

    return int(round(target_pct * max_hardware))


def calculate_keyboard_brightness(lux, settings, max_hardware):
    """macOS behavior: Keyboard backlight turns ON in dim light and OFF in bright daylight."""
    if not settings["kbd_control_enabled"] or max_hardware <= 0:
        return 0

    threshold = settings["kbd_threshold_lux"]
    if lux >= threshold:
        return 0

    ratio = (threshold - lux) / threshold
    target_pct = (settings["kbd_max_percent"] / 100.0) * ratio
    return int(round(target_pct * max_hardware))


def write_sysfs(path, value):
    """Safely writes an integer to a sysfs attribute."""
    try:
        with open(path, "w") as f:
            f.write(str(int(value)))
        return True
    except PermissionError:
        print(f"[Error] Permission denied writing to {path}. Are you running as root?", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[Error] Failed to write {value} to {path}: {e}", file=sys.stderr)
        return False


def run_daemon(settings, als, screen, kbd):
    """Main daemon loop with signal handling, pause detection, and smoothing."""
    running = True

    def handle_signal(sig, frame):
        nonlocal running
        print("\n[macbook-als] Stopping daemon gracefully...")
        running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print(f"[macbook-als] Daemon active. Polling every {settings['poll_interval']}s...")

    smoothed_lux = read_sensor_lux(als)
    alpha = settings["smoothing_factor"]
    last_screen_val = -1
    last_kbd_val = -1
    was_paused = False

    while running:
        # Check if temporarily paused
        if os.path.exists(PAUSE_FILE):
            if not was_paused:
                print("[macbook-als] Paused by user toggle. Adjustments suspended.")
                was_paused = True
            time.sleep(settings["poll_interval"])
            continue
        elif was_paused:
            print("[macbook-als] Resumed from user toggle.")
            was_paused = False
            # Re-read raw lux to avoid a sudden jump after being paused
            smoothed_lux = read_sensor_lux(als)

        raw_lux = read_sensor_lux(als)
        smoothed_lux = (alpha * raw_lux) + ((1.0 - alpha) * smoothed_lux)

        if screen:
            target_screen = calculate_screen_brightness(smoothed_lux, settings, screen["max"])
            if abs(target_screen - last_screen_val) >= max(1, int(screen["max"] * 0.01)):
                if write_sysfs(screen["path"], target_screen):
                    last_screen_val = target_screen

        if kbd and settings["kbd_control_enabled"]:
            target_kbd = calculate_keyboard_brightness(smoothed_lux, settings, kbd["max"])
            if abs(target_kbd - last_kbd_val) >= max(1, int(kbd["max"] * 0.02)):
                if write_sysfs(kbd["path"], target_kbd):
                    last_kbd_val = target_kbd

        time.sleep(settings["poll_interval"])


def main():
    parser = argparse.ArgumentParser(description="macbook-als: Ambient Light Sensor auto-brightness for MacBooks on Linux")
    parser.add_argument("-t", "--toggle", action="store_true", help="Toggle auto-brightness ON/OFF (no sudo needed)")
    parser.add_argument("-p", "--pause", action="store_true", help="Temporarily pause auto-brightness")
    parser.add_argument("-r", "--resume", action="store_true", help="Resume auto-brightness")
    parser.add_argument("-s", "--status", action="store_true", help="Show current daemon & pause status")
    parser.add_argument("--test", action="store_true", help="Probe hardware and print readings once without modifying brightness")
    parser.add_argument("--monitor", action="store_true", help="Continuously print sensor and target values to terminal (read-only)")
    args = parser.parse_args()

    # Handle quick non-daemon commands
    if args.toggle:
        toggle_state()
        return

    if args.pause:
        set_paused_state(True)
        return

    if args.resume:
        set_paused_state(False)
        return

    if args.status:
        show_status()
        return

    settings, conf_file = load_config()

    als = HardwareDetector.find_als()
    screen = HardwareDetector.find_backlight()
    kbd = HardwareDetector.find_kbd_backlight()

    print("========================================")
    print("      macbook-als: Hardware Probe       ")
    print("========================================")
    print(f"Config loaded: {conf_file or 'Default fallback'}")
    print(f"ALS Sensor:    {als['path'] if als else 'NOT DETECTED'} ({als['type'] if als else 'n/a'})")
    print(f"Display BL:    {screen['name'] if screen else 'NOT DETECTED'} (max: {screen['max'] if screen else 'n/a'})")
    print(f"Keyboard BL:   {kbd['name'] if kbd else 'NOT DETECTED'} (max: {kbd['max'] if kbd else 'n/a'})")
    print("----------------------------------------")

    if not als:
        print("[!] No Ambient Light Sensor found. Check if applesmc or iio sensor driver is loaded.")
        sys.exit(1)

    if not screen and not kbd:
        print("[!] Neither screen backlight nor keyboard backlight was found.")
        sys.exit(1)

    if args.test:
        raw_lux = read_sensor_lux(als)
        print(f"Current Raw Lux:           {raw_lux:.2f}")
        if screen:
            calc_screen = calculate_screen_brightness(raw_lux, settings, screen["max"])
            pct = (calc_screen / screen["max"]) * 100
            print(f"Calculated Screen Target:  {calc_screen}/{screen['max']} ({pct:.1f}%)")
        if kbd:
            calc_kbd = calculate_keyboard_brightness(raw_lux, settings, kbd["max"])
            k_pct = (calc_kbd / kbd["max"]) * 100
            print(f"Calculated Keyboard Target:{calc_kbd}/{kbd['max']} ({k_pct:.1f}%)")
        print("----------------------------------------")
        print("Hardware probe complete (read-only test).")
        return

    if args.monitor:
        print("Entering live monitor mode (read-only, Ctrl+C to exit)...")
        smoothed = read_sensor_lux(als)
        try:
            while True:
                raw = read_sensor_lux(als)
                smoothed = (settings["smoothing_factor"] * raw) + ((1.0 - settings["smoothing_factor"]) * smoothed)
                scr_str = "N/A"
                if screen:
                    val = calculate_screen_brightness(smoothed, settings, screen["max"])
                    scr_str = f"{val}/{screen['max']} ({(val/screen['max'])*100:.0f}%)"
                kbd_str = "N/A"
                if kbd:
                    kval = calculate_keyboard_brightness(smoothed, settings, kbd["max"])
                    kbd_str = f"{kval}/{kbd['max']} ({(kval/kbd['max'])*100:.0f}%)"
                print(f"\rLux (raw/smooth): {raw:6.1f} / {smoothed:6.1f} | Screen: {scr_str:>14} | Kbd: {kbd_str:>12}", end="", flush=True)
                time.sleep(settings["poll_interval"])
        except KeyboardInterrupt:
            print("\nMonitor stopped.")
            return

    # Check root before daemon execution
    if os.geteuid() != 0:
        print("[!] Warning: Writing to /sys/class requires root privileges.")
        print("    Run with 'sudo macbook-als' or install as systemd service.")
        sys.exit(1)

    run_daemon(settings, als, screen, kbd)


if __name__ == "__main__":
    main()
