using Reloaded.Hooks.Definitions;
using Reloaded.Hooks.Definitions.Enums;
using Reloaded.Mod.Interfaces;
using System.Runtime.InteropServices;
using IReloadedHooks = Reloaded.Hooks.ReloadedII.Interfaces.IReloadedHooks;

namespace WotLCharacters
{
    /// <summary>
    /// Gives War of the Lions' own items (ids 0x100-0x13B) a home in IC, whose item code is WotL's own cut down to 261
    /// items (0-0xFD plus its bonus items 0x100-0x104). research/ITEM_EXPANSION.md has the whole map; in short:
    ///  - a page near the executable holds the per-item arrays sized for 0x105 ids (bag counts, the owned mirror), the
    ///    equipment bonus table (0x55 rows), the menu order charts and the new items' own records;
    ///  - every instruction addressing a moved array is re-pointed, the id bounds that must accept the new ids are
    ///    widened, and the item getters answer the new ids from the page (ItemSites.g.cs, tools/item_sites.py);
    ///  - the save never grows: the new items' counts ride in the event variable block's last bytes (no variable id
    ///    reaches them; the block is saved whole, battle suspends included), and the charts keep their vanilla save
    ///    fields current, so a save stays loadable without the mod (the new items then simply vanish).
    /// Every patched byte is checked before anything is written: a game update disarms the expansion, never half-arms it.
    /// </summary>
    internal unsafe class ItemExpansion
    {
        public static ItemExpansion? Instance { get; private set; }

        public const int FirstNewId = 0x105;
        private const int MaxCount = 99;

        // Every WotL item (ItemData.g.cs; text rows and icons in tools/build_data.py, WOTL_ITEMS). How each is obtained:
        // the Tynar Rouge from Agrias's Birthday (AgriasBirthday.cs); Ras Algethi and Mirage Vest on Balthier from IC's
        // own code (0x27176B, WotL's: unit 0xA2 set up for event 518 gets the table at 0x714460); the rest, as in
        // WotL, came from multiplayer modes IC does not have (research/ITEM_EXPANSION.md).
        private static readonly HashSet<int> Enabled = ItemData.Items.Select(i => i.Id).ToHashSet();

        // Page layout. Per-id tables cover ids 0x100-0x3FF (IC masks item ids with 0x3FF), indexed id - 0x100.
        private const int PageSize = 0x10000;
        private const int BAG = 0x0000, OWNED = 0x0800, ATTR = 0x1000, ALLITEMS = 0x3000, CHARTS = 0x4000,
            COMMON = 0x7000, WEAPON = 0xA000, SHIELD = 0xB800, ARMOR = 0xBE00, ACCESSORY = 0xC400, CHEMIST = 0xCA00,
            PAIR = 0xD400, RANGE = 0xDA00, DTYPE = 0xDD00, VALID = 0xE000, ZERO = 0xE300, STUB = 0xE400;
        private static readonly int[] ArrayOffsets = { BAG, OWNED, ATTR, ALLITEMS };   // ItemSites.Arrays order
        private const int TableFirst = 0x100, TableCount = 0x300;
        private const int ChartWords = 0x200, AllItemsWords = 0x400;
        private const int AttrRow = 0x1A, VanillaAttrRows = 0x55;
        private const ushort EndMarker = 0x00FF, Wall = 0xFFFF;

        // The new items' counts in the event variable block: +0x2FC "WC", version, 0, then one byte per id from 0x105.
        private const int TailOffset = 0x2FC, TailHeader = 4;
        private const int TailLength = TailHeader + ItemSites.MaxItemId - FirstNewId + 1;
        private static readonly byte[] TailMagic = { (byte)'W', (byte)'C', 1, 0 };

        private readonly ILogger _logger;
        private readonly IModConfig _modConfig;
        private readonly nint _base;
        private nint _page;
        private readonly object _sync = new();
        private readonly List<IAsmHook> _asmHooks = new();

