"""Give an HD map mesh the battle surface IC's battle maps have (the GT_n_panel_ui object), for maps IC only ever used
for scenes but a ported WotL battle is fought on.

  python tools/panel_ui.py 45        writes FFTIVC/data/enhanced/bg/meshes/map_045_mesh.bin

Why: every map IC fights on has a GT_n_panel_ui object in bg/meshes/map_NNN_mesh.bin; the movement/target grid and
the cursor are drawn on it. Scene-only maps (45, 20, 96, ...) have none, and a battle there (WotL's chapel ruins
battle 532, map 45) shows no grid and a cursor stuck at one height, while units move fine (classic terrain).

FFTOMESH layout (every map without animation data; checked on 107 of IC's 117 meshes):
  0x000  "FFTOMESH", u32 map id, u32 1, u32 0x1000 x4, u32 0x2000, zeros
  0x030  object names, 0x20 bytes each (NUL, then 0xFE fill), up to 32: "model", "GT_0_map", ..., "GT_8_panel_ui"
  0x430  u32 object count, NA (quad vertices), NB (triangle vertices), NC, ND, NA + NB, 0, 0, 0
  0x454  u8 object index per vertex: NA, then NB (then NC + ND)
         positions, 16 bytes per vertex (A, then B): f32 x, y (negative is up; height h -> -12 h), z (28 per tile),
         then a u32 attribute per polygon corner: corner 0 = tile tag (u8 row << 1 | level, u8 column; FE FF = none),
         1 = u16 0, u16 polygon id, 2 = BB BB FF FF (quads), last = 01 80 FF FF
         normals, 8 bytes per vertex: int16 x, y, z (4096 = 1), 0
         records, 32 bytes per vertex: u32 render slot (a permutation of 0..N-1), u32 0, u32 material (the n of
         GT_n), 20 zero bytes
         UV and lighting, 28 bytes per RENDER SLOT (not element order: the vertex buffer, grouped by material in object
         order, panel last): u32 material, f32 u, v, 16 lighting bytes (1.15.0 wrote these in element order, which
         put wrong UVs and materials on most of the map)
  end    512 bytes (64 doubles, 1.0)
(NC / ND vertices, on a few maps, take only the index byte and 16 bytes of position.)
A panel is every tile-tagged polygon of the map, copied 0.2 above it with the same attributes (map 76: all 241 of
its tagged polygons), plus flat or sloped tiles of eight triangles (polygon id FFFF, a 2 x 2 split) on tiles the map
has no tagged polygon for (IC does this on some such tiles, not consistently; here: every tile the classic terrain
does not block, e.g. map 45's arch). Its vertices take the highest render slots; their UVs are tile-local, u = (x -
28 col) / 28, v = (28 (row + 1) - z) / 28, which the grid textures (bg/ui/panel/*.tga) are drawn with (1.15.2 copied
the map's UVs: the highlight came out as one flat fill); lighting bytes are neutral (IC's are noise around 0x80);
every panel polygon winds counter-clockwise seen from above (positive in x/z). The game uses a panel only when
nxd RefinedBgMeshNode marks its object (Unknown16 = 1; tools/build_data.py adds the row).
Classic terrain (fftpack/map/new_map_new_mapNNN_*.bin, pointer at +0x68): u8 width, depth, then 8 bytes per tile,
level 0 then level 1 at +256 tiles: +0 surface (low 6 bits), +2 height, +3 slope rise (low 5 bits), +4 slope type
(0x52 rises toward +x, 0x58 toward -x, 0x85 toward +z, 0x25 toward -z; others are corner slopes), +6 flags (& 3:
blocked).
"""
import os, struct, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
GAME = r'H:/FFT/Game Files'
OUT = os.path.join(ROOT, 'FFTIVC', 'data', 'enhanced', 'bg', 'meshes')
LIFT = 0.2

def read(path):
    d = open(path, 'rb').read()
    assert d[:8] == b'FFTOMESH'
    nobj, na, nb, nc, nd = struct.unpack_from('<5I', d, 0x430)
    n = na + nb
    size = 0x454 + n * 85 + (nc + nd) * 17 + 512
    if nc or nd or size != len(d): raise SystemExit('%s: layout with extra data not handled' % path)
    names = [d[0x30 + 0x20 * i:0x50 + 0x20 * i].split(b'\0')[0].decode() for i in range(nobj)]
    obj = d[0x454:0x454 + n]
    o = 0x454 + n
    pos = [d[o + 16 * k:o + 16 * k + 16] for k in range(n)]; o += 16 * n
    nrm = [d[o + 8 * k:o + 8 * k + 8] for k in range(n)]; o += 8 * n
    rec = [d[o + 32 * k:o + 32 * k + 32] for k in range(n)]; o += 32 * n
    uvl = [d[o + 28 * k:o + 28 * k + 28] for k in range(n)]; o += 28 * n
    return dict(head=d[:0x30], names=names, na=na, nb=nb, obj=obj, pos=pos, nrm=nrm, rec=rec, uvl=uvl, tail=d[o:])

SLOPES = {0x00: lambda u, v: 0, 0x52: lambda u, v: u, 0x58: lambda u, v: 1 - u, 0x85: lambda u, v: v, 0x25: lambda u, v: 1 - v}
NEUTRAL = bytes([0x80]) * 16
UP = struct.pack('<4h', 0, -4096, 0, 0)

