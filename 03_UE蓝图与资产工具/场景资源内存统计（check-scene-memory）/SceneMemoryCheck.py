# -*- coding: utf-8 -*-
"""
UE Editor 命令行脚本：按子关卡统计 StaticMesh / Material / Texture 内存占用（去重），
以及 LOD0 三角形数（按实例数加权）Top5、资源内存（按实例数加权）Top5 的 StaticMesh 资源。

口径：
  使用 UObject::GetResourceSizeBytes(EResourceSizeMode::Exclusive)，
  通过项目 C++ wrapper UPythonExtensionFunctionLibrary::GetObjectResourceSizeBytes 暴露给 Python，
  与编辑器 Size Map / Asset Audit 的 Memory 列同口径。
  数值反映"加载后常驻内存近似"，不是磁盘字节。

用法（与 check-scene-full 相同，通过 UE4Editor-Cmd 调用）：
  -MainLevel=Chapter01_IcelakeCity -Platform=all|pc|phone
  -OutputPath=E:/Trunk/SceneMemoryCheckResult.json  （可选）
  -IncludeEngineRefs=0|1  （可选，默认 0：仅统计 /Game/ 包）
"""
import unreal
import json
import os
import sys
import gc
from datetime import datetime

PLATFORM_ALL = "all"
PLATFORM_PC = "pc"
PLATFORM_PHONE = "phone"


def long_package_name_to_filename(long_pkg, ext):
    """手动实现 /Game/... 或 /Engine/... 到磁盘文件路径的转换，仅用于 TopAssets 给出 DiskPath 与 .umap 路径解析。"""
    if not long_pkg:
        return ""
    s = str(long_pkg)
    if s.startswith("/Game/"):
        rel = s[len("/Game/"):]
        base = os.path.join(unreal.Paths.project_content_dir(), rel)
    elif s.startswith("/Engine/"):
        rel = s[len("/Engine/"):]
        try:
            engine_content = unreal.Paths.engine_content_dir()
        except Exception:
            engine_content = ""
        if not engine_content:
            return ""
        base = os.path.join(engine_content, rel)
    else:
        return ""
    if ext and not ext.startswith("."):
        ext = "." + ext
    return os.path.normpath(base + (ext or ""))


def find_main_level_path(main_level_name, platform=PLATFORM_ALL):
    content_dir = unreal.Paths.project_content_dir()
    search_dirs = []
    if platform == PLATFORM_ALL:
        search_dirs = [
            os.path.join(content_dir, "Maps", "Levels"),
            os.path.join(content_dir, "Maps_Phone", "Levels"),
        ]
    elif platform == PLATFORM_PC:
        search_dirs = [os.path.join(content_dir, "Maps", "Levels")]
    elif platform == PLATFORM_PHONE:
        search_dirs = [os.path.join(content_dir, "Maps_Phone", "Levels")]
    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            continue
        for root, dirs, files in os.walk(search_dir):
            for f in files:
                if f == main_level_name + ".umap":
                    return os.path.join(root, f)
    return ""


def find_sub_levels_from_filesystem(main_level_path, platform=PLATFORM_ALL):
    main_level_dir = os.path.dirname(main_level_path)
    main_base = os.path.splitext(os.path.basename(main_level_path))[0]
    sub_level_paths = []
    for root, dirs, files in os.walk(main_level_dir):
        for f in files:
            if not f.endswith(".umap"):
                continue
            base_name = os.path.splitext(f)[0]
            if base_name == main_base:
                continue
            if platform == PLATFORM_PHONE and "Maps_Phone" not in root.replace("\\", "/"):
                continue
            if platform == PLATFORM_PC and "Maps_Phone" in root.replace("\\", "/"):
                continue
            if (
                "_Art_" in base_name
                or "_Design_" in base_name
                or "_Task_" in base_name
                or "DividedEffect" in base_name
                or "DividedFoliage" in base_name
            ):
                sub_level_paths.append(os.path.join(root, f))
    return sorted(sub_level_paths)


