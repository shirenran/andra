"""Minimal DEX parser for class / method / string search (no native deps)."""

from __future__ import annotations

import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class DexError(RuntimeError):
    pass


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]


def _sleb128(data: bytes, off: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        b = data[off]
        off += 1
        result |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            if shift < 35 and (b & 0x40):
                result |= -(1 << (shift + 7))
            return result, off
        shift += 7


def _uleb128(data: bytes, off: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        b = data[off]
        off += 1
        result |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            return result, off
        shift += 7


def _uleb128p1(data: bytes, off: int) -> tuple[int, int]:
    v, off = _uleb128(data, off)
    return v - 1, off


@dataclass(frozen=True)
class MethodRef:
    class_name: str
    name: str
    proto: str
    access_flags: int | None = None

    @property
    def signature(self) -> str:
        return f"{self.class_name}->{self.name}{self.proto}"


@dataclass(frozen=True)
class FieldRef:
    class_name: str
    name: str
    type_name: str

    @property
    def signature(self) -> str:
        return f"{self.class_name}->{self.name}:{self.type_name}"


class DexFile:
    def __init__(self, data: bytes, source: str = "<memory>"):
        if len(data) < 0x70 or data[:4] != b"dex\n":
            raise DexError(f"Not a DEX file: {source}")
        self.data = data
        self.source = source
        self.string_ids_size = _u32(data, 56)
        self.string_ids_off = _u32(data, 60)
        self.type_ids_size = _u32(data, 64)
        self.type_ids_off = _u32(data, 68)
        self.proto_ids_size = _u32(data, 72)
        self.proto_ids_off = _u32(data, 76)
        self.field_ids_size = _u32(data, 80)
        self.field_ids_off = _u32(data, 84)
        self.method_ids_size = _u32(data, 88)
        self.method_ids_off = _u32(data, 92)
        self.class_defs_size = _u32(data, 96)
        self.class_defs_off = _u32(data, 100)

        self._strings: list[str] | None = None
        self._types: list[str] | None = None
        self._classes: list[str] | None = None
        self._methods: list[MethodRef] | None = None
        self._fields: list[FieldRef] | None = None

    @classmethod
    def from_path(cls, path: Path) -> "DexFile":
        return cls(path.read_bytes(), str(path))

    def string(self, idx: int) -> str:
        if idx < 0 or idx >= self.string_ids_size:
            raise DexError(f"string_id out of range: {idx}")
        off = _u32(self.data, self.string_ids_off + idx * 4)
        # MUTF-8 string data: uleb128 length, then bytes
        _size, p = _uleb128(self.data, off)
        end = self.data.index(b"\x00", p)
        raw = self.data[p:end]
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="replace")

    def type_name(self, idx: int) -> str:
        if idx < 0 or idx >= self.type_ids_size:
            raise DexError(f"type_id out of range: {idx}")
        str_idx = _u32(self.data, self.type_ids_off + idx * 4)
        return descriptor_to_java(self.string(str_idx))

    def proto(self, idx: int) -> str:
        # proto_id_item: shorty_idx, return_type_idx, parameters_off
        base = self.proto_ids_off + idx * 12
        ret = self.type_name(_u32(self.data, base + 4))
        params_off = _u32(self.data, base + 8)
        params: list[str] = []
        if params_off:
            size = _u32(self.data, params_off)
            for i in range(size):
                type_idx = _u16(self.data, params_off + 4 + i * 2)
                params.append(self.type_name(type_idx))
        return f"({', '.join(params)}){ret}"

    @property
    def strings(self) -> list[str]:
        if self._strings is None:
            self._strings = [self.string(i) for i in range(self.string_ids_size)]
        return self._strings

    @property
    def types(self) -> list[str]:
        if self._types is None:
            self._types = [self.type_name(i) for i in range(self.type_ids_size)]
        return self._types

    @property
    def classes(self) -> list[str]:
        if self._classes is None:
            out: list[str] = []
            for i in range(self.class_defs_size):
                base = self.class_defs_off + i * 32
                class_idx = _u32(self.data, base)
                out.append(self.type_name(class_idx))
            self._classes = out
        return self._classes

    def class_defs(self) -> list[dict]:
        """Return class_def metadata including superclass and access flags."""
        out: list[dict] = []
        for i in range(self.class_defs_size):
            base = self.class_defs_off + i * 32
            class_idx = _u32(self.data, base)
            access = _u32(self.data, base + 4)
            super_idx = _u32(self.data, base + 8)
            interfaces_off = _u32(self.data, base + 12)
            source_file_idx = _u32(self.data, base + 16)
            class_data_off = _u32(self.data, base + 24)
            interfaces: list[str] = []
            if interfaces_off:
                n = _u32(self.data, interfaces_off)
                for j in range(n):
                    interfaces.append(self.type_name(_u16(self.data, interfaces_off + 4 + j * 2)))
            source = None
            if source_file_idx != 0xFFFFFFFF:
                try:
                    source = self.string(source_file_idx)
                except DexError:
                    source = None
            out.append(
                {
                    "class": self.type_name(class_idx),
                    "access_flags": access,
                    "super": self.type_name(super_idx) if super_idx != 0xFFFFFFFF else None,
                    "interfaces": interfaces,
                    "source_file": source,
                    "class_data_off": class_data_off,
                }
            )
        return out

    def iter_defined_method_codes(self) -> Iterable[tuple[MethodRef, int]]:
        """Yield (MethodRef, code_item_offset) for methods that have code."""
        for cdef in self.class_defs():
            off = cdef["class_data_off"]
            if not off:
                continue
            class_name = cdef["class"]
            static_fields_size, off = _uleb128(self.data, off)
            instance_fields_size, off = _uleb128(self.data, off)
            direct_methods_size, off = _uleb128(self.data, off)
            virtual_methods_size, off = _uleb128(self.data, off)

            for _ in range(static_fields_size + instance_fields_size):
                _, off = _uleb128(self.data, off)
                _, off = _uleb128(self.data, off)

            def read_methods(count: int, start_off: int) -> int:
                method_idx = 0
                cur = start_off
                for _ in range(count):
                    diff, cur = _uleb128(self.data, cur)
                    access, cur = _uleb128(self.data, cur)
                    code_off, cur = _uleb128(self.data, cur)
                    method_idx += diff
                    mbase = self.method_ids_off + method_idx * 8
                    class_idx = _u16(self.data, mbase)
                    proto_idx = _u16(self.data, mbase + 2)
                    name_idx = _u32(self.data, mbase + 4)
                    ref = MethodRef(
                        class_name=self.type_name(class_idx)
                        if class_idx < self.type_ids_size
                        else class_name,
                        name=self.string(name_idx),
                        proto=self.proto(proto_idx),
                        access_flags=access,
                    )
                    if code_off:
                        yield_buf.append((ref, code_off))
                return cur

            yield_buf: list[tuple[MethodRef, int]] = []
            off = read_methods(direct_methods_size, off)
            off = read_methods(virtual_methods_size, off)
            yield from yield_buf

    def _parse_class_data_methods(self) -> list[MethodRef]:
        """All methods declared in class_data (with or without code)."""
        methods: list[MethodRef] = []
        for cdef in self.class_defs():
            off = cdef["class_data_off"]
            if not off:
                continue
            class_name = cdef["class"]
            static_fields_size, off = _uleb128(self.data, off)
            instance_fields_size, off = _uleb128(self.data, off)
            direct_methods_size, off = _uleb128(self.data, off)
            virtual_methods_size, off = _uleb128(self.data, off)
            for _ in range(static_fields_size + instance_fields_size):
                _, off = _uleb128(self.data, off)
                _, off = _uleb128(self.data, off)

            def read_methods(count: int, start_off: int) -> int:
                method_idx = 0
                cur = start_off
                for _ in range(count):
                    diff, cur = _uleb128(self.data, cur)
                    access, cur = _uleb128(self.data, cur)
                    code_off, cur = _uleb128(self.data, cur)
                    method_idx += diff
                    mbase = self.method_ids_off + method_idx * 8
                    class_idx = _u16(self.data, mbase)
                    proto_idx = _u16(self.data, mbase + 2)
                    name_idx = _u32(self.data, mbase + 4)
                    methods.append(
                        MethodRef(
                            class_name=self.type_name(class_idx)
                            if class_idx < self.type_ids_size
                            else class_name,
                            name=self.string(name_idx),
                            proto=self.proto(proto_idx),
                            access_flags=access,
                        )
                    )
                    _ = code_off
                return cur

            off = read_methods(direct_methods_size, off)
            off = read_methods(virtual_methods_size, off)
        return methods

    def scan_invokes_and_strings(self) -> tuple[dict[int, list[MethodRef]], dict[int, list[MethodRef]]]:
        """
        Scan all method bytecode once.

        Returns:
          invoke_map: method_id -> list of caller MethodRefs
          string_map: string_id -> list of MethodRefs that load the string
        """
        # opcode sizes in code units (16-bit)
        # From dalvik opcodes — default 1; overrides for multi-unit
        OP_SIZE = [1] * 256
        for op, sz in {
            0x00: 1,  # nop
            # 12x / 11x / 10x mostly 1
            0x14: 3,  # const/high16
            0x15: 2,  # const/high16 actually 2? const/high16 is 21s -> 2
            0x16: 3,  # const-wide/16
            0x17: 3,  # const-wide/32
            0x18: 5,  # const-wide
            0x19: 2,  # const-wide/high16
            0x1A: 2,  # const-string
            0x1B: 3,  # const-string/jumbo
            0x1C: 2,  # const-class
            0x20: 2,  # instance-of
            0x22: 2,  # new-instance
            0x1F: 2,  # check-cast
            0x24: 3,  # filled-new-array
            0x25: 3,  # filled-new-array/range
            0x26: 3,  # fill-array-data
            0x27: 1,
            0x28: 1,  # goto
            0x29: 2,  # goto/16
            0x2A: 3,  # goto/32
            0x2B: 3,  # packed-switch
            0x2C: 3,  # sparse-switch
            # 2d-31 if 2
            **{op: 2 for op in range(0x2D, 0x32)},
            **{op: 2 for op in range(0x32, 0x3E)},  # if-eq ... if-lez
            0x3E: 1,
            # 44-51 iget/iput etc 2
            **{op: 2 for op in range(0x44, 0x6E)},
            # 6e-72 invoke 3
            **{op: 3 for op in range(0x6E, 0x73)},
            # 74-78 invoke-range 3
            **{op: 3 for op in range(0x74, 0x79)},
            **{op: 3 for op in (0x14,)},  # const 31i = 3
            0x13: 2,  # const/16
            0x12: 1,  # const/4
            0x15: 2,
            # 01-0e moves mostly 1; 03 move-long 1; some 2
            0x03: 1,
            0x02: 1,
            0x05: 1,
            0x06: 1,
            0x08: 1,
            0x09: 1,
            # 0a-0e 1
            # array op 2
            **{op: 2 for op in range(0x21, 0x23)},
            0x23: 2,  # new-array
            # 7b-8f conversions 1
            # 90-af binop 2
            **{op: 2 for op in range(0x90, 0xB0)},
            **{op: 2 for op in range(0xB0, 0xD0)},
            **{op: 2 for op in range(0xD0, 0xE3)},
            # 0xfb+ unused
        }.items():
            OP_SIZE[op] = sz
        # Fix known multi-unit
        OP_SIZE[0x14] = 3  # const
        OP_SIZE[0x15] = 2
        OP_SIZE[0x16] = 3
        OP_SIZE[0x17] = 3
        OP_SIZE[0x18] = 5
        OP_SIZE[0x19] = 2
        OP_SIZE[0x1A] = 2
        OP_SIZE[0x1B] = 3
        OP_SIZE[0x1C] = 2
        for op in range(0x6E, 0x73):
            OP_SIZE[op] = 3
        for op in range(0x74, 0x79):
            OP_SIZE[op] = 3
        # invoke-polymorphic 4/4
        OP_SIZE[0xFA] = 4
        OP_SIZE[0xFB] = 4
        OP_SIZE[0xFC] = 3  # invoke-custom
        OP_SIZE[0xFD] = 3
        OP_SIZE[0xFE] = 2  # const-method-handle
        OP_SIZE[0xFF] = 2

        invoke_map: dict[int, list[MethodRef]] = {}
        string_map: dict[int, list[MethodRef]] = {}

        data = self.data
        for caller, code_off in self.iter_defined_method_codes():
            # code_item: registers_size u16, ins u16, outs u16, tries u16,
            # debug_info off u32, insns_size u32, insns[]
            insns_size = _u32(data, code_off + 12)
            insns_off = code_off + 16
            end = insns_off + insns_size * 2
            p = insns_off
            while p + 2 <= end:
                op = data[p]
                # packed payload pseudo-opcodes
                if op == 0x00 and p + 2 <= end:
                    # might be nop or switch payload — if second byte non-zero could be packed
                    second = data[p + 1]
                    if second == 0x01:  # packed-switch payload
                        # ident, size, first_key, targets...
                        if p + 8 <= end:
                            size = _u16(data, p + 2)
                            p += 8 + size * 4
                            continue
                    if second == 0x02:  # sparse-switch
                        if p + 4 <= end:
                            size = _u16(data, p + 2)
                            p += 4 + size * 8
                            continue
                    if second == 0x03:  # fill-array-data
                        if p + 8 <= end:
                            element_width = _u16(data, p + 2)
                            size = _u32(data, p + 4)
                            payload = (size * element_width + 1) // 2  # code units
                            p += 8 + payload * 2
                            continue

                size = OP_SIZE[op] if op < 256 else 1
                units = max(1, size)

                if op == 0x1A and p + 4 <= end:  # const-string BBBB
                    str_idx = _u16(data, p + 2)
                    string_map.setdefault(str_idx, []).append(caller)
                elif op == 0x1B and p + 6 <= end:  # const-string/jumbo
                    str_idx = _u32(data, p + 2)
                    string_map.setdefault(str_idx, []).append(caller)
                elif 0x6E <= op <= 0x72 and p + 6 <= end:
                    # invoke-kind: op, A|G, BBBB method, DC, FE
                    method_idx = _u16(data, p + 2)
                    invoke_map.setdefault(method_idx, []).append(caller)
                elif 0x74 <= op <= 0x78 and p + 6 <= end:
                    # invoke-kind/range: op, AA, BBBB, CCCC
                    method_idx = _u16(data, p + 2)
                    invoke_map.setdefault(method_idx, []).append(caller)
                elif op in (0xFA, 0xFB) and p + 8 <= end:
                    method_idx = _u16(data, p + 2)
                    invoke_map.setdefault(method_idx, []).append(caller)

                p += units * 2
                # safety
                if units <= 0:
                    p += 2

        return invoke_map, string_map

    def method_id_index(self, class_name: str, method_name: str) -> list[int]:
        """Return method_id indices matching class+name (any proto)."""
        hits: list[int] = []
        for i in range(self.method_ids_size):
            base = self.method_ids_off + i * 8
            cidx = _u16(self.data, base)
            nidx = _u32(self.data, base + 4)
            if self.string(nidx) != method_name:
                continue
            if self.type_name(cidx) == class_name:
                hits.append(i)
        return hits

    def method_ref_at(self, method_id: int) -> MethodRef:
        base = self.method_ids_off + method_id * 8
        return MethodRef(
            class_name=self.type_name(_u16(self.data, base)),
            name=self.string(_u32(self.data, base + 4)),
            proto=self.proto(_u16(self.data, base + 2)),
        )

    @property
    def methods(self) -> list[MethodRef]:
        if self._methods is None:
            # Prefer method_id table (all referenced methods) + enrich defined ones
            refs: list[MethodRef] = []
            for i in range(self.method_ids_size):
                base = self.method_ids_off + i * 8
                class_idx = _u16(self.data, base)
                proto_idx = _u16(self.data, base + 2)
                name_idx = _u32(self.data, base + 4)
                refs.append(
                    MethodRef(
                        class_name=self.type_name(class_idx),
                        name=self.string(name_idx),
                        proto=self.proto(proto_idx),
                    )
                )
            self._methods = refs
        return self._methods

    @property
    def defined_methods(self) -> list[MethodRef]:
        return self._parse_class_data_methods()

    @property
    def fields(self) -> list[FieldRef]:
        if self._fields is None:
            out: list[FieldRef] = []
            for i in range(self.field_ids_size):
                base = self.field_ids_off + i * 8
                class_idx = _u16(self.data, base)
                type_idx = _u16(self.data, base + 2)
                name_idx = _u32(self.data, base + 4)
                out.append(
                    FieldRef(
                        class_name=self.type_name(class_idx),
                        name=self.string(name_idx),
                        type_name=self.type_name(type_idx),
                    )
                )
            self._fields = out
        return self._fields


def descriptor_to_java(desc: str) -> str:
    """Convert DEX type descriptor to Java-ish name."""
    if not desc:
        return desc
    dims = 0
    while desc.startswith("["):
        dims += 1
        desc = desc[1:]
    prim = {
        "V": "void",
        "Z": "boolean",
        "B": "byte",
        "S": "short",
        "C": "char",
        "I": "int",
        "J": "long",
        "F": "float",
        "D": "double",
    }
    if desc in prim:
        name = prim[desc]
    elif desc.startswith("L") and desc.endswith(";"):
        name = desc[1:-1].replace("/", ".")
    else:
        name = desc
    return name + ("[]" * dims)


class ApkIndex:
    """Multi-DEX index over an APK or directory of .dex files."""

    def __init__(self, dexes: list[DexFile], source: str):
        self.dexes = dexes
        self.source = source
        # per-dex caches: list of (invoke_map, string_map) aligned with self.dexes
        self._xref_cache: list[tuple[dict[int, list[MethodRef]], dict[int, list[MethodRef]]] | None] | None = None

    def _ensure_xref(self) -> list[tuple[dict[int, list[MethodRef]], dict[int, list[MethodRef]]]]:
        if self._xref_cache is not None and all(x is not None for x in self._xref_cache):
            return self._xref_cache  # type: ignore
        self._xref_cache = []
        for dex in self.dexes:
            self._xref_cache.append(dex.scan_invokes_and_strings())
        return self._xref_cache  # type: ignore

    @classmethod
    def load(cls, path: str | Path) -> "ApkIndex":
        path = Path(path).expanduser().resolve()
        if not path.exists():
            raise DexError(f"Path not found: {path}")

        dexes: list[DexFile] = []
        if path.suffix.lower() == ".dex":
            dexes.append(DexFile.from_path(path))
        elif path.is_dir():
            for p in sorted(path.glob("*.dex")):
                dexes.append(DexFile.from_path(p))
            if not dexes:
                raise DexError(f"No .dex files in directory: {path}")
        else:
            # APK / ZIP
            with zipfile.ZipFile(path) as zf:
                names = [n for n in zf.namelist() if n.endswith(".dex")]
                if not names:
                    raise DexError(f"No classes*.dex in {path}")
                for name in sorted(names):
                    dexes.append(DexFile(zf.read(name), f"{path}!{name}"))
        return cls(dexes, str(path))

    def search_classes(self, keyword: str, limit: int = 20, offset: int = 0) -> list[str]:
        kw = keyword.lower()
        hits: list[str] = []
        seen: set[str] = set()
        for dex in self.dexes:
            for name in dex.classes:
                if kw in name.lower() and name not in seen:
                    seen.add(name)
                    hits.append(name)
        return hits[offset : offset + limit]

    def find_class(
        self,
        class_name_pattern: str | None = None,
        pkg: list[str] | None = None,
        super_class: str | None = None,
        interfaces: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        hits: list[dict] = []
        for dex in self.dexes:
            for cdef in dex.class_defs():
                name = cdef["class"]
                if class_name_pattern:
                    # exact full name OR simple name exact OR contains (Andra-like: exact first, fuzzy ok)
                    simple = name.rsplit(".", 1)[-1]
                    pat = class_name_pattern
                    if name != pat and simple != pat and pat.lower() not in name.lower():
                        continue
                if pkg:
                    if not any(name.startswith(p.rstrip(".") + ".") or name == p for p in pkg):
                        continue
                if super_class and cdef.get("super") != super_class:
                    continue
                if interfaces:
                    ifaces = set(cdef.get("interfaces") or [])
                    if not all(i in ifaces for i in interfaces):
                        continue
                hits.append(cdef)
        return hits[offset : offset + limit]

    def search_strings(self, keyword: str, limit: int = 20, offset: int = 0) -> list[dict]:
        kw = keyword
        hits: list[dict] = []
        seen: set[str] = set()
        for dex in self.dexes:
            for s in dex.strings:
                if kw in s and s not in seen:
                    seen.add(s)
                    hits.append({"value": s, "source": dex.source})
        return hits[offset : offset + limit]

    def find_method(
        self,
        method_name_pattern: str | None = None,
        in_class: str | None = None,
        param_count: int | None = None,
        return_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        """Find methods.

        Guardrails (avoid multi-minute freezes on huge multi-dex APKs):
        - Without ``in_class``, ``method_name_pattern`` is **required** and must
          be at least 2 characters (substring match, case-insensitive).
        - Hard scan cap: stop after collecting ``limit + offset`` hits or after
          scanning a bounded number of method ids.
        """
        if not in_class:
            if not method_name_pattern or len(method_name_pattern.strip()) < 2:
                raise DexError(
                    "find_method without in_class requires method_name_pattern "
                    "of length >= 2 (refuse full-APK method scans)."
                )
        hits: list[dict] = []
        seen: set[str] = set()
        need = max(1, limit) + max(0, offset)
        # Bound work on multi-dex mega apps (large multi-dex apps).
        scanned = 0
        scan_cap = 250_000 if in_class else 120_000
        for dex in self.dexes:
            for m in dex.methods:
                scanned += 1
                if scanned > scan_cap and len(hits) >= need:
                    break
                if scanned > scan_cap * 2:
                    break
                if in_class and m.class_name != in_class:
                    continue
                if method_name_pattern:
                    if in_class:
                        # exact when class constrained (Andra semantics)
                        if m.name != method_name_pattern:
                            continue
                    elif method_name_pattern.lower() not in m.name.lower():
                        continue
                if param_count is not None:
                    # proto like "(a, b)ret"
                    inside = m.proto[m.proto.find("(") + 1 : m.proto.find(")")]
                    count = 0 if not inside.strip() else len(inside.split(","))
                    if count != param_count:
                        continue
                if return_type:
                    ret = m.proto[m.proto.rfind(")") + 1 :]
                    # allow descriptor or java name
                    if return_type not in (ret, descriptor_to_java(return_type) if len(return_type) <= 2 else return_type):
                        if ret != return_type and not ret.endswith(return_type):
                            continue
                sig = m.signature
                if sig in seen:
                    continue
                seen.add(sig)
                hits.append(
                    {
                        "class": m.class_name,
                        "name": m.name,
                        "proto": m.proto,
                        "signature": sig,
                    }
                )
                if len(hits) >= need:
                    break
            if len(hits) >= need:
                break
        return hits[offset : offset + limit]

    def find_field(
        self,
        field_name_pattern: str | None = None,
        in_class: str | None = None,
        field_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        hits: list[dict] = []
        seen: set[str] = set()
        for dex in self.dexes:
            for f in dex.fields:
                if in_class and f.class_name != in_class:
                    continue
                if field_name_pattern and field_name_pattern.lower() not in f.name.lower():
                    continue
                if field_type and field_type not in (f.type_name,):
                    if field_type.lower() not in f.type_name.lower():
                        continue
                sig = f.signature
                if sig in seen:
                    continue
                seen.add(sig)
                hits.append(
                    {
                        "class": f.class_name,
                        "name": f.name,
                        "type": f.type_name,
                        "signature": sig,
                    }
                )
        return hits[offset : offset + limit]

    def class_hierarchy(self, class_name: str, depth: int = 3) -> dict:
        by_name: dict[str, dict] = {}
        for dex in self.dexes:
            for cdef in dex.class_defs():
                by_name[cdef["class"]] = cdef
        chain: list[str] = []
        cur = class_name
        for _ in range(max(1, depth)):
            chain.append(cur)
            info = by_name.get(cur)
            if not info or not info.get("super"):
                break
            cur = info["super"]
        children = [n for n, c in by_name.items() if c.get("super") == class_name]
        info = by_name.get(class_name)
        return {
            "class": class_name,
            "super_chain": chain,
            "interfaces": (info or {}).get("interfaces") or [],
            "subclasses_sample": children[:50],
            "subclass_count": len(children),
            "found": info is not None,
        }

    def stats(self) -> dict:
        return {
            "source": self.source,
            "dex_count": len(self.dexes),
            "class_count": sum(len(d.classes) for d in self.dexes),
            "string_count": sum(len(d.strings) for d in self.dexes),
            "method_id_count": sum(d.method_ids_size for d in self.dexes),
            "field_id_count": sum(d.field_ids_size for d in self.dexes),
        }

    def find_caller(
        self,
        class_name: str,
        method_name: str,
        limit: int = 30,
        offset: int = 0,
    ) -> list[dict]:
        """Find methods that invoke class_name.method_name (any overload)."""
        xrefs = self._ensure_xref()
        hits: list[dict] = []
        seen: set[str] = set()
        for dex, (invoke_map, _) in zip(self.dexes, xrefs):
            ids = dex.method_id_index(class_name, method_name)
            for mid in ids:
                target = dex.method_ref_at(mid)
                for caller in invoke_map.get(mid, []):
                    key = f"{caller.signature}=>{target.signature}"
                    if key in seen:
                        continue
                    seen.add(key)
                    hits.append(
                        {
                            "caller_class": caller.class_name,
                            "caller_method": caller.name,
                            "caller_proto": caller.proto,
                            "caller_signature": caller.signature,
                            "callee_class": target.class_name,
                            "callee_method": target.name,
                            "callee_proto": target.proto,
                            "callee_signature": target.signature,
                            "source": dex.source,
                        }
                    )
        return hits[offset : offset + limit]

    def find_usage(
        self,
        keyword: str,
        search_in: str = "both",
        limit: int = 30,
        offset: int = 0,
    ) -> list[dict]:
        """
        Find where a string constant is used, and/or methods/classes whose names match.

        search_in: "string" | "method" | "class" | "both" (string+method name)
        """
        search_in = (search_in or "both").lower()
        hits: list[dict] = []
        seen: set[str] = set()

        if search_in in ("string", "both"):
            xrefs = self._ensure_xref()
            for dex, (_, string_map) in zip(self.dexes, xrefs):
                for i, s in enumerate(dex.strings):
                    if keyword not in s:
                        continue
                    users = string_map.get(i, [])
                    if not users:
                        # string exists but no const-string found (maybe only in metadata)
                        key = f"str:{s}:<pool>"
                        if key not in seen:
                            seen.add(key)
                            hits.append(
                                {
                                    "kind": "string_pool",
                                    "value": s,
                                    "used_by": None,
                                    "source": dex.source,
                                }
                            )
                        continue
                    for user in users:
                        key = f"str:{s}:{user.signature}"
                        if key in seen:
                            continue
                        seen.add(key)
                        hits.append(
                            {
                                "kind": "string",
                                "value": s,
                                "used_by_class": user.class_name,
                                "used_by_method": user.name,
                                "used_by_proto": user.proto,
                                "used_by_signature": user.signature,
                                "source": dex.source,
                            }
                        )

        if search_in in ("method", "both"):
            for m in self.find_method(method_name_pattern=keyword, limit=limit * 2):
                key = f"method:{m['signature']}"
                if key in seen:
                    continue
                seen.add(key)
                hits.append({"kind": "method_name", **m})

        if search_in == "class":
            for c in self.search_classes(keyword, limit=limit * 2):
                key = f"class:{c}"
                if key in seen:
                    continue
                seen.add(key)
                hits.append({"kind": "class_name", "class": c})

        return hits[offset : offset + limit]

    def find_class_usage(self, class_name: str, limit: int = 40, offset: int = 0) -> list[dict]:
        """
        Approximate class usage: methods that invoke any method declared on class_name,
        plus subclasses / fields typed as the class.
        """
        xrefs = self._ensure_xref()
        hits: list[dict] = []
        seen: set[str] = set()

        # invoke any method on this class
        for dex, (invoke_map, _) in zip(self.dexes, xrefs):
            for mid in range(dex.method_ids_size):
                ref = dex.method_ref_at(mid)
                if ref.class_name != class_name:
                    continue
                for caller in invoke_map.get(mid, []):
                    key = f"invoke:{caller.signature}=>{ref.signature}"
                    if key in seen:
                        continue
                    seen.add(key)
                    hits.append(
                        {
                            "kind": "invoke",
                            "caller_signature": caller.signature,
                            "callee_signature": ref.signature,
                            "source": dex.source,
                        }
                    )
                    if len(hits) >= offset + limit:
                        break
                if len(hits) >= offset + limit:
                    break

        # fields with this type
        for f in self.find_field(field_type=class_name, limit=limit):
            key = f"field:{f['signature']}"
            if key in seen:
                continue
            seen.add(key)
            hits.append({"kind": "field_type", **f})

        # subclasses
        hier = self.class_hierarchy(class_name, depth=1)
        for sub in hier.get("subclasses_sample") or []:
            key = f"subclass:{sub}"
            if key in seen:
                continue
            seen.add(key)
            hits.append({"kind": "subclass", "class": sub})

        return hits[offset : offset + limit]
