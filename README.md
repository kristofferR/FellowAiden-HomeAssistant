# Fellow Aiden Integration for Home Assistant

<p align="center">
  <a href="https://github.com/kristofferR/FellowAiden-HomeAssistant/releases"><img src="https://img.shields.io/github/v/release/kristofferR/FellowAiden-HomeAssistant" alt="GitHub Release"></a>
  <a href="https://github.com/kristofferR/FellowAiden-HomeAssistant/actions/workflows/validate.yml"><img src="https://img.shields.io/github/actions/workflow/status/kristofferR/FellowAiden-HomeAssistant/validate.yml?label=validation" alt="Validation"></a>
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Default-blue.svg" alt="HACS"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/kristofferR/FellowAiden-HomeAssistant" alt="License"></a>
</p>

<img src="device.png" alt="Device Image" align="right" width="200"/>

> *“A good brew is like a good friend: reliable, comforting, and occasionally in need of a little maintenance.”*  

This is a custom integration that brings your coffee brewer into the Home Assistant universe. Because life’s too short for bad coffee and disconnected devices.

*Special thanks to [Brandon Dixon (9b)](https://github.com/9b) for creating the [fellow-aiden](https://github.com/9b/fellow-aiden) Python library that laid the groundwork for this integration!*

<sub>You might also like my [Brew.link to Aiden](https://greasyfork.org/en/scripts/524547-brew-link-to-aiden) userscript to send Brew.link profiles directly to your Fellow Aiden.</sub>

## Table of Contents
- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Services](#services)
- [FAQ & Troubleshooting](#faq--troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **Real-Time Sensors:**
  - **Sensors** for brew phase, pump, heater, connectivity, water usage, number of brews, average water per brew and more.
  - **Analytics:** Daily/weekly/monthly water usage tracking, brew patterns, and timing insights.
  - **Binary sensors** for brewing, lid status, missing water, baskets inserted, etc.
- **Device Info:** Displays firmware, SKU, serial number, elevation, Wi-Fi and Bluetooth inventory, plus cloud connection state.
- **Cloud Push:** Receives the same Firebase data messages as the Fellow Android app, refreshes state immediately, and exposes connection diagnostics.
- **Brew Management:** 
  - Create, list, delete, and manage brew profiles from Home Assistant
  - Schedule management
- **Services:** A collection of services for all brewing operations
- **Smart Logging:** Detailed API logging for manual operations, quiet polling for regular updates
- **Water Usage Tracking:** Historical tracking with reset capabilities and period-specific sensors

## Screenshot

<p align="center">
<img width="720" alt="Image" src="https://github.com/user-attachments/assets/6cf8a133-dc34-4ae6-a1e7-845c8d150d25" />
</p>

---

## Installation

Choose one of the following methods to install the **Fellow Aiden** integration:

### 1. Install via HACS (Recommended)

**Prerequisites:**
- **Home Assistant** and **HACS (Home Assistant Community Store)** installed. [HACS Installation Guide](https://hacs.xyz/docs/installation/prerequisites)

**Steps:**

1. **Install the Integration**
   - Open Home Assistant and click on **HACS** in the sidebar.
   - Search for **"Fellow Aiden"** and select it.
   - Click **"Download"**.

2. **Configure the Integration**
   - **Restart Home Assistant**.
   - After restarting, navigate to **Settings > Devices & Services**.
   - Click **"Add Integration"**, find **"Fellow Aiden"**, and follow the prompts to log in with your brewer account credentials.

<details>
<summary><strong>Manual Installation</strong></summary>

1. **Download or Clone the Repository**
   ```bash
   cd /config/custom_components
   git clone https://github.com/kristofferR/FellowAiden-HomeAssistant.git fellow
   ```
   - Ensure the folder is named exactly `fellow`.

2. **Restart Home Assistant**
   - This allows Home Assistant to detect the new integration.

3. **Add the Integration**
   - Go to **Settings > Devices & Services**.
   - Click **"Add Integration"**, search for **"Fellow Aiden"**, and follow the prompts to log in with your brewer account credentials.

</details>

---

## Configuration

### Installation parameters

| Parameter | Description |
|-----------|-------------|
| **Email** | The email address for your Fellow Aiden account. |
| **Password** | Your Fellow account password. |
| **Brewer** | The Aiden to add when the account contains more than one unconfigured brewer. |

Each Aiden is represented by its own Home Assistant config entry. To add
multiple brewers from the same Fellow account, run **Add Integration** once for
each brewer and choose a different brewer each time. Already configured
brewers are omitted from the chooser.

### Options

After installation, go to **Settings > Devices & Services > Fellow Aiden > Configure** to change:

| Option | Default | Range | Description |
|--------|---------|-------|-------------|
| Cloud push | On | On/Off | Register a private Android FCM receiver for immediate cloud-triggered updates. |
| Update interval | 10 s | 10-300 s | Fallback polling interval while push is unavailable. Connected push uses a 60-second safety poll. |

---

## How data is updated

The integration uses Fellow's v2 cloud API. By default it registers an Android-compatible Firebase receiver and refreshes every configured brewer on the account when Fellow sends a data message. A 60-second safety poll remains active while push is connected. If push disconnects or is disabled, live state returns to the configurable polling interval (default 10 seconds). Profiles and schedules refresh separately every 60 seconds. Historical brew and water usage data is tracked locally and kept for 365 days.

Receiver credentials and tokens are kept in Home Assistant's private storage and are excluded from diagnostics and logs. Each data message also fires a `fellow_cloud_push` event with `config_entry_ids`, `category`, and the FCM `data` mapping, so automations can react to notification types that Fellow adds without waiting for an integration update.

There is no local brewer connection. Both push messages and refreshed device state travel through Fellow's cloud services.

---

## Removal

1. Go to **Settings > Devices & Services**.
2. Find **Fellow Aiden** and click the three-dot menu.
3. Click **Delete**.

---

## Supported devices

The **Fellow Aiden** coffee brewer. No other Fellow products are supported.

---

## Supported functionality

### Entities

| Platform | Entity | Description |
|----------|--------|-------------|
| Sensor | Total brews | Lifetime brew count. |
| Sensor | Total water volume | Lifetime water usage in liters. |
| Sensor | Last brew volume | Water used in the most recent brew (mL). |
| Sensor | Instant Brew water | Configured Instant Brew volume (mL). |
| Sensor | Brew phase | Live bloom, pulse, drip-finish, paused, or idle phase. |
| Sensor | Last brew start/end time | Timestamps of the last brew. |
| Sensor | Last brew duration | How long the last brew took. |
| Sensor | Last brew time | When the last brew finished. |
| Sensor | Water used today/this week/this month | Period water usage from local tracking. |
| Sensor | Average water per brew | Lifetime average (mL). |
| Sensor | Average brew duration | Historical average (minutes). |
| Sensor | Current profile | The active or most recently used brew profile. |
| Sensor | Basket | Which basket is inserted: single serve, batch, or missing. |
| Sensor | Chime volume | Device chime setting (diagnostic, disabled by default). |
| Binary sensor | Brewing | Whether the brewer is running. |
| Binary sensor | Carafe | Whether the carafe is present. |
| Binary sensor | Heater | Whether the heater is on. |
| Binary sensor | Pump | Whether the pump is on. |
| Binary sensor | Lid | Whether the lid is open. |
| Binary sensor | Shower head | Whether the shower head is present. |
| Binary sensor | Missing water | Whether the water tank is empty. |
| Binary sensor | Cleaning / rinsing | Whether a maintenance cycle is running. |
| Binary sensor | Cloud connection | Whether the brewer reports a cloud connection. |
| Binary sensor | Firmware update | Whether a firmware update is required. |
| Binary sensor | Brew error / unsynced changes | Cloud and live-state problem indicators. |

### Services

| Service | Description |
|---------|-------------|
| `fellow.create_profile` | Create a brew profile with full parameter control. |
| `fellow.delete_profile` | Delete a profile by ID. |
| `fellow.list_profiles` | List all profiles (returns response data). |
| `fellow.get_profile_details` | Get full details for one profile. |
| `fellow.create_schedule` | Create a brewing schedule with day/time/profile. |
| `fellow.delete_schedule` | Delete a schedule by ID. |
| `fellow.toggle_schedule` | Enable or disable a schedule. |
| `fellow.list_schedules` | List all schedules. |
| `fellow.reset_water_tracking` | Reset the water usage baseline. |
| `fellow.debug_water_usage` | Dump raw water usage records. |
| `fellow.refresh_and_log_data` | Force a data refresh and return the API response. |

Service actions continue to work without a target when only one Fellow Aiden
entry is loaded. With multiple brewers, choose the **Brewer** config entry (or
provide `config_entry_id` in YAML) so the action cannot affect the wrong Aiden.

---

## Automation examples

Notify when a brew finishes:

```yaml
automation:
  - alias: "Brew finished notification"
    trigger:
      - platform: state
        entity_id: binary_sensor.fellow_aiden_brewer_brewing
        from: "on"
        to: "off"
    action:
      - service: notify.mobile_app
        data:
          title: "Coffee's ready"
          message: "Your brew just finished."
```

Log water usage at midnight:

```yaml
automation:
  - alias: "Log water usage at midnight"
    trigger:
      - platform: time
        at: "00:00:00"
    action:
      - service: logbook.log
        data:
          name: "Fellow Aiden"
          message: >
            Water today:
            {{ states('sensor.fellow_aiden_brewer_water_used_today') }} L
```

---

## Known limitations

- No direct brew start: v2 advertises remote brewing, but the observed cancellation endpoint did not reliably stop a running brew. The integration does not expose an unsafe start-only control.
- No remote profile selection: the mobile client contains a selection route, but Fellow's live Aiden gateway rejects authenticated calls to it. The integration exposes the current profile as a sensor instead of a non-functional control.
- Cloud push uses Fellow's Android Firebase registration flow, which is an undocumented mobile protocol. The integration automatically reconnects and retains polling as the source-of-truth fallback.
- Cloud-only: all data comes through Fellow's servers. If their API is down, the integration can't update.

---

## Use cases

- **Morning routine**: schedule a brew at 6:30 AM on weekdays and automate kitchen lights when brewing starts.
- **Water tracking**: monitor daily consumption and alert on unusual spikes.
- **Profile management**: create and rotate brew profiles from automations.
- **Brew logging**: track brew frequency, profile usage, and water per brew over time.

---

## FAQ & Troubleshooting

1. **"Device not found" / "No supported brewer found"** -- Make sure the account you used has at least one Fellow Aiden brewer linked to it. Mixed-device and multi-Aiden accounts are supported; unsupported Fellow products are omitted from the brewer chooser.

2. **Sensors showing "Unknown"** -- The brewer may not have reported data yet. Wait a few minutes. If it persists for days, file a bug report.

3. **"Authentication failed" after setup** -- Your password may have changed. Go to **Settings > Devices & Services > Fellow Aiden** and use **Reconfigure** to update your credentials.

4. **Diagnostics** -- Download from **Settings > Devices & Services > Fellow Aiden > (device) > Download diagnostics**. Attach to bug reports. Sensitive data (password, MAC addresses, IP) is automatically redacted.

5. **Water usage sensors show 0** -- Water tracking is cumulative and stored locally. If the store was lost, use `fellow.reset_water_tracking` to set a new baseline.

---

## Contributing

- **Issues**: Spot a bug, have a feature request, or can’t resist a coffee pun? [Open an issue](https://github.com/kristofferR/FellowAiden-HomeAssistant/issues).  
- **PRs**: Fork, code, and send a pull request. We welcome improvements—just keep code style and good taste in brew puns consistent.  
- **Local Testing**: If you break something, revert changes or blame the brew cycle. Either is acceptable.

---

## License

This project is released under the [GPL-3.0 license](LICENSE). Use it, change it, share it—just don’t blame us if your coffee cravings skyrocket.

---

**Enjoy** your now-connected coffee brewer, and may your mornings be bright, your lid properly closed, and your water tank never empty.
