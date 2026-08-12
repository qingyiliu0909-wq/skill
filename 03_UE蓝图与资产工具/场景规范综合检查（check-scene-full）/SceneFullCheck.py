import unreal
import json
import os
import sys
import gc
import shlex
from datetime import datetime

PLATFORM_ALL = "all"
PLATFORM_PC = "pc"
PLATFORM_PHONE = "phone"

CHECK_ITEM_LEVELBOUNDS = "LevelBounds"
CHECK_ITEM_MOBILITY = "Mobility"
CHECK_ITEM_BATCHING = "Batching"
CHECK_ITEM_REFLECTION = "ReflectionSphere"
CHECK_ITEM_CROSSLEVEL = "CrossLevel"
CHECK_ITEM_DECAL = "Decal"
CHECK_ITEM_SIMPLERUNTIME = "SimpleRuntimeActor"
CHECK_ITEM_LAYER = "Layer"
CHECK_ITEM_LEVELPROXY = "LevelProxy"

ALL_CHECK_ITEMS = [
    CHECK_ITEM_LEVELBOUNDS,
    CHECK_ITEM_MOBILITY,
    CHECK_ITEM_BATCHING,
    CHECK_ITEM_REFLECTION,
    CHECK_ITEM_CROSSLEVEL,
    CHECK_ITEM_DECAL,
    CHECK_ITEM_SIMPLERUNTIME,
    CHECK_ITEM_LAYER,
    CHECK_ITEM_LEVELPROXY,
]

PHONE_ONLY_ITEMS = {CHECK_ITEM_MOBILITY, CHECK_ITEM_BATCHING, CHECK_ITEM_DECAL, CHECK_ITEM_SIMPLERUNTIME}

