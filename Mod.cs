using WotLCharacters.Configuration;
using WotLCharacters.Template;
using Reloaded.Memory.SigScan.ReloadedII.Interfaces;
using Reloaded.Mod.Interfaces;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;

using IReloadedHooks = Reloaded.Hooks.ReloadedII.Interfaces.IReloadedHooks;

namespace WotLCharacters
{
    /// <summary>
    /// WotL Restoration mod for Final Fantasy Tactics (ModId WotLCharacters).
    /// Names, jobs and shapes come from the nxd tables and the job portrait ids from FFTIVC/tables/enhanced/JobData.xml.
    /// This code patches the hardcoded portrait tables the mod loader does not expose, and guards a null pointer
    /// the game reads when drawing these portraits.
    /// The mod also restores the War of the Lions events IC left out (all of WotL's 512-581) and WotL's 40 items:
    /// data built by tools/build_data.py, the birthday reward in AgriasBirthday.cs, the item tables in
    /// ItemExpansion.cs. research/IMPLEMENTATION_GUIDE.html explains all of it.
    /// </summary>
    public class Mod : ModBase
    {
        private readonly IModLoader _modLoader;
        private readonly IReloadedHooks? _hooks;
        private readonly ILogger _logger;
        private readonly IMod _owner;
        private Config _configuration;
        private readonly IModConfig _modConfig;

        private readonly nint _baseAddress;
        private readonly object _lock = new();

        private AgriasBirthday? _agriasBirthday;

        // Needed together for the monster palette pointer fix
        private nint _ramzaJobAddress;
        private nint _monsterPaletteGlobalAddress;

        // Balthier and Luso (spritesets 0xA2/0xA3) are hardcoded by the game to face ids 0x6C/0x6D -> wldface 163/164.
        // The other WotL units have spritesets of 0x82 and above, which take portrait table[MonsterPortrait of their job].
        // JobData.xml sets MonsterPortrait of jobs 165-168 to these table indices (unused in all six tables).
        // Face ids 0x6E/0x6F already map to wldface 167/166 in vanilla. 0x63/0x64 are unused (-1) in the vanilla face map;
        // 0x61/0x62 are left for the Blue Mage mod. None of 165-168 are swapped by the wldface remap function and each
        // already has its own UI texture slot, so no remap hook or slot patch is needed.
        private static readonly PortraitMapping[] _portraits =
        {
            new("Deathknight", 165, 0x63, 165),
            new("Templar", 166, 0x6F, 166),
            new("Celebrant", 167, 0x6E, 167),
            new("Dark Dragon", 168, 0x64, 168),
        };

        private readonly record struct PortraitMapping(string Name, int TableIndex, int FaceId, uint Wldface);

        // Restored WotL tavern rumors (Gossip ids after IC's own 0-22) and the towns whose taverns list each (bit
        // 0x4000 >> town), WotL's own masks (PSP BOOT.BIN 0x31F85C, the same table, entries 22-25). Must match RUMORS
        // in tools/build_data.py.
        private static readonly RumorTown[] _rumorTowns =
        {
            new("Rash of Thefts", 23, 0x4140),           // Lesalia, Gariland, Gollund
            new("A Call for Guards", 24, 0x0020),        // Dorter
            new("Disorder in the Order", 25, 0x1100),    // Eagrose, Gariland
            new("Lionel's New Liege Lord", 26, 0x056A),  // Limberry, Gariland, Gollund, Dorter, Goug, Bervenia
        };

        private readonly record struct RumorTown(string Name, int Id, uint Mask);