def convert_abs_path_to_package_name(abs_path):
    project_dir = unreal.Paths.project_dir()
    rel = os.path.relpath(abs_path, project_dir)
    rel = rel.replace("\\", "/")
    if rel.startswith("Content/"):
        rel = rel[len("Content/") :]
    package_name = "/Game/" + rel
    if package_name.endswith(".umap"):
        package_name = package_name[: -len(".umap")]
    return package_name


def is_phone_level(file_path):
    return "Maps_Phone" in file_path.replace("\\", "/")


def get_sub_levels(main_level_path, platform=PLATFORM_ALL):
    sub_level_paths = []
    package_name = convert_abs_path_to_package_name(main_level_path)
    world = unreal.load_object(None, package_name)
    use_filesystem_fallback = False

    if not world:
        world = unreal.EditorLoadingAndSavingUtils.load_map(main_level_path)

    if world and hasattr(world, "world_composition") and world.world_composition:
        tile_list = world.world_composition.get_tiles_list()
        for i in range(tile_list.num()):
            tile = tile_list.get(i)
            tile_package_name = str(tile.package_name)
            tile_base_name = os.path.basename(tile_package_name).split(".")[-1]
            if not (
                "_Art_" in tile_base_name
                or "_Design_" in tile_base_name
                or "_Task_" in tile_base_name
                or "DividedEffect" in tile_base_name
                or "DividedFoliage" in tile_base_name
            ):
                continue
            tile_file_path = long_package_name_to_filename(tile_package_name, ".umap")
            if tile_file_path and os.path.exists(tile_file_path):
                if platform == PLATFORM_PC and "Maps_Phone" in tile_file_path.replace("\\", "/"):
                    continue
                if platform == PLATFORM_PHONE and "Maps_Phone" not in tile_file_path.replace("\\", "/"):
                    continue
                sub_level_paths.append(tile_file_path)
    else:
        use_filesystem_fallback = True

    if not sub_level_paths:
        use_filesystem_fallback = True

    if use_filesystem_fallback:
        sub_level_paths = find_sub_levels_from_filesystem(main_level_path, platform)

    return sub_level_paths


def asset_path_to_long_package(asset_path):
    if not asset_path:
        return ""
    s = str(asset_path)
    if "." in s:
        return s.split(".", 1)[0]
    return s


_MEMORY_SIZE_CACHE = {}
_LOAD_FAILED_PACKAGES = set()


def _load_object_for_long_pkg(long_pkg):
    """尝试以多种路径形态加载资源对象，兼容 PackagePath / ObjectPath。"""
    obj = None
    try:
        obj = unreal.load_object(None, long_pkg)
    except Exception:
        obj = None
    if obj:
        return obj
    asset_name = long_pkg.rsplit("/", 1)[-1] if "/" in long_pkg else long_pkg
    try:
        obj = unreal.load_object(None, "{}.{}".format(long_pkg, asset_name))
    except Exception:
        obj = None
    return obj


def memory_size_bytes_for_long_package(long_pkg, include_engine_refs):
    """通过 GetResourceSizeBytes(Exclusive) 读取资源加载后的内存占用，按包名缓存。"""
    if not long_pkg:
        return 0
    if not long_pkg.startswith("/Game/") and not (include_engine_refs and long_pkg.startswith("/Engine/")):
        return 0
    cached = _MEMORY_SIZE_CACHE.get(long_pkg)
    if cached is not None:
        return cached
    obj = _load_object_for_long_pkg(long_pkg)
    if not obj:
        _LOAD_FAILED_PACKAGES.add(long_pkg)
        _MEMORY_SIZE_CACHE[long_pkg] = 0
        return 0
    size = 0
    try:
        size = int(unreal.PythonExtensionFunctionLibrary.get_object_resource_size_bytes(obj, True))
    except Exception as e:
        unreal.log_warning("get_object_resource_size_bytes failed for {}: {}".format(long_pkg, e))
        size = 0
    _MEMORY_SIZE_CACHE[long_pkg] = size
    return size


