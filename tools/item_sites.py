"""Finds every code site the item-table expansion patches in FFT_enhanced.exe, and writes them to ItemSites.g.cs.

  python tools/item_sites.py            (needs capstone; caches the disassembly in build/text_dis.pkl)

Why: IC's item code is War of the Lions' own (same range tables and getters), cut down to 261 items: ids 0-0xFD
plus IC's five bonus items 0x100-0x104. Giving WotL's items (0x100-0x13B, its own ids; the five Fell Swords, whose
WotL ids IC's bonus items hold, move to WotL's unused weapon slots) a home means:
  - relocating the per-item arrays sized for 0x105 ids to a page the mod owns (bag counts, the "owned" mirror),
    the item-attribute table (0x55 rows) and the equip picker's all-items chart;
  - widening the id bounds of the code that has to accept the new ids (inventory, menus, charts, equipping,
    equipment bonuses), leaving the ones that guard fixed-size buffers or battle specials alone (see BOUNDS);
  - hooking the item getters (ItemExpansion.cs; their prologues are checked here too).
Each site is written with its instruction's exact bytes, which the mod checks before arming: a game update that
moves anything leaves the expansion off (and logs which site), it never half-patches. Re-run this after an update.
research/ITEM_EXPANSION.md explains every array, bound and why it is (or is not) widened.
"""
import bisect, os, pickle, re, struct, sys
import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
EXE = r'D:/Games/Steam/steamapps/common/FINAL FANTASY TACTICS - The Ivalice Chronicles/FFT_enhanced.exe'
CACHE = os.path.join(ROOT, 'build', 'text_dis.pkl')
OUT = os.path.join(ROOT, 'ItemSites.g.cs')

MAX_ID = 0x13B                 # the last WotL item id (Sage's Ring)
ID_LIMIT = MAX_ID + 1          # 0x13C: bounds of the form "id < 0x105"

data = open(EXE, 'rb').read()
e = struct.unpack_from('<I', data, 0x3C)[0]
nsec = struct.unpack_from('<H', data, e + 6)[0]; optsz = struct.unpack_from('<H', data, e + 20)[0]
IMAGEBASE = struct.unpack_from('<Q', data, e + 24 + 24)[0]
secs = []
for i in range(nsec):
    o = e + 24 + optsz + i * 40
    secs.append((data[o:o + 8].rstrip(b'\0').decode(),) + struct.unpack_from('<IIII', data, o + 8))
def rva2off(rva):
    for n, vsz, va, rsz, raw in secs:
        if va <= rva < va + max(vsz, rsz): return raw + rva - va
TEXT = [s for s in secs if s[0] == '.text'][0]
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); md.detail = True

def sweep():
    if os.path.exists(CACHE): return pickle.load(open(CACHE, 'rb'))
    n, vsz, va, rsz, raw = TEXT
    fast = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64); fast.skipdata = True
    ins = [(i.address - IMAGEBASE, i.size, i.mnemonic, i.op_str) for i in fast.disasm(data[raw:raw + rsz], IMAGEBASE + va)]
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    pickle.dump(ins, open(CACHE, 'wb'))
    return ins
INS = sweep()
ADDRS = [x[0] for x in INS]

def decode(rva):
    off = rva2off(rva)
    return next(md.disasm(data[off:off + 16], IMAGEBASE + rva, 1))

def insn_bytes(rva, size): o = rva2off(rva); return data[o:o + size]

