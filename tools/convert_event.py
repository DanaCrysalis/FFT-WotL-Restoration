"""Convert FFT ReMixed event 159 (Agrias's Birthday, PSX TEST.EVT) into an
Ivalice Chronicles enhanced-mode script (script/enhanced/event159.e) plus a
draft text file for scenario .pzd authoring.

Inputs (extracted from the ReMixed-patched ROM):
  TEST_remixed.EVT   - EVENT/TEST.EVT, 0x2000 bytes per event
  evlen_remixed.bin  - ReMixed's opcode parameter-length table (BATTLE.BIN 0xE6170)
  evlen_enh.bin      - IC enhanced-mode lengths (exe table @file 0x67FF00 with 0x10=17, 0x51=7, 0xEB=10)

What changes, and why:
  * ReMixed-only opcodes are removed. IC defines its own opcodes on several of
    the same numbers (AC, AE, C3, C4, CD, CE), so leaving them in would run
    unrelated IC instructions.
      CE 9E 00            loads ReMixed's world-trigger record from disc
      0003-003B           "hold a button to skip" subroutine (0C/0A/01/0D/04/0B)
      0C B0 (x52 kept)    call to that subroutine -> E5 01 00 E5 04 00, the two waits
                          the subroutine did (dialogue box, then camera)
      0E F0               the skip subroutine's jump target
      AC/AE/C1/C3/C4 ...  inventory +1 Setiemson, item-name variable, Agrias raw HP/MP x1.1
      CD 80 00 00         ReMixed trigger bookkeeping
    The item grant and the HP/MP boost move to the mod's C# side.
  * DisplayMessage / ChangeDialog get IC's widened fields: 32-bit global text
    IDs, and DisplayMessage's final byte becomes a u16.
"""
import struct, sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from convert_wotl import fit

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'research')
OUT = os.path.join(HERE, '..', 'build')
EVENT = 159
TEXT_ID_BASE = 381590          # message n -> TEXT_ID_BASE + n (vanilla IDs end at ~357600)

R = open(os.path.join(SRC, 'evlen_remixed.bin'), 'rb').read()
E = open(os.path.join(SRC, 'evlen_enh.bin'), 'rb').read()
evt = open(os.path.join(SRC, 'TEST_remixed.EVT'), 'rb').read()[EVENT * 0x2000:(EVENT + 1) * 0x2000]
text_ptr = struct.unpack_from('<I', evt, 0)[0]
script, text = evt[4:text_ptr], evt[text_ptr:]

def disasm(sc, table):
    out, i = [], 0
    while i < len(sc):
        op = sc[i]; n = table[op]
        out.append((i, op, sc[i + 1:i + 1 + n])); i += 1 + n
        if op == 0xDB: break
    return out

# Byte ranges of the ReMixed script to drop outright (offsets from the disassembly).
DROP_RANGES = [(0x0000, 0x003C),   # CE 9E 00 + skip subroutine (label B0 .. return)
               (0x0864, 0x0894),   # AC..C4: inventory +1, item-name text variable
               (0x08B7, 0x08E8),   # 0E F0 label, C3/C1/B4/B6/C4: Agrias HP/MP x1.1
               (0x08F8, 0x08FC)]   # CD 80 00 00
def dropped(off): return any(a <= off < b for a, b in DROP_RANGES)

def tid(n): return 0xFFFFFFFF if n == 0xFFFF else TEXT_ID_BASE + n

# ReMixed's scene is War of the Lions' Agrias's Birthday, and IC still ships some of WotL's art for it:
#  - the gift box is unit 0xA9 of WotL's cast (ENTD 527), sprite set 0xA9 (unit_psp/spr_dst_bchr_sword_m_spr.bin): works;
#  - ReMixed's "custom" Mustadio/Agrias pose sheet 0x7A is byte for byte WotL's event sprite sheet 0x8E (same frame table
#    and pixels; IC's copy adds palettes), so slot 0 loads 0x8E. Enhanced mode draws event sheets from textures, and
#    vanilla IC's texture for 0x8E (tex_1279) is a copy of sheet 0x36, which scrambled the poses (v0.3.1); the mod ships
#    the real texture (research/art/tex_1279.bin). `--idle-poses` skips the sheet and uses the idle pose instead.
# `--standin` also drops the gift box (the fallback before WotL's cast was found).
STANDIN_ART = '--standin' in sys.argv
WOTL_POSES = '--idle-poses' not in sys.argv
GIFT_BOX_UNIT = b'\xA9\x00'
UNIT_OPS = {0x11, 0x3B, 0x44, 0x45, 0x46, 0x4E, 0x6F}        # first parameter is the unit id (u16)
SLOT0_ANIMS = range(0x1F4, 0x200)
IDLE_ANIM = 0x0002
REMIXED_POSE_SHEET, WOTL_POSE_SHEET = 0x7A, 0x8E

