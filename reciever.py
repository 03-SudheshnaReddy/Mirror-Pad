# receiver_gui.py
import PySimpleGUI as sg
import threading, socket, json
from protocol import (
    read_frame, unpack_message_from_wrapper,
    compute_checksum_for_obj_content, apply_patches
)

DISCOVERY_PORT = 50000
TCP_PORT = 50010
DISCOVERY_MSG = b"NOTEPAD_DISCOVERY_V1"
DISCOVERY_REPLY = b"NOTEPAD_HERE_V1"

# custom theme
my_theme = {
    'BACKGROUND': '#1E1F26','TEXT': '#FFD700','INPUT': '#2C2F33','TEXT_INPUT': '#FFFFFF',
    'SCROLL': '#99AAB5','BUTTON': ('white', '#FF69B4'),'PROGRESS': ('#01826B', '#D0D0D0'),
    'BORDER': 2, 'SLIDER_DEPTH': 0, 'PROGRESS_DEPTH': 0,
}
sg.LOOK_AND_FEEL_TABLE['PrincessSudhi'] = my_theme
sg.theme('PrincessSudhi')

layout = [
    [sg.Text("🌸 Sudhi Receiver Pad 🌸", font=("Segoe UI", 16, "bold"),
             text_color='#FF69B4', background_color='#1E1F26',
             expand_x=True, justification='center')],
    [sg.Multiline("", size=(80,24), font=("Consolas", 13),
                  background_color='#2C2F33', text_color='white',
                  key='-TXT-', disabled=True)],
    [sg.Text("Status:", size=(7,1), background_color='#1E1F26'),
     sg.Text("○ Waiting...", key='-STATUS-', text_color='red',
             background_color='#1E1F26', font=("Segoe UI",11,'italic'))]
]
win = sg.Window("Receiver Notepad", layout, finalize=True)

# discovery responder (UDP broadcast reply)
def discovery_responder():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', DISCOVERY_PORT))
    while True:
        data, addr = s.recvfrom(1024)
        if data == DISCOVERY_MSG:
            print(f"Discovery request from {addr}, replying...")
            s.sendto(DISCOVERY_REPLY, addr)

# TCP server thread
class TCPServer(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(('', TCP_PORT))
        self.server.listen(1)
        self.conn = None
        self.connected = False

    def run(self):
        while True:  # always accept new connections
            try:
                print("💤 Waiting for a sender...")
                conn, addr = self.server.accept()
                print(f"✅ Connected from {addr}")
                self.conn = conn
                self.connected = True
                # notify GUI
                win.write_event_value("-UPDATE_STATUS-", "connected")

                conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                conn.settimeout(5.0)

                while True:
                    try:
                        outer = read_frame(conn)
                        if outer is None:
                            raise ConnectionError("Peer closed connection")

                        obj = unpack_message_from_wrapper(outer)
                        received_chk = obj.get('checksum')
                        if not received_chk:
                            continue
                        computed = compute_checksum_for_obj_content(obj)
                        if computed != received_chk:
                            print("checksum mismatch, ignoring")
                            continue

                        handler_queue.append(obj)

                    except socket.timeout:
                        print("⚠️ Timeout, disconnecting...")
                        break
                    except Exception as e:
                        print("conn error", e)
                        break

            finally:
                if self.conn:
                    try:
                        self.conn.close()
                    except:
                        pass
                print("❌ Connection closed")
                self.conn = None
                self.connected = False
                # notify GUI
                win.write_event_value("-UPDATE_STATUS-", "waiting")

handler_queue = []
threading.Thread(target=discovery_responder, daemon=True).start()
server = TCPServer()
server.start()

doc_text = ""
last_seq = 0
while True:
    ev, vals = win.read(timeout=200)
    if ev == sg.WIN_CLOSED:
        break

    if ev == "-UPDATE_STATUS-":
        if vals[ev] == "connected":
            win['-STATUS-'].update("● Connected", text_color='lightgreen')
        else:
            win['-STATUS-'].update("○ Waiting...", text_color='red')

    # process incoming objects
    if handler_queue:
        obj = handler_queue.pop(0)
        seq = obj.get('seq', 0)
        if seq <= last_seq:
            print("stale seq", seq, "last", last_seq)
        else:
            if obj.get('type') == 'full':
                doc_text = obj.get('text', '')
            elif obj.get('type') == 'patch':
                doc_text = apply_patches(doc_text, obj.get('patches', []))
            last_seq = seq
            win['-TXT-'].update(doc_text)
            win['-STATUS-'].update(f"● Got seq {seq}", text_color='lightgreen')

win.close()