        private readonly byte[] _lastTail = new byte[TailLength], _lastBagNew = new byte[TailLength - TailHeader];
        private readonly byte[] _lastBagOld = new byte[FirstNewId], _lastBagOldPage = new byte[FirstNewId];
        private readonly byte[] _lastAttr = new byte[VanillaAttrRows * AttrRow];
        private readonly List<Chart> _charts = new();

        private sealed class Chart
        {
            public nint Vanilla, Page; public int VanillaWords, PageWords;
            public ushort[] LastVanilla = Array.Empty<ushort>(), LastPage = Array.Empty<ushort>();
        }

        private ItemExpansion(ILogger logger, IModConfig modConfig, nint baseAddress)
        {
            _logger = logger; _modConfig = modConfig; _base = baseAddress;
        }

        /// <summary>Checks, then arms everything, or nothing. Call once, before the game runs.</summary>
        public static ItemExpansion? TryArm(IReloadedHooks hooks, ILogger logger, IModConfig modConfig, nint baseAddress)
        {
            var x = new ItemExpansion(logger, modConfig, baseAddress);
            try
            {
                var problems = x.Verify();
                if (problems.Count > 0)
                {
                    foreach (var p in problems.Take(8)) x.Log("Item expansion: " + p);
                    x.Log($"Item expansion NOT armed ({problems.Count} site(s) differ; game update?). WotL items are unavailable; " +
                          "rerun tools/item_sites.py on the new executable");
                    return null;
                }
                x.Arm(hooks);
                Instance = x;
                x.Log($"Item expansion armed: page {x._page:X}, {ItemSites.Relocations.Length} relocations, " +
                      $"{ItemSites.Bounds.Length} bounds, {x._asmHooks.Count} hooks, items {string.Join(", ", Enabled.Select(id => ItemName(id)))}");
                return x;
            }
            catch (Exception ex)
            {
                x.Log($"Item expansion failed to arm: {ex}");
                return null;
            }
        }

        public bool IsEnabled(int id) => Enabled.Contains(id);

        /// <summary>Adds n of an item to the party's bag (0..99), as the game's own bag accessor would.</summary>
        public int AddItem(int id, int n)
        {
            lock (_sync)
            {
                byte* count = (byte*)(_page + BAG + id);
                *count = (byte)Math.Clamp(*count + n, 0, MaxCount);
                return *count;
            }
        }

        // ---- checks -------------------------------------------------------------------------------------------------

        private List<string> Verify()
        {
            var problems = new List<string>();
            void Expect(uint rva, string hex, string what)
            {
                var want = Hex(hex);
                var got = new ReadOnlySpan<byte>((void*)(_base + (nint)rva), want.Length);
                if (!got.SequenceEqual(want)) problems.Add($"{what} at {rva:X}: expected {hex}, found {Convert.ToHexString(got)}");
            }
            foreach (var r in ItemSites.Relocations) Expect(r.Rva, r.Bytes, "relocation");
            foreach (var b in ItemSites.Bounds) Expect(b.Rva, b.Old, "bound (" + b.Why + ")");
            foreach (var c in ItemSites.LowValidityCalls) Expect(c.Rva, c.Bytes, "IsValidItem call");
            foreach (var h in ItemSites.Hooks) Expect(h.Rva, h.Bytes, "getter " + h.Name);
            foreach (var a in ItemSites.Anchors) Expect(a.Rva, a.Bytes, a.Name);
            foreach (var s in ItemSites.Slots)
            {
                nint value = *(nint*)(_base + (nint)s.Slot);
                if (value != _base + (nint)s.Chart) problems.Add($"chart slot {s.Slot:X} holds {value - _base:X}, expected {s.Chart:X} (another mod?)");
            }
            return problems;
        }

        // ---- arming -------------------------------------------------------------------------------------------------

