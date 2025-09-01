import zlib, json, base64, hashlib, struct

FRAG_HEADER = struct.Struct("!I")  # 4 byte length prefix

def compress_bytes(b: bytes) -> bytes:
    return zlib.compress(b)

def decompress_bytes(b: bytes) -> bytes:
    return zlib.decompress(b)

def sha256_hex_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def canonical_json_bytes(obj: dict) -> bytes:
    return json.dumps(obj, separators=(',', ':'), sort_keys=True).encode('utf-8')

def compute_checksum_for_obj_content(obj: dict) -> str:
    tmp = dict(obj)
    tmp.pop('checksum', None)
    return sha256_hex_bytes(canonical_json_bytes(tmp))

def pack_message_with_wrapper(obj: dict) -> bytes:
    payload = canonical_json_bytes(obj)
    comp = compress_bytes(payload)
    b64 = base64.b64encode(comp).decode('ascii')
    outer = json.dumps({'payload': b64}, separators=(',', ':'), sort_keys=True).encode('utf-8')
    return outer

def unpack_message_from_wrapper(outer_bytes: bytes) -> dict:
    try:
        wrapper = json.loads(outer_bytes.decode('utf-8'))
        comp_b64 = wrapper['payload'].encode('ascii')
        comp = base64.b64decode(comp_b64)
        payload = decompress_bytes(comp)
        obj = json.loads(payload.decode('utf-8'))
        return obj
    except Exception as e:
        print("⚠️ unpack error:", e)
        return {}

def frame_message(msg_bytes: bytes) -> bytes:
    return FRAG_HEADER.pack(len(msg_bytes)) + msg_bytes

def recvall(sock, n):
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data

def read_frame(sock):
    header = recvall(sock, 4)
    if not header:
        return None
    (length,) = FRAG_HEADER.unpack(header)
    payload = recvall(sock, length)
    return payload

# simple line diffs
def calc_line_patches(old_text: str, new_text: str, max_patch_ratio=0.30):
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    patches = []
    changed = 0
    L = max(len(old_lines), len(new_lines))
    for i in range(L):
        old = old_lines[i] if i < len(old_lines) else None
        new = new_lines[i] if i < len(new_lines) else None
        if old != new:
            changed += 1
            patches.append((i, new))
    if L == 0:
        ratio = 1.0 if changed > 0 else 0.0
    else:
        ratio = changed / L
    if ratio > max_patch_ratio:
        return None
    return patches

def apply_patches(base_text: str, patches):
    try:
        lines = base_text.splitlines()
        for idx, newline in patches:
            if newline is None:
                if 0 <= idx < len(lines):
                    lines.pop(idx)
            else:
                if idx < len(lines):
                    lines[idx] = newline
                else:
                    # extend safely without filling too many empty lines
                    if idx > len(lines) + 100:  # safeguard against crazy index
                        print(f"⚠️ patch index {idx} too far, ignoring")
                        continue
                    while len(lines) < idx:
                        lines.append('')
                    lines.append(newline)
        return "\n".join(lines)
    except Exception as e:
        print("⚠️ patch apply error:", e)
        return base_text  # fallback to old text if something goes wrong
