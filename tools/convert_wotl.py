"""Convert War of the Lions events (PSP TEST.EVT, research/TEST_wotl.EVT) into Ivalice Chronicles enhanced scripts
plus their text, for events IC keeps the setup records of but ships no scripts or text for (512-581).

    from convert_wotl import convert
    lines = convert([519, 520, 521, 522, 524], text_base=382000)

writes build/wotl/eventNNN.e and returns the text entries [{'id', 'unit', 'text'}] in text id order.

WotL scripts already use IC's classic opcode set and lengths (research/evlen_ic.bin), so the conversion only:
  * widens DisplayMessage (0x10, 14 -> 17 bytes) and ChangeDialog (0x51, 5 -> 7 bytes) to IC's enhanced layout:
    32-bit global text ids, and DisplayMessage's last byte becomes a u16;
  * splits a message into pages at WotL's paragraph breaks (blank lines). IC keeps each text entry to one line
    of speech and pages longer ones with chained ChangeDialogs on the same box (E5 01 00 / 51 box id), so every
    page gets its own text id;
  * stops on any opcode whose length differs between the classic and enhanced tables, or that IC redefines,
    rather than guess.
Text: PSX encoding with 0x95 as the space (PSX uses 0xFA); decoded with convert_event.py's table plus the codes
only WotL uses.
"""
import os, re, struct

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, '..', 'research')
OUT = os.path.join(HERE, '..', 'build', 'wotl')
RECORD = 0x2800

CLASSIC = open(os.path.join(RES, 'evlen_ic.bin'), 'rb').read()
ENHANCED = open(os.path.join(RES, 'evlen_enh.bin'), 'rb').read()
IC_OPCODES = set(range(0xA6, 0xB0)) | set(range(0xC2, 0xCF)) | set(range(0xE7, 0xEF))   # IC's own meanings
WIDENED = {0x10, 0x51}

# Event sprite sheet -> the enhanced-mode texture that draws it (WotL-only sheets; vanilla IC ships copies of
# sheet 0x36 there, the real ones come from fftivc.texture.mobilesprites, see research/art/README.md).
# The sheet -> texture table is in the exe (143 u32 from RVA 0x7136B4 - 0x89 * 4 in the file). A vanilla sheet needs
# WotL's extra rows when a WotL scene uses frames WotL added to it: every vanilla event texture stops at row 442 of
# 512, and WotL drew its extra frames below that (Ovelia's grass whistle on 0x1E, her prayer and wound on 0x7C). The
# Mobile set redraws the whole sheet (same layout and palette, different shading), so for vanilla sheets the mod ships
# IC's own rows 0-441 with only Mobile's rows 442-511 appended: vanilla scenes keep IC's art. Delita's 0x45
# (tex_1219) also has extra rows in the Mobile set, but IC's own texture matches WotL's footage (the user compared),
# so it is not shipped; only sheets listed here are.
SHEET_TEXTURES = {0x8E: 1279, 0x8C: 1280, 0x8B: 1281, 0x89: 1282, 0x8D: 1283, 0x8A: 1284,
                  0x1E: 1179, 0x7C: 1263, 0x0D: 1159, 0x81: 1271, 0x64: 1252, 0x21: 1177, 0x88: 1278, 0x09: 1160, 0x85: 1275}
# research/art holds the textures for the sheets the ported scenes use so far: 0x8E (birthday), 0x8A (Balthier),
# 0x8B (Luso), 0x1E and 0x7C (Ovelia), 0x0D and 0x81 (Wiegraf and Loffrey), 0x64 (Cletienne and Meliadoul), 0x21
# (Agrias visits Ovelia), 0x88 and 0x8D (Beowulf and Reis), 0x09 and 0x85
# (Gariland gossip); the build stops if a scene loads a
# listed sheet whose texture is missing. tools/sheet_textures.py builds the vanilla sheets' ones.

def disasm(sc, table):
    out, i = [], 0
    while i < len(sc):
        op = sc[i]; n = table[op]
        out.append((i, op, sc[i + 1:i + 1 + n])); i += 1 + n
        if op == 0xDB: break
    return out

def record(event):
    evt = open(os.path.join(RES, 'TEST_wotl.EVT'), 'rb').read()[event * RECORD:(event + 1) * RECORD]
    ptr = struct.unpack_from('<I', evt, 0)[0]
    if not 8 < ptr < RECORD: raise SystemExit('WotL event %d is a placeholder' % event)
    return evt[4:ptr], evt[ptr:].rstrip(b'\0')

