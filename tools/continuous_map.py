"""The multi-stage battle minimap (ui/ffto/battle/ffto_battle_continuous_map.uib) for the stage chains WotL's ports
change. IC draws the chain from ContinuousSortieConfirm rows (which point, line and unit keys each stage plays: see
research/NOTES.md), but every map's markers, lines and per-stage timelines are components in this UIB (tools/uib.py):
MapA..MapH, each a 900x540 layer over one 362x222 panel of ui_battle_continuous_map_dotart_uitx, shown by MapAll.

  python tools/continuous_map.py            writes FFTIVC/data/enhanced/ui/ffto/battle/ffto_battle_continuous_map.uib
  python tools/continuous_map.py --preview sheet.png out.png    also draws the edited maps' markers on their panels

A map with more stages than its component has is rebuilt from a component that has enough (MapH has 4: PointStart,
Point01..04; Line01..04; Point/Move/Position/Stay timelines per stage), whose copy is then placed for the new map.

Layout rules (read from IC's own maps):
  a point's node origin is its marker's top-left: the marker's centre is origin + (30, 15)
  a line starts at the centre of the point it leaves: origin = that centre, anchor (0, 4), rotation = atan2(dy, dx)
    to the next point's centre, y-scale -1 when heading left (the texture stays upright), width = the distance
  the unit stands over the point it is at: roughly origin + (0, -91)
  timelines: HomePosition places the points and lines; PointN (N < last) blinks the next point and line; MoveN walks
    the unit from stage N-1 to N; PositionN / StayN put it at stage N
"""
import math, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uib import Uib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = r'H:/FFT/Game Files'
PATH = os.path.join('ui', 'ffto', 'battle', 'ffto_battle_continuous_map.uib')
OUT = os.path.join(ROOT, 'FFTIVC', 'data', 'enhanced', PATH)

POINT_NAMES = ['PointStart', 'Point01', 'Point02', 'Point03', 'Point04']
UNIT_OFFSET = (0, -91)

# component: (template component, [(point origin, unit position or None for the default offset)], art panel)
MAPS = {
    # Limberry: Castle Gate -> Keep -> Inner Court (WotL's Argath battle, map 127) -> Undercroft. IC's own points kept
    # (with its hand-placed unit positions); the Inner Court on the terrace west of the keep.
    'MapE': ('MapH', [((760, 466), (764, 374)), ((464, 273), (460, 178)), ((326, 125), (326, 38)),
                      ((120, 175), None), ((226, 79), (222, -14))], 6),
}

def centre(p): return p[0] + 30, p[1] + 15

def all_nodes(u, c):
    """{name: node} over a component's whole node tree."""
    nodes = {}
    def walk(n):
        nodes[n['name']] = n
        for ch in n.get('children', []): walk(ch)
    for n in u.node_list(c['nodes'], c['node_count']): walk(n)
    return nodes

def place(u, name, points, units):
    c = u.find(name)
    nodes = all_nodes(u, c)
    stages = len(points)
    assert all(POINT_NAMES[k] in nodes for k in range(stages)) and 'Line%02d' % (stages - 1) in nodes, name
    def origin(node, xy): struct.pack_into('<2i', u.d, node['base'] + 8, *xy)
    lines = {}
    for k, p in enumerate(points):
        origin(nodes[POINT_NAMES[k]], p)
        if k:
            (x0, y0), (x1, y1) = centre(points[k - 1]), centre(p)
            line = nodes['Line%02d' % k]
            lines[line['name']] = (x0, y0)
            origin(line, (x0, y0))
            struct.pack_into('<f', u.d, line['base'] + 0x10, math.atan2(y1 - y0, x1 - x0))
            struct.pack_into('<f', u.d, line['base'] + 0x18, -1.0 if x1 < x0 else 1.0)
            struct.pack_into('<i', u.d, line['base'] + 0x44, round(math.hypot(x1 - x0, y1 - y0)))
    origin(nodes['Unit'], units[0])
    def set_xy(e, xy): struct.pack_into('<2i', u.d, e['data'] + 0x74, *xy)
    for t in u.timelines(c):
        pos = [e for e in t['elements'] if e['dtype'] == 5002]
        if t['name'] == 'HomePosition':
            for e in pos:
                target = t['targets'][e['target']]['name']
                if target in POINT_NAMES: set_xy(e, points[POINT_NAMES.index(target)])
                elif target in lines: set_xy(e, lines[target])
            continue
        kind, stage = next(((k, t['name'][len(k):]) for k in ('Point', 'Move', 'Position', 'Stay') if t['name'].startswith(k)))
        stage = 0 if stage == 'Start' else int(stage)
        for e in pos:
            assert t['targets'][e['target']]['name'] == 'Unit', (name, t['name'])
            set_xy(e, units[stage - 1] if kind == 'Move' and e['start'] == 0 else units[stage])

def build():
    u = Uib(os.path.join(GAME, PATH))
    for name, (template, spec, panel) in MAPS.items():
        points = [p for p, _ in spec]
        units = [unit or (p[0] + UNIT_OFFSET[0], p[1] + UNIT_OFFSET[1]) for p, unit in spec]
        if sum(n in POINT_NAMES for n in all_nodes(u, u.find(name))) < len(points): u.copy_component(template, name)
        place(u, name, points, units)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    u.save(OUT)
    return u

def preview(u, art, path):
    """Draws the edited maps' points, lines and unit positions on their panels of `art` (the dotart sheet as a PNG)."""
    from PIL import Image, ImageDraw
    art = Image.open(art).convert('RGB')
    shots = []
    for name, (template, spec, panel) in MAPS.items():
        row, col = divmod(panel - 1, 3)
        w, h = art.width / 3, art.height / 3
        img = art.crop((round(col * w), round(row * h), round((col + 1) * w), round((row + 1) * h))).resize((900, 540))
        d = ImageDraw.Draw(img)
        c = u.find(name)
        nodes = all_nodes(u, c)
        for k in range(1, len(spec)):
            ln = nodes['Line%02d' % k]
            x0, y0, a, L = ln['x'], ln['y'], ln['rot'], ln['w']
            d.line((x0, y0, x0 + L * math.cos(a), y0 + L * math.sin(a)), fill=(255, 60, 60), width=4)
        for k in range(len(spec)):
            x, y = centre((nodes[POINT_NAMES[k]]['x'], nodes[POINT_NAMES[k]]['y']))
            d.ellipse((x - 10, y - 10, x + 10, y + 10), outline=(255, 255, 0), width=3)
            d.text((x + 13, y - 6), POINT_NAMES[k], fill=(255, 255, 255))
        for t in u.timelines(c):
            if t['name'].startswith('Position'):
                ux, uy = [e for e in t['elements'] if e['dtype'] == 5002][0]['values']
                d.rectangle((ux - 4, uy - 4, ux + 4, uy + 4), outline=(0, 255, 255), width=2)
        shots.append(img)
    shots[0].save(path)

if __name__ == '__main__':
    u = build()
    print('wrote', OUT)
    if '--preview' in sys.argv: preview(u, *sys.argv[sys.argv.index('--preview') + 1:][:2])
