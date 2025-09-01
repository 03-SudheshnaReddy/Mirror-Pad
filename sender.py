# sender_gui.py
import PySimpleGUI as sg
import threading, time, socket, json
from protocol import (pack_message_with_wrapper, frame_message,
                      compute_checksum_for_obj_content, calc_line_patches, apply_patches)

# --- Fixed Receiver IP + Port ---
RECEIVER_IP = "192.168.137.240"   # Your receiver’s IP
TCP_PORT = 50010

# --- Theme (PrincessSudhi) ---
my_theme = {
    'BACKGROUND': '#1E1F26','TEXT': '#FFD700','INPUT': '#2C2F33','TEXT_INPUT': '#FFFFFF',
    'SCROLL': '#99AAB5','BUTTON': ('white', '#FF69B4'),'PROGRESS': ('#01826B', '#D0D0D0'),
    'BORDER': 2, 'SLIDER_DEPTH': 0, 'PROGRESS_DEPTH': 0,
}
sg.LOOK_AND_FEEL_TABLE['PrincessSudhi'] = my_theme
sg.theme('PrincessSudhi')

# GUI layout
layout = [
    [sg.Text("🌸 Sudhi Sender Pad 🌸", font=("Segoe UI", 16, "bold"),
             text_color='#FF69B4', background_color='#1E1F26', expand_x=True, justification='center')],
    [sg.Multiline("", size=(80,24), font=("Consolas", 13), background_color='#2C2F33',
                  text_color='white', key='-TXT-', enable_events=True)],
    [sg.Text("Status:", size=(7,1), background_color='#1E1F26'),
     sg.Text("○ Disconnected", key='-STATUS-', text_color='red', background_color='#1E1F26', font=("Segoe UI",11,'italic'))]
]
win = sg.Window("Sender Notepad", layout, finalize=True)

# Network worker (direct connect + send)
class NetWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.tcp_sock = None
        self.connected = False
        self.lock = threading.Lock()
        self.seq = 0

    def connect(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((RECEIVER_IP, TCP_PORT))
            sock.settimeout(None)
            self.tcp_sock = sock
            self.connected = True
            return True
        except Exception as e:
            print("connect failed:", e)
            return False

    def send_obj(self, obj: dict):
        try:
            outer = pack_message_with_wrapper(obj)
            msg = frame_message(outer)
            with self.lock:
                self.tcp_sock.sendall(msg)
                self.seq += 1
        except Exception as e:
            print("send failed:", e)
            self.connected = False

net = NetWorker()
net.start()

# background thread to keep trying to connect
def try_connect_loop():
    while True:
        if not net.connected:
            ok = net.connect()
            if ok:
                print(f"✅ Connected to receiver at {RECEIVER_IP}:{TCP_PORT}")
        time.sleep(2.0)

threading.Thread(target=try_connect_loop, daemon=True).start()

# typing/debounce logic
last_text = ""
last_sent_full = ""
DEBOUNCE_MS = 400
last_event_time = time.time()

while True:
    ev, vals = win.read(timeout=DEBOUNCE_MS)
    if ev == sg.WIN_CLOSED:
        break
    cur = vals['-TXT-']
    if cur != last_text:
        last_event_time = time.time()
        last_text = cur
    # if idle beyond debounce, produce patch
    if time.time() - last_event_time > DEBOUNCE_MS/1000.0:
        if cur != last_sent_full and net.connected:
            patches = calc_line_patches(last_sent_full, cur)
            if patches is None:
                obj = {"seq": net.seq+1, "type":"full", "text": cur}
                obj['checksum'] = compute_checksum_for_obj_content(obj)
                net.send_obj(obj)
                last_sent_full = cur
            else:
                obj = {"seq": net.seq+1, "type":"patch", "patches": patches}
                obj['checksum'] = compute_checksum_for_obj_content(obj)
                net.send_obj(obj)
                last_sent_full = apply_patches(last_sent_full, patches)
            win['-STATUS-'].update(f"● Sent seq {net.seq}", text_color='lightgreen')
    win['-STATUS-'].update(f"● Connected" if net.connected else "○ Disconnected",
                           text_color='lightgreen' if net.connected else 'red')

win.close()
