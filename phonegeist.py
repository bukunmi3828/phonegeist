"""Phonegeist: a local phone-to-keyboard server for Windows.

Type text from your phone into the active field on a Windows PC over the local network.
Includes photo and file transfer capabilities without cloud services or logging.
"""

from __future__ import annotations

import argparse
import logging
import random
import re
import socket
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import qrcode
from flask import Flask, request, Response, send_from_directory
from pynput.keyboard import Controller, Key

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024

kb = Controller()
RECEIVED_DIR = Path.home() / "Downloads" / "Phonegeist"
SHARE_DIR = Path.home() / "Downloads" / "Phonegeist Share"
ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".bmp", ".tif", ".tiff"
}

state: dict[str, bool] = {"stop": False, "paused": False, "running": False}
lock = threading.Lock()

logger = logging.getLogger(__name__)

PAGE = """
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Phonegeist</title><style>
body{font-family:system-ui;margin:0;padding:16px;background:#111;color:#eee}
textarea{width:100%;height:170px;font-size:16px;padding:10px;border-radius:8px;border:1px solid #444;background:#1c1c1c;color:#eee;box-sizing:border-box}
label{display:block;margin:14px 0 6px}
input[type=range]{width:100%}
button{padding:16px;font-size:17px;border:0;border-radius:8px;color:#fff}
#send{width:100%;background:#4a7;margin-top:16px}
#send:active{background:#385}
.ctrls{display:flex;gap:10px;margin-top:12px}
.ctrls button{flex:1}
#pause{background:#c93}#stop{background:#c44}
.row{display:flex;justify-content:space-between;font-size:14px;color:#aaa}
#status{text-align:center;margin-top:12px;color:#8c8;min-height:20px}
.photos{margin-top:28px;padding-top:20px;border-top:1px solid #333}
#photos{width:100%;box-sizing:border-box;padding:12px;background:#1c1c1c;border:1px solid #444;border-radius:8px}
#upload{width:100%;background:#4676c8;margin-top:12px}
#progress{width:100%;margin-top:12px;display:none}
#uploadStatus{text-align:center;margin-top:8px;color:#8cf;min-height:20px}
.downloadItem{display:flex;align-items:center;gap:10px;justify-content:space-between;margin-top:10px;padding:10px;background:#1c1c1c;border:1px solid #333;border-radius:8px}
.downloadItem span{overflow-wrap:anywhere}
.downloadItem a{flex:none;padding:10px 12px;border-radius:8px;background:#4a7;color:#fff;text-decoration:none}
#downloadStatus{text-align:center;margin-top:8px;color:#8cf;min-height:20px}
</style></head><body>
<textarea id="t" placeholder="Paste your text here"></textarea>
<label>Speed <span id="sv">60</span> ms/char</label>
<input type="range" id="s" min="20" max="200" value="60">
<div class="row"><span>fast</span><span>slow</span></div>
<label>Start delay <span id="dv">3</span>s (time to click the field)</label>
<input type="range" id="d" min="1" max="10" value="3">
<button id="send" onclick="go()">Send to laptop</button>
<div class="ctrls">
 <button id="pause" onclick="pause()">Pause</button>
 <button id="stop" onclick="stop()">Stop</button>
</div>
<div id="status"></div>
<section class="photos">
 <h2>Send photos to computer</h2>
 <input id="photos" type="file" accept="image/*" multiple>
 <button id="upload" onclick="uploadPhotos()">Transfer photos</button>
 <progress id="progress" max="100" value="0"></progress>
 <div id="uploadStatus"></div>
</section>
<section class="photos">
 <h2>Download from computer</h2>
 <button id="refreshDownloads" onclick="loadDownloads()">Refresh files</button>
 <div id="downloadStatus"></div>
 <div id="downloads"></div>
</section>
<script>
s.oninput=()=>sv.textContent=s.value
d.oninput=()=>dv.textContent=d.value
async function go(){
 status.textContent="Typing starts in "+d.value+"s — click your field now!"
 const r=await fetch('/type',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({text:t.value,speed:+s.value/1000,delay:+d.value})})
 const j=await r.json()
 if(!r.ok) status.textContent=j.error||"Could not start typing"
}
async function pause(){
 const r=await fetch('/pause',{method:'POST'})
 const j=await r.json()
 document.getElementById('pause').textContent=j.paused?"Resume":"Pause"
 status.textContent=j.paused?"Paused":"Resumed"
}
async function stop(){
 await fetch('/stop',{method:'POST'})
 document.getElementById('pause').textContent="Pause"
 status.textContent="Stopped"
}
function uploadPhotos(){
 const files=document.getElementById('photos').files
 if(!files.length){uploadStatus.textContent="Choose one or more photos first.";return}
 const data=new FormData()
 for(const file of files)data.append('photos',file)
 const xhr=new XMLHttpRequest()
 progress.style.display="block"; progress.value=0
 upload.disabled=true; uploadStatus.textContent="Transferring…"
 xhr.upload.onprogress=e=>{if(e.lengthComputable)progress.value=e.loaded/e.total*100}
 xhr.onload=()=>{
   upload.disabled=false
   try{
     const j=JSON.parse(xhr.responseText)
     uploadStatus.textContent=xhr.status===200
       ? j.saved+" photo"+(j.saved===1?"":"s")+" saved on the computer."
       : j.error||"Transfer failed."
   }catch(_){uploadStatus.textContent="Transfer failed."}
 }
 xhr.onerror=()=>{upload.disabled=false;uploadStatus.textContent="Connection lost during transfer."}
 xhr.open('POST','/upload'); xhr.send(data)
}
function formatBytes(bytes){
 if(bytes<1024)return bytes+" B"
 const units=["KB","MB","GB","TB"]
 let size=bytes/1024, unit=0
 while(size>=1024&&unit<units.length-1){size/=1024;unit++}
 return size.toFixed(size>=10?0:1)+" "+units[unit]
}
async function loadDownloads(){
 const holder=document.getElementById('downloads')
 downloadStatus.textContent="Loading..."
 holder.innerHTML=""
 try{
   const r=await fetch('/downloads')
   const j=await r.json()
   if(!r.ok){downloadStatus.textContent=j.error||"Could not load files.";return}
   if(!j.files.length){downloadStatus.textContent="No files in the computer share folder yet.";return}
   downloadStatus.textContent=""
   for(const file of j.files){
     const row=document.createElement('div')
     row.className='downloadItem'
     const name=document.createElement('span')
     name.textContent=file.name+" ("+formatBytes(file.size)+")"
     const link=document.createElement('a')
     link.href='/download/'+encodeURIComponent(file.name)
     link.textContent='Download'
     row.append(name,link)
     holder.append(row)
   }
 }catch(_){downloadStatus.textContent="Could not load files."}
}
loadDownloads()
setInterval(async()=>{
 const r=await fetch('/status'); const j=await r.json()
 if(!j.running && status.textContent==="Typing…") status.textContent="Done."
 if(j.running) status.textContent=j.paused?"Paused":"Typing…"
},700)
</script></body></html>
"""