def terrain(mapno):
    import glob
    f = sorted(glob.glob(os.path.join(GAME, 'fftpack', 'map', 'new_map_new_map%03d_*.bin' % mapno)))[0]
    d = open(f, 'rb').read(); p = struct.unpack_from('<I', d, 0x68)[0]
    w, depth = d[p], d[p + 1]
    tiles = {}
    for level in (0, 1):
        for row in range(depth):
            for col in range(w):
                o = p + 2 + level * 256 * 8 + (row * w + col) * 8
                t = d[o:o + 8]
                if level == 1 and not any(t): continue
                tiles[(row, col, level)] = t
    return tiles

def tile_uv(x, z, row, col):
    return (x - 28 * col) / 28, (28 * (row + 1) - z) / 28

def add_panel(m, tiles=None):
    if any('panel_ui' in n for n in m['names']): raise SystemExit('the map already has a panel')
    gts = [int(n.split('_')[1]) for n in m['names'] if n.startswith('GT_')]
    material = max(gts) + 1
    new_obj = len(m['names'])
    m['names'].append('GT_%d_panel_ui' % material)
    order = [max(struct.unpack_from('<I', r, 0)[0] for r in m['rec']) + 1]
    added = {'A': [], 'B': []}
    new_uvl = []                    # render slots order, order + 1, ...: appended after every existing slot
    def vertex(part, x, y, z, attr, normal, row, col):
        added[part].append((struct.pack('<3f', x, y, z) + attr, normal, struct.pack('<3I', order[0], 0, material) + bytes(20)))
        new_uvl.append(struct.pack('<I2f', material, *tile_uv(x, z, row, col)) + NEUTRAL)
        order[0] += 1
    covered = set()
    for part, first, count, size in (('A', 0, m['na'], 4), ('B', m['na'], m['nb'], 3)):
        for p in range(first, first + count, size):
            tag = m['pos'][p][12:14]
            if tag == b'\xFE\xFF': continue          # no tile tag
            row, col, level = tag[0] >> 1, tag[1], tag[0] & 1
            covered.add((row, col, level))
            for k in range(p, p + size):
                x, y, z = struct.unpack_from('<3f', m['pos'][k])
                vertex(part, x, y - LIFT, z, m['pos'][k][12:], m['nrm'][k], row, col)
    fills = []
    for (row, col, level), t in sorted((tiles or {}).items()):
        if (row, col, level) in covered or t[6] & 3 or (t[0] & 0x3F) == 0x3F: continue
        if t[4] not in SLOPES: raise SystemExit('tile %s: slope type %02X not handled' % ((row, col, level), t[4]))
        rise = SLOPES[t[4]]
        height = lambda u, v: -12 * (t[2] + (t[3] & 0x1F) * rise(u, v)) - LIFT
        tag = bytes([row << 1 | level, col])
        fills.append((row, col, level))
        for i in (0, 1):
            for j in (0, 1):
                # a quarter of the tile, (u0, v0) to (u0 + 0.5, v0 + 0.5), as two triangles, counter-clockwise from above
                u0, v0 = i / 2, j / 2
                pts = [(u0, v0), (u0 + .5, v0), (u0 + .5, v0 + .5), (u0, v0 + .5)]
                for tri in ((pts[0], pts[1], pts[2]), (pts[0], pts[2], pts[3])):
                    xz = [(28 * col + 28 * u, 28 * (row + 1) - 28 * v) for u, v in tri]
                    (ax, az), (bx, bz), (cx, cz) = xz
                    if (bx - ax) * (cz - az) - (bz - az) * (cx - ax) < 0: tri, xz = tri[::-1], xz[::-1]
                    attrs = [tag + b'\xFF\xFF', b'\x00\x00\xFF\xFF', b'\x01\x80\xFF\xFF']
                    for (u, v), (x, z), attr in zip(tri, xz, attrs):
                        vertex('B', x, height(u, v), z, attr, UP, row, col)
    a, b = added['A'], added['B']
    na, nb = m['na'] + len(a), m['nb'] + len(b)
    split = lambda lst: (lst[:m['na']], lst[m['na']:])
    parts = {}
    for i, key in enumerate(('pos', 'nrm', 'rec')):             # element order: A, then B
        oa, ob = split(m[key])
        parts[key] = oa + [v[i] for v in a] + ob + [v[i] for v in b]
    parts['uvl'] = m['uvl'] + new_uvl                               # render order (see the docstring)
    oa, ob = split(list(m['obj']))
    obj = bytes(oa + [new_obj] * len(a) + ob + [new_obj] * len(b))
    names = b''.join((n.encode() + b'\0').ljust(0x20, b'\xFE') for n in m['names']).ljust(0x400, b'\0')
    counts = struct.pack('<9I', len(m['names']), na, nb, 0, 0, na + nb, 0, 0, 0)
    out = m['head'] + names + counts + obj + b''.join(b''.join(parts[k]) for k in ('pos', 'nrm', 'rec', 'uvl')) + m['tail']
    return out, len(a) // 4, len(b) // 3, material, fills

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for mapno in map(int, sys.argv[1:]):
        src = os.path.join(GAME, 'bg', 'meshes', 'map_%03d_mesh.bin' % mapno)
        out, quads, tris, material, fills = add_panel(read(src), terrain(mapno))
        dst = os.path.join(OUT, 'map_%03d_mesh.bin' % mapno)
        open(dst, 'wb').write(out)
        check = read(dst)
        assert check['names'][-1] == 'GT_%d_panel_ui' % material
        print('map %d: GT_%d_panel_ui, %d quads + %d triangles (filled tiles %s) -> %s' % (mapno, material, quads, tris, fills, dst))