        private void Arm(IReloadedHooks hooks)
        {
            _page = AllocateNear(PageSize);
            FillPage();

            // Hooks are built (assembled) first and switched on last: a failure here leaves the game untouched
            CreateGetterHooks(hooks);
            CreateSaveHook(hooks);

            // Code: relocations (all computed before any is written), bounds, the low-id validity stub
            var displacements = ItemSites.Relocations.Select(r =>
            {
                nint insn = _base + (nint)r.Rva;
                nint target = _page + ArrayOffsets[r.Array] + r.Delta;
                long disp = r.Rip ? (long)target - (long)(insn + Hex(r.Bytes).Length) : (long)target - (long)_base;
                if (disp < int.MinValue || disp > int.MaxValue) throw new InvalidOperationException($"{r.Rva:X}: page out of reach");
                return (Address: insn + r.DispOffset, Disp: (int)disp);
            }).ToList();
            foreach (var d in displacements) Write(d.Address, BitConverter.GetBytes(d.Disp));
            foreach (var b in ItemSites.Bounds) Write(_base + (nint)b.Rva, Hex(b.New));
            WriteLowValidityStub();
            foreach (var c in ItemSites.LowValidityCalls)
            {
                nint call = _base + (nint)c.Rva;
                Write(call + 1, BitConverter.GetBytes((int)(_page + STUB - (call + 5))));
            }

            // Menu order charts: the live readers go through these slots
            foreach (var s in ItemSites.Slots)
            {
                var chart = _charts.First(c => c.Vanilla == _base + (nint)s.Chart);
                Write(_base + (nint)s.Slot, BitConverter.GetBytes((long)chart.Page));
            }

            lock (_sync) Sync();
            foreach (var h in _asmHooks) h.Activate();
            new Thread(SyncLoop) { IsBackground = true, Name = "WotL items sync" }.Start();
        }

        private void FillPage()
        {
            new Span<byte>((void*)_page, PageSize).Clear();

            // Arrays: the vanilla contents first (zero at boot, but a late arm would keep the state)
            Copy(_base + 0x11A7C00, _page + BAG, FirstNewId);
            Copy(_base + 0x3C52740, _page + OWNED, FirstNewId);
            Copy(_base + 0x80FEA0, _page + ATTR, VanillaAttrRows * AttrRow);
            Fill16(_page + ALLITEMS, AllItemsWords, Wall);
            Fill16(_page + CHARTS, ChartWords * 9, Wall);

            // Charts: the nine the slots reach (Items tab x5, equip picker x4) and the picker's all-items chart
            int next = 0;
            foreach (var s in ItemSites.Slots)
            {
                if (_charts.Any(c => c.Vanilla == _base + (nint)s.Chart)) continue;
                _charts.Add(NewChart(_base + (nint)s.Chart, s.Words, _page + CHARTS + next++ * ChartWords * 2, ChartWords));
            }
            _charts.Add(NewChart(_base + 0x1874726, 263, _page + ALLITEMS, AllItemsWords));

            // Per-id tables: everything answers "no item" unless enabled
            new Span<byte>((void*)(_page + RANGE), TableCount).Fill(0xFF);
            new Span<byte>((void*)(_page + DTYPE), TableCount).Fill(0xFF);
            foreach (var it in ItemData.Items)
            {
                if (it.AttrRow >= 0) Copy(Hex(it.Attr), _page + ATTR + it.AttrRow * AttrRow);
                if (!Enabled.Contains(it.Id)) continue;
                int i = it.Id - TableFirst;
                Copy(Hex(it.Common), _page + COMMON + i * 12);
                ((byte*)(_page + RANGE))[i] = (byte)it.RangeIndex;
                ((byte*)(_page + DTYPE))[i] = (byte)it.DataType;
                ((byte*)(_page + VALID))[i] = 1;
                var sub = Hex(it.Sub);
                switch (it.DataType)
                {
                    case 5: Copy(sub, _page + WEAPON + i * 8); break;
                    case 6: Copy(sub, _page + SHIELD + i * 2); break;
                    case 7: Copy(sub, _page + ARMOR + i * 2); break;
                    case 8: Copy(sub, _page + ACCESSORY + i * 2); break;
                    case 9: Copy(sub, _page + CHEMIST + i * 3); break;
                }
                if (it.Pair.Length > 0) Copy(Hex(it.Pair), _page + PAIR + i * 2);
            }
        }

