# macbook-als-fix 

A lightweight, zero-dependency Ambient Light Sensor (ALS) auto-brightness daemon for MacBook devices running Linux.

It brings back native macOS-style automatic display brightness and keyboard backlighting with smooth transitions, hysteresis filtering, and quick one-touch toggling.

---

## Step 1: Quick Test 

Clone the repository and verify that your MacBook's sensors are detected:
```bash
git clone https://github.com/faqpy/macbook-als-fix.git
cd macbook-als-fix
python3 macbook-als.py --test
```

To see the sensor readings and brightness calculations update in real time without modifying any screen settings:

```bash
# Cover the webcam/sensor with your hand to watch lux drop
python3 macbook-als.py --monitor
```

---

## Step 2: Installation

Run the simple install script with root privileges:

```bash
sudo ./install.sh
```

This installs:
1. Executable to `/usr/local/bin/macbook-als`
2. Configuration file to `/etc/macbook-als.conf`
3. Systemd service to `/etc/systemd/system/macbook-als.service`

---

## Step 3: Enable the Background Service

Start the service and enable it to launch automatically on every boot:

```bash
sudo systemctl enable --now macbook-als

# You can check if the service is running by:
sudo systemctl status macbook-als
```

---

## Toggling Auto-Brightness

You can toggle or pause auto-brightness anytime **without needing `sudo`**:

```bash
# Toggle between active and paused (sends desktop notification):
# You can also set this to a keybind fo efficiency
macbook-als --toggle

# Or explicitly pause / resume:
macbook-als --pause
macbook-als --resume

# Check current status:
macbook-als --status
```

---

## Configuration

You can customize sensitivity, thresholds, and behavior by editing `/etc/macbook-als.conf`:

```ini
[General]
poll_interval = 1.0       # Seconds between sensor checks
smoothing_factor = 0.25    # Lower = smoother transitions (0.05 to 0.5)
max_expected_lux = 1000.0  # Max sensor range

[Screen]
min_screen_percent = 5     # Minimum display brightness (never black)
max_screen_percent = 100   # Maximum display brightness

[Keyboard]
enabled = true             # Set false to disable keyboard backlight control
threshold_lux = 150.0      # Ambient lux below which keyboard lights up
max_percent = 80           # Keyboard backlight brightness in complete darkness
```

After changing settings, restart the service:
```bash
sudo systemctl restart macbook-als
```

---

## Uninstallation

To completely remove the service and binaries:

```bash
sudo ./uninstall.sh
```
