#!/usr/bin/env python3
"""
umap_parser.py — Unreal Engine .umap / .uasset binary parser
Extracts actor exports and their tagged FProperties using only Python built-ins.

Supported: UE 4.14+ through UE 5.x

IMPORTANT — UE4.27 Pitfalls (verified against engine source):
  1. Import table: FileVersionUE4 >= 519 adds PackageName field (VER_UE4_NON_OUTER_PACKAGE_IMPORT)
  2. Export table: TemplateIndex exists when ver >= 507 (NOT 508 as some docs claim)
  3. Export table: PackageGuid (16 bytes) is ALWAYS serialized, never version-gated
  4. FPropertyTag: BoolProperty value is in the tag header, PropertySize=0
  5. FPropertyTag: StructProperty has NO HasSerializeMetaData byte in UE4 (UE5 only)
  6. Class resolution: When Import.class_name == "Class", use Import.object_name instead
  7. Export table: FirstExportDependency is int32, NOT int64 (causes 4-byte offset drift)
  8. Export table: PackageFlags is ALWAYS serialized (no version gate)
  9. Export table: bool fields (bForcedExport etc.) serialize as uint32 (4 bytes), not 1 byte

Usage:
    python3 umap_parser.py <file.umap> [--output actors.json] [--class BP_MyActor] [--verbose]
"""

import struct
import json
import sys
import os
import argparse
from typing import Optional

PACKAGE_MAGIC = 0x9E2A83C1

VER_UE4_ADD_PACKAGEFLAGS_TO_EXPORT = 322
VER_UE4_LOAD_FOR_EDITOR_GAME = 364
VER_UE4_STRUCT_GUID_IN_PROPERTY_TAG = 441
VER_UE4_GATHERABLE_TEXT_DATA = 459
VER_UE4_COOKED_ASSETS_IN_EDITOR_SUPPORT = 484
VER_UE4_PROPERTY_GUID_IN_PROPERTY_TAG = 503
VER_UE4_PRELOAD_DEPENDENCIES_IN_COOKED_EXPORTS = 506
VER_UE4_TemplateIndex_IN_COOKED_EXPORTS = 507
VER_UE4_PROPERTY_TAG_SET_MAP_SUPPORT = 509
VER_UE4_64BIT_EXPORTMAP_SERIALSIZES = 510
VER_UE4_NAME_HASHES_SERIALIZED = 516
VER_UE4_NON_OUTER_PACKAGE_IMPORT = 519


class BinaryReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.size = len(data)

    def seek(self, offset: int):
        self.pos = offset

    def tell(self) -> int:
        return self.pos

    def read_bytes(self, n: int) -> bytes:
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def read_uint32(self) -> int:
        return struct.unpack_from('<I', self.data, self._adv(4))[0]

    def read_int32(self) -> int:
        return struct.unpack_from('<i', self.data, self._adv(4))[0]

    def read_int64(self) -> int:
        return struct.unpack_from('<q', self.data, self._adv(8))[0]

    def read_uint64(self) -> int:
        return struct.unpack_from('<Q', self.data, self._adv(8))[0]

    def read_float(self) -> float:
        return struct.unpack_from('<f', self.data, self._adv(4))[0]

    def read_double(self) -> float:
        return struct.unpack_from('<d', self.data, self._adv(8))[0]

    def read_bool(self) -> bool:
        return self.read_int32() != 0

    def read_fstring(self) -> Optional[str]:
        length = self.read_int32()
        if length == 0:
            return None
        if length < 0:
            byte_len = (-length) * 2
            raw = self.read_bytes(byte_len)
            return raw.decode('utf-16-le').rstrip('\x00')
        else:
            raw = self.read_bytes(length)
            return raw.decode('utf-8', errors='replace').rstrip('\x00')

    def read_fname(self, name_table: list) -> str:
        idx = self.read_int32()
        number = self.read_int32()
        if 0 <= idx < len(name_table):
            name = name_table[idx]
            return f"{name}_{number - 1}" if number > 0 else name
        return f"<unknown_name_{idx}>"

    def _adv(self, n: int) -> int:
        old = self.pos
        self.pos += n
        return old

    def remaining(self) -> int:
        return self.size - self.pos