def mem_refs(lo, hi):
    """Instructions whose memory operand (rip-relative, or image-relative disp32 off a base register holding the
    image base) addresses [lo, hi): (rva, size, disp offset, rip?, target)."""
    import numpy as np
    n, vsz, va, rsz, raw = TEXT
    a = np.frombuffer(data, dtype=np.uint8, count=rsz, offset=raw).astype(np.int64)
    d = a[:-3] | (a[1:-2] << 8) | (a[2:-1] << 16) | (a[3:] << 24)
    d = np.where(d >= 2 ** 31, d - 2 ** 32, d)
    pos = va + np.arange(len(d))
    cand = set(np.nonzero((d >= lo) & (d < hi))[0].tolist())                         # image-relative
    cand |= set(np.nonzero((pos + 4 + d >= lo - 16) & (pos + 4 + d < hi))[0].tolist())  # rip-relative (+imm after)
    out = []
    for c in sorted(cand):
        p = va + c
        k = bisect.bisect_right(ADDRS, p) - 1
        start, size = INS[k][0], INS[k][1]
        if not (start < p and p + 4 <= start + size): continue
        i = decode(start)
        # (capstone reports disp_size = the operand size on word stores, so check the four bytes themselves)
        if i.disp_offset != p - start or struct.unpack_from('<i', data, rva2off(p))[0] != i.disp: continue
        mem = [op for op in i.operands if op.type == capstone.x86.X86_OP_MEM]
        if not mem: continue
        rip = mem[0].mem.base == capstone.x86.X86_REG_RIP
        target = start + size + i.disp if rip else i.disp
        if lo <= target < hi: out.append((start, size, p - start, rip, target, '%s %s' % (i.mnemonic, i.op_str)))
    return out

# --- arrays the mod moves -------------------------------------------------------------------------------------------
# (name, vanilla RVA, vanilla extent searched, new size on the mod's page)
ARRAYS = [
    ('Bag',       0x11A7C00, 0x104 + 1, 0x410),   # u8 count per item id; +0x104/+0x108 are other dwords
    ('Owned',     0x3C52740, 0x108, 0x410),       # u8 bag + equipped per id, rebuilt by 0x396174; 0x3C52848 is a word var
    ('Attribute', 0x80FEA0, 1, 0x100 * 0x1A),     # 0x1A-byte equipment bonus rows; base references only
    ('AllItems',  0x1874726, 0x20E, 0x400 * 2),   # equip picker's every-owned-item chart, u16, 0x00FF-ended
]

def relocations():
    rows = []
    for idx, (name, base, extent, size) in enumerate(ARRAYS):
        for start, isz, doff, rip, target, text in mem_refs(base, base + extent):
            rows.append((start, isz, doff, rip, idx, target - base, text))
    # 0x286160 (keeps the all-items chart equal to the owned set) walks it off the picker block's base:
    # lea rsi, [picker] ... [rsi + rcx*2 + 0x1E6]. Its base moves with the chart (new - 0x1E6).
    i = decode(0x286179)
    assert '%s %s' % (i.mnemonic, i.op_str) == 'lea rsi, [rip + 0x15ee3c0]', i.op_str
    rows.append((0x286179, i.size, i.disp_offset, True, 3, -0x1E6, 'lea rsi, [picker] (all-items walk base)'))
    return sorted(rows)