def do_type(text: str, speed: float, delay: float) -> None:
    """Type text into the active Windows field using synthesized keyboard events.

    Respects pause/stop signals and handles special characters (newlines, tabs).
    Runs in a background thread; updates shared state when complete.

    Args:
        text: The text to type, may contain newlines and tabs.
        speed: Delay in seconds between keystrokes.
        delay: Initial delay in seconds before typing starts.
    """
    try:
        end_of_delay = time.monotonic() + delay
        while time.monotonic() < end_of_delay:
            with lock:
                if state["stop"]:
                    return
            time.sleep(min(0.05, end_of_delay - time.monotonic()))

        text = text.replace("\r\n", "\n").replace("\r", "\n")
        key_hold = min(0.008, speed * 0.25)
        for ch in text:
            with lock:
                if state["stop"]:
                    break
            while True:
                with lock:
                    if not state["paused"] or state["stop"]:
                        break
                time.sleep(0.1)
            with lock:
                if state["stop"]:
                    break

            key = Key.enter if ch == "\n" else Key.tab if ch == "\t" else ch
            kb.press(key)
            time.sleep(key_hold)
            kb.release(key)
            time.sleep(speed + random.uniform(0, speed * 0.7))
    except Exception:
        logger.exception("Typing worker failed")
    finally:
        with lock:
            state["running"] = False
            state["paused"] = False

@app.route('/')
def home() -> Response:
    """Serve the Phonegeist web interface."""
    return Response(PAGE, mimetype='text/html')