        // Setup record bytes (0x18 per event: +2 map, +3 weather, +4 time of day) that IC's data cannot stage as
        // WotL did. WotL scenes staged on WotL-only maps, which have no HD background in IC (enhanced maps stop at
        // 116), get a stand-in map. The scripts' own ChangeMaps are converted by tools/build_data.py (map_map); keep
        // the two in step.
        private static readonly EventRecordPatch[] _eventRecords =
        {
            new(536, 2, 126, 20),   // Delita and Ovelia ("Tietra"): opens at Zeltennia Castle Keep (its ChangeMap -> map 2)
            // (Argath, 537-542, plays on WotL's own map 127 since 1.21.0: tools/build_data.py MAP_COPIES)
            // Argath in WotL's place, between the Limberry keep and the undercroft: WotL's 394 (the keep battle won)
            // went on to 537 and 542 (Argath falls) to 395 (the undercroft stub) through var 0x55 + CallFunction 06;
            // IC's 394 goes to 395 (next 395, 0x80). Now 394 -> 537 and 542 -> 395 (world map flag already set);
            // the chain's minimap and confirm rows: tools/build_data.py CONTINUOUS_STAGES
            new(394, 0x12, 0x8B, 0x19),
            new(394, 0x13, 0x01, 0x02),
            new(542, 0x12, 0x00, 0x8B),
            new(542, 0x13, 0x00, 0x01),
            // Beowulf and Reis: WotL's 560 (the gate battle won) went on to 561 (the oratory battle) only through var
            // 0x55 + CallFunction 06, which IC's scripts never use; IC's form is the record's next event with the
            // world-map flag (0x80, already set): next = 561
            new(560, 0x12, 0x00, 0x31),
            new(560, 0x13, 0x00, 0x02),
            // Delita and Ovelia at Zeirchele Falls, in WotL's place in the story: WotL's record 195 (the end of the
            // Lionel Castle sequence) plays 512 at once (next 512, 0x81); IC's goes back to the world map and plays
            // 196 (next 196, 0x80). 195 now plays 512, and 515 (the falls battle won, world map flag already set)
            // takes over IC's hand-off to 196, as WotL's 515 did through var 0x55 + CallFunction 06. As in WotL, the
            // scene has no world trigger: saves already past 195 do not get it.
            new(195, 0x12, 0xC4, 0x00),
            new(195, 0x13, 0x00, 0x02),
            new(195, 0x14, 0x80, 0x81),
            new(515, 0x12, 0x00, 0xC4),
        };

        private readonly record struct EventRecordPatch(ushort Event, int Offset, byte From, byte To);

        private const int PORTRAIT_TABLE_COUNT = 6;

        private const int PORTRAIT_ENTRY_SIZE = 2;
        private const int FACEMAP_ENTRY_SIZE = 4;

        // Memory patch data structure
        private struct MemoryPatch
        {
            public string Description;
            public nint Address;
            public byte[] Data;

            public MemoryPatch(string description, nint address, byte[] data)
            {
                Description = description;
                Address = address;
                Data = data;
            }
        }

