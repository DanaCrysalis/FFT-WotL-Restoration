"""Enhanced-mode textures for vanilla event sprite sheets that War of the Lions drew extra frames on.

  python tools/sheet_textures.py 1159 1271        writes research/art/tex_NNNN.bin for each texture number

IC's event textures (system/ffto/g2d.dat) stop at row 442 of 512; WotL drew its extra frames below that. The Mobile
Sprites set (fftivc.texture.mobilesprites, Spikedrose, used with permission) has full 512-row sheets, but redraws the
rest of each sheet too (same layout and palette indices, different shading), so the texture shipped is IC's own
rows 0-441 with only Mobile's rows 442-511 appended: vanilla scenes keep IC's art. The sheet -> texture number table
is in the exe (see convert_wotl.SHEET_TEXTURES).
g2d.dat: u32 index offset at +8, u16 count at +12; 16-byte index entries (u32 offset, u24 size); an entry's data
starts 16 bytes in, zlib-compressed when its byte +4 is 2.
"""
import os, struct, sys, zlib

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
G2D = r'H:/FFT/Game Files/system/ffto/g2d.dat'
MOBILE = r'H:/FFT/ModLoader/Mods/fftivc.texture.mobilesprites/FFTIVC/data/enhanced/system/ffto/g2d'
ROW = 256                 # 512 pixels, 4bpp
IC_ROWS, ROWS = 442, 512

def ic_texture(n):
    d = open(G2D, 'rb').read()
    index = struct.unpack_from('<I', d, 8)[0]
    entry = index + n * 16
    off, size = struct.unpack_from('<I', d, entry)[0], int.from_bytes(d[entry + 4:entry + 7], 'little')
    body = d[off + 16:off + size]
    return zlib.decompress(body) if d[off + 4] == 2 else body

def build(n):
    ic = ic_texture(n)
    mobile = open(os.path.join(MOBILE, 'tex_%d.bin' % n), 'rb').read()
    assert len(ic) == IC_ROWS * ROW and len(mobile) == ROWS * ROW, (n, len(ic), len(mobile))
    if not any(mobile[len(ic):]): raise SystemExit('tex_%d: the Mobile sheet has no extra rows; IC\'s own is enough' % n)
    open(os.path.join(ROOT, 'research', 'art', 'tex_%d.bin' % n), 'wb').write(ic + mobile[len(ic):])
    print('tex_%d' % n)

if __name__ == '__main__':
    for n in map(int, sys.argv[1:]): build(n)