        private Chart NewChart(nint vanilla, int vanillaWords, nint page, int pageWords)
        {
            var c = new Chart { Vanilla = vanilla, VanillaWords = vanillaWords, Page = page, PageWords = pageWords };
            Adopt(c, Read16(vanilla, vanillaWords));
            return c;
        }

        // IsValidItem for code that sizes buffers for 0x105 ids: refuses the new ids, then asks the real one.
        private void WriteLowValidityStub()
        {
            var code = new List<byte> { 0x0F, 0xB7, 0xC1, 0x3D, 0x05, 0x01, 0x00, 0x00, 0x73, 0x0C, 0x48, 0xB8 }; // movzx eax,cx; cmp eax,0x105; jae no; mov rax,
            code.AddRange(BitConverter.GetBytes((long)(_base + 0x2B8EBC)));
            code.AddRange(new byte[] { 0xFF, 0xE0, 0x31, 0xC0, 0xC3 });                                           // jmp rax; no: xor eax,eax; ret
            Copy(code.ToArray(), _page + STUB);
        }

        private void CreateGetterHooks(IReloadedHooks hooks)
        {
            string P(int offset) => $"0x{(long)(_page + offset):X}";
            string Entry(string rest) => string.Join('\n', "use64", "movzx eax, cx", "cmp eax, 0x105", "jb orig", "cmp eax, 0x400", rest, "orig:");
            string Sub(int type, int size, int table) => Entry(string.Join('\n',
                "jae none", $"mov rdx, {P(DTYPE - TableFirst)}", $"cmp byte [rdx+rax], {type}", "jne none",
                $"imul eax, eax, {size}", $"mov rdx, {P(table - TableFirst * size)}", "add rax, rdx", "ret",
                "none:", "xor eax, eax", "ret"));
            var code = new Dictionary<string, string>
            {
                // range index (0-12; index % 7 is the category), or -1
                ["SecondaryItemType"] = Entry(string.Join('\n', "jae bad", $"mov rdx, {P(RANGE - TableFirst)}",
                    "movsx eax, byte [rdx+rax]", "ret", "bad:", "or eax, -1", "ret")),
                // 12-byte common record (an all-zero one, "no item", past the table)
                ["ItemCommon"] = Entry(string.Join('\n', "jae zero", "lea rax, [rax+rax*2]", $"mov rdx, {P(COMMON - TableFirst * 12)}",
                    "lea rax, [rdx+rax*4]", "ret", "zero:", $"mov rax, {P(ZERO)}", "ret")),
                ["ItemWeapon"] = Sub(5, 8, WEAPON),
                ["ItemShield"] = Sub(6, 2, SHIELD),
                ["ItemArmor"] = Sub(7, 2, ARMOR),
                ["ItemAccessory"] = Sub(8, 2, ACCESSORY),
                ["ItemChemist"] = Sub(9, 3, CHEMIST),
                // weapon / shield sprite pair
                ["ItemSpritePair"] = Entry(string.Join('\n', "jae none", $"mov rdx, {P(DTYPE - TableFirst)}",
                    "movzx edx, byte [rdx+rax]", "cmp edx, 5", "je pair", "cmp edx, 6", "jne none", "pair:",
                    "add eax, eax", $"mov rdx, {P(PAIR - TableFirst * 2)}", "add rax, rdx", "ret", "none:", "xor eax, eax", "ret")),
                ["IsValidItem"] = Entry(string.Join('\n', "jae no", $"mov rdx, {P(VALID - TableFirst)}",
                    "movzx eax, byte [rdx+rax]", "ret", "no:", "xor eax, eax", "ret")),
            };
            foreach (var h in ItemSites.Hooks)
                _asmHooks.Add(hooks.CreateAsmHook(code[h.Name].Split('\n'), (long)(_base + (nint)h.Rva), AsmHookBehaviour.ExecuteFirst));
        }

