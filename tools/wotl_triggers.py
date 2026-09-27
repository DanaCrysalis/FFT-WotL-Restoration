"""Dump War of the Lions' world-map event triggers from the PSP ISO.

  python tools/wotl_triggers.py [--all]      (default: only blocks that play events >= 512)

The trigger table sits in PSP_GAME/SYSDIR/BOOT.BIN (unencrypted ELF). It is the source of IC's
EnhancedWorldEvent table (same ops; IC's Type = WotL op), minus the WotL-only blocks:
  0x31E698  u16 offsets per location (IC Town keys 0..43) into a list of block offsets; each list ends with 0.
            All offsets are bytes from 0x31E698.
  0x31E8E2  blocks: u16 op + u16 args; conditions, then one action op ends the block. Ends ~0x31F7F8.
Event scripts are fftpack file 21 (TEST.EVT) with 0x2800-byte records; see NOTES.md.
"""
import os, sqlite3, struct, sys

ISO = r"H:/FFT/ISOs/Final Fantasy Tactics - The War of the Lions (USA).iso"
BOOT_LBA, BOOT_SIZE = 130480, 3835044
LOCATION_TABLE, BLOCKS_START = 0x31E698, 0x31E8E2

ARGS = {0x00: 0, 0x01: 2, 0x02: 2, 0x03: 2, 0x04: 1, 0x0E: 1, 0x10: 2, 0x11: 2, 0x19: 2, 0x1A: 8, 0x1D: 1,
        0x1E: 3, 0x1F: 2, 0x20: 2, 0x21: 2, 0x22: 1, 0x23: 1, 0x24: 1, 0x29: 2, 0x2A: 1, 0x2B: 1}
ACTIONS = {0x00, 0x19, 0x1A, 0x1D, 0x20, 0x21, 0x22, 0x23, 0x24, 0x2A}
NAMES = {0x01: 'var==', 0x02: 'var>=', 0x03: 'var<=', 0x04: 'inParty', 0x0E: 'gil>=', 0x10: 'date>=',
         0x11: 'date<=', 0x19: 'PLAY', 0x1A: 'play2'}

def boot():
    with open(ISO, 'rb') as f:
        f.seek(BOOT_LBA * 2048); return f.read(BOOT_SIZE)

def block(B, p):
    ops = []
    while True:
        op = struct.unpack_from('<H', B, p)[0]; n = ARGS[op]
        ops.append((op,) + (struct.unpack_from('<%dH' % n, B, p + 2) if n else ())); p += 2 + 2 * n
        if op in ACTIONS: return ops

def locations(B):
    T = LOCATION_TABLE; first = struct.unpack_from('<H', B, T)[0]
    out = []
    for i in range(first // 2):
        p = T + struct.unpack_from('<H', B, T + 2 * i)[0]; blocks = []
        while (o := struct.unpack_from('<H', B, p)[0]):
            blocks.append(block(B, T + o)); p += 2
        out.append(blocks)
    return out

def fmt(ops):
    return '; '.join(NAMES.get(o[0], 'op%02X' % o[0]) + ' ' + ','.join(
        (hex(v) if NAMES.get(o[0], '').startswith('var') and j == 0 else str(v)) for j, v in enumerate(o[1:])) for o in ops)

if __name__ == '__main__':
    names = {}
    db = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'research', 'vanilla', 'town_names.txt')
    if os.path.exists(db):
        names = dict(line.rstrip('\n').split('\t', 1) for line in open(db, encoding='utf-8'))
    for L, blocks in enumerate(locations(boot())):
        for k, ops in enumerate(blocks):
            if '--all' in sys.argv or any(o[0] == 0x19 and o[1] >= 512 for o in ops):
                print(L, names.get(str(L), ''), k, '|', fmt(ops))
