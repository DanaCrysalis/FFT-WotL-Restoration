using Reloaded.Hooks.Definitions;
using Reloaded.Memory.SigScan.ReloadedII.Interfaces;
using Reloaded.Mod.Interfaces;
using IReloadedHooks = Reloaded.Hooks.ReloadedII.Interfaces.IReloadedHooks;

namespace WotLCharacters
{
    /// <summary>
    /// The code half of Agrias's Birthday (War of the Lions events 578/579, the scene via FFT ReMixed's event 159).
    /// The scripts, text, trigger and rules are data (tools/build_data.py). This:
    ///  - checks the two setup records IC still carries for the scene are as expected;
    ///  - grants the reward when the scene raises its "reward pending" flag: WotL's Tynar Rouge (ItemExpansion; a
    ///    Septieme Sens, ReMixed's reward, when the expansion is not armed) and Agrias's raw HP and MP x 1.1, as
    ///    ReMixed did with its custom memory-writing event instructions.
    /// See research/NOTES.md for how every address and format was found.
    /// </summary>
    internal class AgriasBirthday
    {
        private readonly ILogger _logger;
        private readonly IModConfig _modConfig;
        private readonly nint _baseAddress;

        // Event setup table: 0x18-byte records, u16 event id at +0, ended by an all-zero record. The setup routine
        // scans it with this LEA (which points at the record for event 1) for at most 0x377 records; vanilla uses 713,
        // the rest of the array is zero.
        private const string SETUP_TABLE_SIGNATURE = "48 8D 1D ?? ?? ?? ?? 41 8B D4 BD 27 00 00 00";
        private const int SETUP_RECORD_SIZE = 0x18;
        private const int SETUP_RECORD_COUNT = 0x377;

        // IC still carries War of the Lions' own (unused) setup for this scene: records 578 (stub, battle-event rules
        // key 163) -> 579 (scene, follow-up 0x8000 = back to the world map), map 96, cast ENTD 527. Only checked, in
        // case a game update or another mod changes them. Fields: +2 map, +7 ENTD (u16), +0x14 follow-up high byte,
        // +0x16 battle-event rules key.
        private const ushort STUB_EVENT = 578;
        private const ushort SCENE_EVENT = 579;
        private const byte MAP_ID = 0x60;
        private const ushort ENTD_ID = 527;
        private const byte STUB_RULES_KEY = 163;

        // Variable operation dispatcher (op, var, value, _, flag): every event-script variable instruction ends here.
        // An identical copy of the function exists, so it is found through the event interpreter's call to it
        // (the ZERO var 0x57 special case right before the call).
        private const string VAR_OP_CALL_SIGNATURE =
            "41 81 F9 BE 00 00 00 75 ?? 83 FA 57 75 ?? 48 8B 05 ?? ?? ?? ?? 44 89 68 10 41 8B C9 44 88 6C 24 20 E8";
        private delegate int VarOpDelegate(int op, int var, int value, nint unused, byte flag);
        private IHook<VarOpDelegate>? _varOpHook;

        private const int OP_ADD = 0xB0;
        private const int VAR_REWARD_PENDING = 0x2F9;   // the scene sets this (ZERO, ADD 1) at its very end (never
                                                        // cleared: WotL's trigger requires it to be 0)...
        private const int VAR_SCENE_SEEN = 0xB6;        // ...just before this one, which a replay already has set

        // Event variables: the pointer global the variable address function reads. Vars 0x80-0x35F are bit flags
        // stored from +0x200.
        private const string VARS_POINTER_SIGNATURE = "48 8B 05 ?? ?? ?? ?? 48 63 C9 48 8D 1C 88";

        // Roster: 54 slots of 0x258 bytes. +0x00 character id, +0x01 party index (0xFF = not in the party),
        // +0x20 and +0x23 raw max HP / MP (24-bit). The 0x105-byte party inventory (count per item id) sits
        // 0x110 bytes before it. The signature's dword at +20 is the roster's RVA + 1.
        private const string ROSTER_SIGNATURE = "48 63 C2 4D 8D 83 ?? ?? ?? ?? 48 69 C8 58 02 00 00 49 8D 83 ?? ?? ?? ??";
        private const int ROSTER_SLOTS = 54;
        private const int ROSTER_SLOT_SIZE = 0x258;
        private const int INVENTORY_BEFORE_ROSTER = 0x110;
        private const byte AGRIAS = 0x1E;
        private const int RAW_HP = 0x20;
        private const int RAW_MP = 0x23;

        private const int TYNAR_ROUGE = 0x138;          // WotL's reward, a WotL item (ItemExpansion)
        private const int FALLBACK_ITEM = 238;          // Septieme Sens (ReMixed's Setiemson, item 0xEE)
        private const int ITEM_MAX_COUNT = 99;

        private nint _varsPointer;
        private nint _roster;