        public Mod(ModContext context)
        {
            _modLoader = context.ModLoader;
            _hooks = context.Hooks;
            _logger = context.Logger;
            _owner = context.Owner;
            _configuration = context.Configuration;
            _modConfig = context.ModConfig;

#if DEBUG
            // Attaches debugger in debug mode
            Debugger.Launch();
#endif
            _baseAddress = Process.GetCurrentProcess().MainModule!.BaseAddress;

            var startupScannerController = _modLoader.GetController<IStartupScanner>();
            if (startupScannerController == null || !startupScannerController.TryGetTarget(out var startupScanner))
            {
                _logger.WriteLine($"[{_modConfig.ModId}] Error: Could not get startup scanner");
                return;
            }

            // Portrait table index -> face id. There are six identical copies, each used by a different screen.
            startupScanner.AddMainModuleScan("00 00 00 00 01 00 02 00 03 00 78 00 79 00 04 00 7A 00 7B 00 7C 00 7D 00 05 00 06 00 7E", result =>
            {
                if (!Found(result.Found, "Portrait tables"))
                    return;

                var tables = FindAllInSection(_baseAddress + result.Offset, new byte[]
                {
                    0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00, 0x78, 0x00, 0x79, 0x00, 0x04, 0x00,
                    0x7A, 0x00, 0x7B, 0x00, 0x7C, 0x00, 0x7D, 0x00, 0x05, 0x00, 0x06, 0x00, 0x7E
                });
                if (tables.Count != PORTRAIT_TABLE_COUNT)
                    _logger.WriteLine($"[{_modConfig.ModId}] Warning: expected {PORTRAIT_TABLE_COUNT} portrait tables, found {tables.Count}");

                var patches = new List<MemoryPatch>();
                foreach (var table in tables)
                {
                    foreach (var portrait in _portraits)
                    {
                        var entry = table + PORTRAIT_ENTRY_SIZE * portrait.TableIndex;
                        WarnIfPortraitEntryUsed(entry, portrait);
                        patches.Add(new MemoryPatch($"{portrait.Name} Portrait", entry, BitConverter.GetBytes((ushort)portrait.FaceId)));
                    }
                }
                ApplyPatches(patches.ToArray());
            });

            // Face id -> wldface table, from the LEA in the face lookup helper
            startupScanner.AddMainModuleScan("48 8D 0D ?? ?? ?? ?? 8B 04 81 C3 B8 C2 00 00 00", result =>
            {
                if (!Found(result.Found, "Face map code"))
                    return;

                var faceMap = ResolveRipRelative(_baseAddress + result.Offset, 3, 7);
                var patches = new List<MemoryPatch>();
                foreach (var portrait in _portraits)
                {
                    var entry = faceMap + FACEMAP_ENTRY_SIZE * portrait.FaceId;
                    if (ReadUInt32(entry) == portrait.Wldface)
                        continue; // vanilla mapping

                    WarnIfFaceIdUsed(entry, portrait.FaceId);
                    patches.Add(new MemoryPatch($"{portrait.Name} Face", entry, BitConverter.GetBytes(portrait.Wldface)));
                }
                ApplyPatches(patches.ToArray());
            });

            // Ramza Chapter 1 job entry, used as a safe default for the monster palette pointer
            startupScanner.AddMainModuleScan("19 00 00 00 00 00 00 00 00 D0 40 06 FF 00 0B 78 0B 69 5F 64 32 6E 30 64 04 03 0A 00 00 00 00 00 00 40", result =>
            {
                if (!Found(result.Found, "Ramza Chapter 1 job data"))
                    return;

                lock (_lock)
                {
                    _ramzaJobAddress = _baseAddress + result.Offset;
                    TrySeedMonsterPaletteGlobal();
                }
            });

            // Global pointer to the last monster's job data, stored here and read for the portrait palette.
            // Portrait code reads it without a null check for face ids >= 0x3F, which crashes if no monster
            // portrait was drawn yet. All WotL character face ids are in that range.
            startupScanner.AddMainModuleScan("48 89 0D ?? ?? ?? ?? 0F B6 49 2E 41 80 F8 5B", result =>
            {
                if (!Found(result.Found, "Monster palette pointer"))
                    return;

                lock (_lock)
                {
                    _monsterPaletteGlobalAddress = ResolveRipRelative(_baseAddress + result.Offset, 3, 7);
                    TrySeedMonsterPaletteGlobal();
                }
            });

            // Tavern rumor town masks (u32 per rumor id, bit 0x4000 >> town), read by the rumor availability check.
            // IC's entries stop at its own rumors; the restored WotL rumors (Gossip rows from tools/build_data.py)
            // need theirs, or no tavern lists them.
            startupScanner.AddMainModuleScan("B8 00 40 00 00 4C 8D 05 ?? ?? ?? ?? 8B CE D3 E8 41 85 04 B8", result =>
            {
                if (!Found(result.Found, "Rumor town masks"))
                    return;

                var table = ResolveRipRelative(_baseAddress + result.Offset + 5, 3, 7);
                var patches = new List<MemoryPatch>();
                foreach (var rumor in _rumorTowns)
                {
                    var entry = table + 4 * rumor.Id;
                    uint mask = rumor.Mask;
                    uint current = ReadUInt32(entry);
                    if (current != 0 && current != mask)
                        _logger.WriteLine($"[{_modConfig.ModId}] Warning: rumor {rumor.Id} town mask was already {current:X}, another mod may be using it");
                    patches.Add(new MemoryPatch($"{rumor.Name} Rumor Town", entry, BitConverter.GetBytes(mask)));
                }
                ApplyPatches(patches.ToArray());
            });

            // Event setup records (0x18 bytes: u16 event id, +2 map, +4 time of day) for WotL scenes IC's map data
            // cannot stage as WotL did. The LEA points at the record for event 1; the table ends with an all-zero record.
            startupScanner.AddMainModuleScan("48 8D 1D ?? ?? ?? ?? 41 8B D4 BD 27 00 00 00", result =>
            {
                if (!Found(result.Found, "Event setup table"))
                    return;

                PatchEventRecords(ResolveRipRelative(_baseAddress + result.Offset, 3, 7));
            });

            // War of the Lions' own items (ids past IC's 261): arms everything or nothing, see ItemExpansion.cs
            if (_hooks != null)
                ItemExpansion.TryArm(_hooks, _logger, _modConfig, _baseAddress);

            // War of the Lions events: all data (tools/build_data.py) except Agrias's Birthday's reward
            if (_hooks != null)
                _agriasBirthday = new AgriasBirthday(startupScanner, _hooks, _logger, _modConfig, _baseAddress);

            else
                _logger.WriteLine($"[{_modConfig.ModId}] Error: no hooks API, Agrias's Birthday reward will not be granted");
        }