class PackageSummary:
    def __init__(self):
        self.tag = 0
        self.legacy_file_version = 0
        self.file_version_ue4 = 0
        self.file_version_ue5 = 0
        self.is_ue5 = False
        self.total_header_size = 0
        self.folder_name = ""
        self.package_flags = 0
        self.name_count = 0
        self.name_offset = 0
        self.export_count = 0
        self.export_offset = 0
        self.import_count = 0
        self.import_offset = 0
        self.custom_version_count = 0

    @staticmethod
    def parse(r: BinaryReader) -> 'PackageSummary':
        s = PackageSummary()
        s.tag = r.read_uint32()
        if s.tag != PACKAGE_MAGIC:
            raise ValueError(f"Invalid UE package magic: 0x{s.tag:08X}")

        s.legacy_file_version = r.read_int32()
        s.is_ue5 = (s.legacy_file_version == -8)

        if s.legacy_file_version != -4:
            r.read_int32()  # LegacyUE3Version

        s.file_version_ue4 = r.read_int32()

        if s.is_ue5:
            s.file_version_ue5 = r.read_int32()

        r.read_int32()  # FileVersionLicenseeUE

        if s.legacy_file_version <= -2:
            custom_count = r.read_int32()
            s.custom_version_count = custom_count
            for _ in range(custom_count):
                r.read_bytes(16)  # GUID
                r.read_int32()    # version

        s.total_header_size = r.read_int32()
        s.folder_name = r.read_fstring() or ""
        s.package_flags = r.read_uint32()

        s.name_count = r.read_int32()
        s.name_offset = r.read_int32()

        if s.is_ue5 and s.file_version_ue5 >= 518:
            r.read_int32()  # SoftObjectPathsCount
            r.read_int32()  # SoftObjectPathsOffset

        if s.file_version_ue4 >= VER_UE4_NAME_HASHES_SERIALIZED or s.is_ue5:
            r.read_fstring()  # LocalizationId

        if s.file_version_ue4 >= VER_UE4_GATHERABLE_TEXT_DATA:
            r.read_int32()  # GatherableTextDataCount
            r.read_int32()  # GatherableTextDataOffset

        s.export_count = r.read_int32()
        s.export_offset = r.read_int32()
        s.import_count = r.read_int32()
        s.import_offset = r.read_int32()

        return s


def parse_name_table(r: BinaryReader, summary: PackageSummary) -> list:
    r.seek(summary.name_offset)
    names = []
    for _ in range(summary.name_count):
        name = r.read_fstring() or ""
        if summary.file_version_ue4 >= VER_UE4_NAME_HASHES_SERIALIZED or summary.is_ue5:
            r.read_bytes(4)  # CaseHash + NonCaseHash (uint16 + uint16)
        else:
            r.read_bytes(4)
        names.append(name)
    return names


class ObjectImport:
    def __init__(self):
        self.class_package = ""
        self.class_name = ""
        self.outer_index = 0
        self.object_name = ""
        self.package_name = ""

    @staticmethod
    def parse(r: BinaryReader, names: list, ue4_ver: int) -> 'ObjectImport':
        imp = ObjectImport()
        imp.class_package = r.read_fname(names)
        imp.class_name = r.read_fname(names)
        imp.outer_index = r.read_int32()
        imp.object_name = r.read_fname(names)
        # PITFALL #1: PackageName exists when ver >= 519 (VER_UE4_NON_OUTER_PACKAGE_IMPORT)
        if ue4_ver >= VER_UE4_NON_OUTER_PACKAGE_IMPORT:
            imp.package_name = r.read_fname(names)
        return imp


def parse_import_table(r: BinaryReader, summary: PackageSummary, names: list) -> list:
    r.seek(summary.import_offset)
    imports = []
    for _ in range(summary.import_count):
        imports.append(ObjectImport.parse(r, names, summary.file_version_ue4))
    return imports


