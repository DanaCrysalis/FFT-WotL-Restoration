"""War of the Lions' own items (ids 0x100-0x139) for IC's item-table expansion, read from WotL's BOOT.BIN.

  python tools/wotl_items.py        writes research/items/wotl_items.json and ItemData.g.cs

IC's item code is WotL's, so WotL's tables slot straight in (see tools/item_sites.py, research/ITEM_EXPANSION.md):
  secondary common records   0x8A5ADAC  12 bytes x 0x3C (0x100-0x13B)
  weapon data                0x8A5B07C  8 bytes, index id - 0x100      shield 0x8A5B17C  2 bytes, id - 0x120
  armor (head + body)        0x8A5B184  2 bytes, id - 0x124            accessory 0x8A5B1A4 2 bytes, id - 0x134
  equipment bonus rows       0x8A5B1B8  0x19 bytes, row - 0x50 (IC's rows are 0x1A: a last flag byte, 0 here)
  weapon/shield sprite pair  0x8A5B3C8  2 bytes, id - 0x100
(vaddr = BOOT.BIN offset + 0x8803FAC). What changes on the way into IC:
  - ids: WotL's own, except the five Fell Swords (0x100-0x104, which IC's bonus items hold) -> 0x116-0x11A, WotL's
    unused weapon slots. IC still special-cases WotL's ids (the can-equip check reserves the Onion gear, 0x106,
    0x120, 0x125, 0x12D, 0x136, for jobs 0xA1/0xA4), so keeping them matters;
  - equipment bonus rows: WotL's 0x50-0x64 are IC's bonus items' 0x50-0x54, so they become 0x55-0x69;
  - item type: the Tynar Rouge's lip rouge (0x24) becomes a perfume (0x1F), so the jobs that wear perfume wear it
    (user's call, 2026-09-25); Fell Swords keep their own type (0x23);
  - record byte 4 (the item's index in its vanilla sub-table; the getters ignore it, IC's bonus items copy a
    vanilla item's): a vanilla item of the same type (DONORS), 0 when there is none.
"""
import json, os, struct

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
ISO = r'H:/FFT/ISOs/Final Fantasy Tactics - The War of the Lions (USA).iso'
BOOT_LBA, BOOT_SIZE = 130480, 3835044          # /PSP_GAME/SYSDIR/BOOT.BIN
IC_EXE = r'D:/Games/Steam/steamapps/common/FINAL FANTASY TACTICS - The Ivalice Chronicles/FFT_enhanced.exe'
IC_COMMON = 0x80EA90                            # IC's 256 primary 12-byte records (RVA)
V = 0x8803FAC

NAMES = {}
for line in open(r'H:/FFT/WotL Sprites/Items/WOTL Items.txt', encoding='utf-8'):
    if line.strip():
        k, n = line.split(' ', 1); NAMES[int(k, 16)] = n.strip()

FELL_SWORDS = {0x100 + k: 0x116 + k for k in range(5)}
TYPE_REMAP = {0x138: (0x24, 0x1F)}             # Tynar Rouge: lip rouge -> perfume
DONORS = {0x138: 0xEE}                          # Tynar Rouge: byte 4 of Septieme Sens (the reward it replaces)
RANGES = [('weapon', 0x100, 8, 0x8A5B07C, 7, 5), ('shield', 0x120, 2, 0x8A5B17C, 9, 6),
          ('armor', 0x124, 2, 0x8A5B184, 10, 7), ('armor', 0x12C, 2, 0x8A5B184, 11, 7),
          ('accessory', 0x134, 2, 0x8A5B1A4, 12, 8)]  # kind, first id, size, table, IC range index, IC data type
SUB_BASE = {'weapon': 0x100, 'shield': 0x120, 'armor': 0x124, 'accessory': 0x134}

def boot():
    with open(ISO, 'rb') as f:
        f.seek(BOOT_LBA * 2048); return f.read(BOOT_SIZE)

