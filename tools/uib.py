"""Reader (and, for the edits the mod needs, writer) for IC's UI layout files (.uib), after AlexCup and Nenkai's 010
Editor template for Final Fantasy XVI's (Nenkai/010GameTemplates, Square Enix/Final Fantasy 16/FF16_uib_UIBinary.bt;
IC's files are the same format, version 10).

  python tools/uib.py <file.uib> [component]      prints the components, or one component's nodes and timelines

Format essentials (every offset is relative to the start of the structure that holds it):
  header: 'UIB\\0', u32 version (10), 16 bytes, u32 TOC offset (0x2C)
  TOC (0x2C): asset list offset, component table offset, component count
  component (GroupEntry, 0x40 bytes): name, size (w, h), properties, nodes (offset, count), timelines (offset, count)
  node list: u32 offsets (relative to the list) to nodes; node: +0 type (1 layer, 2 image, 3 text, 4 ninegrid,
    6 rect, 7 ellipse, 8 bezier, 10 reference = an instance of another component, 11 effect, 13 mask), +4 name,
    +8 origin (x, y), +0x10 rotation, +0x14 scale, +0x1C anchor, +0x44 size, +0x4C data offset; layers: children at
    +0x90 (offset) / +0x94 (count); references: the component's name at +0x70
  timeline (UIComponentTimeline, 0x60 bytes): name, flags, info at +8 {type, elements (offset, count), asset groups,
    targets (offset, count), frame count}; element (0x20 bytes): index, name, type, frame start, frame count, target
    index, 2 bools, data offset (the keyframe data: type, 0x2C bytes, value(s) at +0x30.. / +0x74)
"""
import struct, sys

