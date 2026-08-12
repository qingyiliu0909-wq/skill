#!/usr/bin/env python3
"""
蓝图与C++同步变量分析工具
分析指定蓝图及其继承链中的所有Replicated/RepNotify变量，
检查这些变量在Lua和C++中修改时是否正确标脏。
"""

import json
import re
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import defaultdict

# 默认路径配置
DEFAULT_JSON_DIR = Path("D:/BlueprintExport_Skill")
DEFAULT_LUA_ROOT = Path("G:/PanDemo/EM/Content/Script")
DEFAULT_CPP_SOURCE = Path("G:/PanDemo/EM/Source/EM")


@dataclass
class SyncVariable:
    """同步变量信息"""
    name: str
    var_type: str
    source_class: str  # 来源类名
    is_rep_notify: bool
    is_replicated: bool
    source_type: str = "Blueprint"  # "Blueprint" 或 "C++"
    lua_modifications: List[Dict] = field(default_factory=list)
    cpp_modifications: List[Dict] = field(default_factory=list)
    has_mark_dirty_lua: bool = False
    has_mark_dirty_cpp: bool = False


@dataclass
class BlueprintInfo:
    """蓝图信息"""
    name: str
    path: Path
    parent_class: Optional[str] = None
    variables: List[SyncVariable] = field(default_factory=list)
    is_cpp_class: bool = False


@dataclass
class CppClassInfo:
    """C++类信息"""
    name: str
    header_path: Optional[Path] = None
    cpp_path: Optional[Path] = None
    parent_class: Optional[str] = None
    variables: List[SyncVariable] = field(default_factory=list)


def normalize_blueprint_name(name: str) -> str:
    """标准化蓝图名称"""
    if name.startswith("/Game/"):
        name = name.split("/")[-1]
    if name.endswith("_C"):
        name = name[:-2]
    return name


def find_json_file(bp_name: str, json_dir: Path) -> Optional[Path]:
    """查找蓝图的JSON导出文件"""
    bp_name = normalize_blueprint_name(bp_name)
    json_file = json_dir / f"{bp_name}.json"
    if json_file.exists():
        return json_file
    json_file = json_dir / f"{bp_name}_C.json"
    if json_file.exists():
        return json_file
    return None