def sum_memory_bytes_for_packages(pkgs, include_engine_refs):
    total = 0
    for p in pkgs:
        total += memory_size_bytes_for_long_package(p, include_engine_refs)
    return total


def asset_data_class_str(ad):
    try:
        if hasattr(ad, "asset_class_path") and ad.asset_class_path:
            n = ad.asset_class_path.asset_name
            return str(n) if n else ""
    except Exception:
        pass
    try:
        if hasattr(ad, "asset_class"):
            return str(ad.asset_class)
    except Exception:
        pass
    return ""


def get_primary_asset_class_for_package(ar, package_name):
    try:
        name = unreal.Name(str(package_name))
    except Exception:
        name = None
    if not name:
        return ""
    try:
        assets = ar.get_assets_by_package_name(name)
    except Exception:
        return ""
    if not assets or len(assets) == 0:
        return ""
    return asset_data_class_str(assets[0])


def is_texture_class(cls_name):
    if not cls_name:
        return False
    return cls_name.startswith("Texture") or cls_name in ("VolumeTexture", "MediaTexture")


def is_material_class(cls_name):
    if not cls_name:
        return False
    return cls_name in (
        "Material",
        "MaterialInstanceConstant",
        "MaterialInstanceDynamic",
        "MaterialFunctionMaterialLayer",
        "MaterialFunction",
    )


def collect_dependency_packages(ar, root_long_packages, include_engine_refs):
    """BFS 收集依赖包名（字符串），仅用于分类；去重。"""
    opts = unreal.AssetRegistryDependencyOptions(
        include_soft_package_references=True,
        include_hard_package_references=True,
        include_searchable_names=False,
        include_soft_management_references=False,
        include_hard_management_references=False,
    )
    visited = set()
    queue = []
    for r in root_long_packages:
        rs = str(r)
        if rs and rs not in visited:
            visited.add(rs)
            queue.append(rs)

    idx = 0
    while idx < len(queue):
        pkg = queue[idx]
        idx += 1
        try:
            deps = ar.get_dependencies(unreal.Name(pkg), opts)
        except Exception:
            try:
                deps = ar.get_dependencies(pkg, opts)
            except Exception:
                deps = None
        if not deps:
            continue
        for d in deps:
            ds = str(d)
            if not ds:
                continue
            if ds.startswith("/Script/"):
                continue
            if ds.startswith("/Game/"):
                pass
            elif include_engine_refs and ds.startswith("/Engine/"):
                pass
            else:
                continue
            if ds not in visited:
                visited.add(ds)
                queue.append(ds)
    return visited


def lod0_triangle_count_per_instance(static_mesh):
    if not static_mesh:
        return 0
    total = 0
    try:
        num_sections = static_mesh.get_num_sections(0)
    except Exception:
        return 0
    for sec in range(int(num_sections)):
        try:
            _v, tris, _n, _uv, _tan = unreal.ProceduralMeshLibrary.get_section_from_static_mesh(
                static_mesh, 0, sec
            )
            if tris:
                total += len(tris) // 3
        except Exception:
            continue
    return total


def static_mesh_component_instance_count(comp):
    try:
        cname = comp.get_class().get_name()
        if cname in ("HierarchicalInstancedStaticMeshComponent", "InstancedStaticMeshComponent"):
            return int(comp.get_instance_count())
    except Exception:
        pass
    return 1


