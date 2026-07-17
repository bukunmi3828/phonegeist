"""Phonegeist: a local phone-to-keyboard server for Windows."""

from flask import Flask, request, Response
from pynput.keyboard import Controller, Key
import argparse
import random
import socket
import sys
import threading
import time

import qrcode

app = Flask(__name__)
kb = Controller()

state = {"stop": False, "paused": False, "running": False}
lock = threading.Lock()

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
setInterval(async()=>{
 const r=await fetch('/status'); const j=await r.json()
 if(!j.running && status.textContent==="Typing…") status.textContent="Done."
 if(j.running) status.textContent=j.paused?"Paused":"Typing…"
},700)
</script></body></html>
"""

def do_type(text, speed, delay):
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
            while True:                     # hold here while paused
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
        app.logger.exception("Typing worker failed")
    finally:
        with lock:
            state["running"] = False
            state["paused"] = False

@app.route('/')
def home():
    return Response(PAGE, mimetype='text/html')

@app.route('/type', methods=['POST'])
def type_text():
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
def pause():
    with lock:
        if not state["running"]:
            state["paused"] = False
            return {'paused': False}
        state["paused"] = not state["paused"]
        return {'paused': state["paused"]}

@app.route('/stop', methods=['POST'])
def stop():
    with lock:
        state["stop"] = True
    return {'ok': True}

@app.route('/status')
def status():
    with lock:
        return {'running': state["running"], 'paused': state["paused"]}

def find_lan_ip():
    """Return the IPv4 address used for the machine's default network route."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # UDP connect selects a route without sending application data.
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return socket.gethostbyname(socket.gethostname())
    finally:
        probe.close()


def print_qr(url, output=None):
    """Print a compact QR code that phone cameras can scan from the terminal."""
    output = output or sys.stdout
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_Q,
        box_size=1,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(out=output, tty=bool(getattr(output, "isatty", lambda: False)()))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Type text from your phone into the active Windows field."
    )
    parser.add_argument("--port", type=int, default=5000, help="server port (default: 5000)")
    parser.add_argument("--no-qr", action="store_true", help="do not print a terminal QR code")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")

    url = f"http://{find_lan_ip()}:{args.port}"
    print("\nPhonegeist")
    print("----------")
    print("Connect the phone and laptop to the same Wi-Fi, then scan:\n")
    if not args.no_qr:
        print_qr(url)
    print(f"\nOpen on your phone: {url}")
    print("Keep this window open. Press Ctrl+C to stop.\n")
    app.run(host="0.0.0.0", port=args.port, threaded=True, use_reloader=False)


if __name__ == '__main__':
    main()