def safe_photo_name(filename: str | None) -> str | None:
    """Create a non-conflicting, filesystem-safe photo filename with UUID suffix.

    Validates image extensions, sanitizes the stem, and appends a UUID fragment.

    Args:
        filename: Original filename from upload.

    Returns:
        Safe filename with UUID suffix, or None if extension is not allowed.
    """
    original = Path(filename or "")
    extension = original.suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return None
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", original.stem).strip(" .")[:100]
    stem = stem or "photo"
    return f"{stem}-{uuid.uuid4().hex[:8]}{extension}"


def safe_shared_file_name(filename: str | None) -> str | None:
    """Validate that a filename refers to a file in the share directory root.

    Prevents path traversal attacks by rejecting paths containing separators.

    Args:
        filename: The filename to validate.

    Returns:
        The filename if valid, None if it contains path separators or is invalid.
    """
    name = Path(filename or "").name
    if not name or name in {".", ".."}:
        return None
    if Path(name).name != filename:
        return None
    return name


@app.route('/upload', methods=['POST'])
def upload_photos() -> tuple[dict[str, Any], int]:
    """Handle photo upload from the phone.

    Validates image formats, generates safe filenames with UUID suffixes,
    and saves files to the receive directory. Fails atomically on I/O errors.
    """
    photos = request.files.getlist('photos')
    if not photos or all(not photo.filename for photo in photos):
        return {'ok': False, 'error': 'no photos selected'}, 400
    if len(photos) > 100:
        return {'ok': False, 'error': 'select no more than 100 photos at once'}, 400

    prepared = []
    for photo in photos:
        if not photo.filename:
            continue
        safe_name = safe_photo_name(photo.filename)
        if safe_name is None:
            return {'ok': False, 'error': f'unsupported image: {photo.filename}'}, 415
        prepared.append((photo, safe_name))

    RECEIVED_DIR.mkdir(parents=True, exist_ok=True)
    saved = []
    try:
        for photo, safe_name in prepared:
            destination = RECEIVED_DIR / safe_name
            photo.save(destination)
            saved.append(destination)
    except OSError:
        for destination in saved:
            destination.unlink(missing_ok=True)
        logger.exception("Photo upload failed")
        return {'ok': False, 'error': 'could not save photos on the computer'}, 500
    return {'ok': True, 'saved': len(saved)}


@app.route('/downloads')
def list_downloads() -> dict[str, Any]:
    """Return a JSON list of files available for download to the phone."""
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for item in SHARE_DIR.iterdir():
        if item.is_file():
            files.append({
                'name': item.name,
                'size': item.stat().st_size,
            })
    files.sort(key=lambda file: file['name'].lower())
    return {'ok': True, 'files': files}


@app.route('/download/<path:filename>')
def download_shared_file(filename: str) -> Response | tuple[dict[str, Any], int]:
    """Serve a file from the share directory, preventing path traversal.

    Args:
        filename: The requested file name.

    Returns:
        The file content, or a 400 error if the path is invalid.
    """
    safe_name = safe_shared_file_name(filename)
    if safe_name is None:
        return {'ok': False, 'error': 'invalid file name'}, 400
    return send_from_directory(SHARE_DIR, safe_name, as_attachment=True)


@app.route('/type', methods=['POST'])
def type_text() -> tuple[dict[str, Any], int]:
    """Start a typing job with text from the phone.

    Validates input, launches a background worker thread, and prevents overlapping jobs.

    Request JSON fields:
        text (str): The text to type (max 100,000 chars).
        speed (float, optional): Seconds per keystroke (0.02–1.0, default 0.06).
        delay (float, optional): Seconds before typing starts (0–30, default 3).
    """
    with lock:
        if state["running"]:
            return {'ok': False, 'error': 'already typing'}, 409

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('text'), str):
        return {'ok': False, 'error': 'text must be a string'}, 400
    if len(data['text']) > 100_000:
        return {'ok': False, 'error': 'text is too long'}, 413
    try:
        speed = max(0.02, min(float(data.get('speed', 0.06)), 1.0))
        delay = max(0, min(float(data.get('delay', 3)), 30))
    except (TypeError, ValueError):
        return {'ok': False, 'error': 'invalid speed or delay'}, 400

    with lock:
        if state["running"]:
            return {'ok': False, 'error': 'already typing'}, 409
        state.update(stop=False, paused=False, running=True)

    t = threading.Thread(target=do_type, args=(
        data['text'], speed, delay))
    t.daemon = True
    try:
        t.start()
    except Exception:
        with lock:
            state["running"] = False
        raise
    return {'ok': True}