def analyze_sub_level(tile_file_path, include_engine_refs, global_acc=None):
    tile_base = os.path.splitext(os.path.basename(tile_file_path))[0]
    loaded_world = unreal.EditorLoadingAndSavingUtils.load_map(tile_file_path)
    if not loaded_world:
        return {"LevelName": tile_base, "Error": "load_map failed"}

    try:
        actors = unreal.EditorLevelLibrary.get_all_level_actors()
    except Exception as e:
        return {"LevelName": tile_base, "Error": "get_all_level_actors: {}".format(str(e))}

    ar = unreal.AssetRegistryHelpers.get_asset_registry()

    mesh_long_packages = set()
    tri_weighted_by_mesh = {}
    mem_weighted_by_mesh = {}

    for actor in actors:
        if not actor:
            continue
        try:
            comps = actor.get_components_by_class(unreal.StaticMeshComponent)
        except Exception:
            continue
        if not comps:
            continue
        for comp in comps:
            try:
                sm = comp.get_editor_property("static_mesh")
            except Exception:
                sm = None
            if not sm:
                continue
            ap = unreal.EditorAssetLibrary.get_path_name_for_loaded_asset(sm)
            long_pkg = asset_path_to_long_package(ap)
            if not long_pkg:
                continue
            mesh_long_packages.add(long_pkg)
            inst = static_mesh_component_instance_count(comp)
            per = lod0_triangle_count_per_instance(sm)
            tri_weighted_by_mesh[long_pkg] = tri_weighted_by_mesh.get(long_pkg, 0) + per * inst
            per_mem = memory_size_bytes_for_long_package(long_pkg, include_engine_refs)
            mem_weighted_by_mesh[long_pkg] = mem_weighted_by_mesh.get(long_pkg, 0) + per_mem * inst

    dep_packages = collect_dependency_packages(ar, mesh_long_packages, include_engine_refs)

    tex_pkgs = set()
    mat_pkgs = set()
    for pkg in dep_packages:
        cls = get_primary_asset_class_for_package(ar, pkg)
        if is_texture_class(cls):
            tex_pkgs.add(pkg)
        elif is_material_class(cls):
            mat_pkgs.add(pkg)

    mesh_bytes = sum_memory_bytes_for_packages(mesh_long_packages, include_engine_refs)
    tex_bytes = sum_memory_bytes_for_packages(tex_pkgs, include_engine_refs)
    mat_bytes = sum_memory_bytes_for_packages(mat_pkgs, include_engine_refs)
    total_bytes = mesh_bytes + tex_bytes + mat_bytes

    if global_acc is not None:
        global_acc["mesh"].update(mesh_long_packages)
        global_acc["tex"].update(tex_pkgs)
        global_acc["mat"].update(mat_pkgs)

    top5_tris = sorted(tri_weighted_by_mesh.items(), key=lambda x: x[1], reverse=True)[:5]
    top5_tris_list = []
    for pkg, tris in top5_tris:
        mem = memory_size_bytes_for_long_package(pkg, include_engine_refs)
        top5_tris_list.append(
            {
                "StaticMeshPackage": pkg,
                "LOD0TrianglesWeighted": int(tris),
                "MemoryBytes": int(mem),
                "MemoryHuman": format_bytes(mem),
            }
        )

    top5_mem = sorted(mem_weighted_by_mesh.items(), key=lambda x: x[1], reverse=True)[:5]
    top5_mem_list = []
    for pkg, weighted_mem in top5_mem:
        single_mem = memory_size_bytes_for_long_package(pkg, include_engine_refs)
        top5_mem_list.append(
            {
                "StaticMeshPackage": pkg,
                "MemoryWeightedBytes": int(weighted_mem),
                "MemoryWeightedHuman": format_bytes(weighted_mem),
                "MemoryBytes": int(single_mem),
                "MemoryHuman": format_bytes(single_mem),
            }
        )

    result = {
        "LevelName": tile_base,
        "SubLevelPath": tile_file_path.replace("\\", "/"),
        "UniqueStaticMeshCount": len(mesh_long_packages),
        "StaticMeshMemoryBytes": mesh_bytes,
        "TextureMemoryBytes": tex_bytes,
        "MaterialMemoryBytes": mat_bytes,
        "TotalMemoryBytes": total_bytes,
        "StaticMeshMemoryHuman": format_bytes(mesh_bytes),
        "TextureMemoryHuman": format_bytes(tex_bytes),
        "MaterialMemoryHuman": format_bytes(mat_bytes),
        "TotalMemoryHuman": format_bytes(total_bytes),
        "DependencyPackageCount": len(dep_packages),
        "TexturePackageCount": len(tex_pkgs),
        "MaterialPackageCount": len(mat_pkgs),
        "Top5MeshesByLOD0TrianglesWeighted": top5_tris_list,
        "Top5MeshesByMemoryWeighted": top5_mem_list,
    }

    del actors
    del loaded_world
    gc.collect()
    unreal.SystemLibrary.collect_garbage()

    return result