# ---- text ----
DIGRAPHS = {(0xD9, 0xB6): '.', (0xD9, 0xC1): "'", (0xD9, 0xC9): '?', (0xD1, 0x1A): '!', (0xDA, 0x74): ',',
            (0xD1, 0x1D): '-', (0xD9, 0xBE): ':', (0xD1, 0x1C): '~',
            (0xDA, 0x68): '—',        # em dash, as IC writes it
            (0xD1, 0x29): '*',             # *sigh*, as IC writes *cough*
            (0xDA, 0x75): ';'}
SINGLE = {0x3E: '!', 0x40: '?', 0x46: ':', 0x5F: '.', 0x93: "'", 0x91: '"', 0x8D: '(', 0x8E: ')', 0x95: ' ', 0xFA: ' ',
          0xF8: '\n', 0xE0: 'Ramza'}

def decode(b):
    s, i = [], 0
    while i < len(b):
        c = b[i]; nxt = b[i + 1] if i + 1 < len(b) else None
        if c == 0xE3 and nxt == 0x08:           # speaker tag E3 08 <name> E3 00: IC names speakers separately
            i = b.index(0xE3, i + 2) + 2; continue
        if c <= 9: s.append(chr(48 + c))
        elif c <= 0x23: s.append(chr(65 + c - 0x0A))
        elif c <= 0x3D: s.append(chr(97 + c - 0x24))
        elif c in SINGLE: s.append(SINGLE[c])
        elif (c, nxt) in DIGRAPHS: s.append(DIGRAPHS[(c, nxt)]); i += 1
        else: raise SystemExit('unknown text code %02X %s in %r' % (c, '%02X' % nxt if nxt is not None else '', bytes(b)))
        i += 1
    return ''.join(s)

# IC's box shows three lines of about 70 characters; a 219-character page overflowed it (Balthier's 524). 99% of IC's
# own dialogue lines are 146 characters or less.
PAGE_MAX = 150

def fit(page):
    """Splits a page longer than PAGE_MAX at sentence ends (or, for one long sentence, between words)."""
    if len(page) <= PAGE_MAX: return [page]
    parts = re.split(r'(?<=[.!?])\s+', page)
    if len(parts) == 1: parts = page.split(' ')
    out = [parts[0]]
    for p in parts[1:]:
        if len(out[-1]) + 1 + len(p) <= PAGE_MAX: out[-1] += ' ' + p
        else: out.append(p)
    return [q for o in out for q in (fit(o) if len(parts) > 1 else [o])]

# WotL marks a stressed word with hyphens ("And that -is- what you seek"); IC's text uses italics ("the Corpse Brigade
# <i>was</i> behind the kidnapping!")
EMPHASIS = re.compile(r"(?<![\w-])-([A-Za-z']+)-(?![\w-])")

def pages(raw):
    """A message's pages: split at blank lines, each page's own line breaks joined with spaces, and long pages
    split again to fit IC's box."""
    text = decode(raw).strip('\n')
    return [EMPHASIS.sub(r'<i>\1</i>', q) for p in re.split(r'\n\s*\n', text) if p.strip() for q in fit(' '.join(p.split()))]

# ---- scripts ----
JOIN_WINDOW = bytes.fromhex('78073c') + bytes.fromhex('e53800')     # DisplayConditions 7 ("... joined"), wait
FADE_OUT_WAIT = bytes.fromhex('e50c00')                             # the wait after the closing ColorScreen

def ic_join_window(script, event):
    """Recruitment scenes (the A2 party check) show the join window under a dark screen in WotL only when the
    check passes; every vanilla IC recruitment instead shows it after the scene's final fade (IC events 170, 213,
    298, 374: ... 3E ColorScreen, E5 0C 00, F1 3C 00, 78 07 3C, E5 38 00). Move it the same way."""
    ins = disasm(bytes(script), ENHANCED)
    if not any(op == 0xA2 for _, op, _ in ins): return script
    raw = bytes(script)
    at = raw.find(JOIN_WINDOW)
    if at < 0: raise SystemExit('event %d: recruitment without the usual join window; check it by hand' % event)
    raw = raw[:at] + raw[at + len(JOIN_WINDOW):]
    ins = disasm(raw, ENHANCED)
    fades = [off for off, op, _ in ins if op == 0x3E and off > at]
    if not fades: raise SystemExit('event %d: no closing ColorScreen for the join window' % event)
    after = fades[-1] + 1 + len(ins[[o for o, _, _ in ins].index(fades[-1])][2])
    if raw[after:after + 3] == FADE_OUT_WAIT: after += 3
    return bytearray(raw[:after] + bytes.fromhex('f13c00') + JOIN_WINDOW + raw[after:])