def standin(op, a):
    """None to drop the instruction, else its (possibly changed) parameters."""
    if op in UNIT_OPS and a[:2] == GIFT_BOX_UNIT: return None
    if op in (0x58, 0x59) and a[0] == 0x00: return None      # Load/SaveEVTCHR slot 0 (sheet 0x7A)
    if op == 0x11 and (a[2] | a[3] << 8) in SLOT0_ANIMS:
        return a[:2] + struct.pack('<H', IDLE_ANIM) + a[4:]
    return a

def wotl_art(op, a):
    if WOTL_POSES:
        if op == 0x58 and (a[1] | a[2] << 8) == REMIXED_POSE_SHEET:
            return a[:1] + struct.pack('<H', WOTL_POSE_SHEET)
        return a
    if op in (0x58, 0x59) and a[0] == 0x00: return None      # Load/SaveEVTCHR slot 0 (the pose sheet)
    if op == 0x11 and (a[2] | a[3] << 8) in SLOT0_ANIMS:
        return a[:2] + struct.pack('<H', IDLE_ANIM) + a[4:]
    return a

# DisplayMessage box style = high nibble of the type byte; these are the ones vanilla IC scripts use.
VANILLA_BOX_STYLES = {0x0, 0x1, 0x7, 0x8, 0x9, 0xF}
SYSTEM_BOX = 0x12
SYSTEM_TAIL = bytes(9)
NO_UNIT = b'\xFD\x00'

# ---- text: decode ReMixed messages (FFT PSX encoding) for the .pzd draft ----
SPECIAL = {(0xD9, 0xB6): '.', (0xD9, 0xC1): "'", (0xD9, 0xC9): '?', (0xD1, 0x1A): '!',
           (0xDA, 0x74): ',', (0xD1, 0x1D): '-', (0xD9, 0xBE): ':', (0xD1, 0x1C): '~'}
SINGLE = {0x3E: '!', 0x40: '?', 0x5F: '.', 0x93: "'", 0x91: '"', 0x8D: '-'}
def decode(b):
    s, i, speaker = [], 0, None
    while i < len(b):
        c = b[i]
        if c <= 9: s.append(chr(48 + c))
        elif c <= 0x23: s.append(chr(65 + c - 0x0A))
        elif c <= 0x3D: s.append(chr(97 + c - 0x24))
        elif c == 0xFA: s.append(' ')
        elif c in SINGLE: s.append(SINGLE[c])
        elif c == 0xF8: s.append('\n')
        elif c == 0xE0: s.append('{Ramza}')
        elif c == 0xEB: s.append('{item}')
        elif (c, b[i + 1] if i + 1 < len(b) else None) in SPECIAL: s.append(SPECIAL[(c, b[i + 1])]); i += 1
        elif c == 0xE3 and b[i + 1] == 0x08:        # speaker tag start ... E3 00
            j = b.index(0xE3, i + 2); speaker = decode(b[i + 2:j])[0]; i = j + 1
        elif c in (0xE2, 0xE3, 0xD1, 0xD9, 0xDA): s.append('<%02X%02X>' % (c, b[i + 1])); i += 1
        else: s.append('<%02X>' % c)
        i += 1
    return ''.join(s).strip('\n'), speaker

msgs = text.split(b'\xFE')