def format_bytes(n):
    if n is None:
        return "0 B"
    x = float(int(n))
    if x < 1024.0:
        return "{} B".format(int(x))
    unit_names = ["KB", "MB", "GB", "TB"]
    ui = 0
    x /= 1024.0
    while x >= 1024.0 and ui < len(unit_names) - 1:
        x /= 1024.0
        ui += 1
    return "{:.2f} {}".format(x, unit_names[ui])


def run(main_level_name, platform, output_path, include_engine_refs):
    if not output_path:
        output_path = os.path.join(unreal.Paths.project_dir(), "SceneMemoryCheckResult.json")

    main_level_path = find_main_level_path(main_level_name, platform)
    if not main_level_path:
        unreal.log_error("Main level not found: {} (platform={})".format(main_level_name, platform))
        return 1

    sub_level_paths = get_sub_levels(main_level_path, platform)
    unreal.log("SceneMemoryCheck: {} sub-levels (platform={}) using GetResourceSizeBytes(Exclusive)".format(
        len(sub_level_paths), platform))

    per_level = []
    sum_mesh = 0
    sum_tex = 0
    sum_mat = 0
    global_acc = {"mesh": set(), "tex": set(), "mat": set()}

    def _try_save_partial(data):
        try:
            tmp_path = output_path + ".partial"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent="\t")
        except Exception as e:
            unreal.log_warning("Partial save failed: {}".format(e))

    for idx, tile_file_path in enumerate(sub_level_paths):
        tile_base = os.path.splitext(os.path.basename(tile_file_path))[0]
        if "_LOD1" in tile_base:
            continue
        unreal.log("[{}/{}] {}".format(idx + 1, len(sub_level_paths), tile_base))
        row = analyze_sub_level(tile_file_path, include_engine_refs, global_acc)
        per_level.append(row)
        if "StaticMeshMemoryBytes" in row:
            sum_mesh += row["StaticMeshMemoryBytes"]
            sum_tex += row["TextureMemoryBytes"]
            sum_mat += row["MaterialMemoryBytes"]

        if (idx + 1) % 200 == 0:
            unique_mesh_bytes = sum_memory_bytes_for_packages(global_acc["mesh"], include_engine_refs)
            unique_tex_bytes = sum_memory_bytes_for_packages(global_acc["tex"], include_engine_refs)
            unique_mat_bytes = sum_memory_bytes_for_packages(global_acc["mat"], include_engine_refs)
            _try_save_partial({
                "MainLevel": main_level_name,
                "Platform": platform,
                "Progress": "{}/{}".format(idx + 1, len(sub_level_paths)),
                "UniqueGrandTotals": {
                    "StaticMeshMemoryBytes": unique_mesh_bytes,
                    "TextureMemoryBytes": unique_tex_bytes,
                    "MaterialMemoryBytes": unique_mat_bytes,
                    "UniqueStaticMeshCount": len(global_acc["mesh"]),
                    "UniqueTexturePackageCount": len(global_acc["tex"]),
                    "UniqueMaterialPackageCount": len(global_acc["mat"]),
                },
                "Levels": per_level,
            })

    unique_mesh_bytes = sum_memory_bytes_for_packages(global_acc["mesh"], include_engine_refs)
    unique_tex_bytes = sum_memory_bytes_for_packages(global_acc["tex"], include_engine_refs)
    unique_mat_bytes = sum_memory_bytes_for_packages(global_acc["mat"], include_engine_refs)

    def _top5_sublevels(rows, key):
        valid = [r for r in rows if key in r]
        valid.sort(key=lambda r: r.get(key, 0), reverse=True)
        out = []
        for r in valid[:5]:
            mb = int(r.get("StaticMeshMemoryBytes", 0))
            tb = int(r.get("TextureMemoryBytes", 0))
            ab = int(r.get("MaterialMemoryBytes", 0))
            tot = int(r.get("TotalMemoryBytes", mb + tb + ab))
            out.append({
                "LevelName": r.get("LevelName", ""),
                "StaticMeshMemoryBytes": mb,
                "TextureMemoryBytes": tb,
                "MaterialMemoryBytes": ab,
                "TotalMemoryBytes": tot,
                "StaticMeshMemoryHuman": format_bytes(mb),
                "TextureMemoryHuman": format_bytes(tb),
                "MaterialMemoryHuman": format_bytes(ab),
                "TotalMemoryHuman": format_bytes(tot),
            })
        return out

    top_sub_levels = {
        "ByTotalMemoryBytes": _top5_sublevels(per_level, "TotalMemoryBytes"),
        "ByStaticMeshMemoryBytes": _top5_sublevels(per_level, "StaticMeshMemoryBytes"),
        "ByTextureMemoryBytes": _top5_sublevels(per_level, "TextureMemoryBytes"),
        "ByMaterialMemoryBytes": _top5_sublevels(per_level, "MaterialMemoryBytes"),
    }

    def _top5_assets(pkg_set):
        rows = []
        for pkg in pkg_set:
            b = memory_size_bytes_for_long_package(pkg, include_engine_refs)
            if b <= 0:
                continue
            rows.append((pkg, b))
        rows.sort(key=lambda x: x[1], reverse=True)
        out = []
        for pkg, b in rows[:5]:
            asset_name = pkg.rsplit("/", 1)[-1] if "/" in pkg else pkg
            disk_path = long_package_name_to_filename(pkg, ".uasset").replace("\\", "/")
            out.append({
                "AssetName": asset_name,
                "PackageName": pkg,
                "DiskPath": disk_path,
                "MemoryBytes": int(b),
                "MemoryHuman": format_bytes(b),
            })
        return out

    top_assets = {
        "ByStaticMeshMemoryBytes": _top5_assets(global_acc["mesh"]),
        "ByTextureMemoryBytes": _top5_assets(global_acc["tex"]),
        "ByMaterialMemoryBytes": _top5_assets(global_acc["mat"]),
    }

    root = {
        "MainLevel": main_level_name,
        "Platform": platform,
        "IncludeEngineRefs": include_engine_refs,
        "MemoryMode": "Exclusive (UObject::GetResourceSizeBytes)",
        "Notes": [
            "本结果使用 UObject::GetResourceSizeBytes(EResourceSizeMode::Exclusive) 统计资源加载后常驻内存近似，不是磁盘字节。",
            "底层通过项目 C++ wrapper UPythonExtensionFunctionLibrary::GetObjectResourceSizeBytes 暴露给 Python，与编辑器 Size Map / Asset Audit Memory 列同口径。",
            "UniqueGrandTotals 为整个主关卡范围的真实去重：同一 Mesh/Texture/Material 被多个子关卡引用只计一次，反映主关卡资源内存占用的实际总量。",
            "SumOfPerLevel 为各子关卡去重内统计的简单相加，同一资源被多个子关卡引用会在合计中重复计入，仅供对比参考。",
            "各子关卡的 StaticMesh/Texture/Material 内存均为该子关卡范围内的去重统计（每个资源只计一次）。",
            "Texture/Material 来自 AssetRegistry 对关卡引用 StaticMesh 包名的依赖闭包；默认仅统计 /Game/（IncludeEngineRefs=0），引擎共享贴图不计入。",
            "Top5MeshesByLOD0TrianglesWeighted：LOD0 三角形数 × 该子关卡所有 StaticMeshComponent（含 ISM/HISM）实例数之和，定位面数大头。",
            "Top5MeshesByMemoryWeighted：单个 StaticMesh 内存 × 该子关卡所有实例数之和，定位运行时常驻内存大头。",
            "TopSubLevels 基于各子关卡内部去重后的内存字节排名（TotalMemoryBytes = StaticMesh+Texture+Material），跨子关卡复用的资源会在不同子关卡中重复计入，仅用于定位内存大头。",
            "TopAssets 基于全主关卡去重集合：同一资源被多个子关卡引用只计一次，反映单个 Mesh/Texture/Material 在内存中的真实大小排名（与 UniqueGrandTotals 同口径）。",
            "Material 在 Exclusive 模式下的内存值偏小（只算 master / instance 自身，不含其引用的贴图），避免与 Texture 项重复计入。",
        ],
        "CheckTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "SubLevelCount": len(per_level),
        "UniqueGrandTotals": {
            "StaticMeshMemoryBytes": unique_mesh_bytes,
            "TextureMemoryBytes": unique_tex_bytes,
            "MaterialMemoryBytes": unique_mat_bytes,
            "StaticMeshMemoryHuman": format_bytes(unique_mesh_bytes),
            "TextureMemoryHuman": format_bytes(unique_tex_bytes),
            "MaterialMemoryHuman": format_bytes(unique_mat_bytes),
            "UniqueStaticMeshCount": len(global_acc["mesh"]),
            "UniqueTexturePackageCount": len(global_acc["tex"]),
            "UniqueMaterialPackageCount": len(global_acc["mat"]),
        },
        "SumOfPerLevel": {
            "StaticMeshMemoryBytes": sum_mesh,
            "TextureMemoryBytes": sum_tex,
            "MaterialMemoryBytes": sum_mat,
            "StaticMeshMemoryHuman": format_bytes(sum_mesh),
            "TextureMemoryHuman": format_bytes(sum_tex),
            "MaterialMemoryHuman": format_bytes(sum_mat),
        },
        "TopSubLevels": top_sub_levels,
        "TopAssets": top_assets,
        "LoadFailedPackageCount": len(_LOAD_FAILED_PACKAGES),
        "LoadFailedPackages": sorted(list(_LOAD_FAILED_PACKAGES))[:50],
        "Levels": per_level,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(root, f, ensure_ascii=False, indent="\t")

    unreal.log("SceneMemoryCheck done -> {}".format(output_path))
    if _LOAD_FAILED_PACKAGES:
        unreal.log_warning("SceneMemoryCheck: {} packages failed to load (their memory counted as 0).".format(
            len(_LOAD_FAILED_PACKAGES)))
    return 0


def get_cmd_line_args():
    args = list(sys.argv)
    try:
        ue_cmd_line = unreal.SystemLibrary.get_command_line()
        if ue_cmd_line:
            args.extend(ue_cmd_line.split())
    except Exception:
        pass
    return args


if __name__ == "__main__" or any("-MainLevel=" in a for a in get_cmd_line_args()):
    main_level = ""
    platform = PLATFORM_ALL
    out_path = None
    include_engine_refs = False
    def _clean(v):
        return v.strip().strip('"').strip("'").strip()

    for arg in get_cmd_line_args():
        if arg.startswith("-MainLevel="):
            main_level = _clean(arg.split("=", 1)[1])
        elif arg.startswith("-Platform="):
            platform = _clean(arg.split("=", 1)[1]).lower()
        elif arg.startswith("-OutputPath="):
            out_path = _clean(arg.split("=", 1)[1])
        elif arg.startswith("-IncludeEngineRefs="):
            v = _clean(arg.split("=", 1)[1]).lower()
            include_engine_refs = v in ("1", "true", "yes")

    if platform not in (PLATFORM_ALL, PLATFORM_PC, PLATFORM_PHONE):
        platform = PLATFORM_ALL

    unreal.log("SceneMemoryCheck args -> MainLevel={} Platform={} OutputPath={} IncludeEngineRefs={}".format(
        main_level, platform, out_path, include_engine_refs))

    if main_level:
        run(main_level, platform, out_path, include_engine_refs)
    else:
        unreal.log_error("Missing parameter: -MainLevel=<MainLevelName>")