def find_main_level_path(main_level_name, platform=PLATFORM_ALL):
    content_dir = unreal.Paths.project_content_dir()
    search_dirs = []
    if platform == PLATFORM_ALL:
        search_dirs = [
            os.path.join(content_dir, "Maps", "Levels"),
            os.path.join(content_dir, "Maps_Phone", "Levels")
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
            if ("_Art_" in base_name
                    or "_Design_" in base_name
                    or "_Task_" in base_name
                    or "DividedEffect" in base_name
                    or "DividedFoliage" in base_name):
                sub_level_paths.append(os.path.join(root, f))
    return sorted(sub_level_paths)

def convert_abs_path_to_package_name(abs_path):
    project_dir = unreal.Paths.project_dir()
    rel = os.path.relpath(abs_path, project_dir)
    rel = rel.replace("\\", "/")
    if rel.startswith("Content/"):
        rel = rel[len("Content/"):]
    package_name = "/Game/" + rel
    if package_name.endswith(".umap"):
        package_name = package_name[:-len(".umap")]
    return package_name

def is_phone_level(file_path):
    return "Maps_Phone" in file_path.replace("\\", "/")

# LayerName 关键字（按"长度优先"排序，确保如 BigMou / DividedFoliage_TypL 等组合关键字
# 优先于较短关键字 Mou / DividedFoliage 匹配）
#
# 来源：Source/EMEditor/Private/Common/WCEditFunctionLibrary.cpp 中 UWCEditFunctionLibrary::SetTilesLayer
# 算法等价：
#     for LevelLayerInfo in LevelLayerInfos:
#         if PackageName.Contains(LayerName):
#             Info.Layer.Name = LayerName        // 仅最后一次匹配生效
#
# 重要背景：FWorldTileInfo / FWorldTileLayer 都是 Engine 中的纯 C++ class（无 USTRUCT/UPROPERTY），
# UE7 Python 实测下 unreal.World 也未暴露 world_composition 属性，
# 因此运行期无法读取每个 Tile 的 Info.Layer.Name。
# 由于 SetTilesLayer 的写入逻辑就是基于子串包含，用同样的子串匹配即可得到等价的 LayerName。
LAYER_NAME_KEYWORDS = [
    "DividedFoliage_TypL",
    "DividedFoliage_TypM",
    "DividedFoliage_TypH",
    "DividedFoliage_TypO",
    "DividedFoliage_Tree",
    "DividedFoliageOther",
    "DividedFoliage",
    "DividedEffect",
    "BigMou",
    "VilMou",
    "HugeObjs",
    "BigObjs",
    "SmallObjs",
    "MiniObjs",
    "Mou",
    "FarScene",
]


def _infer_layer_name_from_package(tile_base_name):
    """根据子关卡 PackageName 推断 Info.Layer.Name（与 SetTilesLayer 写入算法等价）。"""
    for keyword in LAYER_NAME_KEYWORDS:
        if keyword in tile_base_name:
            return keyword
    return ""


def _try_get_tile_layer_name_from_wc_tile(tile):
    """尽最大可能从 WorldComposition tile 对象读取 Layer.Name。

    不同 UE 版本 / Python 绑定对 tile/info/layer 的暴露不一致，这里做多路径兼容探测：
    - tile.info.layer.name
    - tile.layer / tile.layer_name
    - get_editor_property("info"/"layer"/"layer_name")
    """
    # 1) 常见链式属性：tile.info.layer.name
    try:
        info = getattr(tile, "info", None)
        if info is not None:
            layer = getattr(info, "layer", None)
            if layer is not None:
                name = getattr(layer, "name", None)
                if name:
                    return str(name)
    except Exception:
        pass

    # 2) tile 上的直出字段
    for attr in ("layer_name", "layer", "LayerName", "Layer"):
        try:
            v = getattr(tile, attr, None)
            if v:
                return str(v)
        except Exception:
            pass

    # 3) editor_property 兜底
    for prop in ("info", "layer", "layer_name", "LayerName"):
        try:
            v = tile.get_editor_property(prop)
            if not v:
                continue
            if prop == "info":
                try:
                    layer = getattr(v, "layer", None)
                    if layer is not None:
                        name = getattr(layer, "name", None)
                        if name:
                            return str(name)
                except Exception:
                    pass
            else:
                return str(v)
        except Exception:
            continue

    return ""


def build_tile_layer_map_from_world(world):
    """从主世界的 WorldComposition Tiles 构建 {tile_base_name: layer_name} 映射。"""
    tile_layer_map = {}
    if not world:
        return tile_layer_map

    # 优先使用 C++ FunctionLibrary（可读到真实 Tile.Info.Layer.Name）
    try:
        if hasattr(unreal, "WCEditFunctionLibrary") and hasattr(unreal.WCEditFunctionLibrary, "get_wc_tile_layer_name_map"):
            m = unreal.WCEditFunctionLibrary.get_wc_tile_layer_name_map(world)
            # Unreal Python 返回 dict-like
            if m:
                for k, v in m.items():
                    tile_layer_map[str(k)] = str(v) if v is not None else ""
                return tile_layer_map
    except Exception:
        pass

    # 兼容：尝试直接走 Python world_composition API（部分版本可用）
    if not hasattr(world, 'world_composition') or not world.world_composition:
        return tile_layer_map

    try:
        tile_list = world.world_composition.get_tiles_list()
    except Exception:
        return tile_layer_map

    try:
        num = tile_list.num()
    except Exception:
        return tile_layer_map

    for i in range(num):
        try:
            tile = tile_list.get(i)
            tile_package_name = str(tile.package_name)
            tile_base_name = os.path.basename(tile_package_name).split(".")[-1]
            layer_name = _try_get_tile_layer_name_from_wc_tile(tile)
            tile_layer_map[tile_base_name] = layer_name
        except Exception:
            continue

    return tile_layer_map


def get_sub_levels(main_level_path, platform=PLATFORM_ALL):
    sub_level_paths = []
    package_name = convert_abs_path_to_package_name(main_level_path)
    world = unreal.load_object(None, package_name)
    use_filesystem_fallback = False

    if not world:
        world = unreal.EditorLoadingAndSavingUtils.load_map(main_level_path)

    if world and hasattr(world, 'world_composition') and world.world_composition:
        tile_list = world.world_composition.get_tiles_list()
        for i in range(tile_list.num()):
            tile = tile_list.get(i)
            tile_package_name = str(tile.package_name)
            tile_base_name = os.path.basename(tile_package_name).split(".")[-1]
            if not ("_Art_" in tile_base_name
                    or "_Design_" in tile_base_name
                    or "_Task_" in tile_base_name
                    or "DividedEffect" in tile_base_name
                    or "DividedFoliage" in tile_base_name):
                continue
            tile_file_path = unreal.Paths.long_package_name_to_filename(tile_package_name, ".umap")
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

def check_level_bounds(level_name, actors):
    results = []
    has_digit = any(c.isdigit() for c in level_name)
    severity = "Error" if has_digit else "Warning"

    level_bounds = None
    for actor in actors:
        if actor and actor.get_class().get_name() == "LevelBounds":
            level_bounds = actor
            break

    if not level_bounds:
        results.append({
            "LevelName": level_name,
            "CheckType": "LevelBounds",
            "RuleType": "缺少LevelBounds",
            "Description": "关卡 {} 缺少 LevelBounds Actor".format(level_name),
            "Severity": severity
        })
        return results

    location = level_bounds.get_actor_location()
    scale = level_bounds.get_actor_scale3d()
    b_auto_update = level_bounds.get_editor_property("auto_update_bounds")

    if abs(location.x) < 100.0 and abs(location.y) < 100.0 and abs(location.z) < 100.0:
        results.append({
            "LevelName": level_name,
            "CheckType": "LevelBounds",
            "RuleType": "Position异常",
            "Description": "LevelBounds Position 不应接近 (0,0,0)",
            "Location": {"X": location.x, "Y": location.y, "Z": location.z},
            "Scale": {"X": scale.x, "Y": scale.y, "Z": scale.z},
            "bAutoUpdateBounds": b_auto_update,
            "Severity": severity
        })

    expected_xy = -1.0
    expected_desc = ""
    level_name_lower = level_name.lower()

    if "dividedfoliageother" in level_name_lower:
        expected_xy = 25600.0
        expected_desc = "(25600, 25600, Z>1000)"
    elif any(kw in level_name_lower for kw in ["big", "huge", "mou", "dividedfoliage"]):
        expected_xy = 12800.0
        expected_desc = "(12800, 12800, Z>1000)"
    elif "small" in level_name_lower:
        expected_xy = 6400.0
        expected_desc = "(6400, 6400, Z>1000)"

    if expected_xy > 0.0:
        if abs(scale.x - expected_xy) > 100.0 or abs(scale.y - expected_xy) > 100.0 or scale.z <= 1000.0:
            results.append({
                "LevelName": level_name,
                "CheckType": "LevelBounds",
                "RuleType": "Scale异常",
                "Description": "LevelBounds Scale 与关卡类型不匹配，期望: {}".format(expected_desc),
                "Location": {"X": location.x, "Y": location.y, "Z": location.z},
                "Scale": {"X": scale.x, "Y": scale.y, "Z": scale.z},
                "bAutoUpdateBounds": b_auto_update,
                "ExpectedValue": expected_desc,
                "Severity": severity
            })

    b_needs_auto_update_check = any(kw in level_name_lower for kw in [
        "small", "big", "mid", "huge", "mou", "dividedfoliage"
    ])
    if b_needs_auto_update_check and b_auto_update:
        results.append({
            "LevelName": level_name,
            "CheckType": "LevelBounds",
            "RuleType": "bAutoUpdateBounds异常",
            "Description": "bAutoUpdateBounds 应为 false 但当前为 true",
            "bAutoUpdateBounds": b_auto_update,
            "ExpectedValue": "false",
            "Severity": severity
        })

    return results

def check_mobility(level_name, actors):
    results = []
    has_digit = any(c.isdigit() for c in level_name)
    severity = "Error" if has_digit else "Warning"

    for actor in actors:
        if not actor:
            continue
        actor_class_name = actor.get_class().get_name()
        if actor_class_name not in ("StaticMeshActor",):
            continue
        try:
            mobility = actor.get_editor_property("mobility")
        except Exception:
            continue
        if mobility != unreal.ComponentMobility.STATIC:
            actor_label = actor.get_actor_label()
            mobility_str = str(mobility)
            results.append({
                "LevelName": level_name,
                "CheckType": "Mobility",
                "RuleType": "移动性非静态",
                "ActorName": actor_label,
                "ActorClass": actor_class_name,
                "Mobility": mobility_str,
                "Description": "模型 [{}] 移动性为 {}，应为 Static".format(actor_label, mobility_str),
                "Severity": severity
            })

    return results

def check_batching(level_name, actors):
    results = []
    has_digit = any(c.isdigit() for c in level_name)
    severity = "Error" if has_digit else "Warning"

    for actor in actors:
        if not actor:
            continue
        try:
            components = actor.get_components_by_class(unreal.InstancedStaticMeshComponent)
        except Exception:
            continue
        if not components:
            continue
        actor_label = actor.get_actor_label()
        actor_class_name = actor.get_class().get_name()
        for comp in components:
            comp_class_name = comp.get_class().get_name()
            if comp_class_name == "HierarchicalInstancedStaticMeshComponent":
                results.append({
                    "LevelName": level_name,
                    "CheckType": "Batching",
                    "RuleType": "组合批(HISM)",
                    "ActorName": actor_label,
                    "ActorClass": actor_class_name,
                    "ComponentClass": comp_class_name,
                    "Description": "存在打组合批(HISM)的Actor: [{}]".format(actor_label),
                    "Severity": severity
                })
            elif comp_class_name == "InstancedStaticMeshComponent":
                results.append({
                    "LevelName": level_name,
                    "CheckType": "Batching",
                    "RuleType": "聚类合批(ISM)",
                    "ActorName": actor_label,
                    "ActorClass": actor_class_name,
                    "ComponentClass": comp_class_name,
                    "Description": "存在聚类合批(ISM)的Actor: [{}]".format(actor_label),
                    "Severity": severity
                })

    return results

def check_reflection_spheres(level_name, actors):
    results = []
    sphere_names = []

    for actor in actors:
        if not actor:
            continue
        actor_class_name = actor.get_class().get_name()
        if actor_class_name in ("SphereReflectionCapture", "ReflectionCapture"):
            sphere_names.append(actor.get_actor_label())

    if sphere_names:
        results.append({
            "LevelName": level_name,
            "CheckType": "ReflectionSphere",
            "RuleType": "反射球列表",
            "SphereNames": sphere_names,
            "Count": len(sphere_names),
            "Description": "关卡包含 {} 个反射球".format(len(sphere_names)),
            "Severity": "Info"
        })

    return results

def check_cross_level_actors(level_name, actors, level_bounds_actor):
    results = []
    has_digit = any(c.isdigit() for c in level_name)
    severity = "Error" if has_digit else "Warning"

    if not level_bounds_actor:
        return results

    lb_location = level_bounds_actor.get_actor_location()
    lb_scale = level_bounds_actor.get_actor_scale3d()
    lb_min_x = lb_location.x - lb_scale.x
    lb_max_x = lb_location.x + lb_scale.x
    lb_min_y = lb_location.y - lb_scale.y
    lb_max_y = lb_location.y + lb_scale.y
    lb_min_z = lb_location.z - lb_scale.z
    lb_max_z = lb_location.z + lb_scale.z

    for actor in actors:
        if not actor:
            continue
        actor_class_name = actor.get_class().get_name()
        if actor_class_name not in ("StaticMeshActor",):
            continue

        try:
            origin = actor.get_actor_location()
            bounds = actor.get_components_bounds()
            extent = bounds.box_extent
        except Exception:
            continue

        actor_min_x = origin.x - extent.x
        actor_max_x = origin.x + extent.x
        actor_min_y = origin.y - extent.y
        actor_max_y = origin.y + extent.y
        actor_min_z = origin.z - extent.z
        actor_max_z = origin.z + extent.z

        cross_count = 0
        if actor_min_x < lb_min_x:
            cross_count += 1
        if actor_max_x > lb_max_x:
            cross_count += 1
        if actor_min_y < lb_min_y:
            cross_count += 1
        if actor_max_y > lb_max_y:
            cross_count += 1
        if actor_min_z < lb_min_z:
            cross_count += 1
        if actor_max_z > lb_max_z:
            cross_count += 1

        if cross_count >= 3:
            actor_label = actor.get_actor_label()
            results.append({
                "LevelName": level_name,
                "CheckType": "CrossLevel",
                "RuleType": "模型跨关卡",
                "ActorName": actor_label,
                "ActorClass": actor_class_name,
                "CrossFaceCount": cross_count,
                "Description": "模型 [{}] 与关卡边界交叉 {} 个面，可能跨3个以上关卡".format(actor_label, cross_count),
                "Severity": severity
            })

    return results

def check_decals(level_name, actors):
    results = []
    has_digit = any(c.isdigit() for c in level_name)
    severity = "Error" if has_digit else "Warning"

    for actor in actors:
        if not actor:
            continue
        actor_class_name = actor.get_class().get_name()
        if actor_class_name == "DecalActor":
            actor_label = actor.get_actor_label()
            results.append({
                "LevelName": level_name,
                "CheckType": "Decal",
                "RuleType": "场景贴花",
                "ActorName": actor_label,
                "ActorClass": actor_class_name,
                "Description": "Maps_Phone下存在场景贴花Actor: [{}]".format(actor_label),
                "Severity": severity
            })

    return results

def check_simple_runtime_actor(level_name, actors):
    results = []
    has_digit = any(c.isdigit() for c in level_name)
    severity = "Error" if has_digit else "Warning"

    for actor in actors:
        if not actor:
            continue
        actor_class_name = actor.get_class().get_name()
        if actor_class_name == "SimpleRuntimeTextureActor":
            actor_label = actor.get_actor_label()
            results.append({
                "LevelName": level_name,
                "CheckType": "SimpleRuntimeActor",
                "RuleType": "ASimpleRuntimeTextureActor",
                "ActorName": actor_label,
                "ActorClass": actor_class_name,
                "Description": "Maps_Phone下存在SimpleRuntimeTextureActor: [{}]".format(actor_label),
                "Severity": severity
            })

    return results

def check_layers(level_name, tile_layer_map=None):
    """检查 WorldComposition 子关卡的图层分配（Info.Layer.Name）。

    实现思路：
        UE7 Python 不暴露 UWorld.WorldComposition / FWorldTileInfo / FWorldTileLayer，
        无法直接读运行期的 Info.Layer.Name。但 SetTilesLayer 写入 Info.Layer.Name 的算法
        本质就是 PackageName.Contains(LayerName)，所以这里用同样的子串匹配，结果与运行期等价。

    输出规则：
    - 匹配到 LayerName        → Info：「Layer=BigObjs (inferred from package name)」
    - 关卡名不含任何 LayerName → Warning：「未分配 Layer」（命名异常或新增了未登记的 Layer 关键字）
    """
    results = []
    layer_name = ""
    source = ""

    if tile_layer_map and level_name in tile_layer_map:
        layer_name = tile_layer_map.get(level_name) or ""
        source = "worldcomposition_tileinfo"
    else:
        layer_name = _infer_layer_name_from_package(level_name)
        source = "inferred_from_package_name"

    if layer_name:
        results.append({
            "LevelName": level_name,
            "CheckType": "Layer",
            "RuleType": "图层分配",
            "ActorName": "",
            "LayerInfo": {
                "LayerName": layer_name,
                "Source": source,
            },
            "Description": "Layer={} ({})".format(layer_name, source),
            "Severity": "Info"
        })
    else:
        results.append({
            "LevelName": level_name,
            "CheckType": "Layer",
            "RuleType": "未分配Layer",
            "ActorName": "",
            "LayerInfo": {
                "LayerName": "",
                "Source": source,
            },
            "Description": "关卡名未匹配任何已注册图层关键字（候选: {}）".format(",".join(LAYER_NAME_KEYWORDS)),
            "Severity": "Warning"
        })

    return results

def check_level_proxy(level_name, loaded_world):
    results = []
    has_digit = any(c.isdigit() for c in level_name)
    severity = "Error" if has_digit else "Warning"

    has_proxy = False
    proxy_refs_valid = True
    proxy_details = []

    if loaded_world and hasattr(loaded_world, 'world_composition') and loaded_world.world_composition:
        try:
            wc = loaded_world.world_composition
            tiles_list = wc.get_tiles_list()
            for i in range(tiles_list.num()):
                tile = tiles_list.get(i)
                tile_package_name = str(tile.package_name)
                tile_base = os.path.basename(tile_package_name).split(".")[-1]
                if tile_base == level_name:
                    has_proxy = True
                    try:
                        streaming_levels = loaded_world.get_streaming_levels()
                        for sl in streaming_levels:
                            if sl and level_name in str(sl.get_world_asset_package_name()):
                                if not sl.is_level_loaded():
                                    proxy_refs_valid = False
                                    proxy_details.append("引用关卡未加载: {}".format(str(sl.get_world_asset_package_name())))
                    except Exception as e:
                        proxy_refs_valid = False
                        proxy_details.append("检查引用失败: {}".format(str(e)))
                    break
        except Exception as e:
            proxy_details.append("WorldComposition API异常: {}".format(str(e)))

    if has_proxy:
        results.append({
            "LevelName": level_name,
            "CheckType": "LevelProxy",
            "RuleType": "LevelProxy存在",
            "HasProxy": True,
            "ProxyRefsValid": proxy_refs_valid,
            "ProxyDetails": proxy_details,
            "Description": "关卡存在LevelProxy，引用{}".format("有效" if proxy_refs_valid else "无效: " + "; ".join(proxy_details)),
            "Severity": "Info" if proxy_refs_valid else severity
        })

    return results

def check_level(level_name, actors, loaded_world, is_phone, check_items=None, tile_layer_map=None):
    if check_items is None:
        check_items = ALL_CHECK_ITEMS

    all_results = []

    if CHECK_ITEM_LEVELBOUNDS in check_items:
        all_results.extend(check_level_bounds(level_name, actors))

    if is_phone and CHECK_ITEM_MOBILITY in check_items:
        all_results.extend(check_mobility(level_name, actors))

    if is_phone and CHECK_ITEM_BATCHING in check_items:
        all_results.extend(check_batching(level_name, actors))

    if is_phone and CHECK_ITEM_DECAL in check_items:
        all_results.extend(check_decals(level_name, actors))

    if is_phone and CHECK_ITEM_SIMPLERUNTIME in check_items:
        all_results.extend(check_simple_runtime_actor(level_name, actors))

    if CHECK_ITEM_REFLECTION in check_items:
        all_results.extend(check_reflection_spheres(level_name, actors))

    if CHECK_ITEM_CROSSLEVEL in check_items:
        level_bounds_actor = None
        for actor in actors:
            if actor and actor.get_class().get_name() == "LevelBounds":
                level_bounds_actor = actor
                break
        if level_bounds_actor:
            all_results.extend(check_cross_level_actors(level_name, actors, level_bounds_actor))

    if CHECK_ITEM_LAYER in check_items:
        all_results.extend(check_layers(level_name, tile_layer_map))

    if CHECK_ITEM_LEVELPROXY in check_items:
        all_results.extend(check_level_proxy(level_name, loaded_world))

    return all_results

def write_results_to_json(results, total_checked, total_errors, total_warnings, total_info, output_path):
    root = {
        "TotalChecked": total_checked,
        "TotalErrors": total_errors,
        "TotalWarnings": total_warnings,
        "TotalInfo": total_info,
        "CheckTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Results": results
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(root, f, ensure_ascii=False, indent="\t")
    unreal.log("Results written to: {}".format(output_path))

def run(main_level_name, platform=PLATFORM_ALL, output_path=None, check_items=None):
    if check_items is None:
        check_items = list(ALL_CHECK_ITEMS)

    if platform == PLATFORM_PC:
        skipped_items = [item for item in check_items if item in PHONE_ONLY_ITEMS]
        check_items = [item for item in check_items if item not in PHONE_ONLY_ITEMS]
        if skipped_items:
            unreal.log_warning("PC模式下跳过手机专属检查项: {}".format(", ".join(skipped_items)))

    if not check_items:
        unreal.log_error("当前平台({})下无可执行的检查项。手机专属检查项(Mobility/Batching/Decal/SimpleRuntimeActor)仅在手机端(all/phone)模式下执行。".format(platform))
        return

    unreal.log("SceneFullCheck Python Start (platform={}, check_items={})".format(platform, ",".join(check_items)))

    if not output_path:
        output_path = os.path.join(unreal.Paths.project_dir(), "SceneFullCheckResult.json")

    main_level_path = find_main_level_path(main_level_name, platform)
    if not main_level_path:
        unreal.log_error("Main level not found: {} (platform={})".format(main_level_name, platform))
        return

    unreal.log("Found main level: {}".format(main_level_path))

    sub_level_paths = get_sub_levels(main_level_path, platform)
    unreal.log("Found {} sub-levels to check (platform={})".format(len(sub_level_paths), platform))

    # 优先从主世界的 WorldComposition tile 信息读 Layer.Name，供子关卡的 Layer 检查使用
    tile_layer_map = {}
    if CHECK_ITEM_LAYER in check_items:
        try:
            main_world = unreal.EditorLoadingAndSavingUtils.load_map(main_level_path)
            tile_layer_map = build_tile_layer_map_from_world(main_world)
            unreal.log("Built tile layer map: {} entries".format(len(tile_layer_map)))
        except Exception as e:
            unreal.log_warning("Build tile layer map failed: {}".format(str(e)))
            tile_layer_map = {}

    all_results = []
    total_checked = 0
    total_errors = 0
    total_warnings = 0
    total_info = 0
    error_level = 0

    for idx, tile_file_path in enumerate(sub_level_paths):
        tile_base = os.path.splitext(os.path.basename(tile_file_path))[0]
        if "_LOD1" in tile_base:
            continue
        is_phone = is_phone_level(tile_file_path)
        unreal.log("[{}/{}] Loading: {}".format(idx + 1, len(sub_level_paths), tile_base))

        loaded_world = unreal.EditorLoadingAndSavingUtils.load_map(tile_file_path)
        if not loaded_world:
            unreal.log_warning("Failed to load: {}".format(tile_file_path))
            continue

        try:
            actors = unreal.EditorLevelLibrary.get_all_level_actors()
        except Exception as e:
            unreal.log_warning("get_all_level_actors failed for {}: {}".format(tile_base, str(e)))
            continue

        total_checked += 1

        results = check_level(tile_base, actors, loaded_world, is_phone, check_items, tile_layer_map)
        if results:
            for r in results:
                all_results.append(r)
                sev = r.get("Severity", "Info")
                if sev == "Error":
                    total_errors += 1
                    error_level = 1
                elif sev == "Warning":
                    total_warnings += 1
                else:
                    total_info += 1

        if (idx + 1) % 50 == 0:
            write_results_to_json(all_results, total_checked, total_errors, total_warnings, total_info, output_path)
            unreal.log("Intermediate results saved at [{}/{}]".format(idx + 1, len(sub_level_paths)))

        del actors
        del loaded_world
        gc.collect()
        unreal.SystemLibrary.collect_garbage()

    write_results_to_json(all_results, total_checked, total_errors, total_warnings, total_info, output_path)

    if total_errors == 0 and total_warnings == 0:
        unreal.log("Scene full check passed. Total checked: {}, Info: {}".format(total_checked, total_info))
    else:
        unreal.log_error("Scene full check found {} error(s), {} warning(s), {} info out of {} level(s) checked. Results written to: {}".format(
            total_errors, total_warnings, total_info, total_checked, output_path))

    return error_level


def get_cmd_line_args():
    args = list(sys.argv)
    try:
        ue_cmd_line = unreal.SystemLibrary.get_command_line()
        if ue_cmd_line:
            # UE 命令行里常包含引号包裹的 -ExecutePythonScript=...，
            # 直接 split() 会把结尾引号残留到最后一个 token（例如 -OutputPath=xxx.json"），
            # 从而导致文件路径无效。这里用 shlex 做更稳健的分词。
            try:
                args.extend(shlex.split(ue_cmd_line, posix=False))
            except Exception:
                args.extend(ue_cmd_line.split())
    except Exception:
        pass
    return args

if __name__ == "__main__" or any("-MainLevel=" in a for a in get_cmd_line_args()):
    main_level = ""
    platform = PLATFORM_ALL
    out_path = None
    check_items = None
    all_args = get_cmd_line_args()
    for arg in all_args:
        if arg.startswith("-MainLevel="):
            main_level = arg.split("=", 1)[1].strip().strip("\"").strip("'")
        elif arg.startswith("-Platform="):
            platform = arg.split("=", 1)[1].strip().strip("\"").strip("'").lower()
        elif arg.startswith("-OutputPath="):
            out_path = arg.split("=", 1)[1].strip().strip("\"").strip("'")
        elif arg.startswith("-CheckItems="):
            items_str = arg.split("=", 1)[1].strip().strip("\"").strip("'")
            parsed_items = [item.strip() for item in items_str.split(",") if item.strip()]
            check_items = [item for item in parsed_items if item in ALL_CHECK_ITEMS]
            if not check_items:
                check_items = None
    if platform not in (PLATFORM_ALL, PLATFORM_PC, PLATFORM_PHONE):
        platform = PLATFORM_ALL
    if main_level:
        run(main_level, platform, out_path, check_items)
    else:
        unreal.log_error("Missing parameter: -MainLevel=<MainLevelName>")