# Pages, as IC lays text out (and as tools/convert_wotl.py does): a message splits at its blank lines, and a page
# longer than IC's three-line box splits again (convert_wotl.fit). Page 1 keeps the message's text id; later pages
# get ids from EXTRA_PAGE_BASE and are shown by chained ChangeDialogs on the same box.
EXTRA_PAGE_BASE = TEXT_ID_BASE + 200
extra_ids = {}
def msg_pages(n):
    body = decode(msgs[n - 1])[0].replace('{Ramza}', 'Ramza')
    return [q for p in re.split(r'\n\s*\n', body) if p.strip() for q in fit(' '.join(p.split()))]
def more_pages(n, box):
    ids = extra_ids.setdefault(n, [])
    while len(ids) < len(msg_pages(n)) - 1:
        ids.append(EXTRA_PAGE_BASE + sum(len(v) for v in extra_ids.values()))
    return b''.join(b'\xE5\x01\x00' + bytes([0x51, box]) + struct.pack('<I', i) + b'\x00\x00' for i in ids)

out = bytearray(); used_msgs = []
for off, op, a in disasm(script, R):
    if dropped(off): continue
    a = standin(op, a) if STANDIN_ART else wotl_art(op, a)
    if a is None: continue
    if op == 0x0C:                                   # call skip helper -> its two waits
        out += b'\xE5\x01\x00\xE5\x04\x00'; continue
    if op == 0x10:                                   # DisplayMessage 14 -> 17
        const, dtype, msg, unit = a[0], a[1], a[2] | a[3] << 8, a[4:6]
        used_msgs.append(msg)
        if dtype >> 4 not in VANILLA_BOX_STYLES:
            # ReMixed's "item received" box (type 0x63): IC maps an unknown style to box slot -1 and crashes
            # (v0.2.0, RVA 0x136541). Use vanilla's plain dialogue window (type 0x12, box 2), which waits for the
            # player, on unit 0xFD ("no unit", as vanilla event 417 uses it with 0x11/0x12) so it has no portrait,
            # then close box 2. Tried before: 0x09 narration (no window, closes itself), 0x12 on Mustadio (his
            # portrait), 0x83 chronicle window on 0xFD (closes itself).
            out += bytes([0x10, const, SYSTEM_BOX]) + struct.pack('<I', tid(msg)) + NO_UNIT + SYSTEM_TAIL
            out += b'\xE5\x01\x00' + bytes([0x51, SYSTEM_BOX & 0x0F]) + b'\xFF\xFF\xFF\xFF\x00\x00' + b'\xE5\x01\x00'
            continue
        out += bytes([0x10, const, dtype]) + struct.pack('<I', tid(msg)) + unit + a[6:13] + bytes([a[13], 0])
        if dtype >> 4 in (0x8, 0x9): out += more_pages(msg, dtype & 0x0F)
        elif len(msg_pages(msg)) > 1: raise SystemExit('multi-page message %d in a type %02X box' % (msg, dtype))
        continue
    if op == 0x51:                                   # ChangeDialog 5 -> 7
        box, msg = a[0], a[1] | a[2] << 8
        if msg != 0xFFFF: used_msgs.append(msg)
        out += bytes([0x51, box]) + struct.pack('<I', tid(msg)) + a[3:5]
        if msg != 0xFFFF: out += more_pages(msg, box)
        continue
    if R[op] != E[op]:
        raise SystemExit('opcode %02X at %04X has a different length in IC; handle it explicitly' % (op, off))
    out += bytes([op]) + a

# Sanity: the result must parse cleanly with IC's enhanced lengths and end at EventEnd.
chk = disasm(bytes(out), E)
assert chk[-1][1] == 0xDB and sum(1 + len(x[2]) for x in chk) == len(out), 'converted script does not parse'
assert len(out) <= 6140, 'script too long for an IC .e'

msgs = text.split(b'\xFE')
lines = []
for n in sorted(set(used_msgs)):
    speaker = decode(msgs[n - 1])[1]
    ps = msg_pages(n)
    for page, (i, t) in enumerate(zip([tid(n)] + extra_ids.get(n, []), ps)):
        lines.append({'msg': n, 'page': page, 'id': i, 'speaker': speaker, 'text': t})

os.makedirs(OUT, exist_ok=True)
open(os.path.join(OUT, 'event159.e'), 'wb').write(bytes(out))
json.dump(lines, open(os.path.join(OUT, 'event159_text.json'), 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
print('script: %d -> %d bytes; %d messages' % (len(script), len(out), len(lines)))