VAR_OPS = range(0xB0, 0xBF)      # ADD .. ZERO: the first parameter is the variable (u16)

def convert(events, text_base, var_map=None, map_map=None, tile_map=None, title=None, set_flags=None):
    """var_map renumbers variables in ADD..ZERO instructions (WotL rumor unlock vars -> IC's rumor ids).
    map_map replaces ChangeMap targets ({WotL map: IC map}, for WotL-only maps IC has no HD background for) and
    tile_map moves units that WarpUnit/WalkTo would put off the stand-in map ({(unit, x, y): (x, y)}).
    title: Caption id for the location title. IC dropped ShowMapTitle (0x91) from every script (it does nothing,
    leaving a silent black screen) and shows titles with its own E7 <Caption id> (u32): Caption rows (13, nxd)
    point at a PlaceName through UnionId 113:<id>, e.g. 1290 -> 12100 "Zeltennia Castle" (event 331); a value
    with no Caption row shows nothing (1.4.5/1.4.6 used PlaceName 1060 directly). IC places E7 after the scene's
    setup, right before its Reveal (4D). An E7 at
    the very start showed nothing (1.4.5 test), so the title goes before the first Reveal after the ShowMapTitle
    (in place if there is none), without IC's 90-frame wait, which would lengthen the black screen. Dropped if no
    title is given.
    set_flags ({event: [var, ...]}) sets flags at the end of an event (ZERO, ADD 1 before EventEnd), for a scene
    WotL only ever reached once through a chain and so never marked as seen, but which the port also triggers."""
    var_map, map_map, tile_map, set_flags = var_map or {}, map_map or {}, tile_map or {}, set_flags or {}
    os.makedirs(OUT, exist_ok=True)
    lines, ids = [], {}
    def page_ids(msgs, n, unit):
        # a group's events share text ids for the same message (battle events repeat their battle's whole text
        # block); keyed by the message's bytes too, in case two events' blocks differ
        key = (n, msgs[n - 1])
        if key not in ids:
            ids[key] = []
            for p in pages(msgs[n - 1]):
                ids[key].append(text_base + len(lines))
                lines.append({'id': text_base + len(lines), 'unit': unit, 'msg': n, 'text': p})
        return ids[key]

    sheets = set()
    for event in events:
        script, text = record(event)
        msgs = text.split(b'\xFE')
        out = bytearray(); box_unit = {}; pending_title = False; closing = []
        for off, op, a in disasm(script, CLASSIC):
            if op in IC_OPCODES: raise SystemExit('event %d: opcode %02X at %04X means something else in IC' % (event, op, off))
            if CLASSIC[op] != ENHANCED[op] and op not in WIDENED:
                raise SystemExit('event %d: opcode %02X at %04X has a different length in IC' % (event, op, off))
            if op == 0x58: sheets.add(a[1] | a[2] << 8)
            if op == 0x10:                                   # DisplayMessage
                const, dtype, n, unit = a[0], a[1], a[2] | a[3] << 8, a[4] | a[5] << 8
                box = dtype & 0x0F; box_unit[box] = unit
                pids = page_ids(msgs, n, unit)
                if len(pids) > 1 and dtype >> 4 == 0x1:
                    # a speech bubble with several pages: IC never pages bubbles; it makes them the portrait box of
                    # the same slot, pages that, and closes it after the last page's wait (WotL event 2's "Mayhap
                    # bowed heads..." bubble is IC event 2's 91 box: DisplayMessage, E5 01, 51 page 2, E5 01, 51 FFFF)
                    dtype = 0x90 | box
                    closing.append(bytes([0x51, box]) + b'\xFF\xFF\xFF\xFF\x00\x00')
                if len(pids) > 1 and dtype == 0x70:
                    # in-battle speech with several pages: IC's 0xF0 box, paged by EB <this page> <next page> 00 00
                    # after each wait and closed by EB <last page> FFFFFFFF 00 00 after the last one (IC event 5:
                    # F0, E5 01, EB c29c -> 509d, E5 01, EB 509d -> FFFFFFFF)
                    out += bytes([0x10, const, 0xF0]) + struct.pack('<I', pids[0]) + a[4:13] + bytes([a[13], 0])
                    for cur, nxt in zip(pids, pids[1:]):
                        out += b'\xE5\x01\x00' + bytes([0xEB]) + struct.pack('<II', cur, nxt) + b'\x00\x00'
                    closing.append(bytes([0xEB]) + struct.pack('<I', pids[-1]) + b'\xFF\xFF\xFF\xFF\x00\x00')
                    continue
                if len(pids) > 1 and dtype >> 4 not in (0x8, 0x9):
                    raise SystemExit('event %d: multi-page message %d in a type %02X box' % (event, n, dtype))
                out += bytes([0x10, const, dtype]) + struct.pack('<I', pids[0]) + a[4:13] + bytes([a[13], 0])
                for pid in pids[1:]:
                    out += b'\xE5\x01\x00' + bytes([0x51, box]) + struct.pack('<I', pid) + b'\x00\x00'
                continue
            if op == 0x51:                                   # ChangeDialog
                box, n = a[0], a[1] | a[2] << 8
                if n == 0xFFFF:
                    out += bytes([0x51, box]) + b'\xFF\xFF\xFF\xFF' + a[3:5]; continue
                pids = page_ids(msgs, n, box_unit[box])
                out += bytes([0x51, box]) + struct.pack('<I', pids[0]) + a[3:5]
                for pid in pids[1:]:
                    out += b'\xE5\x01\x00' + bytes([0x51, box]) + struct.pack('<I', pid) + b'\x00\x00'
                continue
            if op == 0xE5 and a == b'\x01\x00' and closing:        # the wait after a paged bubble / battle speech
                out += bytes([op]) + a
                for close in closing: out += close
                closing.clear(); continue
            if op == 0x43 and a == b'\x06':
                # CallFunction 06 ends WotL's story events that hand over to the next one (8, 195, 233, 236, ...: go
                # on to the event in var 0x55 through the world map). IC's scripts never use it: IC set var 0x55
                # itself and gave those records a next event with the world-map flag (+0x12 next, +0x14 0x80). The
                # ported scenes return to the world map through their record's own 0x80.
                continue
            if op in VAR_OPS and a[:2] == b'\x55\x00':
                # var 0x55, the story's next-event marker (WotL 515: 196, 542: 200 then 195, ...): the ported scenes
                # play from world triggers, possibly long after WotL's moment, so they must not move it
                continue
            if op == 0x91:                                            # ShowMapTitle -> IC's title, see above
                pending_title = bool(title)
                continue
            if op == 0x4D and pending_title:                          # Reveal
                out += bytes([0xE7]) + struct.pack('<I', title); pending_title = False
            if op == 0x4C and (a[0] | a[1] << 8) in map_map:          # ChangeMap
                a = struct.pack('<H', map_map[a[0] | a[1] << 8]) + a[2:]
            if op in (0x5F, 0x28) and (a[0] | a[1] << 8, a[2], a[3]) in tile_map:   # WarpUnit / WalkTo: unit, x, y
                a = a[:2] + bytes(tile_map[(a[0] | a[1] << 8, a[2], a[3])]) + a[4:]
            if op in VAR_OPS and (a[0] | a[1] << 8) in var_map:
                a = struct.pack('<H', var_map[a[0] | a[1] << 8]) + a[2:]
            out += bytes([op]) + a
        if pending_title: raise SystemExit('event %d: ShowMapTitle without a later Reveal; place the title by hand' % event)
        out = ic_join_window(out, event)
        if set_flags.get(event):
            assert out[-1] == 0xDB
            out = out[:-1] + b''.join(bytes([0xBE]) + struct.pack('<H', v) + bytes([0xB0]) + struct.pack('<HH', v, 1)
                                      for v in set_flags[event]) + b'\xDB'
        chk = disasm(bytes(out), ENHANCED)
        assert chk[-1][1] == 0xDB and sum(1 + len(x[2]) for x in chk) == len(out), 'event %d does not parse' % event
        open(os.path.join(OUT, 'event%03d.e' % event), 'wb').write(bytes(out))
        print('event %d: %d -> %d bytes' % (event, len(script), len(out)))
    return lines, sheets

if __name__ == '__main__':
    import sys, json
    evs = [int(x) for x in sys.argv[1:]] or [519, 520, 521, 522, 524]
    lines, sheets = convert(evs, 382000)
    for l in lines: print(l['id'], '%02X' % l['unit'], l['text'])
    print('sheets', ['%02X' % s for s in sorted(sheets)])