class Uib:
    def __init__(self, path_or_bytes):
        self.d = bytearray(open(path_or_bytes, 'rb').read() if isinstance(path_or_bytes, str) else path_or_bytes)
        d = self.d
        assert d[:4] == b'UIB\0', 'not a UIB file'
        self.version = self.u32(4)
        self.toc = self.u32(0x18)
        self.comp_table = self.toc + self.i32(self.toc + 4)
        self.comp_count = self.i32(self.toc + 8)

    # --- primitives ---
    def u32(self, o): return struct.unpack_from('<I', self.d, o)[0]
    def i32(self, o): return struct.unpack_from('<i', self.d, o)[0]
    def f32(self, o): return struct.unpack_from('<f', self.d, o)[0]
    def cstr(self, o):
        e = self.d.index(b'\0', o); return self.d[o:e].decode('utf-8', 'replace')
    def rel_str(self, base, field):
        off = self.i32(field)
        return self.cstr(base + off) if off else None

    # --- components ---
    def component(self, k):
        b = self.comp_table + 0x40 * k
        return dict(index=k, base=b, name=self.rel_str(b, b), w=self.i32(b + 4), h=self.i32(b + 8),
                    props=b + self.i32(b + 0xC), nodes=b + self.i32(b + 0x10), node_count=self.i32(b + 0x14),
                    timelines=b + self.i32(b + 0x18), timeline_count=self.i32(b + 0x1C))

    def components(self):
        return [self.component(k) for k in range(self.comp_count)]

    def find(self, name):
        return next(c for c in self.components() if c['name'] == name)

    # --- nodes ---
    def node_list(self, at, count):
        return [self.node(at + self.i32(at + 4 * i)) for i in range(count)]

    def node(self, b):
        t = self.i32(b)
        n = dict(base=b, type=t, name=self.rel_str(b, b + 4), x=self.i32(b + 8), y=self.i32(b + 0xC),
                 rot=self.f32(b + 0x10), sx=self.f32(b + 0x14), sy=self.f32(b + 0x18),
                 ax=self.i32(b + 0x1C), ay=self.i32(b + 0x20), w=self.i32(b + 0x44), h=self.i32(b + 0x48),
                 data=b + self.i32(b + 0x4C))
        if t == 1:                                   # layer: children (offset, count at +0x90 / +0x94)
            n['children'] = self.node_list(b + self.i32(b + 0x90), self.u32(b + 0x94))
        elif t == 10:                                # reference: an instance of another component (name at +0x70)
            n['ref'] = self.rel_str(b, b + 0x70)
        return n

    # --- timelines ---
    def timelines(self, comp):
        return [self.timeline(comp['timelines'] + 0x60 * i) for i in range(comp['timeline_count'])]

    def timeline(self, b):
        info = b + 8
        el_at, el_n = info + self.i32(info + 4), self.i32(info + 8)
        tg_at, tg_n = info + self.i32(info + 0x14), self.i32(info + 0x18)
        return dict(base=b, name=self.rel_str(b, b), flags=self.u32(b + 4), type=self.i32(info),
                    frames=self.i32(info + 0x1C), elements=[self.element(el_at + 0x20 * i) for i in range(el_n)],
                    targets=[self.target(tg_at, i) for i in range(tg_n)])

    def target(self, list_at, i):
        b = list_at + self.i32(list_at + 4 * i)
        t = self.i32(b)
        return dict(base=b, type=t, name=self.rel_str(b, b + 0x28) if t == 4001 else None)

    def element(self, b):
        data = b + self.i32(b + 0x1C)
        e = dict(base=b, index=self.i32(b), name=self.rel_str(b, b + 4), type=self.i32(b + 8),
                 start=self.i32(b + 0xC), count=self.i32(b + 0x10), target=self.i32(b + 0x14),
                 data=data, dtype=self.i32(data))
        e['values'] = [self.f32(data + 0x74), self.f32(data + 0x78)] if e['dtype'] in (5004,) else \
                      [self.f32(data + 0x74)] if e['dtype'] in (5005, 5009) else \
                      [self.i32(data + 0x74), self.i32(data + 0x78)] if e['dtype'] in (5002, 5003) else []
        return e

    # --- every offset field of a component (for copying structures elsewhere in the file) ---
    def offset_fields(self, comp):
        """[(field address, struct base)] for every non-zero offset reachable from the component's properties, nodes
        and timelines, per the template (a structure's offsets are relative to its own start)."""
        out, seen = [], set()
        def field(base, at):
            if self.i32(at): out.append((at, base)); return base + self.i32(at)
            return None
        def asset_entry(a):
            if a is None or ('a', a) in seen: return
            seen.add(('a', a)); field(a, a + 4)
            n = field(a, a + 8)
            if n is not None: field(n, n + 4)
        def texture_asset(t):
            if t is None: return
            asset_entry(field(t, t))
        def texture_assets(at, count, size=0x2C):
            for i in range(count): texture_asset(at + size * i)
        def node(b):
            if ('n', b) in seen: return
            seen.add(('n', b)); t = self.i32(b)
            field(b, b + 4)
            data = field(b, b + 0x4C)
            if t == 1:
                lst = field(b, b + 0x90)
                if lst is not None: node_list(lst, self.u32(b + 0x94))
            elif t == 10:
                field(b, b + 0x70); asset_entry(field(b, b + 0x74))
            elif t == 11:
                asset_entry(field(b, b + 0x74))
            elif t == 13:
                asset_entry(field(b, b + 0x9C)); field(b, b + 0xA0)
            if data is None: return
            if t in (2, 13):
                at = field(data, data + 0x40)
                if at is not None: texture_assets(at, self.i32(data + 0x44))
            elif t == 3:
                field(data, data + 0x44)
            elif t == 4:
                at = field(data, data + 0x40)
                if at is not None: texture_asset(at)
            elif t == 5:
                at = field(data, data + 0x40)
                if at is not None: texture_asset(at)
                field(data, data + 0x68); field(data, data + 0x6C)
            elif t == 7:
                at = field(data, data + 0x50)
                if at is not None: texture_asset(at)
            elif t == 8:
                field(data, data + 0x80)
        def node_list(at, count):
            for i in range(count):
                n = field(at, at + 4 * i)
                if n is not None: node(n)
        def timeline(m):
            field(m, m)
            info = m + 8
            el = field(info, info + 4)
            for i in range(self.i32(info + 8) if el is not None else 0):
                e = el + 0x20 * i
                field(e, e + 4)
                x = field(e, e + 0x1C)
                if x is not None and self.i32(x) == 5028: field(x, x + 0x30)
            ag = field(info, info + 0xC)
            for i in range(self.i32(info + 0x10) if ag is not None else 0):
                g = ag + 0xC * i
                lst = field(g, g + 4)
                for j in range(self.i32(g + 8) if lst is not None else 0):
                    asset_entry(field(lst, lst + 4 * j))
            tg = field(info, info + 0x14)
            for i in range(self.i32(info + 0x18) if tg is not None else 0):
                t = field(tg, tg + 4 * i)
                if t is not None and self.i32(t) == 4001: field(t, t + 0x28)
            field(m, m + 0x30); asset_entry(field(m, m + 0x34)); field(m, m + 0x3C)
        p = comp['props']
        names = field(p, p + 4)
        for i in range(self.i32(p + 8) if names is not None else 0): field(names, names + 4 * i)
        asset_entry(field(p, p + 0x98))
        if self.i32(p + 0xAC) > 0: texture_asset(field(p, p + 0xA8))
        if comp['node_count']: node_list(comp['nodes'], comp['node_count'])
        for i in range(comp['timeline_count']): timeline(comp['timelines'] + 0x60 * i)
        return out

    def extent(self, comp):
        """The byte range [lo, hi) the component's own structures occupy (targets in the shared string pool and
        asset data excluded), and its offset fields."""
        fields = self.offset_fields(comp)
        starts = [comp['props'], comp['nodes'], comp['timelines']] + [a for a, b in fields]
        return min(starts), fields

    def copy_component(self, source, target):
        """Makes component `target` a copy of component `source`: `source`'s structures are copied to the end of the
        file (every offset leaving the copied block re-aimed) and `target`'s record points at the copy. Returns the
        copy's delta (new address - old address) so its values can be edited."""
        src, dst = self.find(source), self.find(target)
        fields = self.offset_fields(src)
        lo = min([src['props'], src['nodes'], src['timelines']] + [a for a, b in fields] + [b for a, b in fields])
        nxt = sorted(c['props'] for c in self.components() if c['props'] > lo)
        hi = nxt[0] if nxt else len(self.d)
        pad = (-len(self.d)) % 16
        new_lo = len(self.d) + pad
        delta = new_lo - lo
        block = bytearray(self.d[lo:hi])
        for at, base in fields:
            if not lo <= at < hi: continue               # a field outside the block (none expected)
            target_addr = base + self.i32(at)
            if lo <= target_addr < hi: continue           # inside the block: moves with it
            struct.pack_into('<i', block, at - lo, target_addr - (base + delta))
        self.d += b'\0' * pad + block
        b = dst['base']
        for off, addr in ((0xC, src['props']), (0x10, src['nodes']), (0x18, src['timelines'])):
            struct.pack_into('<i', self.d, b + off, addr + delta - b)
        struct.pack_into('<i', self.d, b + 0x14, src['node_count'])
        struct.pack_into('<i', self.d, b + 0x1C, src['timeline_count'])
        return delta, lo, hi

    def save(self, path):
        open(path, 'wb').write(self.d)

def show_node(n, depth=0):
    extra = (' -> ' + n['ref']) if n.get('ref') else ''
    print('%s%s [%d] @(%d,%d) %dx%d%s' % ('  ' * depth, n['name'], n['type'], n['x'], n['y'], n['w'], n['h'], extra))
    for c in n.get('children', []): show_node(c, depth + 1)

if __name__ == '__main__':
    u = Uib(sys.argv[1])
    if len(sys.argv) < 3:
        for c in u.components():
            print('%2d %-20s %dx%d nodes %d timelines %d' % (c['index'], c['name'], c['w'], c['h'], c['node_count'], c['timeline_count']))
        sys.exit()
    c = u.find(sys.argv[2])
    print(c['name'], c['w'], c['h'])
    for n in u.node_list(c['nodes'], c['node_count']): show_node(n, 1)
    for t in u.timelines(c):
        print('timeline %s type %d frames %d targets %s' % (t['name'], t['type'], t['frames'], [x['name'] for x in t['targets']]))
        for e in t['elements']:
            print('    el %s type %d frames %d+%d target %d data %d %s' % (e['name'], e['type'], e['start'], e['count'], e['target'], e['dtype'], ['%.1f' % v if isinstance(v, float) else v for v in e['values']]))