# --- bounds ---------------------------------------------------------------------------------------------------------
# (rva of the instruction, expected text, new immediate, why). Only these are widened; the rest of the 0x105 / 0xFF+6
# family is left alone on purpose (research/ITEM_EXPANSION.md lists every site and the reason).
B = ID_LIMIT
BOUNDS = [
    (0x2847F8, 'mov eax, 0x3ff', None, None),  # anchor only (checked, not patched)
    (0x2847FD, 'mov r8d, 0x103', MAX_ID - 1, 'bag add/get: ids 1..0x104'),
    (0x28756F, 'mov eax, 0x105', B, 'bag count getter'),
    (0x15415B, 'cmp esi, 0x105', B, 'item count shown in a menu'),
    (0x100F82, 'mov eax, 0x104', MAX_ID, '"party has this item" check'),
    (0x101070, 'mov eax, 0x104', MAX_ID, 'bag add (event/treasure path)'),
    (0x23D592, 'mov eax, 0x105', B, 'return an item list to the bag'),
    (0x284722, 'cmp rax, 0x105', B, 'clamp bag counts to 99 with equipped copies (store guard)'),
    (0x2847C7, 'cmp ebx, 0x105', B, 'clamp bag counts to 99 with equipped copies (loop)'),
    (0x288CD8, 'cmp edi, 0x105', B, 'menu list builder: ids walked'),
    (0x289072, 'cmp ebx, 0x105', B, 'shop sell list: ids walked'),
    (0x39711F, 'cmp edi, 0x105', B, 'menu list builder twin (jobs 161/164)'),
    (0x285E2C, 'mov eax, 0x105', B, 'chart walk (menu-order rebuild)'),
    (0x2862F6, 'mov eax, 0x105', B, 'chart walk (chart search)'),
    (0x39678E, 'mov eax, 0x105', B, 'chart walk (third housekeeper copy)'),
    (0x285EE4, 'lea r10d, [r11 + 6]', B - 0xFF, 'chart walk (remove from chart)'),
    (0x285FB2, 'lea r14d, [r15 + 6]', B - 0xFF, 'Items-tab chart housekeeper'),
    (0x2860AB, 'lea r14d, [r15 + 6]', B - 0xFF, 'equip picker chart housekeeper'),
    (0x39687E, 'lea r14d, [r15 + 6]', B - 0xFF, 'third chart housekeeper (owned mirror)'),
    (0x286185, 'lea edi, [rbp + 6]', B - 0xFF, 'all-items chart maintainer: ids walked'),
    (0x2BDA4D, 'mov ecx, 0x105', B, 'status screen equipment copy'),
    (0x277A99, 'mov eax, 0x105', B, 'equipment bonuses applied to a unit'),
    (0x277AA8, 'cmp byte ptr [rdi + 7], 0x55', 0x100 - 1, 'equipment bonus row bound (attribute table)'),
    (0x0FA7E2, 'cmp byte ptr [rax + 7], 0x55', 0x100 - 1, 'equipment bonus row bound'),
    (0x29F726, 'cmp byte ptr [rax + 7], 0x55', 0x100 - 1, 'equipment bonus row bound'),
    (0x286D81, 'cmp sil, 0x55', 0x100 - 1, 'equipment bonus row bound (item detail)'),
    (0x396A6F, 'cmp sil, 0x55', 0x100 - 1, 'equipment bonus row bound (item detail twin)'),
    # Hands: "the right hand holds 0xFF or an id >= 0x105 -> use the other word of the pair / the left hand". Left
    # alone, a new weapon reads as an empty hand (bare-handed attacks). None of these indexes a buffer by the id.
    (0x226FDD, 'lea ecx, [rdx + 6]', B - 0xFF, 'attack setup: the weapon a unit strikes with'),
    (0x2C4EB5, 'lea ecx, [rdx + 6]', B - 0xFF, 'attack setup (copy)'),
    (0x2DE6FD, 'lea ecx, [rdx + 6]', B - 0xFF, 'attack setup (copy)'),
    (0x2FE434, 'lea ecx, [rdx + 6]', B - 0xFF, 'attack setup (copy)'),
    (0x33B5B9, 'lea ecx, [rdx + 6]', B - 0xFF, 'attack setup (copy)'),
    (0x37863E, 'lea ecx, [rdx + 6]', B - 0xFF, 'attack setup (copy)'),
    (0x27F000, 'lea ecx, [rdx + 6]', B - 0xFF, 'weapon of a unit (range/reach)'),
    (0x2822A1, 'lea r14d, [rbp + 6]', B - 0xFF, 'weapon of the acting unit'),
    (0x284C08, 'lea ecx, [rdx + 6]', B - 0xFF, 'unit -> menu copy: hands'),
    (0x3602F3, 'mov ecx, 0x105', B, 'unit -> menu copy: hands (copy)'),
    (0x396368, 'lea r8d, [r9 + 6]', B - 0xFF, 'unit -> menu copy, jobs 161/164: hands and equipment check'),
    (0x3059BE, 'lea esi, [rdi + 6]', B - 0xFF, 'ability check against the weapon held'),
    (0x309EF6, 'mov edx, 0x105', B, 'is the unit holding anything'),
    (0x28024D, 'mov r8d, 0x105', B, 'battle unit weapon selection'),
    (0x1ED958, 'cmp ax, 4', MAX_ID - 0x100, 'right hand item lookup (0x1EDC50, null-checked)'),
    (0x1ED97F, 'cmp ax, 4', MAX_ID - 0x100, 'left hand item lookup'),
    (0x39617E, 'mov eax, 2', 8, 'owned mirror rebuild: copy 8 x 0x80 + 5 bag bytes, not 2 x 0x80 + 5'),
    (0x396194, 'lea r8d, [rax + 0x7e]', 0x78, 'owned mirror rebuild: the copy stride (0x80) is count + 0x7E'),
]