class ObjectExport:
    def __init__(self):
        self.class_index = 0
        self.super_index = 0
        self.template_index = 0
        self.outer_index = 0
        self.object_name = ""
        self.save_flags = 0
        self.serial_size = 0
        self.serial_offset = 0
        self.is_asset = False

    @staticmethod
    def parse(r: BinaryReader, names: list, summary: PackageSummary) -> 'ObjectExport':
        exp = ObjectExport()
        ue4_ver = summary.file_version_ue4
        is_ue5 = summary.is_ue5

        exp.class_index = r.read_int32()
        exp.super_index = r.read_int32()

        # PITFALL #2: TemplateIndex exists when ver >= 507 (NOT 508)
        if ue4_ver >= VER_UE4_TemplateIndex_IN_COOKED_EXPORTS or is_ue5:
            exp.template_index = r.read_int32()

        exp.outer_index = r.read_int32()
        exp.object_name = r.read_fname(names)
        exp.save_flags = r.read_uint32()

        # SerialSize and SerialOffset: int64 when ver >= 510, else int32
        if ue4_ver >= VER_UE4_64BIT_EXPORTMAP_SERIALSIZES or is_ue5:
            exp.serial_size = r.read_int64()
            exp.serial_offset = r.read_int64()
        else:
            exp.serial_size = r.read_int32()
            exp.serial_offset = r.read_int32()

        r.read_int32()   # bForcedExport
        r.read_int32()   # bNotForClient
        r.read_int32()   # bNotForServer

        # PITFALL #3: PackageGuid (16 bytes) is ALWAYS serialized, never removed
        r.read_bytes(16)  # PackageGuid (FGuid)

        # PackageFlags is ALWAYS serialized (no version gate in engine source)
        r.read_uint32()   # PackageFlags

        if ue4_ver >= VER_UE4_LOAD_FOR_EDITOR_GAME:
            r.read_int32()    # bNotAlwaysLoadedForEditorGame

        if ue4_ver >= VER_UE4_COOKED_ASSETS_IN_EDITOR_SUPPORT:
            exp.is_asset = r.read_int32() != 0

        if ue4_ver >= VER_UE4_PRELOAD_DEPENDENCIES_IN_COOKED_EXPORTS:
            r.read_int32()    # FirstExportDependency (int32, NOT int64!)
            r.read_int32()    # SerializationBeforeSerializationDependencies
            r.read_int32()    # CreateBeforeSerializationDependencies
            r.read_int32()    # SerializationBeforeCreateDependencies
            r.read_int32()    # CreateBeforeCreateDependencies

        return exp


def parse_export_table(r: BinaryReader, summary: PackageSummary, names: list) -> list:
    r.seek(summary.export_offset)
    exports = []
    for _ in range(summary.export_count):
        exports.append(ObjectExport.parse(r, names, summary))
    return exports


def resolve_class_name(class_index: int, imports: list, exports_list: list) -> str:
    """Resolve the class name for an export entry.

    PITFALL #6: When Import.class_name == "Class", the Import is a UClass meta-reference.
    The actual class name is Import.object_name (e.g. "NavMeshBoundsVolume"), NOT "Class".
    """
    if class_index == 0:
        return "Class"
    if class_index < 0:
        imp_idx = -class_index - 1
        if 0 <= imp_idx < len(imports):
            imp = imports[imp_idx]
            if imp.class_name == "Class":
                return imp.object_name
            return imp.class_name
    else:
        exp_idx = class_index - 1
        if 0 <= exp_idx < len(exports_list):
            return exports_list[exp_idx].object_name
    return "<unknown>"


def resolve_outer_name(outer_index: int, imports: list, exports_list: list) -> str:
    if outer_index == 0:
        return ""
    if outer_index < 0:
        imp_idx = -outer_index - 1
        if 0 <= imp_idx < len(imports):
            return imports[imp_idx].object_name
    else:
        exp_idx = outer_index - 1
        if 0 <= exp_idx < len(exports_list):
            return exports_list[exp_idx].object_name
    return ""


def read_vector(r: BinaryReader, use_double: bool = False) -> dict:
    if use_double:
        return {"X": r.read_double(), "Y": r.read_double(), "Z": r.read_double()}
    return {"X": r.read_float(), "Y": r.read_float(), "Z": r.read_float()}


def read_rotator(r: BinaryReader) -> dict:
    return {"Pitch": r.read_float(), "Yaw": r.read_float(), "Roll": r.read_float()}


def read_quat(r: BinaryReader, use_double: bool = False) -> dict:
    if use_double:
        return {"X": r.read_double(), "Y": r.read_double(),
                "Z": r.read_double(), "W": r.read_double()}
    return {"X": r.read_float(), "Y": r.read_float(),
            "Z": r.read_float(), "W": r.read_float()}