        private bool Found(bool found, string name)
        {
            if (!found)
                _logger.WriteLine($"[{_modConfig.ModId}] {name} could not be found");
            return found;
        }

        private unsafe void PatchEventRecords(nint firstRecord)
        {
            var patches = new List<MemoryPatch>();
            foreach (var patch in _eventRecords)
            {
                for (int i = 0; i < 0x377; i++)
                {
                    nint record = firstRecord + i * 0x18;
                    ushort id = *(ushort*)record;
                    if (id == 0) break;
                    if (id != patch.Event) continue;
                    byte value = *(byte*)(record + patch.Offset);
                    if (value != patch.From)
                        _logger.WriteLine($"[{_modConfig.ModId}] Warning: event {patch.Event} record +{patch.Offset} is {value}, expected {patch.From}; not changed");
                    else
                        patches.Add(new MemoryPatch($"Event {patch.Event} Record +{patch.Offset}", record + patch.Offset, new[] { patch.To }));
                    break;
                }
            }
            ApplyPatches(patches.ToArray());
        }

        private unsafe void TrySeedMonsterPaletteGlobal()
        {
            if (_ramzaJobAddress == 0 || _monsterPaletteGlobalAddress == 0)
                return;

            // Only fill it if the game has not set it; Ramza's entry has a monster palette of 0
            if (*(nint*)_monsterPaletteGlobalAddress == 0)
                ApplyPatches(new MemoryPatch("Monster Palette Pointer Default", _monsterPaletteGlobalAddress, BitConverter.GetBytes((long)_ramzaJobAddress)));
        }

        private unsafe void WarnIfPortraitEntryUsed(nint entry, PortraitMapping portrait)
        {
            ushort current = *(ushort*)entry;
            if (current != 0 && current != portrait.FaceId)
                _logger.WriteLine($"[{_modConfig.ModId}] Warning: portrait table entry {portrait.TableIndex} was already set to face id {current:X}, another mod may be using it");
        }

        private void WarnIfFaceIdUsed(nint entry, int faceId)
        {
            uint current = ReadUInt32(entry);
            if (current != uint.MaxValue)
                _logger.WriteLine($"[{_modConfig.ModId}] Warning: face id {faceId:X} was already mapped to wldface {current}, another mod may be using it");
        }

        private static unsafe uint ReadUInt32(nint address) => *(uint*)address;

        // Reads a rip-relative operand: target = instruction + instructionLength + disp32
        private static unsafe nint ResolveRipRelative(nint instruction, int displacementOffset, int instructionLength)
        {
            return instruction + instructionLength + *(int*)(instruction + displacementOffset);
        }

        // Finds every occurrence of a pattern within the PE section containing 'address'
        private unsafe List<nint> FindAllInSection(nint address, byte[] pattern)
        {
            var results = new List<nint>();
            var (start, size) = GetSectionBounds(address);
            if (size == 0)
                return results;

            var section = new ReadOnlySpan<byte>((void*)start, size);
            int offset = 0;
            while (true)
            {
                int index = section.Slice(offset).IndexOf(pattern);
                if (index < 0)
                    break;

                results.Add(start + offset + index);
                offset += index + 1;
            }
            return results;
        }

