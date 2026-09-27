# Art taken from other mods

- `tex_1279.bin`: enhanced-mode texture for event sprite sheet 0x8E (War of the Lions' Mustadio/Agrias birthday poses;
  512x512, 4bpp). Vanilla IC ships this slot (and tex_1280-1284 for sheets 0x8C, 0x8B, 0x89, 0x8D, 0x8A) as copies of
  sheet 0x36, which is why the poses drew as scrambled pieces.
- `tex_1284.bin`: the same for sheet 0x8A (War of the Lions' Balthier poses, used by his recruitment scene 524).

- `tex_1179.bin` (sheet 0x1E, Ovelia's grass whistle, scene 536) and `tex_1263.bin` (sheet 0x7C, Ovelia's prayer
  and wound, chapel ruins scene 532): vanilla sheets WotL drew extra frames on, below row 442 where IC's textures stop.
  Each is IC's own texture (g2d.dat entry, rows 0-441) with the Mobile texture's rows 442-511 appended; the Mobile
  set redraws the rest of the sheet (same layout and palette), which vanilla scenes should not pick up.

- `tex_1283.bin`: WotL-only sheet 0x8D (Beowulf and Reis's scenes 553-569), the Mobile texture as is. `tex_1159`,
  `tex_1177`, `tex_1252`, `tex_1264`, `tex_1271`, `tex_1278`, `tex_1160`, `tex_1275`: vanilla sheets with WotL rows, built like 1179/1263
  (tools/sheet_textures.py).

All are from "FF Tactics Mobile Sprites" (fftivc.texture.mobilesprites) by Spikedrose, v1.0.4.

- `items/`: War of the Lions item icons (WotL ids 0x100-0x139, names in items.json), from Spikedrose's Mobile item
  set (H:/FFT/WotL Sprites/Items/Mobile), converted by tools/item_icons.py to IC's icon textures: small 48x48 as
  drawn, large 100x100 scaled 2x. Staged by WotL id until the item-table expansion assigns their IC ids.

Spikedrose gave permission (2026-09-24) to use and redistribute these in this mod.