def read_struct_value(r: BinaryReader, struct_name: str, size: int, names: list, is_ue5: bool) -> any:
    use_double = is_ue5

    if struct_name == "Vector":
        return read_vector(r, use_double)
    elif struct_name == "Vector2D":
        return {"X": r.read_float(), "Y": r.read_float()}
    elif struct_name == "Rotator":
        return read_rotator(r)
    elif struct_name == "Quat":
        return read_quat(r, use_double)
    elif struct_name == "Transform":
        rot = read_quat(r, use_double)
        trans = read_vector(r, use_double)
        scale = read_vector(r, use_double)
        return {"Rotation": rot, "Translation": trans, "Scale3D": scale}
    elif struct_name == "LinearColor":
        return {"R": r.read_float(), "G": r.read_float(),
                "B": r.read_float(), "A": r.read_float()}
    elif struct_name == "Color":
        b, g, rv, a = r.read_bytes(4)
        return {"R": rv, "G": g, "B": b, "A": a}
    elif struct_name in ("Guid", "GameplayTag"):
        return r.read_bytes(size).hex()
    elif struct_name == "SoftObjectPath":
        asset_path = r.read_fstring()
        sub_path = r.read_fstring()
        return {"AssetPathName": asset_path, "SubPathString": sub_path}
    else:
        return r.read_bytes(size).hex()


def read_property_value(r: BinaryReader, prop_type: str, prop_size: int,
                         struct_name: str, names: list, is_ue5: bool) -> any:
    """Dispatch to appropriate value reader by property type.

    PITFALL #4: BoolProperty value is in the tag header (already read there).
    PropertySize is 0, so we do NOT read any value bytes here.
    """
    if prop_type == "BoolProperty":
        # Value already read from tag header; PropertySize == 0
        return None  # actual value stored in tag parsing above
    elif prop_type == "ByteProperty":
        if struct_name and struct_name != "None" and struct_name != "ByteProperty":
            return r.read_fname(names)
        return r.read_bytes(1)[0]
    elif prop_type == "Int8Property":
        return struct.unpack('<b', r.read_bytes(1))[0]
    elif prop_type == "Int16Property":
        return struct.unpack('<h', r.read_bytes(2))[0]
    elif prop_type == "IntProperty":
        return r.read_int32()
    elif prop_type == "Int64Property":
        return r.read_int64()
    elif prop_type == "UInt16Property":
        return struct.unpack('<H', r.read_bytes(2))[0]
    elif prop_type == "UInt32Property":
        return r.read_uint32()
    elif prop_type == "UInt64Property":
        return r.read_uint64()
    elif prop_type == "FloatProperty":
        return r.read_float()
    elif prop_type == "DoubleProperty":
        return r.read_double()
    elif prop_type == "StrProperty":
        return r.read_fstring()
    elif prop_type == "NameProperty":
        return r.read_fname(names)
    elif prop_type == "TextProperty":
        r.read_bytes(prop_size)
        return "<TextProperty>"
    elif prop_type == "ObjectProperty" or prop_type == "SoftObjectProperty":
        return r.read_int32()
    elif prop_type == "EnumProperty":
        return r.read_fname(names)
    elif prop_type == "StructProperty":
        return read_struct_value(r, struct_name, prop_size, names, is_ue5)
    elif prop_type == "ArrayProperty":
        count = r.read_int32()
        remaining_size = prop_size - 4
        if remaining_size > 0:
            r.read_bytes(remaining_size)
        return f"<Array[{count}]>"
    else:
        r.read_bytes(prop_size)
        return f"<{prop_type}:{prop_size}bytes>"