def imm_patch(rva, text, new):
    i = decode(rva)
    got = '%s %s' % (i.mnemonic, i.op_str)
    if got != text: raise SystemExit('%x: expected "%s", found "%s"' % (rva, text, got))
    old = insn_bytes(rva, i.size)
    if new is None: return old, old
    if i.imm_offset:                                     # mov/cmp reg, imm32 or cmp mem, imm8
        size = i.imm_size
        if size == 1 and not 0 <= new <= 0xFF: raise SystemExit('%x: %x does not fit an imm8' % (rva, new))
        repl = bytearray(old); repl[i.imm_offset:i.imm_offset + size] = new.to_bytes(size, 'little')
    else:                                                # lea r, [r + disp8]
        assert i.disp_size == 1 and 0 <= new <= 0x7F, (hex(rva), new)
        repl = bytearray(old); repl[i.disp_offset] = new
    return old, bytes(repl)

# The "party is carrying 100 of something" check 0x2D6688 copies the 0x105 bag bytes into a 0x110-byte stack buffer
# and increments buf[id] for every equipped item that passes IsValidItem: a new id there writes past the frame.
# Its two IsValidItem calls go to a stub that also refuses ids >= 0x105 (the mod's), so the check keeps its size.
LOW_VALIDITY_CALLS = [0x2D6754, 0x2D6767]

# Item getters the mod hooks (ItemExpansion.cs): (name, rva, prologue bytes as on disk).
HOOKS = [('SecondaryItemType', 0x2B8BCC), ('ItemCommon', 0x2B8C44), ('ItemWeapon', 0x2B8C74),
         ('ItemShield', 0x2B8CD4), ('ItemArmor', 0x2B8D3C), ('ItemAccessory', 0x2B8DA0), ('ItemChemist', 0x2B8E04),
         ('ItemSpritePair', 0x2B8E60), ('IsValidItem', 0x2B8EBC)]
IS_VALID_ITEM = 0x2B8EBC

# Menu order charts (u16 item ids, 0x00FF-ended): the live readers find them through these pointer slots, and the
# save only ever copies the vanilla blocks, so the mod points the slots at its own bigger copies and keeps the
# vanilla blocks in sync (ItemExpansion.cs). (slot RVA, vanilla chart RVA, capacity in words incl. the end marker)
SLOTS = [(0x67F498, 0x7B2550, 141), (0x67F4A0, 0x7B2678, 30), (0x67F4A8, 0x7B24B0, 38), (0x67F4B0, 0x7B2500, 34),
         (0x67F4B8, 0x7B26B8, 21),                                           # Items tab: hands, head, body, acc., items
         (0x689C38, 0x7B2550, 141), (0x689C40, 0x7B2678, 30), (0x689C48, 0x7B24B0, 38), (0x689C50, 0x7B2500, 34),
         (0x689C58, 0x7B26B8, 21),                                           # a second copy of the same table
         (0x67FA90, 0x1874540, 141), (0x67FA98, 0x187465A, 30), (0x67FAA0, 0x1874696, 38),
         (0x67FAA8, 0x18746E2, 34)]                                          # equip picker: hands, head, body, acc.

# The save serializer (every save, the autosave included, goes through it; the mod flushes its sync first) and the
# event variable address function's load of the variable block pointer (the counts of the new items live in the
# block's last 0x104 bytes, which no variable id reaches: vars 0x360-0x3FF, the last range, end at +0x2FC).
ANCHORS = [('SaveSerializer', 0x218F78, 16), ('VarsPointerLoad', 0x2EC2A8, 7)]
i = decode(0x2EC2A8); VARS_POINTER = 0x2EC2A8 + i.size + i.disp

def cs(b): return '"' + b.hex(' ').upper() + '"'