        private unsafe (nint Start, int Size) GetSectionBounds(nint address)
        {
            byte* pe = (byte*)_baseAddress + *(int*)(_baseAddress + 0x3C);
            ushort numSections = *(ushort*)(pe + 6);
            ushort optionalHeaderSize = *(ushort*)(pe + 20);
            byte* section = pe + 24 + optionalHeaderSize;
            for (int i = 0; i < numSections; i++, section += 40)
            {
                uint virtualSize = *(uint*)(section + 8);
                uint virtualAddress = *(uint*)(section + 12);
                nint start = _baseAddress + (nint)virtualAddress;
                if (address >= start && address < start + (nint)virtualSize)
                    return (start, (int)virtualSize);
            }
            return (0, 0);
        }

        private void ApplyPatches(params MemoryPatch[] patches)
        {
            // Scan callbacks may run concurrently and patches can share pages, so protection changes are serialized
            lock (_lock)
            {
                int successfulPatches = 0;
                foreach (var patch in patches)
                {
                    if (ApplySinglePatch(patch))
                        successfulPatches++;
                }

                if (successfulPatches != patches.Length)
                    _logger.WriteLine($"[{_modConfig.ModId}] Failed: {patches.Length - successfulPatches}/{patches.Length}");
            }
        }

        private unsafe bool ApplySinglePatch(MemoryPatch patch)
        {
            try
            {
                byte* ptr = (byte*)patch.Address;

                // Make memory writable
                if (!VirtualProtect(patch.Address, (UIntPtr)patch.Data.Length, MemoryProtection.ExecuteReadWrite, out uint oldProtect))
                {
                    _logger.WriteLine($"[{_modConfig.ModId}] Failed to change memory protection for '{patch.Description}'");
                    return false;
                }

                // Write the bytes
                for (int i = 0; i < patch.Data.Length; i++)
                {
                    ptr[i] = patch.Data[i];
                }

                // Restore original protection
                VirtualProtect(patch.Address, (UIntPtr)patch.Data.Length, (MemoryProtection)oldProtect, out _);

                // Verify the patch
                for (int i = 0; i < patch.Data.Length; i++)
                {
                    if (ptr[i] != patch.Data[i])
                    {
                        _logger.WriteLine($"[{_modConfig.ModId}] Verification failed for '{patch.Description}' at byte {i}");
                        return false;
                    }
                }

                _logger.WriteLine($"[{_modConfig.ModId}] Applied '{patch.Description}' at {patch.Address:X} ({patch.Data.Length} bytes)");
                return true;
            }
            catch (Exception ex)
            {
                _logger.WriteLine($"[{_modConfig.ModId}] Exception while applying '{patch.Description}': {ex.Message}");
                return false;
            }
        }

        #region Windows API
        [DllImport("kernel32.dll")]
        private static extern bool VirtualProtect(IntPtr lpAddress, UIntPtr dwSize,
            MemoryProtection flNewProtect, out uint lpflOldProtect);

        [Flags]
        private enum MemoryProtection : uint
        {
            Execute = 0x10,
            ExecuteRead = 0x20,
            ExecuteReadWrite = 0x40,
            ExecuteWriteCopy = 0x80,
            NoAccess = 0x01,
            ReadOnly = 0x02,
            ReadWrite = 0x04,
            WriteCopy = 0x08,
            GuardModifierflag = 0x100,
            NoCacheModifierflag = 0x200,
            WriteCombineModifierflag = 0x400
        }
        #endregion

        #region Standard Overrides
        public override void ConfigurationUpdated(Config configuration)
        {
            _configuration = configuration;
            _logger.WriteLine($"[{_modConfig.ModId}] Config Updated: Applying");
        }
        #endregion

        #region For Exports, Serialization etc.
#pragma warning disable CS8618
        public Mod() { }
#pragma warning restore CS8618
        #endregion
    }
}