        // The serializer: flush the sync first, so a save made right after an item changed hands carries it.
        private void CreateSaveHook(IReloadedHooks hooks)
        {
            delegate* unmanaged<void> flush = &OnSave;
            var code = new[] { "use64", "push rax", "push rcx", "push rdx", "push r8", "push r9", "push r10", "push r11",
                "sub rsp, 0x20", $"mov rax, 0x{(long)flush:X}", "call rax", "add rsp, 0x20",
                "pop r11", "pop r10", "pop r9", "pop r8", "pop rdx", "pop rcx", "pop rax" };
            uint rva = ItemSites.Anchors.First(a => a.Name == "SaveSerializer").Rva;
            _asmHooks.Add(hooks.CreateAsmHook(code, (long)(_base + (nint)rva), AsmHookBehaviour.ExecuteFirst));
        }

        [UnmanagedCallersOnly]
        private static void OnSave()
        {
            var x = Instance;
            if (x == null) return;
            try { lock (x._sync) x.Sync(); }
            catch (Exception ex) { x.Log("Item sync at save failed: " + ex.Message); }
        }

        // ---- sync ---------------------------------------------------------------------------------------------------

        private void SyncLoop()
        {
            while (true)
            {
                Thread.Sleep(50);
                try { lock (_sync) Sync(); }
                catch (Exception ex) { Log("Item sync failed: " + ex.Message); Thread.Sleep(5000); }
            }
        }

        /// <summary>
        /// Two-way sync between what the game works on (the page) and what it saves and loads (vanilla places). A vanilla
        /// place that changed since the last sync was written by the game's load, new game or battle restore (or a tool):
        /// the page adopts it. Otherwise a page that changed is projected back onto the vanilla place.
        /// </summary>
        private void Sync()
        {
            SyncNewCounts();
            SyncOldCounts();
            foreach (var c in _charts) SyncChart(c);
            SyncAttributes();
        }

        private void SyncNewCounts()
        {
            nint block = *(nint*)(_base + (nint)ItemSites.VarsPointer);
            if (block == 0) return;
            var tail = new Span<byte>((void*)(block + TailOffset), TailLength);
            var bag = new Span<byte>((void*)(_page + BAG + FirstNewId), TailLength - TailHeader);
            if (!tail.SequenceEqual(_lastTail))
            {
                bool ours = tail[..TailHeader].SequenceEqual(TailMagic);
                for (int i = 0; i < bag.Length; i++) bag[i] = ours ? Math.Min(tail[TailHeader + i], (byte)MaxCount) : (byte)0;
            }
            else if (bag.SequenceEqual(_lastBagNew)) return;
            TailMagic.CopyTo(tail);
            bag.CopyTo(tail[TailHeader..]);
            tail.CopyTo(_lastTail);
            bag.CopyTo(_lastBagNew);
        }

        // The game (its save copies included) now works on the page's bag. The vanilla bag, ids 0-0x104, is kept equal to
        // it both ways for whatever else reads or edits it there (cheat tables, save tools, other mods).
        private void SyncOldCounts()
        {
            var vanilla = new Span<byte>((void*)(_base + 0x11A7C00), FirstNewId);
            var page = new Span<byte>((void*)(_page + BAG), FirstNewId);
            if (!vanilla.SequenceEqual(_lastBagOld)) vanilla.CopyTo(page);
            else if (!page.SequenceEqual(_lastBagOldPage)) page.CopyTo(vanilla);
            else return;
            vanilla.CopyTo(_lastBagOld);
            page.CopyTo(_lastBagOldPage);
        }