        public AgriasBirthday(IStartupScanner scanner, IReloadedHooks hooks, ILogger logger, IModConfig modConfig, nint baseAddress)
        {
            _logger = logger;
            _modConfig = modConfig;
            _baseAddress = baseAddress;

            scanner.AddMainModuleScan(SETUP_TABLE_SIGNATURE, result =>
            {
                if (!result.Found) { Log("Warning: event setup table not found, could not check events 578/579"); return; }
                CheckSetupRecords(RipTarget(result.Offset + 3));
            });

            scanner.AddMainModuleScan(VARS_POINTER_SIGNATURE, result =>
            {
                if (!result.Found) { Log("Error: event variables not found, the birthday reward will not be granted"); return; }
                _varsPointer = RipTarget(result.Offset + 3);
            });

            scanner.AddMainModuleScan(ROSTER_SIGNATURE, result =>
            {
                if (!result.Found) { Log("Error: roster not found, the birthday reward will not be granted"); return; }
                _roster = _baseAddress + ReadInt32(_baseAddress + result.Offset + 20) - 1;
            });

            scanner.AddMainModuleScan(VAR_OP_CALL_SIGNATURE, result =>
            {
                if (!result.Found) { Log("Error: variable dispatcher not found, the birthday reward will not be granted"); return; }
                nint call = _baseAddress + result.Offset + VAR_OP_CALL_SIGNATURE.Split(' ').Length - 1;
                nint target = call + 5 + ReadInt32(call + 1);
                _varOpHook = hooks.CreateHook<VarOpDelegate>(VarOpImpl, target).Activate();
                Log($"Hooked variable dispatcher at {target:X}");
            });
        }

        /// <summary>Checks WotL's stub and scene records are still what the port relies on.</summary>
        private unsafe void CheckSetupRecords(nint firstRecord)
        {
            byte* stub = null, scene = null;
            for (int i = 0; i < SETUP_RECORD_COUNT; i++)
            {
                byte* record = (byte*)(firstRecord + i * SETUP_RECORD_SIZE);
                int id = record[0] | record[1] << 8;
                if (id == 0) break;
                if (id == STUB_EVENT) stub = record;
                if (id == SCENE_EVENT) scene = record;
            }
            bool Matches(byte* r) => r != null && r[2] == MAP_ID && (r[7] | r[8] << 8) == ENTD_ID;
            if (!Matches(stub) || !Matches(scene) || stub[0x16] != STUB_RULES_KEY || scene[0x14] != 0x80)
            {
                Log($"Warning: event {STUB_EVENT}/{SCENE_EVENT} setup records are not the expected War of the Lions ones " +
                    "(game update or another mod?); Agrias's Birthday may not play correctly");
                return;
            }
            Log($"Events {STUB_EVENT}/{SCENE_EVENT} setup records OK (map {MAP_ID}, ENTD {ENTD_ID})");
        }

        private int VarOpImpl(int op, int var, int value, nint unused, byte flag)
        {
            int result = _varOpHook!.OriginalFunction(op, var, value, unused, flag);
            if (op == OP_ADD && var == VAR_REWARD_PENDING && value == 1)
            {
                try { GrantReward(); }
                catch (Exception ex) { Log($"Error granting the birthday reward: {ex.Message}"); }
            }
            return result;
        }

        private unsafe void GrantReward()
        {
            if (_varsPointer == 0 || _roster == 0) { Log("Error: birthday reward skipped, addresses missing"); return; }

            // A replay of the scene (the "seen" flag is already set) grants nothing
            nint vars = *(nint*)_varsPointer;
            uint flags = *(uint*)(vars + 0x200 + ((VAR_SCENE_SEEN - 0x80) >> 5) * 4);
            if ((flags >> (VAR_SCENE_SEEN & 31) & 1) != 0) { Log("Birthday scene replayed, no reward"); return; }

            // The Tynar Rouge, WotL's own reward, when the item expansion is armed; otherwise ReMixed's Septieme Sens
            int item, now;
            var items = ItemExpansion.Instance;
            if (items != null && items.IsEnabled(TYNAR_ROUGE))
            {
                item = TYNAR_ROUGE;
                now = items.AddItem(TYNAR_ROUGE, 1);
            }
            else
            {
                Log("Item expansion not armed: the birthday reward falls back to a Septieme Sens");
                byte* count = (byte*)(_roster - INVENTORY_BEFORE_ROSTER + FALLBACK_ITEM);
                if (*count < ITEM_MAX_COUNT) (*count)++;
                item = FALLBACK_ITEM; now = *count;
            }

            for (int slot = 0; slot < ROSTER_SLOTS; slot++)
            {
                byte* unit = (byte*)(_roster + slot * ROSTER_SLOT_SIZE);
                if (unit[0] != AGRIAS || unit[1] == 0xFF) continue;
                int hp = Boost(unit + RAW_HP), mp = Boost(unit + RAW_MP);
                Log($"Birthday reward granted: item {item:X} x1 (now {now}), Agrias (slot {slot}) raw HP -> {hp}, raw MP -> {mp}");
                return;
            }
            Log($"Birthday reward granted: item {item:X} x1 (now {now}); Agrias not found in the party, no stat boost");
        }

        /// <summary>Raw 24-bit stat x 11 / 10, as ReMixed does.</summary>
        private static unsafe int Boost(byte* stat)
        {
            int value = stat[0] | stat[1] << 8 | stat[2] << 16;
            value = Math.Min(value * 11 / 10, 0xFFFFFF);
            stat[0] = (byte)value; stat[1] = (byte)(value >> 8); stat[2] = (byte)(value >> 16);
            return value;
        }

        private nint RipTarget(int dispOffset) => _baseAddress + dispOffset + 4 + ReadInt32(_baseAddress + dispOffset);
        private static unsafe int ReadInt32(nint address) => *(int*)address;
        private void Log(string message) => _logger.WriteLine($"[{_modConfig.ModId}] {message}");
    }
}