def main():
    lines = ['// <auto-generated> by tools/item_sites.py from FFT_enhanced.exe; do not edit by hand. </auto-generated>',
             'namespace WotLCharacters', '{', '    internal static partial class ItemSites', '    {',
             '        public const int MaxItemId = 0x%X;' % MAX_ID, '']
    lines.append('        // Arrays moved to the mod\'s page: name, vanilla RVA, new size')
    lines.append('        public static readonly (string Name, uint Rva, int Size)[] Arrays =')
    lines.append('        {')
    for name, base, extent, size in ARRAYS: lines.append('            ("%s", 0x%X, 0x%X),' % (name, base, size))
    lines.append('        };\n')
    lines.append('        // Instructions addressing a moved array: RVA, bytes, displacement offset, rip-relative, array, offset')
    lines.append('        public static readonly (uint Rva, string Bytes, int DispOffset, bool Rip, int Array, int Delta)[] Relocations =')
    lines.append('        {')
    rel = relocations()
    for start, isz, doff, rip, idx, delta, text in rel:
        lines.append('            (0x%X, %s, %d, %s, %d, %s0x%X),   // %s' % (start, cs(insn_bytes(start, isz)), doff,
                     'true' if rip else 'false', idx, '-' if delta < 0 else '', abs(delta), text))
    lines.append('        };\n')
    lines.append('        // Bounds widened: RVA, vanilla bytes, patched bytes')
    lines.append('        public static readonly (uint Rva, string Old, string New, string Why)[] Bounds =')
    lines.append('        {')
    for rva, text, new, why in BOUNDS:
        old, repl = imm_patch(rva, text, new)
        if new is None: continue
        lines.append('            (0x%X, %s, %s, "%s"),' % (rva, cs(old), cs(repl), why.replace('"', '\\"')))
    lines.append('        };\n')
    lines.append('        // Calls to IsValidItem redirected to the low-id stub')
    lines.append('        public static readonly (uint Rva, string Bytes)[] LowValidityCalls =')
    lines.append('        {')
    for rva in LOW_VALIDITY_CALLS:
        i = decode(rva); assert i.mnemonic == 'call' and int(i.op_str, 16) - IMAGEBASE == IS_VALID_ITEM
        lines.append('            (0x%X, %s),' % (rva, cs(insn_bytes(rva, i.size))))
    lines.append('        };\n')
    lines.append('        // Getter prologues (first 16 bytes) the mod hooks')
    lines.append('        public static readonly (string Name, uint Rva, string Bytes)[] Hooks =')
    lines.append('        {')
    for name, rva in HOOKS: lines.append('            ("%s", 0x%X, %s),' % (name, rva, cs(insn_bytes(rva, 16))))
    lines.append('        };\n')
    lines.append('        // Menu order chart pointer slots: slot RVA, vanilla chart RVA, capacity (words incl. end marker)')
    lines.append('        public static readonly (uint Slot, uint Chart, int Words)[] Slots =')
    lines.append('        {')
    for slot, chart, words in SLOTS:
        v = struct.unpack_from('<Q', data, rva2off(slot))[0] - IMAGEBASE
        assert v == chart, (hex(slot), hex(v))
        lines.append('            (0x%X, 0x%X, %d),' % (slot, chart, words))
    lines.append('        };\n')
    lines.append('        // Other code the mod relies on: the save serializer (hooked) and the event variable pointer load')
    lines.append('        public static readonly (string Name, uint Rva, string Bytes)[] Anchors =')
    lines.append('        {')
    for name, rva, n in ANCHORS: lines.append('            ("%s", 0x%X, %s),' % (name, rva, cs(insn_bytes(rva, n))))
    lines.append('        };')
    lines.append('        public const uint VarsPointer = 0x%X;   // qword: the event variable block' % VARS_POINTER)
    lines += ['    }', '}', '']
    open(OUT, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines))
    print('%d relocations, %d bounds, %d hooks, %d slots -> %s' % (len(rel), len(BOUNDS) - 1, len(HOOKS), len(SLOTS), OUT))
    for r in rel: print('  %x %-5s %s %+x  %s' % (r[0], 'rip' if r[3] else 'abs', ARRAYS[r[4]][0], r[5], r[6]))

if __name__ == '__main__':
    main()
