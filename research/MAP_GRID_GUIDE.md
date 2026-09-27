# Battle grids for Ivalice Chronicles maps

How the WotL Characters mod gave map 45 (Zeltennia Castle – Chapel Ruins), a map IC only uses for cutscenes, a working battle grid and height-following cursor, and what you need to know to do the same for another map. Everything here was worked out from the game's own files (Steam release, checked 2026-09-25) and confirmed in game.

The generator is `tools/panel_ui.py` in the WotL Characters source; `tools/build_data.py` runs it and adds the nxd row.

## The short version

In enhanced (HD) mode, a map is battle-ready when all three of these hold:

1. Its HD mesh (`bg/meshes/map_NNN_mesh.bin`) contains a **panel object** named `GT_n_panel_ui`: an invisible copy of every walkable surface, one set of polygons per battle tile. The movement/target highlights and the cursor are drawn on it.
2. The nxd table **RefinedBgMeshNode** has a row for that object with `Unknown16 = 1`. The game identifies the panel by this flag, never by the object's name.
3. The panel's texture coordinates are **tile-local** (0 to 1 across each tile), so the grid textures draw one bordered square per tile.

Units walk on the classic terrain data, which every map has, so a map missing any of these still plays; only the grid and cursor break.

## Symptoms and their causes