def parse_blueprint_json(json_path: Path) -> Optional[BlueprintInfo]:
    """解析蓝图JSON文件"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  警告: 无法解析 {json_path}: {e}")
        return None
    
    blueprint_data = data.get('blueprint', data)
    bp_name = blueprint_data.get('name', json_path.stem)
    bp_info = BlueprintInfo(
        name=bp_name,
        path=json_path,
        parent_class=blueprint_data.get('parentClass'),
        is_cpp_class=False
    )
    
    variables = blueprint_data.get('variables', [])
    for var in variables:
        is_rep = var.get('isReplicated', False)
        is_rep_notify = var.get('isRepNotify', False)
        
        if is_rep or is_rep_notify:
            sync_var = SyncVariable(
                name=var.get('name', 'Unknown'),
                var_type=var.get('type', 'Unknown'),
                source_class=bp_name,
                is_rep_notify=is_rep_notify,
                is_replicated=is_rep,
                source_type="Blueprint"
            )
            bp_info.variables.append(sync_var)
    
    return bp_info


def find_cpp_files(class_name: str, cpp_source: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """
    查找C++类的头文件和源文件
    返回: (header_path, cpp_path)
    """
    # 移除A/U前缀（如果存在）
    base_name = class_name
    if base_name.startswith('A') or base_name.startswith('U'):
        base_name = base_name[1:]
    
    header_path = None
    cpp_path = None
    
    if cpp_source.exists():
        # 搜索头文件
        for h_file in cpp_source.rglob("*.h"):
            if h_file.name == f"{base_name}.h":
                header_path = h_file
                break
        
        # 搜索源文件
        for cpp_file in cpp_source.rglob("*.cpp"):
            if cpp_file.name == f"{base_name}.cpp":
                cpp_path = cpp_file
                break
    
    return header_path, cpp_path


def parse_cpp_header(header_path: Path) -> Optional[CppClassInfo]:
    """解析C++头文件，提取同步变量"""
    try:
        with open(header_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"  警告: 无法读取 {header_path}: {e}")
        return None
    
    # 提取类名
    class_match = re.search(r'class\s+\w+\s+(?:EM_API\s+)?(A\w+|U\w+)', content)
    if not class_match:
        return None
    
    class_name = class_match.group(1)
    cpp_info = CppClassInfo(name=class_name, header_path=header_path)
    
    # 提取父类
    parent_match = re.search(r'class\s+\w+\s+(?:EM_API\s+)?\w+\s*:\s*public\s+(\w+)', content)
    if parent_match:
        cpp_info.parent_class = parent_match.group(1)
    
    # 查找同步变量声明
    # 模式: UPROPERTY(...Replicated...) 类型 变量名;
    upattern = r'UPROPERTY\s*\(\s*([^)]*Replicated[^)]*)\s*\)\s*\n\s*([\w<>,:\s]+?)\s+(\w+)\s*;'
    
    for match in re.finditer(upattern, content, re.MULTILINE | re.DOTALL):
        uproperty_args = match.group(1)
        var_type = match.group(2).strip()
        var_name = match.group(3)
        
        is_rep_notify = 'ReplicatedUsing' in uproperty_args
        is_replicated = 'Replicated' in uproperty_args
        
        sync_var = SyncVariable(
            name=var_name,
            var_type=var_type,
            source_class=class_name,
            is_rep_notify=is_rep_notify,
            is_replicated=is_replicated,
            source_type="C++"
        )
        cpp_info.variables.append(sync_var)
    
    # 也尝试单行模式
    single_line_pattern = r'UPROPERTY\s*\(\s*([^)]*Replicated[^)]*)\s*\)\s*([\w<>,:\s]+?)\s+(\w+)\s*;'
    for match in re.finditer(single_line_pattern, content):
        uproperty_args = match.group(1)
        var_type = match.group(2).strip()
        var_name = match.group(3)
        
        # 检查是否已添加
        if not any(v.name == var_name for v in cpp_info.variables):
            is_rep_notify = 'ReplicatedUsing' in uproperty_args
            is_replicated = 'Replicated' in uproperty_args
            
            sync_var = SyncVariable(
                name=var_name,
                var_type=var_type,
                source_class=class_name,
                is_rep_notify=is_rep_notify,
                is_replicated=is_replicated,
                source_type="C++"
            )
            cpp_info.variables.append(sync_var)
    
    return cpp_info


def analyze_cpp_modifications(var_name: str, class_name: str, cpp_path: Path) -> Tuple[List[Dict], bool]:
    """
    分析C++源文件中的变量修改
    返回: (修改位置列表, 是否标脏)
    """
    modifications = []
    has_mark_dirty = False
    
    try:
        with open(cpp_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            lines = content.split('\n')
    except Exception as e:
        return modifications, has_mark_dirty
    
    # 查找变量修改模式
    # 1. 直接赋值: VarName = 
    # 2. 自增/自减: VarName++, ++VarName, VarName--, --VarName
    # 3. 复合赋值: VarName +=, VarName -=, etc.
    
    patterns = [
        rf'\b{re.escape(var_name)}\s*=',
        rf'\b{re.escape(var_name)}\s*\+\+',
        rf'\+\+\s*{re.escape(var_name)}\b',
        rf'\b{re.escape(var_name)}\s*--',
        rf'--\s*{re.escape(var_name)}\b',
        rf'\b{re.escape(var_name)}\s*\+=',
        rf'\b{re.escape(var_name)}\s*-=',
        rf'\b{re.escape(var_name)}\s*\*=',
        rf'\b{re.escape(var_name)}\s*/=',
    ]
    
    for i, line in enumerate(lines, 1):
        for pattern in patterns:
            if re.search(pattern, line):
                # 检查是否在注释中
                stripped = line.strip()
                if stripped.startswith('//') or stripped.startswith('*'):
                    continue
                
                # 向前检查50行是否有MarkDirty
                check_start = max(0, i - 50)
                check_end = min(len(lines), i + 5)
                context = '\n'.join(lines[check_start:check_end])
                
                # 查找 MARK_PROPERTY_DIRTY_FROM_NAME
                dirty_pattern = rf'MARK_PROPERTY_DIRTY_FROM_NAME\s*\(\s*[^,]+\s*,\s*{re.escape(var_name)}\s*,'
                is_dirty = bool(re.search(dirty_pattern, context))
                
                # 也检查各种标脏函数调用
                mark_patterns = [
                    rf'MarkDirty_{re.escape(var_name)}\s*\(',  # MarkDirty_VarName
                    rf'Mark{re.escape(var_name)}AsDirty',      # MarkVarNameAsDirty
                    rf'Mark{re.escape(var_name)}Dirty',        # MarkVarNameDirty
                ]
                for mp in mark_patterns:
                    if re.search(mp, context):
                        is_dirty = True
                        break
                
                if is_dirty:
                    has_mark_dirty = True
                
                modifications.append({
                    'file': str(cpp_path),
                    'line': i,
                    'code': line.strip(),
                    'has_mark_dirty': is_dirty
                })
                break  # 只记录一次每行
    
    return modifications, has_mark_dirty


def build_inheritance_chain(bp_name: str, json_dir: Path, cpp_source: Path) -> Tuple[List[BlueprintInfo], List[CppClassInfo]]:
    """构建蓝图和C++继承链"""
    bp_chain = []
    cpp_chain = []
    visited = set()
    current_name = normalize_blueprint_name(bp_name)
    
    while current_name and current_name not in visited:
        visited.add(current_name)
        
        # 先尝试查找蓝图
        json_file = find_json_file(current_name, json_dir)
        if json_file:
            bp_info = parse_blueprint_json(json_file)
            if bp_info:
                bp_chain.append(bp_info)
                parent = bp_info.parent_class
                if parent:
                    if parent.startswith('/Script/'):
                        # C++类，转到C++查找
                        current_name = parent.split('.')[-1]
                        # 查找C++类
                        header_path, cpp_path = find_cpp_files(current_name, cpp_source)
                        if header_path:
                            cpp_info = parse_cpp_header(header_path)
                            if cpp_info:
                                cpp_info.cpp_path = cpp_path
                                cpp_chain.append(cpp_info)
                        break
                    else:
                        current_name = normalize_blueprint_name(parent)
                else:
                    break
            else:
                break
        else:
            # 尝试查找C++类
            header_path, cpp_path = find_cpp_files(current_name, cpp_source)
            if header_path:
                cpp_info = parse_cpp_header(header_path)
                if cpp_info:
                    cpp_info.cpp_path = cpp_path
                    cpp_chain.append(cpp_info)
                    # 继续查找C++父类
                    current_name = cpp_info.parent_class
                else:
                    break
            else:
                print(f"  警告: 找不到 {current_name} 的信息")
                break
    
    return bp_chain, cpp_chain


def find_lua_files(bp_name: str, lua_root: Path) -> List[Path]:
    """查找蓝图对应的所有Lua文件"""
    bp_name = normalize_blueprint_name(bp_name)
    lua_files = []
    
    if lua_root.exists():
        for lua_file in lua_root.rglob("*.lua"):
            if lua_file.name == f"{bp_name}_C.lua":
                lua_files.append(lua_file)
    
    return lua_files


def analyze_lua_modifications(var_name: str, lua_files: List[Path]) -> Tuple[List[Dict], bool]:
    """分析Lua文件中的变量修改"""
    modifications = []
    has_mark_dirty = False
    
    for lua_file in lua_files:
        try:
            with open(lua_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception:
            continue
        
        for i, line in enumerate(lines, 1):
            pattern = rf'self\.{re.escape(var_name)}\s*='
            if re.search(pattern, line):
                check_start = max(0, i - 50)
                check_end = min(len(lines), i + 5)
                context = ''.join(lines[check_start:check_end])
                
                dirty_pattern = rf'MarkDirty\s*\(\s*["\']{re.escape(var_name)}["\']\s*\)'
                is_dirty = bool(re.search(dirty_pattern, context))
                
                if is_dirty:
                    has_mark_dirty = True
                
                modifications.append({
                    'file': str(lua_file.relative_to(lua_file.parent.parent.parent)),
                    'line': i,
                    'code': line.strip(),
                    'has_mark_dirty': is_dirty
                })
    
    return modifications, has_mark_dirty


def analyze_blueprint(
    bp_name: str,
    json_dir: Path,
    lua_root: Path,
    cpp_source: Path
) -> Dict:
    """分析指定蓝图"""
    print(f"\n分析蓝图: {bp_name}")
    print("=" * 60)
    
    # 1. 构建继承链
    print("\n[1/5] 构建继承链...")
    bp_chain, cpp_chain = build_inheritance_chain(bp_name, json_dir, cpp_source)
    
    print(f"  找到 {len(bp_chain)} 个蓝图类, {len(cpp_chain)} 个C++类")
    for bp in bp_chain:
        print(f"  - [BP] {bp.name}: {len(bp.variables)} 个同步变量")
    for cpp in cpp_chain:
        print(f"  - [C++] {cpp.name}: {len(cpp.variables)} 个同步变量")
    
    # 2. 收集所有同步变量
    print("\n[2/5] 收集同步变量...")
    all_variables: Dict[str, SyncVariable] = {}
    
    # 从基类到子类遍历
    for bp in reversed(bp_chain):
        for var in bp.variables:
            if var.name not in all_variables:
                all_variables[var.name] = var
    
    for cpp in reversed(cpp_chain):
        for var in cpp.variables:
            if var.name not in all_variables:
                all_variables[var.name] = var
    
    print(f"  共 {len(all_variables)} 个唯一同步变量")
    
    # 3. 查找Lua文件
    print("\n[3/5] 查找Lua文件...")
    lua_files = find_lua_files(bp_name, lua_root)
    if lua_files:
        print(f"  找到 {len(lua_files)} 个Lua文件")
    else:
        print("  未找到Lua文件")
    
    # 4. 检查Lua修改
    print("\n[4/5] 检查Lua修改...")
    for var_name, var in all_variables.items():
        if lua_files:
            mods, has_dirty = analyze_lua_modifications(var_name, lua_files)
            var.lua_modifications = mods
            var.has_mark_dirty_lua = has_dirty
    
    # 5. 检查C++修改
    print("\n[5/5] 检查C++修改...")
    for var_name, var in all_variables.items():
        if var.source_type == "C++":
            # 查找该变量所属的C++类
            for cpp in cpp_chain:
                if cpp.name == var.source_class and cpp.cpp_path:
                    mods, has_dirty = analyze_cpp_modifications(var_name, cpp.name, cpp.cpp_path)
                    var.cpp_modifications = mods
                    var.has_mark_dirty_cpp = has_dirty
                    break
    
    # 识别问题变量
    problem_vars = []
    for var in all_variables.values():
        has_lua_problem = var.lua_modifications and not var.has_mark_dirty_lua
        has_cpp_problem = var.cpp_modifications and not var.has_mark_dirty_cpp
        
        if has_lua_problem or has_cpp_problem:
            problem_vars.append(var)
    
    return {
        'blueprint_name': bp_name,
        'bp_chain': bp_chain,
        'cpp_chain': cpp_chain,
        'variables': list(all_variables.values()),
        'lua_files': lua_files,
        'problem_variables': problem_vars
    }


def generate_report(result: Dict, output_file: Optional[Path] = None):
    """生成分析报告"""
    if not result:
        return
    
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    lines = []
    bp_name = result['blueprint_name']
    
    lines.append(f"# 蓝图与C++同步变量分析报告: {bp_name}")
    lines.append("")
    
    # 继承链
    lines.append("## 继承链")
    for bp in result['bp_chain']:
        parent_info = f" (父类: {bp.parent_class})" if bp.parent_class else ""
        lines.append(f"- [BP] {bp.name}{parent_info}")
    for cpp in result['cpp_chain']:
        parent_info = f" (父类: {cpp.parent_class})" if cpp.parent_class else ""
        lines.append(f"- [C++] {cpp.name}{parent_info}")
    lines.append("")
    
    # Lua文件
    lines.append("## Lua文件")
    lua_files = result['lua_files']
    if lua_files:
        for f in lua_files:
            lines.append(f"- `{f}`")
    else:
        lines.append("- 未找到Lua文件")
    lines.append("")
    
    # 同步变量列表
    lines.append("## 同步变量列表")
    lines.append("")
    lines.append("| 变量名 | 类型 | 来源 | 同步方式 | Lua修改 | C++修改 | 标脏状态 | 风险 |")
    lines.append("|--------|------|------|----------|---------|---------|----------|------|")
    
    for var in result['variables']:
        sync_type = "RepNotify" if var.is_rep_notify else "Replicated"
        source = f"[{var.source_type}] {var.source_class}"
        
        # Lua修改
        if var.lua_modifications:
            lua_info = f"{len(var.lua_modifications)}处"
            lua_dirty = "已标脏" if var.has_mark_dirty_lua else "未标脏"
        else:
            lua_info = "无"
            lua_dirty = "-"
        
        # C++修改
        if var.cpp_modifications:
            cpp_info = f"{len(var.cpp_modifications)}处"
            cpp_dirty = "已标脏" if var.has_mark_dirty_cpp else "未标脏"
        else:
            cpp_info = "无"
            cpp_dirty = "-"
        
        # 风险等级
        has_lua_problem = var.lua_modifications and not var.has_mark_dirty_lua
        has_cpp_problem = var.cpp_modifications and not var.has_mark_dirty_cpp
        
        if has_lua_problem or has_cpp_problem:
            risk = "[CRITICAL]" if var.is_replicated else "[HIGH]"
        elif var.lua_modifications or var.cpp_modifications:
            risk = "[MEDIUM]"
        else:
            risk = "[LOW]"
        
        dirty_status = f"Lua:{lua_dirty}, C++:{cpp_dirty}"
        
        lines.append(
            f"| {var.name} | {var.var_type} | {source} | {sync_type} | "
            f"{lua_info} | {cpp_info} | {dirty_status} | {risk} |"
        )
    
    lines.append("")
    
    # 问题变量详情
    problem_vars = result['problem_variables']
    if problem_vars:
        lines.append("## [!] 问题变量详情")
        lines.append("")
        lines.append(f"发现 **{len(problem_vars)}** 个变量修改未标脏，可能导致网络同步问题。")
        lines.append("")
        
        for var in problem_vars:
            has_lua_problem = var.lua_modifications and not var.has_mark_dirty_lua
            has_cpp_problem = var.cpp_modifications and not var.has_mark_dirty_cpp
            
            risk = "[CRITICAL]" if var.is_replicated else "[HIGH]"
            lines.append(f"### {risk} {var.name}")
            lines.append("")
            lines.append(f"- **类型**: {var.var_type}")
            lines.append(f"- **来源**: [{var.source_type}] {var.source_class}")
            lines.append(f"- **同步方式**: {'RepNotify' if var.is_rep_notify else 'Replicated'}")
            lines.append("")
            
            # Lua修改详情
            if has_lua_problem:
                lines.append("**Lua修改 (未标脏)**:")
                lines.append("")
                for mod in var.lua_modifications[:5]:
                    lines.append(f"```lua")
                    lines.append(f"-- {mod['file']}:{mod['line']}")
                    lines.append(f"{mod['code']}")
                    lines.append(f"```")
                    lines.append("")
                if len(var.lua_modifications) > 5:
                    lines.append(f"*... 还有 {len(var.lua_modifications) - 5} 处修改 ...*")
                    lines.append("")
                
                lines.append("**Lua修复建议**:")
                lines.append("```lua")
                lines.append(f"self:MarkDirty(\"{var.name}\")")
                lines.append(f"self.{var.name} = newValue")
                lines.append("```")
                lines.append("")
            
            # C++修改详情
            if has_cpp_problem:
                lines.append("**C++修改 (未标脏)**:")
                lines.append("")
                for mod in var.cpp_modifications[:5]:
                    lines.append(f"```cpp")
                    lines.append(f"// {mod['file']}:{mod['line']}")
                    lines.append(f"{mod['code']}")
                    lines.append(f"```")
                    lines.append("")
                if len(var.cpp_modifications) > 5:
                    lines.append(f"*... 还有 {len(var.cpp_modifications) - 5} 处修改 ...*")
                    lines.append("")
                
                lines.append("**C++修复建议**:")
                lines.append("```cpp")
                lines.append(f"// 在修改后添加标脏")
                lines.append(f"{var.name} = newValue;")
                lines.append(f"MARK_PROPERTY_DIRTY_FROM_NAME({var.source_class}, {var.name}, this);")
                lines.append("```")
                lines.append("")
    else:
        lines.append("## [OK] 检查结果")
        lines.append("")
        lines.append("未发现同步变量修改未标脏的问题。")
        lines.append("")
    
    report = "\n".join(lines)
    
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n报告已保存到: {output_file}")
    else:
        print("\n" + "=" * 60)
        print(report)
    
    return report


def main():
    parser = argparse.ArgumentParser(description='分析蓝图与C++同步变量')
    parser.add_argument('--blueprint', '-b', required=True, help='蓝图名称')
    parser.add_argument('--json-dir', '-j', type=Path, default=DEFAULT_JSON_DIR,
                        help=f'JSON导出目录 (默认: {DEFAULT_JSON_DIR})')
    parser.add_argument('--lua-root', '-l', type=Path, default=DEFAULT_LUA_ROOT,
                        help=f'Lua脚本根目录 (默认: {DEFAULT_LUA_ROOT})')
    parser.add_argument('--cpp-source', '-c', type=Path, default=DEFAULT_CPP_SOURCE,
                        help=f'C++源码目录 (默认: {DEFAULT_CPP_SOURCE})')
    parser.add_argument('--output', '-o', type=Path, help='输出报告路径')
    
    args = parser.parse_args()
    
    result = analyze_blueprint(
        args.blueprint,
        args.json_dir,
        args.lua_root,
        args.cpp_source
    )
    
    if result:
        generate_report(result, args.output)
    else:
        print("分析失败")
        sys.exit(1)


if __name__ == '__main__':
    main()