@app.route('/pause', methods=['POST'])
def pause() -> dict[str, bool]:
    """Toggle pause on an active typing job.

    Returns the new pause state. If no job is running, returns paused=False.
    """
    with lock:
        if not state["running"]:
            state["paused"] = False
            return {'paused': False}
        state["paused"] = not state["paused"]
        return {'paused': state["paused"]}

@app.route('/stop', methods=['POST'])
def stop() -> dict[str, bool]:
    """Stop the active typing job immediately."""
    with lock:
        state["stop"] = True
    return {'ok': True}

@app.route('/status')
def status() -> dict[str, bool]:
    """Return the current state of the typing worker."""
    with lock:
        return {'running': state["running"], 'paused': state["paused"]}

def find_lan_ip() -> str:
    """Return the IPv4 address used for the machine's default network route.

    Attempts UDP route selection to find the primary interface; falls back
    to gethostbyname if that fails.

    Returns:
        An IPv4 address string suitable for LAN access.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return socket.gethostbyname(socket.gethostname())
    finally:
        probe.close()


def print_qr(url: str, output: Any = None) -> None:
    """Print a compact QR code that phone cameras can scan from the terminal.

    Args:
        url: The URL to encode in the QR code.
        output: A file-like object; defaults to sys.stdout.
    """
    output = output or sys.stdout
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_Q,
        box_size=1,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(out=output, tty=bool(getattr(output, "isatty", lambda: False)()))


def choose_receive_directory(initial_directory: Path) -> Path:
    """Show the native Windows folder picker, falling back when cancelled.

    Args:
        initial_directory: Default directory to show in the picker.

    Returns:
        The selected directory, or initial_directory if cancelled or an error occurs.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            title="Choose where Phonegeist should save photos",
            initialdir=str(initial_directory),
            mustexist=True,
            parent=root,
        )
        root.destroy()
        return Path(selected) if selected else initial_directory
    except (ImportError, OSError, RuntimeError):
        logger.exception("Could not open the folder picker")
        return initial_directory


def main(argv: list[str] | None = None) -> None:
    """Start the Phonegeist server and display connection information.

    Initializes the Flask app, prints the QR code or URL, and starts listening
    on all local network interfaces.

    Args:
        argv: Command-line arguments; defaults to sys.argv[1:] if None.
    """
    global RECEIVED_DIR, SHARE_DIR
    parser = argparse.ArgumentParser(
        prog="phonegeist",
        description="Type text from your phone into the active Windows field via local network.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        metavar="PORT",
        help="server port (default: 5000)",
    )
    parser.add_argument(
        "--no-qr",
        action="store_true",
        help="do not print a terminal QR code (still shows the URL)",
    )
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument(
        "--choose-folder",
        action="store_true",
        help="show a Windows folder picker dialog before starting",
    )
    destination.add_argument(
        "--receive-dir",
        type=Path,
        metavar="FOLDER",
        help="directory where photos from the phone are saved",
    )
    parser.add_argument(
        "--share-dir",
        type=Path,
        metavar="FOLDER",
        help="directory whose files are offered for download to the phone",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if args.receive_dir:
        RECEIVED_DIR = args.receive_dir.expanduser().resolve()
    elif args.choose_folder:
        RECEIVED_DIR = choose_receive_directory(RECEIVED_DIR)
    if args.share_dir:
        SHARE_DIR = args.share_dir.expanduser().resolve()

    url = f"http://{find_lan_ip()}:{args.port}"
    print("\nPhonegeist")
    print("----------")
    print("Connect the phone and laptop to the same Wi-Fi, then scan:\n")
    if not args.no_qr:
        print_qr(url)
    print(f"\nOpen on your phone: {url}")
    print(f"Photos will be saved to: {RECEIVED_DIR}")
    print(f"Files for phone downloads: {SHARE_DIR}")
    print("Keep this window open. Press Ctrl+C to stop.\n")
    app.run(host="0.0.0.0", port=args.port, threaded=True, use_reloader=False)


if __name__ == '__main__':
    main()