def read_properties(r: BinaryReader, names: list, end_offset: int,
                    is_ue5: bool, ue4_ver: int) -> dict:
    """Read all tagged FProperties until 'None' sentinel or end_offset.

    Handles the following pitfalls (see module docstring):
      - BoolProperty: value in tag header, PropertySize=0
      - StructProperty: NO HasSerializeMetaData in UE4
      - HasPropertyGuid: only when ver >= 503
    """
    props = {}

    while r.tell() < end_offset:
        try:
            prop_name = r.read_fname(names)
            if prop_name == "None" or prop_name.startswith("<unknown"):
                break

            prop_type = r.read_fname(names)
            prop_size = r.read_int32()
            array_index = r.read_int32()

            struct_name = None
            bool_val = None

            # Type-specific extra header fields (only when Type.GetNumber() == 0)
            if prop_type == "StructProperty":
                struct_name = r.read_fname(names)
                # StructGuid: 16 bytes when ver >= 441
                if ue4_ver >= VER_UE4_STRUCT_GUID_IN_PROPERTY_TAG or is_ue5:
                    r.read_bytes(16)  # StructGuid (FGuid)
                # PITFALL #5: NO HasSerializeMetaData byte in UE4!
                # That byte only exists in UE5. Reading it in UE4 causes all
                # subsequent property values to be garbage (1.8e-38 etc.)
            elif prop_type == "BoolProperty":
                # PITFALL #4: Bool value is stored IN the tag header, not in value data.
                # PropertySize is 0 for BoolProperty.
                bool_val = r.read_bytes(1)[0] != 0
            elif prop_type == "ByteProperty":
                struct_name = r.read_fname(names)
            elif prop_type == "EnumProperty":
                struct_name = r.read_fname(names)
            elif prop_type == "ArrayProperty":
                if ue4_ver >= 282 or is_ue5:
                    struct_name = r.read_fname(names)
            elif prop_type in ("SetProperty", "MapProperty"):
                if ue4_ver >= VER_UE4_PROPERTY_TAG_SET_MAP_SUPPORT or is_ue5:
                    struct_name = r.read_fname(names)
                    if prop_type == "MapProperty":
                        r.read_fname(names)  # ValueType

            # HasPropertyGuid: only when ver >= 503
            if ue4_ver >= VER_UE4_PROPERTY_GUID_IN_PROPERTY_TAG or is_ue5:
                has_guid = r.read_bytes(1)[0]
                if has_guid:
                    r.read_bytes(16)  # PropertyGuid

            # Read value data
            value_start = r.tell()

            if prop_type == "BoolProperty":
                # BoolProperty: value already read from header, PropertySize == 0
                value = bool_val
            else:
                value = read_property_value(r, prop_type, prop_size, struct_name, names, is_ue5)

            # Advance to expected end based on PropertySize
            expected_end = value_start + prop_size
            if r.tell() != expected_end and prop_size > 0:
                r.seek(expected_end)

            key = f"{prop_name}[{array_index}]" if array_index > 0 else prop_name
            props[key] = value

        except Exception:
            break

    return props


def parse_umap(filepath: str, filter_classes: list = None, verbose: bool = False) -> list:
    with open(filepath, 'rb') as f:
        data = f.read()

    r = BinaryReader(data)

    if verbose:
        print(f"[*] File size: {len(data):,} bytes")

    summary = PackageSummary.parse(r)
    if verbose:
        print(f"[*] UE{'5' if summary.is_ue5 else '4'} package detected")
        print(f"[*] FileVersionUE4={summary.file_version_ue4}, exports={summary.export_count}")

    names = parse_name_table(r, summary)
    if verbose:
        print(f"[*] Name table: {len(names)} entries")

    imports = parse_import_table(r, summary, names)
    if verbose:
        print(f"[*] Import table: {len(imports)} entries")

    exports_meta = parse_export_table(r, summary, names)
    if verbose:
        print(f"[*] Export table: {len(exports_meta)} entries")

    results = []
    for i, exp in enumerate(exports_meta):
        class_name = resolve_class_name(exp.class_index, imports, exports_meta)
        outer_name = resolve_outer_name(exp.outer_index, imports, exports_meta)

        if filter_classes:
            if not any(fc.lower() in class_name.lower() for fc in filter_classes):
                continue

        if exp.serial_size < 8:
            continue

        entry = {
            "ExportIndex": i,
            "ExportName": exp.object_name,
            "ClassName": class_name,
            "OuterName": outer_name,
            "SerialOffset": exp.serial_offset,
            "SerialSize": exp.serial_size,
            "Properties": {}
        }

        if exp.serial_offset > 0 and exp.serial_size > 0:
            try:
                r.seek(exp.serial_offset)
                end = exp.serial_offset + exp.serial_size
                entry["Properties"] = read_properties(r, names, end, summary.is_ue5, summary.file_version_ue4)
            except Exception as e:
                entry["ParseError"] = str(e)

        results.append(entry)

    if verbose:
        print(f"[*] Parsed {len(results)} exports")

    return results


def main():
    parser = argparse.ArgumentParser(description="Parse Unreal Engine .umap files")
    parser.add_argument("input", help="Path to .umap file")
    parser.add_argument("--output", "-o", default="actors.json", help="Output JSON file")
    parser.add_argument("--class", dest="filter_class", nargs="*",
                        help="Filter by class name(s)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: File not found: {args.input}")
        sys.exit(1)

    try:
        results = parse_umap(args.input, filter_classes=args.filter_class, verbose=args.verbose)
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        print(f"[OK] Wrote {len(results)} exports to {args.output}")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