| What you see | Cause |
|---|---|
| No grid squares; the cursor sits at one height and the Height readout never changes; units move normally | The map has no panel object (it is a cutscene-only map) |
| After adding a panel: black or stretched patches all over the map | The UV/lighting array was written in vertex order instead of render-slot order (see below) |
| Map looks fine but the cursor is still flat | The panel has no RefinedBgMeshNode row with `Unknown16 = 1` |
| Cursor follows height, but the highlight is one flat blue fill without tile borders | Panel UVs are copied from the map texture instead of being tile-local |
| Cursor jumps up or down on a few tiles (map 45's arch) | Those tiles have no tile-tagged map polygon, so the panel has a hole there; add fill tiles |

## Files involved

| File | Role |
|---|---|
| `bg/meshes/map_NNN_mesh.bin` | HD mesh ("FFTOMESH"): the drawn map and its panel |
| `fftpack/map/new_map_new_mapNNN_*.bin` | Classic mesh with IC's edits; its terrain block drives movement, heights and slopes |
| `nxd/refinedbgmeshnode.nxd` | Per-map, per-object flags; marks the panel |
| `nxd/refinedbgtexture.nxd` | Textures for each map material (the panel material has none) |
| `nxd/refinedbguitextureframes.nxd` | The grid textures, `bg/ui/panel/*.tga` (cursor, move range, attack range...) |

With fftivc.utility.modloader, modded copies go under `FFTIVC/data/enhanced/` at the same paths.

## Which maps lack a panel

33 of IC's 108 HD meshes have no panel. The tool handles the 10 marked *simple*; the others use two further vertex groups (NC/ND, 19 maps) or carry extra data whose layout is not decoded (4 maps).

- **Simple:** 1 Eagrose Castle Gate, 9 Eagrose Castle Solar, 23 The Beoulve Manse, 37 Zaland Outskirts, 43 Warjilis Harbor, 45 Zeltennia Castle – Chapel Ruins, 46 The Tomb of Barbaneth Beoulve, 48 Sal Ghidos Slumtown, 100 Cemetery, 115 Abandoned Watchtower (unused)
- **NC/ND groups:** 4, 8, 11, 14, 18, 20, 21, 24, 26, 51, 62, 65, 68, 92, 93, 94, 95, 96, 104
- **Extra data:** 38 Goug, 41 Bunansa Residence, 53 The Imperial Capitoline, 73 Mill Interior

## The FFTOMESH format

All offsets are from the start of the file; all values little-endian.

| Offset | Contents |
|---|---|
| 0x000 | `"FFTOMESH"`, u32 map id, u32 1, u32 0x1000 ×4, u32 0x2000, zeros to 0x30 |
| 0x030 | Object names, 0x20 bytes each: text, a NUL, then 0xFE fill. 32 slots; unused slots are zero |
| 0x430 | u32 object count, NA (quad vertices), NB (triangle vertices), NC, ND, NA+NB, then three zero u32s |
| 0x454 | u8 object index per vertex: NA entries, then NB (then NC + ND) |
| next | **Positions**, 16 bytes per vertex, quads first then triangles |
| next | **Normals**, 8 bytes per vertex, same order |
| next | **Records**, 32 bytes per vertex, same order |
| next | **UV + lighting**, 28 bytes per **render slot** |
| end | 512 bytes: 64 doubles, all 1.0 |

File size = 0x454 + 85 × (NA + NB) + 17 × (NC + ND) + 512, which holds for 98 of the 108 meshes. Quads are 4 consecutive vertices, triangles 3.

### Object names

`model` is the root. `GT_n_<name>` objects are drawn with material *n*, whose textures RefinedBgTexture lists (for example `gt_0_map045_map_color`). `l_…` objects appear to be locators and `FT_…` another kind; neither matters for the grid. The panel is `GT_n_panel_ui`, with *n* one above the highest material the map uses. IC ships no texture for it.

### Positions (16 bytes)

f32 x, f32 y, f32 z, then one u32 attribute that depends on the vertex's corner within its polygon.

- Tiles are 28 units wide: tile column *c* spans x = 28c to 28c + 28, row *r* spans z = 28r to 28r + 28.
- y is negative upward: terrain height *h* sits at y = −12 × h.

Corner attributes:

| Corner | Bytes | Meaning |
|---|---|---|
| First | `RR CC FF FF` | Tile tag: RR = row × 2 + level (level 1 is the upper layer, under bridges and arches), CC = column. `FE FF FF FF` means not on any tile |
| Second | `00 00 II II` | u16 polygon id |
| Third (quads only) | `BB BB FF FF` | constant |
| Last | `01 80 FF FF` | end of polygon |

The map mesh's tile-tagged polygons are the same ones the classic mesh tags (map 76: 241 in both).

### Normals (8 bytes)

int16 x, y, z, 0, where 4096 = 1.0. Straight up is (0, −4096, 0). These follow vertex order: 97% agree with the polygons' geometric normals in that order, against 51% under the render-slot permutation.

### Records (32 bytes)

| Offset | Contents |
|---|---|
| +0 | u32 render slot (a permutation of 0 … N−1) |
| +4 | u32 0 |
| +8 | u32 material (the *n* of the object's `GT_n`) |
| +12 | 20 zero bytes |

### UV + lighting (28 bytes per render slot)

This array is the render vertex buffer. It is **not** in vertex order: entry *s* belongs to the vertex whose record says slot *s*. It is grouped by material in object order, with the panel last.

| Offset | Contents |
|---|---|
| +0 | u32 material (always equals the owning vertex's record material) |
| +4 | f32 u, f32 v |
| +12 | 16 lighting bytes |

Writing this array in vertex order is the mistake that produces black and stretched patches across the whole map.

## Building a panel

The panel is a copy of the map's walkable surfaces, lifted slightly, plus filler for tiles the map mesh doesn't tag.

1. **Copy every tile-tagged polygon** of the map's objects into a new object `GT_n_panel_ui`.
   - Raise each vertex by 0.2 (y − 0.2).
   - Keep the four corner attributes and the normals as they are.
2. **Give every panel vertex a new render slot**, continuing after the map's highest slot, and material *n*. Append the UV/lighting entries after all existing entries, in slot order. Leave IC's existing entries untouched.
3. **Set tile-local UVs** on every panel vertex, from its tile tag's row *r* and column *c*:
   - u = (x − 28c) / 28
   - v = (28 × (r + 1) − z) / 28

   Quads come out as (0,0)–(1,1); partial tiles use 0.5 steps. Use neutral lighting bytes (0x80); IC's are noise around that value.
4. **Fill the gaps.** For every tile the classic terrain doesn't block that has no tagged polygon, add a tile of eight triangles:
   - split the tile 2 × 2 and each quarter into two triangles;
   - follow the tile's height and slope;
   - use polygon id FFFF, an up normal and tile-local UVs.

   IC does the same on some of its own maps, though not consistently.
5. **Wind every panel polygon counter-clockwise seen from above**: a positive cross product of (b − a) × (c − a) in the x/z plane. All of IC's panel polygons do.
6. **Add the node row** to RefinedBgMeshNode for the new object, once per arrangement (Key2) the map has.
7. Update the counts at 0x430 and the object index table, and rewrite the file.

### The RefinedBgMeshNode row

Keys: map number, arrangement (Key2), object index (Key3). IC's panel rows have `Unknown16 = 1`; 82 of its 85 panels do, and no other object has it. They usually also have `UnknownC = −100`, likely a draw bias. The mod copies map 76's panel row (node 13):

| Unknown8 | UnknownC | Unknown10 | Unknown14 | Unknown15 | Unknown16 | Unknown17 | Unknown18 |
|---|---|---|---|---|---|---|---|
| 0 | −100 | 0 | 1 | 0 | 1 | 1 | 1 |

The table is hash-keyed (use_base_row_id 0), so adding a row is safe.

## Classic terrain (for heights and fill tiles)

In `fftpack/map/new_map_new_mapNNN_*.bin` (IC's edited copy; `map_mapNNN_*` are the originals), the u32 at +0x68 points at the terrain block:

- u8 width (columns, x) and u8 depth (rows, z);
- 8 bytes per tile, row by row, for level 0;
- level 1 at +256 tiles (2,048 bytes further).

| Byte | Meaning |
|---|---|
| +0 | Surface type (low 6 bits; 0x3F = none) |
| +2 | Height |
| +3 | Slope rise (low 5 bits) |
| +4 | Slope type |
| +6 | Flags (low 2 bits set = blocked) |

Slope directions, measured from tagged polygons on sloped tiles across eight maps:

| Type | Rises toward | Type | Rises toward |
|---|---|---|---|
| 0x52 | +x | 0x11 | +x −z |
| 0x58 | −x | 0x14 | −x −z |
| 0x85 | +z | 0x41 | +x +z |
| 0x25 | −z | 0x44 | −x +z |
| | | 0x66, 0x69, 0x96, 0x99 | corner shapes: +x −z, −x −z, +x +z, −x +z |

The tool handles flat tiles and the four inclines, and stops on anything else. A sloped tile spans height h to h + rise along its direction.

## How the result was checked

- **Round trip on map 76 (Zeklaus Desert):** strip IC's own panel, regenerate it with the tool, and compare. The tool rebuilds the same 241 polygons. IC starts each copied quad one corner later, which only changes the triangulation diagonal. IC's render slots come out byte-identical, and every vertex's record material matches its slot's material.
- **In game on map 45:** the grid draws per-tile squares, the cursor and Height readout follow the terrain, and the arch works end to end.

## Upgrading a cutscene map: checklist

1. Check the mesh has the simple layout: NC = ND = 0 and the size formula holds.
2. Run `python tools/panel_ui.py NNN`; it writes `FFTIVC/data/enhanced/bg/meshes/map_NNN_mesh.bin` and lists the tiles it filled.
3. Add the RefinedBgMeshNode row and ship the table (the mod's `build_data.py` does this for every map in `PANEL_MAPS`).
4. For an event battle, the rest of the setup is separate: the event's setup record, cast, battle rules and so on. The map itself needs nothing else.

## What's still unknown

- The layout of the NC/ND vertex groups and of the 10 meshes with extra data.
- IC's rule for fill tiles. It adds them on some untagged tiles only, and on map 76's cactus tiles one height step above the terrain.
- The meaning of the render-slot order within the panel. IC interleaves quads and triangles; appending them in order works.
- The other RefinedBgMeshNode fields, and the corner slope shapes in detail.
- WotL-only maps 125–127 have no HD mesh in IC at all. The mod stages their scenes on stand-in maps instead.