        private void SyncChart(Chart c)
        {
            var vanilla = Read16(c.Vanilla, c.VanillaWords);
            if (!vanilla.AsSpan().SequenceEqual(c.LastVanilla)) { Adopt(c, vanilla); return; }
            var page = Read16(c.Page, c.PageWords);
            if (page.AsSpan().SequenceEqual(c.LastPage)) return;
            // Project: vanilla ids only (a save loaded without the mod must not meet a new id), up to its capacity
            var kinds = new List<ushort>();
            foreach (var w in page)
            {
                if (w == EndMarker || w >= Wall) break;
                if (w < FirstNewId && kinds.Count < c.VanillaWords - 1) kinds.Add(w);
            }
            kinds.Add(EndMarker);
            for (int i = 0; i < kinds.Count; i++) ((ushort*)c.Vanilla)[i] = kinds[i];
            c.LastVanilla = Read16(c.Vanilla, c.VanillaWords);
            c.LastPage = page;
        }

        // Page = vanilla up to its end marker (or its capacity, if the marker is missing), the marker, then a wall of
        // 0xFFFF words: the charts' walks stop at the marker or at any word above the id bound, never run off the page.
        private static void Adopt(Chart c, ushort[] vanilla)
        {
            int n = 0;
            while (n < vanilla.Length && vanilla[n] != EndMarker) n++;
            var page = (ushort*)c.Page;
            for (int i = 0; i < n; i++) page[i] = vanilla[i];
            page[n] = EndMarker;
            for (int i = n + 1; i < c.PageWords; i++) page[i] = Wall;
            c.LastVanilla = vanilla;
            c.LastPage = Read16(c.Page, c.PageWords);
        }

        // Equipment bonus rows 0-0x54 follow the vanilla table (fftivc.utility.modloader and other mods edit it there)
        private void SyncAttributes()
        {
            var vanilla = new Span<byte>((void*)(_base + 0x80FEA0), _lastAttr.Length);
            if (vanilla.SequenceEqual(_lastAttr)) return;
            vanilla.CopyTo(new Span<byte>((void*)(_page + ATTR), _lastAttr.Length));
            vanilla.CopyTo(_lastAttr);
        }

        // ---- helpers ------------------------------------------------------------------------------------------------

        private nint AllocateNear(int size)
        {
            uint imageSize = *(uint*)(_base + *(int*)(_base + 0x3C) + 0x50);
            long start = ((long)_base + imageSize + 0xFFFF) & ~0xFFFFL;
            for (long a = start; a < (long)_base + 0x7F000000L - size; a += 0x10000)
            {
                nint p = VirtualAlloc((nint)a, (nuint)size, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
                if (p != 0) return p;
            }
            throw new InvalidOperationException("no free memory within 2 GB of the executable");
        }

        private static readonly object ProtectLock = new();
        private static void Write(nint address, byte[] bytes)
        {
            lock (ProtectLock)
            {
                if (!VirtualProtect(address, (nuint)bytes.Length, PAGE_EXECUTE_READWRITE, out uint old))
                    throw new InvalidOperationException($"VirtualProtect failed at {address:X}");
                Marshal.Copy(bytes, 0, address, bytes.Length);
                VirtualProtect(address, (nuint)bytes.Length, old, out _);
            }
        }

        private static void Copy(nint from, nint to, int length) => Buffer.MemoryCopy((void*)from, (void*)to, length, length);
        private static void Copy(byte[] from, nint to) => Marshal.Copy(from, 0, to, from.Length);
        private static void Fill16(nint at, int words, ushort value) => new Span<ushort>((void*)at, words).Fill(value);
        private static ushort[] Read16(nint at, int words) => new ReadOnlySpan<ushort>((void*)at, words).ToArray();
        private static byte[] Hex(string hex) => hex.Length == 0 ? Array.Empty<byte>() : Convert.FromHexString(hex.Replace(" ", ""));
        private static string ItemName(int id) => ItemData.Items.FirstOrDefault(i => i.Id == id).Name ?? $"{id:X}";
        private void Log(string message) => _logger.WriteLine($"[{_modConfig.ModId}] {message}");

        private const uint MEM_COMMIT = 0x1000, MEM_RESERVE = 0x2000, PAGE_EXECUTE_READWRITE = 0x40;
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern nint VirtualAlloc(nint address, nuint size, uint type, uint protect);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool VirtualProtect(nint address, nuint size, uint newProtect, out uint oldProtect);
    }
}
