# Phonegeist

<p align="center">
  <img src="assets/phonegeist-logo.png" alt="Phonegeist logo" width="420">
</p>

Phonegeist turns a phone into a text remote for a Windows PC. Start the app,
scan the QR code shown in the terminal, paste text on the phone, and Phonegeist
types it into the active field on the PC using normal Windows keyboard events.

The phone does not need an app. Everything is hosted locally by the PC, and the
text stays on the local network.

## Requirements

- Windows 10 or 11
- Python 3.10 or newer
- A phone and PC connected to the same Wi-Fi network

Phone hotspots may isolate the hotspot phone from connected devices. If the QR
address does not open, connect both devices to a normal router or a third
device's hotspot.

## Quick start

1. Download and extract the project.
2. Double-click `start-phonegeist.bat`.
3. On the first run, allow Python through Windows Firewall for the current
   private network.
4. Scan the QR code displayed in the terminal.
5. Paste text on the phone and select the typing speed and start delay.
6. Press **Send to laptop**, then click the destination field on the PC.

Keep the terminal window open while using Phonegeist. Press `Ctrl+C` in that
window to stop the server.

## Command-line installation

Create a virtual environment and install the project:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install .
phonegeist
```

To use a different port or omit the QR code:

```powershell
phonegeist --port 8080
phonegeist --no-qr
```

For development, install the requirements and run the source file directly:

```powershell
python -m pip install -r requirements.txt
python typer.py
```

## Phone controls

| Control | Action |
| --- | --- |
| Send to laptop | Starts the countdown and then types the text |
| Pause / Resume | Pauses and continues the active typing job |
| Stop | Cancels the active typing job |

Start at 60–80 ms per character. Some applications discard very fast synthetic
input, so use 100–120 ms if characters are missing.

Line breaks generate real Enter presses and tabs generate real Tab presses. In
chat applications, Enter may submit a message.

## Security and privacy

Phonegeist listens on all local network interfaces so the phone can reach it.
There is currently no login or encryption. Only run it on a network you trust,
close it when finished, and do not expose port 5000 to the public internet.

The tool sends programmatically generated keyboard events. It does not use
Playwright or Selenium, but software-generated input may still be detectable.
Use it only where typing assistance is allowed.

## Troubleshooting

### The QR address does not load

- Confirm the phone and PC are on the same normal Wi-Fi network.
- Disable mobile data temporarily if the phone prefers it over Wi-Fi.
- Allow Python through Windows Firewall when prompted.
- Avoid guest Wi-Fi, client-isolated networks, and a hotspot hosted by the same
  phone that is scanning the code.

### Some characters are missing

Increase the speed setting to at least 60 ms per character. Slower or busy
applications may need 100–120 ms.

### The QR code is hard to scan

Maximize the terminal window, increase its font size, and ensure the entire
quiet border around the QR code is visible. The URL is also printed below it
for manual entry.

## Contributing

Issues and pull requests are welcome. Please keep changes focused, test on
Windows, and avoid adding cloud services—the project is designed to remain
local-first.

## License

Phonegeist is released under the [MIT License](LICENSE).
