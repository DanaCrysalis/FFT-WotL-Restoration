"""Dump War of the Lions' battle-event rules (IC's EnhancedBattleEvent) from the PSP ISO.

  python tools/wotl_rules.py <key> [<key> ...]

Table in PSP_GAME/SYSDIR/BOOT.BIN at 0x2F2494: u16 offset per rules key (the setup record's +0x16) to a
0-terminated list of block offsets, all relative to 0x2F2494. A block is u16 op + u16 args: conditions,
then one action. Ops = IC UnkType4; fields: 01 (var, value) -> UnknownC, Unknown14=[value];
04/0B (unit) -> CharaControlId; 05/06/08/18 (unit, value) -> CharaControlId, Unknown14=[value];
16 () ; 19/1C (event) -> Unknown10.
"""
import struct, sys
sys.path.insert(0, __import__('os').path.dirname(__file__))
from wotl_triggers import boot

TABLE = 0x2F2494
ARGS = {0x01: 2, 0x04: 1, 0x05: 2, 0x06: 2, 0x08: 2, 0x0B: 1, 0x16: 0, 0x18: 2, 0x19: 1, 0x1C: 1, 0x1D: 1,
        0x1F: 1, 0x21: 1, 0x22: 1, 0x23: 1, 0x25: 4, 0x27: 2}
ACTIONS = {0x19, 0x1C}

def block(B, p):
    ops = []
    while True:
        op = struct.unpack_from('<H', B, p)[0]; n = ARGS[op]
        ops.append((op,) + (struct.unpack_from('<%dH' % n, B, p + 2) if n else ())); p += 2 + 2 * n
        if op in ACTIONS: return ops

def rules(B, key):
    p = TABLE + struct.unpack_from('<H', B, TABLE + 2 * key)[0]; out = []
    while (o := struct.unpack_from('<H', B, p)[0]):
        out.append(block(B, TABLE + o)); p += 2
    return out

if __name__ == '__main__':
    B = boot()
    for key in map(int, sys.argv[1:]):
        for i, ops in enumerate(rules(B, key)):
            print(key, i, '|', '; '.join('%02X ' % o[0] + ','.join(hex(v) for v in o[1:]) for o in ops))
