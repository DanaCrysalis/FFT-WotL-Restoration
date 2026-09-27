# Agrias's Birthday port: research notes

Source: FFT ReMixed v1.2.63.3, event 159 in EVENT/TEST.EVT. Images in H:\FFT\ISOs: clean USA .bin, pre-patched
`FFT ReMixed v1.2.63.3.bin`, and the War of the Lions PSP .iso (the event's origin).

## Event scripts: PSX vs IC

- Opcode parameter-length tables:
  - PSX vanilla / ReMixed: BATTLE.BIN file offset 0xE6170 (RAM 0x8014D170). `evlen_clean.bin`, `evlen_remixed.bin`.
  - IC exe: FFT_enhanced.exe file offset 0x67FF00 (`evlen_ic.bin`). It is the classic-mode table; classic `.e` scripts parse with it.
  - IC enhanced `.e` scripts need three changes (`evlen_enh.bin`): 0x10 DisplayMessage 14->17, 0x51 ChangeDialog 5->7, 0xEB 6->10.
    All 560 `script/enhanced/*.e` parse cleanly to 0xDB with it.
- Enhanced field changes: text IDs widen from u16 message numbers to u32 global text IDs.
  - DisplayMessage: `10 <const 10> <type> <textId u32> <unit u16> <7 bytes as PSX> <last byte widened to u16>`
  - ChangeDialog: `51 <box> <textId u32, FFFFFFFF = close> <2 bytes as PSX>`
- IC defines its own opcodes in A6-AF, C2-CE and E7-EE. Several collide with ReMixed's custom ones (AC, AE, C3, C4, CD, CE).

## ReMixed custom opcodes used by event 159

ReMixed's event-instruction upgrade: dispatcher hook at RAM 0x801588BC (from the vanilla loop at 0x80143D0C).
Event variables are u32 at RAM 0x8005771C (var n at +4n).

| op | meaning in event 159 |
|---|---|
| 0A b0 / 0B / 0C b0 | label B0 / return / call B0. B0 = wait dialogue (E5 01), wait camera (E5 04), and if pad bit 0x0800 at 0x80045944 is set, close windows and jump to label F0 (skip scene) |
| 01 / 04 / 0D f0 / 0E f0 | if / endif / goto F0 / label F0 (only inside the skip helper) |
| AC r, imm16 | var r = imm16 << 16 |
| AE r, imm16 | var r = imm16 |
| C1 dst off16 base size | dst = read(var[base] + off, size) |
| C4 src off16 base size | write(var[base] + off, var[src], size) |
| C3 charId, dst | var dst = pointer to the party unit with that special character id (0x1E = Agrias), -1 if absent |
| CE n | load a 0x400 block from disc (LBA 0x14B08 + n/2) into 0x800475E0 / 0x80049A18: ReMixed's world-trigger records (block 0x9E: "var 0x1FD == 1 -> event 0x9F") |
| CD a b c | write (c<<10 \| b<<8 \| a) into the u16 table at 0x8004E5D0[var 0x27] (trigger bookkeeping) |

Reward block: `B2 2C 00 50 C3` gil -50,000 (var 0x2C); inventory byte 0x800597CE += 1 (base 0x800596E0 -> item 0xEE Setiemson);
0x80165EF4 = 0x38EE (item name for the message); Agrias raw HP (unit +0x22, 3 bytes) and raw MP (+0x25) x 11/10;
var 0x2F9 = 1, var 0xB6 = 1. Neither var is used by any IC enhanced script.

## Event setup (PSX ATTACK.OUT)

Table at ATTACK.OUT 0x10920, 0x18 bytes per event, u16 event id at +0, u16 map at +2, u16 ENTD at +7.
ReMixed record 159: `9f 00 60 00 00 26 00 97 01 00 ... 9e 00` = map 96 (tavern interior, also used by ReMixed event 144 "Bar Master"), ENTD 407.

ENTD 407 (ENTD4 entry 23) units, unit id at +0x20:
Agrias (char 0x1E, unit 0x34), Mustadio (0x16, unit 0x22), Ramza (0x03, unit 0x03), NPC sprite 0x5E / name 0x5D (unit 0xA9, likely the barkeep),
three generic job 0x4A units (unit 0x80, 0x81, 0x82).

## IC side

- Event setup table in the exe at file offset 0x8EAE98 (same 0x18 layout; 713 records, room for 887). Record 159 is the
  entry of a vanilla chapter 2 battle (map 0x29, ENTD 0x115, rules key 50 -> scene 160): do not touch it.
- ENTD 407 is used by IC events 139-145, so it cannot be reused. Free ids: see the trigger section (470-511). OverrideEntryData.nxd (Key = ENTD id, Key2 = slot) can define the units without replacing the ENTD file.
- Text: an event's lines live in `nxd/text/scenario/scenario<key>.en.pzd`, where `<key>` is the ScenarioId row whose EventIds lists the event (355 of 356 events). Text IDs are global and unique; vanilla uses 300000-357600. This port uses 381590 + message number.
- Speaker values are voice/character codes (e.g. 1030100 Agrias ch.1); 31 vanilla lines have no Speaker, so unvoiced lines are fine.
- `event159.e` is a copy of `event000.e` because 159 is a battle (battles and stubs share that placeholder script).

## World-map trigger (IC)

- IC converted the PSX WLDCORE world conditionals into `EnhancedWorldEvent.nxd` (table id 199, TripleKeyed):
  Key = location (0-14 are the towns), Key2 = condition block, Key3 = step. Blocks are tried in Key2 order; the first block whose
  conditions all pass fires.
- Evaluator: RVA 0x343AF8 (modloader layout signature). It rebuilds the PSX u16 bytecode per block, then runs handlers from
  the table at RVA 0x684E90 (0x2C ops). Row -> bytecode: Type 1 -> `0001 Unknown10 list[0]`; Type 4 -> `0004 list[0]`;
  Types 32/33 use Unknown14/18; anything else (2, 3, 25...) -> `type` + the whole list.
- Handlers: 1 var == v, 2 var >= v (v read as u16), 3 var <= v, 4 character id present in the 54-slot roster,
  0x19 (25) play event [id, mode] (sets status |= 9).
- GetVar 0x1402332D8 / SetVar 0x140233368 / var op dispatcher 0x140242700 / var address 0x140242984.
  Vars < 0x80 are u32, 0x80-0x35F are 1-bit, 0x360-0x3FF are 4-bit. SetVar clamps var 0x2C (gil) to 99,999,999.
- ReMixed's trigger block (placed in all 15 towns):
  `0001 0094 0001` (chapter 4 flag; vanilla gates its ch.4 Goug sidequests on it) · `0002 002C C350` (gil >= 50,000) ·
  `0001 002E 0006` + `0001 002F 0016` (month 6, day 22 = Cancer 1; the calendar uses real month/day) ·
  `0001 00B6 0000` (not seen yet) · `0004` Lavian 0x78, Alicia 0x79, Agrias 0x1E, Mustadio 0x16 · `0019 009F 0002`.
- Event chaining: an event's follow-up word (built from setup record +0x12..+0x14) of 0 means "continue to event N+1"
  (vanilla world triggers point at empty stub events N that chain to the real scene N+1); 0x8000 means "back to the world map".
  ReMixed's `CD 80 00 00` writes 0x8000 for event 159 at runtime.
- Setup function: RVA 0x2FB7C8; var 0x27 holds the event id to play. Record fields: +2 map (byte), +3 weather/time nibbles,
  +7 ENTD, +0xD/+0xE copied to globals, +0x16 EnhancedBattleEvent key (0 for scenes).
- Records with a nonzero +0x16 are battles or stubs; their battle-event rules (EnhancedBattleEvent, keyed by +0x16) pick the
  next event. See the v0.1.0 test section for why the port uses new events 744/745 instead of 159.
- ENTD: IC has 713 event records; ENTD 458-469 are used by later events. Unreferenced: 470-511 (486, 494, 500 have override rows).
- Debug leftover: the battle-condition checker 0x1402391C4 forces var 0x27 from globals at RVA 0x2FF9E4C (flag) / 0x2FF9F4C (event id).

## Art the scene depends on

- Unit 0xA9 is a prop (the gift box): hidden, drawn beside Mustadio, carried to Agrias, erased. Sprite set 0x5E = ReMixed custom (5E.SPR).
- EVTCHR 0x85 (townsfolk poses, slot 1) is vanilla. EVTCHR 0x7A (slot 0: Mustadio anims 0x1F4-0x1FB, Agrias 0x1FC-0x1FF) is ReMixed custom art.

## WotL reference

- ISO `PSP_GAME/USRDIR/fftpack.bin`: u32 count (3968), u32 0x10, then count+1 u32 byte offsets from the pack start.
  File 21 = event archive (same size as IC's event_test_evt; only 9 records differ, all in the non-event region >= 512).
  WotL event text is compressed; file 43 holds item names including Tynar Rouge.

## v0.1.0 test (2026-09-24): crash

Triggered correctly, showed "Orbonne Monastery" (map 96's Map row has PlaceNameId -1), music played, black screen,
then an access violation at RVA 0xC7695 (per-frame update of a map-load object at render context +0x24280, data null).
Root cause found: every vanilla world trigger (63 of 63) starts a placeholder stub N with a battle-event key and a
confirm prompt; its rule `var 509 == 1 -> event N+1` starts the scene. And slot 159 is the entry of a vanilla chapter 2
battle (map 41, rules key 50 -> scene 160), so overwriting it was also wrong. v0.2.0 adds new events 744 (stub, shaped
like vanilla 464) and 745 (scene, like 465), appended to the setup table (887 slots, 713 used), with rules key 171.

## What the mod does (v0.2.0)

- Data (tools/build_data.py -> FFTIVC/data/enhanced): event744.e (placeholder stub), event745.e (the scene);
  scenario9159.en.pzd (ScenarioId 9159 [745] -> ScionFiles 2165); a 10-row trigger block ([744, 2]) appended to towns 0-14;
  EnhancedBattleEvent key 171 (var 509 == 1 -> 745); EventId 744 = 464's (confirm 7:139), 745 = 465's (Unknown4 = 745);
  Battle rows 744/745; ENTD 470 = ReMixed ENTD 407 minus the gift box.
- Code (Mod.cs): appends setup records 744/745; hooks the variable dispatcher 0x140242700 (via the event interpreter's call site,
  since an identical copy exists at 0x1402EC038). On `ADD var 0x2F9, 1` it adds one item 238 (Septieme Sens) and
  multiplies Agrias's raw HP/MP by 1.1, unless var 0xB6 (scene seen) is already set.
- Party inventory: 0x105 count bytes at RVA 0x11A7C00, directly before the roster (RVA 0x11A7D10).
- Stand-in art: gift box removed; EVTCHR 0x7A not loaded and its animations (0x1F4-0x1FF) replaced by idle (0x0002).
  `convert_event.py --real-art` keeps ReMixed's original instructions.

## Still open

- CallFunction 0x14 near the end: kept as-is; confirm it does the same thing in IC.
- Speaker codes for Mustadio / ch.4 Agrias / Ramza.
- Whether the modloader serves a brand-new `.pzd` path, or needs a FileLists entry.
- Whether a brand-new ScenarioId row + scenario pzd is enough for IC to show text for event 159 (needs an in-game test).

## v0.2.0 test (2026-09-24): crash at the reward message

Scene ran through all dialogue, then crashed at RVA 0x136541 (rbp = text id 381619, message 29). DisplayMessage box style
is the high nibble of the type byte; ReMixed's "item received" box is type 0x63 (style 6), which vanilla IC never uses
(styles 0, 1, 7, 8, 9, F). IC resolves it to box slot -1 and writes outside its array. v0.2.1 converts unknown styles to
the vanilla centred narration box (type 0x09, layout bytes `00 00 00 d3 ff 00 00 0a 00` from event 2's prayer line).

## v0.2.1 test (2026-09-24): scene completes, reward works

- Reward log: raw HP 1,004,115 -> 1,104,527, raw MP -> 582,736 (x1.1). In game 215 -> 224 HP, 32 -> 35 MP: the boost scales only
  the raw (growth) part; equipment and other flat bonuses are unchanged. Same as ReMixed.
- Box type 0x09 (narration) has no window and closes by itself; speaker 5005000 is "Girl" in the Speaker table.
  The label comes from `Speaker-<lang>.nxd` (code -> Name; e.g. 5005001 "Narration", 1030600 Mustadio, 1030100 Agrias,
  1010103 Ramza; code 1 has no name). Lines can also override it inline with `<speaker="Name">`.
  v0.2.2: reward line in type 0x12 (plain window, no portrait, waits for input), speaker 1.
- v0.2.2 test: no more "Orbonne Monastery" title (it came from the direct-to-scene path). Type 0x12 shows the unit's portrait
  (Mustadio). v0.2.3: vanilla chronicle-narration window, as event 376 does it: `10 10 83 <id> FD 00 00..0D 00` (unit 0xFD =
  no unit), `E5 01 00`, then `51 03 FFFFFFFF 00 00` to close box 3 (box = low nibble of the type). Styles 8/9 open windows
  that stay until a ChangeDialog closes them.

## ENTD5 and the dormant War of the Lions events (2026-09-24)

- ENTD ids >= 0x200 come from fftpack file 892, `event_btlevt_bin_entrydata_add_ent.bin` (entry = id - 512, 0x280 each).
  Loader RVA 0x284098: for id >= 0x200 it allocates 0xC800 bytes (80 entries) and reads file 0x37C with that size, so ids
  512-591 are addressable; more needs both 0xC800 immediates patched. The file has 77 entries; unreferenced: 534 (Beowulf/Reis/
  Wiegraf), 535-549 and 586 (empty), 587/588 (chapter 1 casts).
- IC keeps WotL's event setup records 512-589 and 596-599 (maps + ENTD 512-533 in this file) but has no scripts, text, scenarios
  or triggers for them. Casts include Balthier (514/528/530), Luso (515/517/531), Ovelia/Delita (512/516/518/521), Beowulf/Reis.
- **ENTD 527 is WotL's Agrias's Birthday cast**: Agrias u34, Mustadio u22, Ramza u03, gift box u0xA9 (sprite set 0xA9), townsfolk
  u80-82: the same unit ids as ReMixed's script. Records **578 (stub, rules key 163, no rows yet) -> 579 (scene, follow 0x8000)**,
  map 96, music 0x26, +4 = 1. EventId 578/579 are plain ('0:0').
- IC's event sprite archive has 143 sheets; 0x89-0x8E are WotL additions. 0x8E is 91% byte-identical to ReMixed's custom sheet
  0x7A (the Mustadio/Agrias poses), so it is very likely the original art.
- (Superseded, see "WotL event storage" below: file 21 uses 0x2800-byte records, so every WotL script is there.)

## v0.3.0 (2026-09-24): moved onto WotL's own events 578/579

- Trigger -> [578, 2]; EnhancedBattleEvent key 163 (var 509 == 1 -> 579); EventId 578 = 464's (confirm 7:139), 579 = 465's
  (Unknown4 = 579); ScenarioId 9159 [579]; scripts event578.e (placeholder) and event579.e.
- No exe records added and no ENTD file shipped: WotL's records 578/579 and cast ENTD 527 are used as they are. Mod.cs only
  checks them (map 0x60, ENTD 527, stub rules key 163, scene follow-up 0x8000).
- Art: the gift box is back (unit 0xA9 of ENTD 527; sprite set 0xA9 -> fftpack 890 unit_psp/spr_dst_bchr_sword_m_spr.bin,
  per the spriteset tables at RVA 0x784BE0/0x784690); slot 0 loads WotL sheet 0x8E instead of ReMixed's 0x7A.
  Sheet 0x8E vs ReMixed 0x7A: identical except 120 bytes in the frame table and the last 0x1000 bytes (probably palettes).
  `convert_event.py --standin` keeps the older fallback (no box, idle poses).

## v0.3.0 test (2026-09-24): crash at scene start

Black screen, music, stutter, crash at RVA 0x217172 (in 0x216EB4): a null row from nxd table 0xAE = CharShape, keyed by the
unit's sprite set (unit +0x0A). Vanilla CharShape stops at 0x9E; 0x9F-0xA8 come from the WotL Characters mod; nothing covers
the gift box's 0xA9. Sprite type table (file 0x672300, 4 bytes per sprite set: SHP, SEQ, flying, height): 0xA9 is SHP/SEQ 0
(humanoid). v0.3.1 adds CharShape 169 = vanilla 0x83's row. Note: `Game Files/nxd.sqlite` was built with the WotL Characters
mod merged in, so don't treat it as vanilla for CharShape.

## v0.3.1 test (2026-09-24): gift box works, poses mangled; no confirm prompt

- The gift box (sprite set 0xA9 + CharShape 169) draws and moves correctly.
- Agrias/Mustadio were drawn as scrambled pieces of their own sprites most of the time. Sheet 0x8E is byte for byte ReMixed's
  0x7A (same frame table and pixels; IC adds palettes at 0x7E0-0x860 and zero padding where ReMixed has 0xFF), and vanilla
  uses the same animation ranges (slot 0 = 0x1F4+, slot 1 = 0x2xx), so the likely cause is IC's enhanced renderer not
  drawing WotL-only event sheets (0x89-0x8E) correctly. Also: WotL's cast uses sprite sets 0x34 (battle_aguri, Agrias) and
  0x22 (battle_musu, Mustadio) where ReMixed's used 0x1E/0x16. v0.3.2 drops sheet 0x8E and uses idle poses (single change,
  to isolate the cause).
- The SortieConfirm (7:139) on the stub never shows a prompt: the scene starts on arrival. Fine as is.

## Event sprite sheet textures (2026-09-24)

Enhanced mode draws event sprite sheets from `system/ffto/g2d/tex_NNNN.bin` (raw 512x512 4bpp). The WotL-only sheets map to
tex_1279 (0x8E), tex_1280 (0x8C), tex_1281 (0x8B), tex_1282 (0x89), tex_1283 (0x8D), tex_1284 (0x8A); vanilla IC ships
those as copies of sheet 0x36 (hence the scrambled poses). "FF Tactics Mobile Sprites" (fftivc.texture.mobilesprites,
Spikedrose) has the real ones. v0.3.3 ships tex_1279 (research/art) and loads sheet 0x8E again. The mobile sprites mod is
not enabled on the user's install, so this mod's copy is the one used.
- v0.3.3 test: all poses correct with tex_1279. The type 0x83 window closes by itself (does not wait). v0.3.4: type 0x12 on
  unit 0xFD (no unit; vanilla event 417 uses 0x11/0x12 on 0xFE/0xFD), then close box 2.
- v0.3.4 test (2026-09-24): works end to end. Reward line waits for input, no name plate, empty portrait frame (acceptable).

## Status after v0.3.4

Working: trigger (Cancer 1, chapter 4, gil >= 50,000, Agrias/Mustadio/Lavian/Alicia), WotL events 578 -> 579, full dialogue,
gift box, special poses (tex_1279), reward window, gil charge, Septieme Sens +1, Agrias raw HP/MP x1.1, return to map.
Open: real Tynar Rouge item (needs the item-table expansion); only English text (scenario9159.en.pzd); permission from
Spikedrose before releasing with tex_1279; next research step is how the WotL ISO stores event scripts/text for events >= 512.

## WotL event storage (2026-09-24)

**Scripts and text**: fftpack file 21 (`research/TEST_wotl.EVT`) is TEST.EVT with **0x2800-byte records** (744 events),
not PSX's 0x2000: that is why slots >= 512 looked like junk before. Each record is the PSX layout (u32 text pointer,
script, text). Scripts use IC's classic opcode lengths (`evlen_ic.bin`; all 513 real events parse):
`python tools/evdis.py research/TEST_wotl.EVT:579 wotl`. Text is the PSX encoding, **not compressed**; the only
difference is 0x95 = space (PSX 0xFA). Battle events repeat their battle's whole text block in every record.
WotL 579 = ReMixed 159's scene (same units, same sheet 0x8E); it ends `ZERO/ADD 0x1B8`, `ZERO/ADD 0x2F9` (seen flag).

**Setup records**: WotL's table is in BOOT.BIN at 0x2EE184 (712 records); IC's records 512-599 are byte-identical.
Chains (+0x12 next id, +0x14 flags): 522->523, 528->529, 553->554, 566->568; 590/591/593/595 are used by IC itself.

**World triggers**: PSP_GAME/SYSDIR/BOOT.BIN (plain ELF), `tools/wotl_triggers.py`. 0x31E698: per-location u16
offsets (44 locations, IC Town keys) to 0-terminated lists of block offsets, all relative to 0x31E698. Blocks from
0x31E8E2: u16 op + u16 args, conditions then one action op. Ops = IC EnhancedWorldEvent Type: 01 var== (var,val),
02 var>=, 03 var<=, 04 inParty (char), 0E gil>= (1 arg), 10/11 date>=/<= (month,day), 19 play (event,mode),
1A play2 (8 args), 1D/20-24/2A other actions, 1E (3 args), 1F/29 (2), 2B (1). Vanilla PSX-era triggers (e.g.
Gollund vars 153/166/167 -> 464) also sit in fftpack file 775, which has none of the WotL blocks.
Battle-event rules (IC EnhancedBattleEvent) are also in BOOT.BIN (~0x2F39D4, e.g. `01 1FD 1 19 <N+1>`); IC has rows
only for keys 169/170, none for WotL keys 146-168.

WotL-only story events (IC has records + ENTD 512-533, no scripts/text/triggers/rules):
| Events | Scene | WotL trigger |
|---|---|---|
| 512-515 | Delita & Ovelia at the falls, Northern Sky scouts (battle) | none found (story-driven?) |
| 516-517 | Wiegraf mourns Milleuda; Loffrey | Balias Swale, var 0x6E == 29, flag 0x2EE == 0 |
| 518-524 | Balthier: alliance battle, then recruitment (523/524) | Dorter, 0x6F >= 13, 0x2F0 == 0, 0x2FA == 1, 0x2FB == 1 |
| 525-530 | Luso: rescue battle, then recruitment (529/530) | Zeklaus Desert, 0x6E == 37, 0x2EF == 0 |
| 531-534 | Ovelia's prayer, assassin, Delita (battle) | Yardrow, 0x6E == 39, 0x2F1 == 0 |
| 535-536 | Delita & Ovelia, "Tietra..." (grass whistle) | Bervenia, 0x6E == 43, 0x2F2 == 0 |
| 537-542 | Argath at the Orbonne undercroft (battle, map 127) | none found |
| 543-547 | Cletienne & Meliadoul, "the marquis has fallen" (battle) | Dorter, 0x6E == 51, 0x2F3 == 0, Meliadoul in party |
| 548-551 | Agrias visits Ovelia ("My lady."), 550 with Lavian/Alicia | Zeltennia, 0x6F >= 16, Agrias, 0x2F4 == 0 |
| 552-569 | Beowulf & Reis vs Celebrant Bremondt: Lionel fields, gate battle, castle battle, rescue | Lionel Castle, 0x6F >= 16, 0xAC == 1, 0x2FD == 1, 0x2F8 == 0, Beowulf + Reis |
| 570-577 | Agrias & Orlandeau vs Northern Sky deserters (battle) | Brigands' Den, 0x6F >= 16, Agrias, 0x2F6 == 0, 0x2FC == 1 |
| 578-579 | Agrias's Birthday (ported) | 8 towns, 0x6F >= 13, Agrias, Mustadio, 0x2F9 == 0, gil >= 50000, 6/22, Lavian, Alicia |
| 580-581 | Gariland tavern patrons gossip about the menu | Gariland, 0x2FE == 0, 0x6E >= 3 |
582-589 and 596-599 are placeholder records (generic 849-byte script, junk text). 600-743 are the multiplayer
Rendezvous missions (IC has their records; ENTD 550-585 are in entrydata_add_ent). None of the 512-581 text exists
in IC's scenario files or in WotL events 0-511.

## v0.4.0 (2026-09-24): Balthier (WotL events 518-524)

Pieces and where each came from:
- **Battle rules** (EnhancedBattleEvent): WotL's table in BOOT.BIN at 0x2F2494 (`tools/wotl_rules.py`): u16 offset per
  rules key to a 0-terminated list of block offsets, all relative to 0x2F2494; blocks are u16 op + args. Ops map 1:1 to
  IC rows (checked on key 41, whose IC rows equal WotL's): 01 (var,val) -> UnknownC/Unknown14=[val]; 04/0B (unit) ->
  CharaControlId; 05/06/08/18 (unit,val) -> CharaControlId/Unknown14; 16 () ; 19/1C (event) -> Unknown10.
  Key 148: 509==1 -> 519; 0x7D==0, 0x80==0, [4 A2][5 A2 1][4 3][5 3 1][0B A2] -> 520; 0x80==0, [4 A2][6 A2 0] -> 521;
  0x80==0, [16] -> 522. Key 149: 509==1 -> 524.
- **Victory condition**: DisplayConditions' first argument is 8 + BattleObjective row (nxd table 0x2F; event 18 passes
  10 = "Protect Argath!"); the handler stores type-8 in the global the objective reader uses (RVA 0xD3AD54, read at
  0x1EB611). 519 passes 8 = "Defeat all enemies!", so no data is needed.
- **EventId**: Unknown4 = the battle's first event for in-battle events (vanilla 34/35 -> 34, 129-135 -> 129);
  Unknown2B = 1 on mid-battle talk events; the battle start has SeadStateParameterId 2. The stub's
  SortieConfirmUnionId '7:N' points at a SortieConfirm row (pre-battle panel: MapId, max-units/threat UI ids);
  row 139 (used for the birthday) is a non-battle one (MapId 0), which is why that prompt never showed.
  New row 375 = copy of 11 (vanilla Dorter battle, same map 32).
- **Scripts** (`tools/convert_wotl.py`): only 0x10/0x51 differ in length; messages are split into pages at WotL's blank
  lines (IC pages long speeches with chained ChangeDialogs). Recruitment: IC moves the join window
  (`78 07 3C`) from WotL's dark-screen block to after the closing fade (`3E ...; E5 0C 00; F1 3C 00; 78 07 3C; E5 38 00`),
  in every vanilla recruitment (170, 213, 298, 374); the converter does the same. 0xA2 is the vanilla party check.
  In-battle speech type 0x70 still works in IC with a plain wait (402 uses); IC's 0xF0 + EB paging is only needed for
  multi-page battle messages (the converter refuses those for now).
- **Text**: WotL codes: DA 68 = em dash, D1 29 = '*', 0x46 = ':'. Speaker row 1162000 "Balthier" added to speaker.en.
- **Cast**: ENTD 514 (Balthier 0xA2 sprite/job/name, lv 35, Glacial Gun/Thief's Cap/Black Garb/Germinas Boots, guest;
  generic enemies), ENTD 528 (Balthier with the join-after-event flag 0x10, Ramza). Name, Sky Pirate job, CharShape 0xA2
  and portrait (face 0x6C -> wldface 163) come from the WotL Characters mod (now a dependency). Sheet 0x8A = tex_1284.
- **Trigger** (Dorter, town 9): WotL's is 0x6F >= 13, 0x2F0 == 0, 0x2FA == 1, 0x2FB == 1, play 518 mode 1. Nothing in WotL's
  scripts, world triggers, battle rules or BOOT.BIN immediates sets 0x2FA-0x2FD, so the port drops 0x2FA/0x2FB.
  IC keeps var 0x6F (story milestone; 13 at event 298) and never uses 0x2EE-0x2FE. 524 sets 0x2F0 (seen), 0x1B4/0x1B5
  (WotL chronicle entries), 0x3F5, clears 0x2E7/0x2E8 (none used by IC scripts).

## Moved into WotL Characters 1.4.0 (2026-09-24)

The Agrias's Birthday mod (fftivc.events.agriasbirthday, last 0.4.0) is folded into WotL Characters (H:\FFT\WotLCharacters):
tools/ and research/ moved as they were, the reward code is AgriasBirthday.cs, BuildLinked.ps1 runs tools/build_data.py
and now publishes to Mods/fftivc.npcs.wotlcharacters (it used to publish to Mods/WotLCharacters). The mod's hand-made
nxd tables stay the source of truth; build_data.py reads the mod's charshape.nxd back and only adds row 169 (the export
tables have no primary key, so rows are deleted then inserted, not INSERT OR REPLACE). The old project and deployed mod
are in H:\FFT\Archive.

### Balthier v0.4.0 test: crash when the battle started (RVA 0x2FC2E3 in the setup routine 0x2FB7C8)
The setup routine reads the battle-event rules; a rule's CharaControlId field is a key of nxd table 0xDA
(CharaControlId), whose Unknown8 byte (row +8) is the actual unit id. Vanilla rows: 0-52, 100-103, 128-139, 256,
500-509, 1000-1006; none for Balthier's 0xA2, so the lookup returned null and `movzx ecx, byte [rax+8]` faulted.
Fix: CharaControlId row 162 -> 162. Any ported battle whose rules name a WotL-only unit needs such a row
(the birthday's rules name no units, so it never hit this).

### Balthier retest (1.4.0): crash at RVA 0xFB6C8 (function 0xFB65C)
The CharaControlId fix worked; the next lookup was nxd table 0x6D = EntryNo, keyed by ENTD id (514), reading
SortieConfirmId at +8. Vanilla EntryNo has rows 0-511 only (one per vanilla ENTD). Story battles: UnknownC [0, N, 0]
(N 200 early -> 5,600-9,000 in chapter 4, probably war funds), Unknown14 [130,145,130]; scenes [] / [130,130,130].
Added 514 = [0,5900,0] and 528 = scene row. Agrias's 527 has no row and works: scenes (kind 1/2) take the other
branch (table 0x9C). EntryArea already has 514.
Retest: same crash. The rows were added (modloader log: "2 added rows for nex table 'entryno'") but the lookup
(0x1403D3AE8) has three modes for single-keyed tables: header byte +0xA (use_base_row_id) set -> plain array,
row = key - header base id (+0xC), bounded by the last row's key and the row count (setup 0x3D3F3C); else a sparse
pointer array over min..max; else a hash. EntryNo is a plain array, so 514 after 511 sat at position 512 and the
lookup ran past the end. **Rule: tables with use_base_row_id must stay contiguous** (EntryNo, CharShape...).
Now every WotL ENTD 512-591 gets an EntryNo row (scene values unless listed).

## 1.4.1 (2026-09-24): Balthier works end to end; text paging; his real trigger chain

- User test: Balthier's battle and recruitment play through. One page overflowed IC's three-line box (219 chars).
  convert_wotl.fit splits pages over 150 chars (99% of IC's own lines are <= 146) at sentence ends; the birthday
  converter (convert_event.py) now pages the same way (extra pages get ids from TEXT_ID_BASE + 200).
- **Tavern rumors** (per the wiki: after Meliadoul at Bervenia, read "Rash of Thefts" at Gollund, then "A Call for
  Guards" at Dorter):
  - Gossip (nxd 0xB5, use_base_row_id): IC rows 0-21 = WotL rumors 0-21; IC's 22 is its own "At Battle's End".
  - Availability (0x36F53C, list built by 0x36EE50 over ids 0-63): UserSituationID check if set; UnkBool2C -> always;
    else town bit (0x4000 >> town) in the u32 mask table at RVA 0x7BE620 (IC entries 22+ are 0) AND var 0x2D1 + id != 0.
  - Reading (0x19D548): if Unknown4 != 0 and counter[Unknown4] < Unknown8: counter = Unknown8 (0xFF660, the same
    counters IC's event opcode E9 sets; counter 0 = main story, e.g. `E9 0, 690`; the Beowulf line is 2), then
    runs Unknown14/Unknown1C pairs: type 102 sets base = value * 10, else SetVar(type + base, value).
  - WotL stores these pairs at the start of each rumor body as `F5 type F6 value` (fftpack 771 msg n; titles fftpack
    43 msg 4130 + n); tools/wotl_rumors.py -> research/wotl_rumors.json. Rash of Thefts: 0x2FA = 1 and unlock
    WotL 0x2E8 (A Call for Guards); A Call for Guards: 0x2FB = 1; Disorder in the Order: 0x2FC; Lionel's New Liege
    Lord: 0x2FD. WotL event 536 (Delita/Ovelia "Tietra" at Bervenia, story var 0x6E == 43) unlocks Rash of Thefts
    (0x2E7) and Lionel's New Liege Lord (0x2EA); 549/551 unlock Disorder in the Order (0x2E9); 524 clears 0x2E7/0x2E8.
  - Port: rumors take IC ids 23+ (WotL 22 -> 23 ...), so WotL unlock vars 0x2E7-0x2EA are renumbered +1 in converted
    scripts and rumor actions (RUMOR_VARS). Counter 3 (unused by IC), stages 10/20. Town masks patched in Mod.cs.
  - WotL text codes added: DA 75 ';', 0x8D/0x8E '(' ')' (0x8D was wrongly '-').
- Bervenia scene 535/536 ported (cutscene: vanilla cast/sheets, WotL map 126 which IC ships). Chapter 4 speakers:
  Delita 1020102, Ovelia 1030701 (IC events 376/429).

## 1.4.2 (2026-09-24)
- Bervenia scene 535/536 now triggers at story var 0x6E >= 43 (WotL: == 43), so saves past that point can still
  reach it, the rumors and Balthier (user's call).
- Spikedrose gave permission to use/redistribute the Mobile Sprites art.
- **Item icons** (for the item-table expansion): IC's enhanced icons are one texture per item id:
  ui/ffto/icon/equip_item/texture/ei_NNN_uitx.tex (100x100, painted HD; 254/255 are 192x192/placeholders) and
  equip_item_s/texture/ei_s_NNN_uitx.tex (48x48 pixel art), each + textureparts/*.utexpt (the texture path, 3-digit
  ids keep lengths). Vanilla has 0-260; 256-260 are IC's DLC items (ids 0x100-0x104), so WotL's 0x100-0x139 need new
  ids. All BC7 (DXGI 98). tools/item_icons.py converts Spikedrose's Mobile item set (48x48) into
  research/art/items/{small,large}/wotl_<id>.tex (large = 2x nearest on 100x100), via tools/png2bc7 (BCnEncoder from
  the modloader) + FF16Tools img-conv; install(out, {wotl id: icon number}) writes them into FFTIVC when ids exist.
  Header bytes 6/0x29 differ from vanilla (0x0B/0xFF vs 0x14/0xC3) as in the mod's working face textures.

## 1.4.3 (2026-09-24): Bervenia scene and rumor fixes (user test of 1.4.2)
- **Map**: IC's HD backgrounds (bg/meshes/map_NNN_mesh.bin) stop at map 116; WotL's maps 125-127 exist only as classic
  data, so enhanced mode drew scene 536 over empty space. Stand-in: map 20 (Zeltennia Castle Keep, Map.Unknown8 =
  PlaceNameId 12000; IC's own Delita/Ovelia scene 429; 9x10 tiles, terrain from the classic mesh's pointer at +0x68).
  build_data map_map/tile_map rewrite ChangeMap and WarpUnit/WalkTo; Mod.cs _eventMaps patches setup record +2 (map).
- **Missing special poses**: every vanilla enhanced event texture (g2d.dat, 143 sheets via the exe table at file
  0x7136B4 - 0x89*4) is 113,152 bytes = rows 0-441 of 512; WotL drew extra frames below that on existing sheets
  (0x1E Ovelia's grass whistle, 0x45 Delita's). Classic sheets (event_evtchr, 0x7800 each) are identical to WotL's.
  Mobile Sprites' textures are full 512 rows; the mod now ships tex_1179 (0x1E) and tex_1219 (0x45). The user does
  not run Mobile Sprites (Reloaded AppConfig EnabledMods: modloader, WotLCharacters, bluemage).
- **Rumor picture**: the rumor screen shows a picture iff Unknown4 > 0 and Unknown8 > 0 (0x1A0472), from IconId via
  Icon row 21 'base/textureparts/base_%02d_uitx' (town art; Town.Unknown1C = a town's). Read actions also need
  Unknown4, so quest rumors always have a picture: Rash of Thefts uses Gollund's (11), A Call for Guards Dorter's (14).
- **Second rumor not unlocking**: the save showed 0x2F2/0x2E8 set but 0x2FA/0x2E9 not. Vanilla event 461 sets
  counter 3 to 10 (E9), so counter 3 was already at stage 10 and the actions were skipped. IC scripts use counters 0-3;
  the rumors now use 12. Save vars: the event variable block (u32 vars, bit flags from +0x200) sits at 0x8798 in
  resume_en0N_main.sav (FF16Tools unpack-save of autoenhanced.png); found by plausible 0x6E/0x6F/date values.

## 1.4.4 (2026-09-24)
- User confirmed the rumor chain works (Rash of Thefts -> A Call for Guards).
- Per the user's review of WotL footage: Delita's poses in 536 really are that stilted, so tex_1219 (sheet 0x45) is no
  longer shipped (IC's own texture); Ovelia's tex_1179 stays. The second part of 536 moves to map 2, Lesalia Castle
  Postern (first Zalmour battle, event 226), 10x11 tiles, so WotL's own positions (Delita at 9,2) are kept; the
  opening stays on map 20.

## 1.4.5 (2026-09-24): location title
- User: 536 looks right on maps 20/2, but opened on a long black screen. It starts with WotL's ShowMapTitle (0x91,
  `00 00 01`), which IC removed from every enhanced script and replaced with its own **E7 <PlaceName id u32>**
  (e.g. event 331 `F1 5A00, E7 1290` = Zeklaus Desert; 154 `E7 1010` Royal City of Lesalia), usually after
  `F1 5A00` and before the Reveal; event 8 also brackets it with `AF 0` (unknown). convert_wotl turns 0x91 into
  E7 in place (group option title); 536 shows Zeltennia Castle (1060), a guess: WotL named its map 126.
- 1.4.5 test: the black pause is now short (the dead ShowMapTitle and its wait are gone), but **E7 showed no title**.
  Placed at the very start (offset 1) it runs before the map/screen is set up; every IC use is later, after
  setup and `F1 5A00`, right before the Reveal (4D). Untried: move E7 to just before the Reveal (without IC's
  90-frame wait, which would bring the black pause back). E7's handler is not in the interpreter's DB-E5 or E8-ED
  compare chains (0x23E9C1 / 0x23EE39); not traced further. The user accepted the outcome as is.
- 1.4.6: the title (E7) now goes right before the scene's first Reveal after the ShowMapTitle (536: offset 0x5D),
  with no added wait; the build stops if a ShowMapTitle has no later Reveal. Awaiting the user's test.
- 1.4.6 test: still no title. Cause: **E7 takes a Caption id, not a PlaceName id**. Caption (nxd, 13 rows, keys
  0,3,50,110,120,1000,1010,1070,1110,1200,1210,1290,1300) has UnionId 113:<PlaceName> (the layout's comment has
  113/115 swapped: 113 resolves to PlaceName, 115 to something else for 110/120) - e.g. 1200 -> 12000 "Zeltennia
  Castle Keep" (IC event 201, map 20), 1290 -> 12100 "Zeltennia Castle" (event 331). 1.4.7 uses 1200. New titles
  need a Caption row (caption.nxd CRC 54135C38 in the pack).
- 1.4.7 test: title displayed.

## 1.5.0 (2026-09-24): Luso (WotL events 525-530)
- 525 stub (rules key 150, Zeklaus Desert map 76) -> 526 battle start (DisplayConditions 0x30 = objective 40) ->
  [527 Luso KO -> game over, 528 victory -> 529] -> 529 stub (key 151) -> 530 recruitment (party check A2, join
  window moved as IC does). Casts ENTD 515 (Luso 0xA3 lv 25 + 6 monsters, sprite set 0x82) and 517 (Luso with the join
  flag, Ramza as sprite 0x02 = chapter 3). Sheet 0x8B -> tex_1281 (Mobile). Speaker row 1163000 "Luso"; Ramza (unit
  0x02) speaks as 1010103. CharaControlId 163, EntryNo 515 = [0,5700,0] (late chapter 3), SortieConfirm 376 = copy of
  13 (the Zeklaus Desert panel, MapId 76).
- WotL window: story var 0x6E == 37, which events 255 (37) -> 260 (38) span: late chapter 3 (chapter 4 = event 298,
  0x6F = 13). Port: 0x6E >= 37 (as Bervenia), so on a chapter 4 save Ramza shows his chapter 3 sprite in 530.
- BattleObjective rows 35-68 are WotL's, unnamed in IC; WotL's objectives were images, so names are written by hand
  (group option objectives): 40 = "Protect Luso!" (IsProtectionMission already 1). vanilla battleobjective.en.nxd
  CRC EA27F2E1.
- 1.5.0 test: Luso's battle, post-battle scene and recruitment work. No prompt before the battle, which matches
  vanilla: world step 0x2482F8 -> trigger evaluator 0x343AF8 -> 0x2479A0 (table 0x9C, union type 0x121: continuous
  battles) or 0x2477C8, which looks up the stub's sortie row (0xFB65C: EventId union 7:<id> -> SortieConfirm, table
  0x36) and shows the panel only if SortieConfirm.Unknown2C != 0. Every vanilla story-battle stub's row has 0 (story
  battles start on arrival); the 196 rows with 1 are the battlegrounds' random-battle rows (no EventId uses them).
  Setting Unknown2C = 1 on rows 375/376 would add a prompt.

## 1.6.0 (2026-09-24): Ovelia's prayer at Yardrow (WotL events 531-534)
- **Setup records** (BOOT.BIN 0x2EE184, 0x18 each; the table is keyed by the record's own u16 id, not by position):
  531 stub (rules key 152), 532 scene + battle start, 533 Ovelia falls (game over), 534 victory scene (flag 0x80:
  world map after). All map 45 (Yardrow), ENTD 516. Rules 152: 509 == 1 -> 532; 0x80 == 0, [4 0C][6 0C 0] -> 533;
  0x80 == 0, [16] -> 534. Trigger: Yardrow (7), 0x6E == 39 (IC event 270 sets 39), 0x2F1 == 0, play 531 mode 2.
- **Cast ENTD 516**: Ovelia (guest), Delita (+0x18 = 0x8C: player controlled; the only unit you move), two ninja
  Assassins (0x80/0x81, lv 22), the thrown blade prop (sprite set 0xA9). No formation: EntryNo stays [] (scene
  style), like vanilla's prologue battle ENTD 387 (preset player units); [0, N, 0] rows are the formation battles.
  The stub copies 464 (generic event SortieConfirm 7:139), not a battle stub's panel.
- **Paging outside portrait boxes** (convert_wotl): IC never pages speech bubbles (0x1x). It turns a multi-page
  bubble into the portrait box of the same slot (IC event 2's "Mayhap bowed heads..." is WotL's 0x11 bubble, IC's
  0x91 box + ChangeDialog) and closes it after the last page's wait. Multi-page in-battle speech (0x70) becomes
  IC's 0xF0 box: E5 01, EB <page> <next page> 00 00 ..., E5 01, EB <last> FFFFFFFF 00 00 (every EB in IC follows
  an F0 box).
- **Objective**: DisplayConditions 0x2C = row 36, named "Protect Ovelia!". Title: Caption 1300 (IC events 255/300
  on map 45). Speakers: Delita 1020101 / Ovelia 1030701 as IC event 255; new Speaker 1164000 "Assassin".
- **Textures**: 532 loads sheet 0x7C (tex_1263), a vanilla sheet with WotL frames in rows 442-511 (Ovelia's prayer
  poses). Mobile's sheets are redrawn (same layout/palette indices, ~60% of pixels differ), so tex_1263 and now
  tex_1179 ship as IC's own texture (g2d.dat: u32 index offset at +8, u16 count at +12, 16-byte entries: u32 offset,
  u24 size; entry data +4 == 2 -> zlib from +16) with only Mobile's rows 442-511 appended.
- **1.6.0 test**: Yardrow works, but in the battle the cursor and effects sat partly sunk into the ground (units moved
  fine). Setup record +4 is the time of day (setup function 0x2FB7C8: +2 -> var 0x33 map, +3 >> 4 -> var 0x30,
  +3 & 0xF -> var 0x23, +4 -> var 0x24). WotL's 531-534 have +4 = 1 (night); IC's own map-45 records (254/255,
  299/300) have 0. The classic GNS of map 45 lists only states 0x00/0x10 (bit 7 = night); vanilla night records
  (+4 = 1: 153, 169, 173, 248, 250, ...) are all on maps with 0x80/0x90 states (11, 93, 14, 56). WotL's PSP data
  must have added a night state IC lacks. **1.6.1**: Mod.cs `_eventRecords` (generalised from `_eventMaps`: event,
  record offset, from, to) sets +4 = 0 on 531-534. Untested.
- **1.6.1 test**: daytime did not help. The cursor stays at one height (the Height readout never changes) and no
  grid tiles show while moving or targeting. **Real cause**: IC's HD map meshes (bg/meshes/map_NNN_mesh.bin,
  "FFTOMESH") carry a `GT_n_panel_ui` object on every map IC fights on (every vanilla battle's map has one); maps IC
  uses only for scenes (0, 1, 4, 8, 9, 11, 14, 15, 18, 20, 21, 23, 24, 26, 33, 37, 38, 41-43, 45, 46, ...) have none.
  Map 45's classic data is complete (terrain, and polygon -> tile tags on 142 polygons), so units move correctly.
  Also: map 45 is PlaceName 14500 "Zeltennia Castle - Chapel Ruins" (Caption 1300), not Yardrow: the scene is an
  interlude triggered at Yardrow, as IC's own 254/255 (Dorter trigger, map 45) is.
- **1.6.2**: night restored (the +4 patch removed; `_eventRecords` kept as the general record patch). Group renamed.
- **TODO (user: build later)**: give map 45 a panel_ui battle surface generated from its classic terrain.
  FFTOMESH notes so far (map_076): "FFTOMESH" + u32 map id + u32 1 + 4 x u32 0x1000 + u32 0x2000; object names in
  0x20-byte slots from 0x30 ("model", "GT_0_map", ..., "GT_8_panel_ui"); at 0x430: u32 object count (14), then
  counts 0x6C4, 0x41A, 0, 0, 0xADE; from 0x454 a u8 per-element object index table (1, 2, 3, ...). Next steps:
  decode vertex/index buffers and the panel_ui object's per-tile layout on a small battle map, then generate one for
  map 45 from its terrain (classic mesh pointer +0x68) and ship a modified map_045_mesh.bin.

## 1.7.0 (2026-09-24): Wiegraf mourns Milleuda; Loffrey (WotL events 516-517)
- Records: 516 stub (rules 147: 509 == 1 -> 517), 517 scene (flag 0x80). Map 77 = PlaceName 17600 "Lenalian Plateau",
  ENTD 513. Trigger: Balias Swale (39), 0x6E == 29 (IC event 190 sets 29), 0x2EE == 0, play 516 mode 2 (port: >= 29).
- Title: no Caption row pointed at 17600; Caption (nxd 13, 13 sparse rows, hashed: use_base_row_id 0) gets new row
  1310 = 113:17600 (build_data group key `captions`; research/vanilla/nxd/caption.nxd, CRC 54135C38).
- Speakers: Wiegraf 1070100 (IC's chapter 1-2 rows; 1070101/1070102 are the Templar), Loffrey 1070700.
- Text: WotL's hyphen emphasis (-is-, D1 1D) -> IC's <i>is</i> (IC uses <i> 17 times; it dropped some of WotL's
  emphasis, e.g. "What do you -think- we do with him?"). Also italicises Balthier's "And <i>you</i> say...".
- Sheets 0x0D (tex_1159) and 0x81 (tex_1271) have WotL-only rows: shipped as IC rows + Mobile rows 442-511, now
  built by tools/sheet_textures.py (also rebuilds 1179/1263 byte-identically).
- Open question: WotL-only scenes each set one of vars 0x1AB-0x1B8 (517: 0x1AD, 524: 0x1B4/5, 530: 0x1B2/3, 536:
  0x1AF, 549: 0x1B0, 551: 0x1B1, 569: 0x1B6/7, 579: 0x1B8; WotL event 90: 0x1AB/0x1AC, which IC's event 90 drops).
  No script or trigger reads them in either game (maybe a PSP-side feature); the ports keep them, harmlessly so far.

## 1.8.0 (2026-09-25): Delita and Ovelia at Zeirchele Falls (WotL events 512-515)
- Records: 512 stub (rules 146: 509 == 1 -> 513; 0x80 == 0, [6 0C 0] -> 514; 0x80 == 0, [16] -> 515), 513 scene +
  battle start (objective 7 "Protect Ovelia!"), 514 Ovelia falls, 515 victory (0x80). Map 83 = PlaceName 18200
  "Zeirchele Falls" (new Caption 1320). ENTD 512: Ovelia (guest), Delita (player controlled), 3 Northern Sky scouts
  (lv 8); no formation. Speakers Delita 1020101 / Ovelia 1030700 (IC event 190), new 1165000 "Northern Sky Scout".
  Sheet 0x7D (tex_1264) has WotL rows.
- **How WotL starts it**: no world trigger; WotL's record 195 (end of the Lionel Castle chain 191-195) chains to 512
  (+0x12 = 512, +0x14 = 0x81). Follow-up word per event (built at 0x2FBAD3 into the u16 array at RVA 0xD3F950):
  next = +0x12 | (+0x13 << 8, stored as << 10), | +0x14 << 8: 0x100 = play next now, 0x8000 = world map. Readers:
  0x2FB872 (setup: preloads the next record's +0xD/+0xE), 0x23EC1D (event end: tests & 0xF300), 0x212651.
- **CallFunction 06 / var 0x55**: WotL ends hand-over events with (ZERO/ADD 0x55 = next event) + CallFunction 06
  (8, 195, 233, 236, 241, 275, 283, 290, 303, 309, 313, 317, 366, 389, 394, 445, 450, 515, 542, 553, 560). IC never
  uses CallFunction 06; it sets 0x55 itself plus E9 counter 0 (story), and gives those records next + 0x80 (IC
  195: next 196, 0x80; also 233, 236, 241, 275, 283, 290, 303, 309, 313, 317, 366, 389, 394). 0x55 is not
  monotonic (303 sets 200 then 104, ...). convert_wotl drops CallFunction 06 and every write to 0x55 (the ports
  play from triggers, maybe long after WotL's moment).
- **Port**: IC's 195 left alone (restoring the chain would need IC's next-196 pointer moved to 515, wrong when the
  interlude plays late). Zeirchele Falls (35) triggers: [0x6E == 29, 0x55 == 196, 0x2ED == 0] (WotL's moment,
  between 195 and the Lionel battle; may never open if IC's next-196 starts the battle directly) and
  [0x6E >= 30, 0x2ED == 0] (after IC event 201). 515 sets 0x2ED (set_flags; free in both games).
- Next: 542 (Argath) writes 0x55 = 200 then 195, so the Argath undercroft scenes may also sit in a story chain.
- **STATUS (user, 2026-09-25)**: 1.8.0 Zeirchele Falls is UNTESTED (user can't test yet). **TODO after that test**:
  restore WotL's original linkage (IC event 195 chains straight into 512 as in WotL), i.e. work out what IC's
  record-195 "next 196 + 0x80" pointer does at runtime (readers 0x23EC1D / 0x212651 / 0x2FB872) and carry it past
  the interlude so the Lionel battle still follows; keep a trigger only for saves already past 195.

## 1.9.0 (2026-09-25): Argath at the Limberry undercroft (WotL events 537-542) - UNTESTED
- Location: Limberry, not Orbonne. WotL's linkage: Limberry sequence 385-394 (Limberry Castle trigger, 0x6E == 49);
  394 ended with 0x55 = 537 + CallFunction 06; 537 stub (rules 154) -> 538 battle; 542 (Argath falls) set
  0x55 = 200 + 195 = 395 (ADD accumulates: "200 then N" writes are 200 + N) -> 395, the undercroft battle. IC's 394
  points at 395 directly (next + 0x80); 390/395 use EventId union 289 (ContinuousSortieConfirm, continuous battles).
  CallFunction 06 + 0x55 targets are started by the record pointer: 196, 237, 242, 395 etc. have no world triggers.
- Rules 154: 509 -> 538; [0x7D 0, 0x80 0, A5 & 3 on turn, 0B 3] -> 539; [0x7D 1, 0x7E 0, 0x80 0, ..., 0B A5] -> 540;
  [0x80 0, 0x7F 0, 8 A5 20 (HP <= 20%?), 5 A5 1] -> 541; [0x80 0, 6 A5 0] -> 542. Objective 37 -> "Defeat Argath!".
- Cast ENTD 519: Argath (sprite/job 0xA5 Deathknight, lv 40; the mod's job 165, CharShape 165, portrait) + five
  undead (sprite 0x82, job 0x9A); party formation: EntryNo 519 = [0,7000,0] (between ENTD 456 5,900 and 457 8,000);
  SortieConfirm 377 = row 11 with MapId 16 (IC has no rows for Limberry maps); CharaControlId 165.
- Map 127: no HD and no classic data in IC. Stand-in map 16 Limberry Castle Keep (10x13, all positions walkable,
  has panel_ui); Mod.cs _eventRecords patches +2 of 537-542. No ShowMapTitle in these scripts.
- var 0x3CC = Argath's story stage (25: 1, 58: 2, 117: 3, 542: 4); no IC nxd/exe reads found; kept, and used as the
  trigger's not-fought test. Trigger: Limberry Castle (4), 0x6E >= 50 (IC 427), 0x3CC == 3, play 537 mode 1.
- Speakers: Argath 1100400, Ramza 1010103, new 1166000 "Mysterious Voice" (unit 0x84's first line).
- **TODO (user)**: restore WotL's linkage (394 -> 537 ... 542 -> 395) after testing, like Zeirchele Falls.
- User's save (2026-09-25): 0x6E 53, 0x6F 16 (past both chain points).
- **1.9.1**: stand-in changed to map 66, Fort Besselat - South Wall (user matched it to WotL's map 127): 9x13, all
  positions in bounds and walkable (heights 2-12), panel_ui present. SortieConfirm 377 MapId 66. Still untested.

## 1.10.0 (2026-09-25): Cletienne and Meliadoul at Dorter (WotL events 543-547) - TESTED OK (user, 2026-09-25)
- Records: 543 stub (rules 155), 544 scene + battle start (objective 19 "Defeat Cletienne!"), 545 talk on
  Meliadoul's turn, 546 Meliadoul falls (0x82 = game over), 547 Cletienne <= 20% HP (0x80): victory, sets 0x2F3 and
  0x3EB = 1 (IC event 457 also sets 1; 327 sets 2; nothing reads it in IC's scripts). Map 31 (Dorter), ENTD 520:
  Cletienne (lv 40), five mages, Meliadoul from the party (ENTD level 254, b1 0x48); a party formation (Ramza and
  Meliadoul warped in, units 0x78-0x7C drawn later): EntryNo 520 = [0,7100,0] (IC ENTD 460 / event 443),
  SortieConfirm 378 = copy of 11 (map 31). CharaControlId 0x27/0x2A are vanilla rows.
- Trigger: Dorter (9), WotL 0x6E == 51 (IC event 430) -> >= 51, 0x2F3 == 0, Meliadoul (0x2A) in party, play 543 mode 1.
- Speakers: Cletienne 1070500, Meliadoul 1070201 (ally, IC's later chapter 4), Ramza 1010103. Sheet 0x64 = tex_1252
  (WotL rows; IC rows + Mobile 442-511). 547 keeps CallFunction 04 (IC uses 04).

## 1.11.0 (2026-09-25): Agrias visits Ovelia (WotL events 548-551) - UNTESTED
- Two versions of one scene, same 31-message block: 550 stub (rules 157) -> 551 with Lavian/Alicia (units 0x81/0x82)
  when both are in the party; else 548 stub (rules 156) -> 549. Map 45 (Chapel Ruins, night; scene only, no battle
  surface needed), ENTD 521. Both set 0x2F4, 0x2E9 (rumor 24 Disorder in the Order -> IC 0x2EA via RUMOR_VARS;
  that rumor is not restored yet) and 0x1B0 / 0x1B1.
- Triggers (WotL, kept as is): Zeltennia Castle (5), 0x6F >= 16, Agrias (0x1E), 0x2F4 == 0, [+ Lavian 0x78, Alicia
  0x79 -> 550], else 548; mode 2. The Lavian/Alicia block is added first.
- Speakers: Ovelia 1030701, Delita 1020102, Agrias 1030100; per-message overrides (new group key
  `message_speakers`, WotL message numbers; converted lines now carry 'msg'): 1 "Familiar Voice" 5002100, 10 new
  1167000 "Delita's Voice". Sheet 0x21 = tex_1177 (WotL rows). convert_wotl text ids now keyed by (message number,
  bytes), so events in one group with different text blocks cannot share ids by mistake.

## 1.12.0 (2026-09-25): Beowulf and Reis vs Celebrant Bremondt (WotL events 552-569) + rumors 25/26 - UNTESTED
- **Counter bug fixed**: IC's quest counters are 12 dwords at obj+0x18 (0xFF660; alt bank +0x68), followed by a byte
  flag bank at +0x48 (setter 0xFF6B8, 16 callers with indices 1, 0xF, 0x14, 0x1A-0x1F, ...; observers notified
  after each write, likely progress/achievement flags). 1.4.3-1.11.0's rumor counter 12 wrote a dword at +0x48,
  i.e. flag bytes 0-3 (byte 0 = 20 after reading A Call for Guards). Now counters 4 (Rash/Call, stages 10/20), 5
  (Disorder), 6 (Lionel's): IC's scripts use 0-3 (E9), rumors 0/2, UserSituation (union 121) 0-3.
- **Rumors 25/26 restored**: Disorder in the Order (WotL 24, sets 0x2FC, Eagrose art 10) and Lionel's New Liege Lord
  (WotL 25, sets 0x2FD, Lionel art 9). Town masks now WotL's own (BOOT.BIN 0x31F85C, entries 22-25: 0x4140 Lesalia/
  Gariland/Gollund, 0x20 Dorter, 0x1100 Eagrose/Gariland, 0x56A Limberry/Gariland/Gollund/Dorter/Goug/Bervenia);
  IC's table (RVA 0x7BE620) has 64 entries. Mod.cs _rumorTowns now carries masks.
- **Beowulf/Reis**: 552 stub -> 553 fields (map 115; record next 554 0x80) -> 554 stub -> 555-560 Lionel Castle Gate
  (map 12, ENTD 523, formation; 560 needs next 561 added by Mod.cs, WotL had it only via 0x55) -> 561 stub -> 562-567
  Lionel Castle Oratory (map 13, ENTD 524; 565 Bremondt -> Dark Dragon via CallFunction 0x11; 566 next 568 0x81) ->
  568 stub -> 569 Reis rescued (map 11). Three groups (unit 0xA6 = Aliste at the gate, Bremondt's body in the
  oratory). Trigger (WotL's): Lionel Castle, 0x6F >= 16, 0xAC == 1, 0x2FD == 1 (rumor read), 0x2F8 == 0, Beowulf and
  Reis in party. Objectives 38 "Defeat Aliste!", 39 "Defeat Celebrant Bremondt!". SortieConfirm 379 = vanilla 50
  (map 12), 380 = 50 with MapId 13. EntryNo 523 [0,8000,0], 524 [0,8300,0]. CharaControlId 0xA6-0xA8. Speakers
  Beowulf 1120100, Reis 1120200, new Aliste 1168000, Celebrant Bremondt 1169000, Ninja 1170000. Sheets 0x88 (tex_1278
  hybrid) and 0x8D (tex_1283, Mobile as is, WotL-only). 569 sets 4-bit stages 0x3D2/0x3D5/0x3D6/0x3D8 (IC sets
  0x3D6/0x3D8 to 1-2 earlier) and clears the Lionel rumor.

## 1.13.0 (2026-09-25): Agrias and Orlandeau vs Northern Sky deserters (WotL events 570-577) - UNTESTED
- 570 stub (rules 162) -> 571 battle start (objective 0 "Defeat all enemies!") -> 572-575 turn talks (Orlandeau 0x0D,
  deserters 0x80/0x82, Ramza, Agrias; scratch vars 0x7D-0x81) -> 576 victory with Agrias (unit 0x1E present) / 577
  without; both 0x80 (world map), set 0x2F6, clear 0x2E9 (-> IC 0x2EA, hides rumor 25). Map 91 Brigands' Den (has
  panel_ui), ENTD 526: six deserters (lv 40-49), Agrias from the party; formation: EntryNo 526 [0,8000,0],
  SortieConfirm 381 = vanilla 16 (map 91). No sheets, no title.
- Trigger (WotL's): Brigands' Den (17), 0x6F >= 16, Agrias in party, 0x2F6 == 0, 0x2FC == 1 (Disorder in the Order,
  IC rumor 25, read); play 570 mode 1. Speakers: new 1171000 "Northern Sky Deserter", Orlandeau 1030200, Agrias
  1030100, Ramza 1010103.

## 1.14.0 (2026-09-25): Gariland tavern gossip (WotL events 580-581) - built, NOT triggered
- 580 stub (rules 164) -> 581 scene (map 96, ENTD 529; sets 0x2FE): patrons discuss WotL's multiplayer "Melee" and
  "Rendezvous" menu entries. IC has neither mode, so per the user it ships without its trigger; WotL's trigger
  (Gariland 6: 0x2FE == 0, 0x6E >= 3, play 580 mode 2) is kept in the group's `triggers_disabled` (not exported).
  Speakers: IC Tavern Patron 2120500/2120600, Tavernmaster 1900700. Sheets 0x09 (tex_1160), 0x85 (tex_1275) hybrids.
- All WotL-only story scenes 512-581 are now ported. WotL 582-589/596-599 are placeholders (WotL's own debug copies of
  other records); 590-595 are IC's.

## 1.15.0 (2026-09-25): battle surface (panel_ui) for map 45 - UNTESTED
- FFTOMESH decoded (tools/panel_ui.py docstring): header, 32 name slots at 0x30, counts at 0x430 (objects, NA quad
  vertices, NB triangle vertices, NC, ND, NA+NB), u8 object index per vertex, then per-vertex arrays in element
  order (A then B): positions 16 (3 f32 + a corner attribute: tile tag row<<1|level, col / polygon id / BBBB /
  8001 end), normals 8 (int16 x,y,z in 4096ths; checked against geometry: 97% element order vs 51% by the
  permutation), records 32 (u32 order-index permutation, 0, material = GT number), UV+lighting 28; 512-byte tail
  (64 doubles 1.0). Size = 0x454 + 85 N + 17 (NC+ND) + 512 for 107 of 117 meshes (the rest carry animation data).
- panel_ui = every tile-tagged polygon of the map, 0.2 higher (y - 0.2), same attributes (map 76: all 241), with the
  highest order indices; its UVs are meaningless (UI shader); no texture file (map 76 has none for GT_8). IC adds
  flat 8-triangle tiles (id FFFF) on some untagged tiles, inconsistently; not generated. Round trip on map 76 (strip
  its panel, regenerate): the same 241 polygons (IC starts copies at a rotated corner; winding kept).
- Map 45: GT_5_panel_ui (material 5), 137 quads + 13 triangles over 136 tiles; 5 flag-0x10 tiles stay without (as
  IC leaves many such tiles). build_data PANEL_MAPS runs it; output FFTIVC/data/enhanced/bg/meshes/map_045_mesh.bin.
- To test: the chapel ruins battle (531-534) must be replayed; the user's save has 0x2F1 (seen) set.
- **1.15.0 test**: map drawn wrong (black/stretched patches on tile tops) and the cursor still flat. Cause: the 28-byte
  UV/lighting array is indexed by render slot (the record's u32 permutation), grouped by material in object order
  with the panel last; its u32 is the slot's material (holds on 76, 2, 45: every element's rec slot has its own
  material). 1.15.0 inserted panel entries in element order, shifting every B vertex's UV/material. **1.15.1**: the
  UV array keeps IC's slots untouched and appends the panel's (material 5, copied from each source vertex's slot).
  Round trip on 76 keeps all IC slots identical and the invariant true. Untested.
- **1.15.1 test**: map renders correctly, cursor still flat. The exe never names objects (no "panel"/"GT_"/FFTOMESH
  strings or name hashes); the per-map object roles are data: nxd **RefinedBgMeshNode** (Key map, Key2 arrangement,
  Key3 object index; hashed, use_base_row_id 0; vanilla CRC CA913FBA): IC's panel nodes have Unknown16 = 1 (82 of
  85, usually with UnknownC = -100), no other node does. Map 45 had rows for objects 0-5 only. Related tables:
  RefinedBgTexture (textures per map material; panels have none), RefinedBgUITextureFrames (bg/ui/panel/*.tga grid
  textures), RefinedBgMeshPolygon/Cond (per-polygon visibility conditions).
- **1.15.2**: build_data adds RefinedBgMeshNode (45, 0, 6) = map 76's panel node 13 (0, -100, 0, 1, 0, 1, 1, 1) for
  each PANEL_MAPS arrangement, and ships the table. Untested.
- **1.15.2 test**: the cursor follows height (the node row works); the highlight was one flat fill, not per-tile
  squares, and the arch confused the cursor. Causes: panel UVs are tile-local (read in render-slot order: u = (x -
  28 col)/28, v = (28 (row+1) - z)/28; IC's quads (0,0)-(1,1), triangles at 0.5 steps), and 1.15.1 had copied the
  map's texture UVs; and the arch tiles (4,2)/(4,3)/(4,6) level 0 and (4,4)/(4,5) level 1 (height 17) have no
  tagged map polygon. **1.15.3**: tile-local UVs, neutral lighting (0x80), and IC-style fill tiles (8 triangles,
  id FFFF, up normal, CCW from above) on every unblocked uncovered tile, following the classic slope (0x52 +x,
  0x58 -x, 0x85 +z, 0x25 -z; derived from tagged polygons on sloped tiles in 8 maps). Untested.
- **1.15.3 confirmed** by the user: grid squares correct, cursor follows height, arch works. Guide for other
  modders: research/MAP_GRID_GUIDE.md (published as an artifact).

## 1.16.0 (2026-09-25): WotL items, first item the Tynar Rouge - UNTESTED
- Full write-up: research/ITEM_EXPANSION.md. IC's item code is WotL's; WotL items keep their WotL ids (IC still
  special-cases them: Onion gear reserved for jobs 0xA1/0xA4 in the can-equip check 0x2886D0), Fell Swords
  0x100-0x104 -> 0x116-0x11A. Built for all 42 (tools/wotl_items.py -> ItemData.g.cs); only the Tynar Rouge (0x138,
  a Perfume per the user, bonus row 0x68: PA+3 MA+3, always Protect/Shell/Haste, strengthen Holy) is enabled.
- ItemExpansion.cs: page near the exe (bag, owned mirror, bonus table, all 10 charts, per-id tables), 63
  relocations + 28 bounds + low-id IsValidItem stub for 0x2D6688 + 14 chart slots + 9 getter asm hooks (FASM,
  checked offline with Reloaded.Assembler) + serializer flush hook; all bytes verified first (tools/item_sites.py
  -> ItemSites.g.cs), all-or-nothing. Counts of ids 0x105+ in the event block tail (+0x2FC, "WC" 1 0; no var id
  reaches it; battle suspend/resume copy the block too, so no sidecar). Charts sync both ways with their vanilla
  save fields (vanilla ids only when projected).
- The birthday reward is now the Tynar Rouge (text "Received the Tynar Rouge! Agrias's HP and MP increased!"), with
  the Septieme Sens as the fallback if the expansion does not arm. Item-en/fr/de/ja row 312 (English text, mod's
  own description), icons ei_312 / ei_s_312 from the staged Mobile icon.
- **1.16.0 test** (user): the reward arrived, Agrias equips it, the equipment bonuses show and apply (Protect/Shell/
  Haste in battle), but no name, no icon, and the detail panel kept the last item's text. The modloader loaded the
  icons and the row ("Processing 1 added rows for nex table 'item.en'"). Cause: Item is a base-row-id table
  (Nex layout use_base_row_id: rows are found by position from the first key), and row 312 sat at position 261.
  **1.16.1**: rows 261-315 are all shipped (blank rows, as vanilla's 254, for ids not in use yet).
- **1.16.1 confirmed** (user): the Tynar Rouge shows its name, icon and description; save/reload keeps it.

## 1.17.0 (2026-09-25): Ras Algethi and Mirage Vest on Balthier - UNTESTED
- How WotL equips them: not through the ENTD (items there are bytes; ENTD 514/528 carry his Glacial Gun, Black Garb,
  Thief's Cap, Germinas Boots in WotL too) but in code: the unit setup loop (WotL 0x88BAE4, IC 0x27176B, the same
  code) checks unit byte 0 == 0xA2 (Balthier) and var 0x27 (the event being played) == 0x206 (518, his battle's stub)
  and copies a 7-word table (WotL 0x8A56058, IC 0x714460, IC still has it: 0, 0x12F, 0, 0x107, 0, 0, 0) over unit
  +0x1A.. (skipping zeros): body = Mirage Vest, right hand = Ras Algethi. IC's sanitizers dropped the two unknown ids;
  with the items enabled, the game equips them itself. (Other WotL immediates 0x107/0x12F at 0x89C6BF4/0x8A2DD28
  pick them or a vanilla item by a mode check: multiplayer rewards.) Whether he keeps them after the recruitment
  scene (ENTD 528, event 523/524, var 0x27 not 518) is for the test.
- Ras Algethi is the first new weapon: 16 hand-slot bounds widened ("right hand is 0xFF or >= 0x105 -> other word /
  left hand": attack setup 0x226FDD and five copies, 0x27F000, 0x2822A1, 0x284C08, 0x3602F3, 0x396368, 0x3059BE,
  0x309EF6, 0x28024D, 0x1ED958/97F), none indexing a buffer by id. Steal/break and auto-sell stay unwidened.
  Item rows: Ras Algethi (gun, sort 807), Mirage Vest (clothing, sort 4016; Speed +1, HP +120, immune Stone/Poison/
  Sleep); text is the mod's own.
- Cletienne & Meliadoul (1.10.0) tested OK by the user.
- **1.17.0 confirmed** (user): Balthier joins with Ras Algethi and Mirage Vest (so WotL's rule also covers the
  recruitment); the gun's attack looks right.

## 1.18.0 (2026-09-25): every WotL item in the data - UNTESTED
- All 40 WotL items enabled (22 weapons incl. the five Fell Swords at 0x116-0x11A, 2 shields, 4 helms/hats, 6 body,
  6 accessories; earlier notes said 42, the right count is 40).
- Text rows for all (tools/build_data.py WOTL_ITEMS: names and the mod's own flavour sentences). The effect lines are
  written from the data by tools/item_text.py, in IC's wording (checked against IC's own items). Weapon effect rows
  (ItemOptionsData) start at RVA 0x80FBA0, not 0x80FBA6: row 9 = Blindness (Blind Knife). The Fell Swords inflict
  Blindness / Doom / Slow / Stop / KO; the Stardust Rod casts Gravity (ability 42).
- Template per item: the category's last plain vanilla item (so magic guns' IsRandomDamage does not leak onto
  Ras Algethi/Fomalhaut; axes and flails keep random damage). SortOrder: the shipped ones kept, the rest after the
  category's last.
- UIItemCategory row 35 "Fell Sword" (a copy of Knight's Sword; the table is base-row-id, IC stops at 34).
- Not yet: only the Tynar Rouge, Ras Algethi and Mirage Vest can be obtained (WotL's other items came from its
  multiplayer modes). Fell Swords (type 0x23) and the Onion gear (reserved for jobs 0xA1/0xA4) have no IC job that
  equips them: IC's JobData still carries WotL's Dark Knight (0xA0, also 0xAF) and Onion Knight (0xA1/0xA4) with
  type 0x23 (and 0x24, lip rouge) in their equipment masks, but they are unnamed and no unit can take them. The hand menu lists cap at 145 kinds (140 vanilla + the new weapons fit unless nearly all are owned).
- **1.18.0 confirmed** (user, 2026-09-25): all 40 items given in a live game (one each, written to the expansion's
  bag page) show their names, icons, descriptions and categories correctly. A unit put into Onion Knight (job 0xA1/
  0xA4; reachable only through Cheat Engine or another mod, its name is blank) sees and equips the Onion gear: the
  can-equip check's reserved-id list (0x2886D0) and the job's equipment mask work with the new ids.

## 1.19.0 (2026-09-25): Zeirchele Falls back in WotL's place in the story - UNTESTED
- User tested 1.8.0's trigger version: Zeirchele Falls plays correctly. User's call: restore WotL's linkage.
- Records (WotL vs IC, compared byte for byte): WotL 195 = next 512 (+0x12 00, +0x13 02) with +0x14 0x81 (play now);
  IC 195 = next 196 (C4 00) with 0x80 (world map, then play next). 515: +0x14 0x80 in both, no next (WotL's script
  handed over through 0x55 = 196 + CallFunction 06, which the port drops; IC's 195 sets 0x55 = 196 itself).
- Mod.cs _eventRecords: 195 -> next 512, 0x81; 515 -> next 196 (flag 0x80 already set). So the Lionel Castle
  sequence plays 195 -> 512 (falls, battle) -> 515 -> world map -> 196, as WotL did.
- Trigger: only [0x6E >= 30, 0x2ED == 0] at Zeirchele Falls remains (saves already past 195). 1.8.0's
  [0x6E == 29, 0x55 == 196] trigger was dropped: with the chain it could only replay the scene. No trigger condition
  can test IC's main story counter (195: E9 counter 0 = 820), which would have been the exact "195 played" test.
- Test needs a save before IC event 195 (chapter 2, the Lionel Castle chain triggered at Lionel Castle, 0x6E == 29).

## 1.20.0 (2026-09-25): Argath's battle named Limberry Castle Undercroft - UNTESTED
- User (Argath test): the battle's title and the save entry read "Fort Besselat - South Wall" (map 66, the stand-in).
  Both come from nxd Map's row for the map: Unknown8 = title PlaceNameId (66: 16500), UnknownC = region (1220 "Fort
  Besselat"), Unknown10 = spot (31000 "South Wall"; the save entry is region + spot). No script title is involved
  (IC's battle starts have no E7). IC's undercroft map 17: 11800 "Limberry Castle Undercroft", 1050, 33200.
- User wanted a map copy (WotL's own map 127 with map 66's data): not possible as mod files: IC's fftpack has only
  map 127's GNS/DST entries (3755/3756), no data or new_map_ terrain entries, and fftivc.utility.modloader only
  replaces existing fftpack indices (its FileLists/fftpack.txt); HD textures would also have to be copied
  (bg/textures/%03d/%s.tga uses the map id folder, 31 MB).
- StandInMapNames.cs: hooks the event setup routine 0x2FB7C8 (sig 40 53 55 56 57 41 54 41 55 41 56 41 57 48 83 EC 68
  BF 64 00 00 00 8B CF E8; no register arguments; reads var 0x64 then 0x27, the event id), and while the event is
  537-542 writes 11800/1050/33200 over map 66's Map row (found in memory by its three ids 16500/1220/31000, which
  appear once in map.nxd at 0x2540, consecutive ints at row +8/+0xC/+0x10); any other event restores them. The rows
  are cached and re-checked before each write.
- **1.20.0 test** (user): the title showed, but the game froze for seconds while loading (the in-memory row scan), and
  the right name is **Limberry Castle Inner Court** (the undercroft is the next map). Replaced in 1.21.0.

## 1.21.0 (2026-09-25): WotL's map 127 (Limberry Castle Inner Court) restored as a copy of map 66 - UNTESTED
- IC already resolves map 127's classic files to map 66's: its per-map file lists (exe 0x685450 and 0x685050, one per
  mode; a GNS entry FEEDBACC <n> -> list[n] = (fftpack index, size)) give map 127 exactly map 66's files, its GNS
  (3755) matches 66's, and the per-map GNS index tables are at 0x7B7130 (GNS) / 0x7B6F30 (GNS - 1). WotL's map 127
  IS Fort Besselat - South Wall (the user's match was exact). Only the HD half was missing.
- tools/build_data.py MAP_COPIES: bg/meshes/map_127_mesh.bin (map 66's, header id 127), bg/textures/127/ (map 66's
  13 textures, 31 MB: the loader uses bg/textures/%03d/%s.tga with the map id), the RefinedBg{Anim,MeshNode,
  MeshPolygon,MeshPolygonCond,SystemTexture,Texture} rows of 66 as 127, Map row 127 = 66's settings with the names
  11850 "Limberry Castle Inner Court" (title), 1050 "Limberry Castle" (region), 33250 "Inner Court" (spot; new
  PlaceName rows, table is sparse-keyed). SortieConfirm 377 MapId 127. Mod.cs no longer patches 537-542's map;
  StandInMapNames.cs removed (no scan, no freeze).
- Open: the continuous-battle minimap (ContinuousSortieConfirm rows 16-18 = Limberry gate/keep/undercroft, image group
  6, nodes PointStart/Point01/Point02 animated by ui/ffto/battle/ffto_battle_continuous_map.uib over the dot-art
  sheet ui_battle_continuous_map_dotart_uitx) for when Argath is relinked between the keep (394) and the undercroft
  (395): a fourth node needs the .uib layout edited.

## 1.22.0 (2026-09-25): Argath relinked between the Limberry keep and undercroft, 4-stage minimap - UNTESTED
- Records (Mod.cs _eventRecords): 394 next 395 -> 537 (8B 01 -> 19 02), 542 next 0 -> 395 (flag 0x80 already set).
  The Limberry Castle trigger (0x6E >= 50, 0x3CC == 3) stays for saves already past 394.
- The minimap is data in two places. ContinuousSortieConfirm (nxd 289) rows sequence it: per stage, the
  ContinuousBattleTimeline keys to play (Unknown8 PointN-1, Unknown10 PositionN-1, Unknown18 PositionN, Unknown20 MoveN,
  Unknown44 StayN-1, Unknown48 the PointN node), the place names (Unknown30/34/38) and the stage (Unknown68). The
  coordinates are all in ui/ffto/battle/ffto_battle_continuous_map.uib: one component per map (MapA..MapH, 900x540)
  with Point nodes, Line nodes (instances of the Line component, rotated/stretched), the Unit, and per-stage
  timelines (HomePosition, PointN, MoveN, PositionN, StayN). A map's stage count is fixed by its component.
- tools/uib.py: reader plus offset walker (offset_fields) and copy_component (copies a component's structures to the
  end of the file, re-aims offsets that leave the block, re-points the target's record). tools/continuous_map.py
  rebuilds MapE from MapH (4 stages) and places it: Gate, Keep as IC, Inner Court at (120,175) (terrace west of the
  keep), Undercroft as IC's Point03. Layout rules in its docstring.
- Rows: 18 is now the Inner Court's (spot 33250), confirmed by stub 537 (EventId copied from 395, union 289:18); new
  row 26 = the undercroft (stage 4, Point03 -> Point04), 395's union 289:26. SortieConfirm 377 dropped.
- Beowulf/Reis is two battles (gate, then the oratory with Bremondt's Dark Dragon phase), exactly IC's Lionel chain
  (MapD, stubs 191 -> 196): stubs 554 / 561 now copy 191 / 196's EventId rows (continuous rows 1 / 2); SortieConfirm
  379 / 380 dropped. A chain sharing a component shares its markers; stage-1 rows' Unknown5C is only the header text
  (UI-en 3915 "Battle at Lionel Castle", 3919 "Battle at Limberry Castle", ... 3923). A chain that needs different
  markers needs its own component: the component table is a fixed 30-entry array (TOC +4 points at it, records'
  offsets are record-relative, so it can be moved to the end of the file), plus a MapAll reference node and timeline
  and a ContinuousBattleTimeline name row; whether the exe caps map keys at 9 is unchecked.

## 1.22.1 (2026-09-25): fallback triggers for Argath and Zeirchele Falls disabled
- User test (a save past 394): the Limberry Castle fallback fired 537 and the minimap showed correctly (Start, Gate,
  Keep with the unit, Inner Court blinking, Undercroft greyed; "Limberry Castle / Inner Court" header).
- But with the relinks, both chains' last events hand off into IC's story (542 -> 395, 515 -> 196), so the fallbacks
  (for saves already past 394 / 195) would replay IC battles those saves have played. Both moved to
  triggers_disabled; the scenes are reached only through the story chain. Keeping them for such saves would need a
  copy of the final event without the hand-off (a spare event record, map patched) chosen by a rules block.

## 2.0.0 (2026-09-25): released as 2.0.0 (major update: all 40 WotL items, map 127, the relinked story chains,
## the continuous-battle minimap); triggers exactly as WotL's, no fallbacks (built as 1.23.0)
- Tested by the user: Agrias visits Ovelia (Zeltennia), the Deserters (Brigands' Den), Beowulf/Reis (fields, gate,
  oratory), the rumors that unlock Balthier.
- Fallbacks removed (Zeirchele Falls, Argath: reached only through their story links, 195 and 394).
- Windows back to WotL's (tools/wotl_triggers.py), after the 2026-09-24 widening for testing: story var 0x6E == (not
  >=) 29 Balias Swale, 37 Zeklaus (Luso), 39 Yardrow, 43 Bervenia, 51 Dorter (Cletienne). Agrias's Birthday as WotL:
  0x6F >= 13 (was ReMixed's chapter 4 flag 0x94), not seen = 0x2F9 (was 0xB6; the scene sets both, 0x2F9 is never
  cleared), the twelve towns other than Lionel, Zeltennia and Dorter (was all 15). Unchanged, already WotL's:
  Balthier (Dorter), Zeltennia (Agrias/Ovelia), Lionel (Beowulf/Reis), Brigands' Den (Deserters).