def pe_reader(path):
    data = open(path, 'rb').read()
    e = struct.unpack_from('<I', data, 0x3C)[0]
    nsec = struct.unpack_from('<H', data, e + 6)[0]; optsz = struct.unpack_from('<H', data, e + 20)[0]
    secs = [struct.unpack_from('<IIII', data, e + 24 + optsz + i * 40 + 8) for i in range(nsec)]
    def read(rva, n):
        for vsz, va, rsz, raw in secs:
            if va <= rva < va + max(vsz, rsz): return data[raw + rva - va:raw + rva - va + n]
    return read

def main():
    d = boot()
    rd = lambda vaddr, n: d[vaddr - V:vaddr - V + n]
    ic = pe_reader(IC_EXE)
    ic_common = [ic(IC_COMMON + 12 * i, 12) for i in range(256)]
    best_by_type = {}
    for i, c in enumerate(ic_common):       # the strongest (highest id) vanilla item of each type
        if c[3] and 0 < i < 0xF0: best_by_type[c[5]] = i
    items = []
    for wid in range(0x100, 0x13C):
        common = bytearray(rd(0x8A5ADAC + 12 * (wid - 0x100), 12))
        if not any(common[:3]) and common[3] == 2: continue            # empty slot
        kind, first, size, table, rng, dtype = [r for r in RANGES if wid >= r[1]][-1]
        sub = rd(table + size * (wid - SUB_BASE[kind]), size)
        ic_id = FELL_SWORDS.get(wid, wid)
        wattr = common[7]
        attr = b''
        if wattr >= 0x50:
            attr = rd(0x8A5B1B8 + 0x19 * (wattr - 0x50), 0x19) + b'\0'
            common[7] = wattr + 5
        if wid in TYPE_REMAP:
            old, new = TYPE_REMAP[wid]; assert common[5] == old; common[5] = new
        donor = DONORS.get(wid, best_by_type.get(common[5]))
        common[4] = ic_common[donor][4] if donor is not None else 0
        pair = rd(0x8A5B3C8 + 2 * (wid - 0x100), 2) if kind in ('weapon', 'shield') else b''
        items.append(dict(wotl_id=wid, ic_id=ic_id, name=NAMES[wid], kind=kind, range_index=rng, data_type=dtype,
                          common=common.hex(' '), sub=sub.hex(' '), attr_row=common[7] if attr else None,
                          attr=attr.hex(' '), pair=pair.hex(' '), donor=donor))
    os.makedirs(os.path.join(ROOT, 'research', 'items'), exist_ok=True)
    json.dump(items, open(os.path.join(ROOT, 'research', 'items', 'wotl_items.json'), 'w'), indent=1)

    cs = ['// <auto-generated> by tools/wotl_items.py from WotL\'s BOOT.BIN; do not edit by hand. </auto-generated>',
          'namespace WotLCharacters', '{', '    internal static partial class ItemData', '    {',
          '        // IC id, WotL id, name, IC range index, IC data type (5 weapon .. 9 chemist), common record,',
          '        // type data (weapon 8 / shield, armor, accessory 2 bytes), equipment bonus row (id, 0x1A bytes), sprite pair',
          '        public static readonly (int Id, int WotlId, string Name, int RangeIndex, int DataType, string Common,'
          ' string Sub, int AttrRow, string Attr, string Pair)[] Items =', '        {']
    for it in items:
        cs.append('            (0x%X, 0x%X, "%s", %d, %d, "%s", "%s", %s, "%s", "%s"),' % (
            it['ic_id'], it['wotl_id'], it['name'].replace('"', '\\"'), it['range_index'], it['data_type'],
            it['common'].upper(), it['sub'].upper(), '0x%X' % it['attr_row'] if it['attr_row'] else '-1',
            it['attr'].upper(), it['pair'].upper()))
    cs += ['        };', '    }', '}', '']
    open(os.path.join(ROOT, 'ItemData.g.cs'), 'w', encoding='utf-8', newline='\n').write('\n'.join(cs))
    for it in items:
        print('%3x -> %3x %-18s %-9s %s | %s | attr %s' % (it['wotl_id'], it['ic_id'], it['name'], it['kind'],
              it['common'], it['sub'], hex(it['attr_row']) if it['attr_row'] else '-'))

if __name__ == '__main__':
    main()
