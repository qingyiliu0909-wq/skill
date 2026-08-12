#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UE T3D文件蓝图分析工具
用于分析Unreal Engine导出的T3D格式文件中的蓝图方法、变量和逻辑
"""

import re
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set


@dataclass
class BlueprintVariable:
    """蓝图变量"""
    name: str
    var_type: str  # 变量类型
    category: str  # 分类
    default_value: Optional[str] = None
    is_exposed: bool = False  # 是否暴露给外部
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "type": self.var_type,
            "category": self.category,
            "is_exposed": self.is_exposed,
        }
        if self.default_value:
            result["default_value"] = self.default_value
        return result


@dataclass
class ExecutionStep:
    """执行步骤"""
    step_type: str  # CallFunction, VariableGet, etc.
    target: str  # 目标对象/类
    method: str  # 方法名
    details: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "step_type": self.step_type,
            "target": self.target,
            "method": self.method,
        }
        if self.details:
            result["details"] = self.details
        return result


@dataclass
class BlueprintFunction:
    """蓝图函数/方法"""
    name: str
    is_event: bool = False  # 是否是事件（如Tick, Construct等）
    is_custom_event: bool = False  # 是否是自定义事件
    is_override: bool = False  # 是否覆盖父类方法
    parent_class: Optional[str] = None
    execution_chain: List[ExecutionStep] = field(default_factory=list)  # 执行链路
    description: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "is_event": self.is_event,
            "is_custom_event": self.is_custom_event,
            "is_override": self.is_override,
            "execution_chain": [e.to_dict() for e in self.execution_chain],
        }
        if self.parent_class:
            result["parent_class"] = self.parent_class
        if self.description:
            result["description"] = self.description
        return result


@dataclass
class BlueprintInfo:
    """蓝图信息"""
    blueprint_name: str
    parent_class: Optional[str] = None
    variables: List[BlueprintVariable] = field(default_factory=list)
    functions: List[BlueprintFunction] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "blueprint_name": self.blueprint_name,
            "parent_class": self.parent_class,
            "variables": [v.to_dict() for v in self.variables],
            "functions": [f.to_dict() for f in self.functions],
        }


class T3DBlueprintAnalyzer:
    """T3D文件蓝图分析器"""
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.content: str = ""
        self.blueprint: Optional[BlueprintInfo] = None
        
    def load_file(self) -> bool:
        """加载T3D文件"""
        encodings = ['utf-8', 'utf-16-le', 'gbk', 'latin-1']

        for encoding in encodings:
            try:
                with open(self.file_path, 'r', encoding=encoding) as f:
                    self.content = f.read()

                # 检查内容是否有效（避免ASCII文件被UTF-16LE错误解析）
                # 如果解码后包含大量不可打印字符或异常模式，尝试下一个编码
                if encoding == 'utf-16-le' and len(self.content) > 100:
                    # UTF-16LE解码ASCII文件会产生大量空白字符
                    null_count = self.content.count('\x00')
                    if null_count > len(self.content) * 0.1:
                        raise UnicodeDecodeError(encoding, '', 0, 0, 'Invalid decoding result')

                print(f"✓ 成功加载文件: {self.file_path}")
                print(f"  文件大小: {len(self.content):,} 字符")
                return True
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"✗ 加载文件失败: {e}")
                return False

        return False
    
    def _extract_block_content(self, content: str, start_pos: int) -> str:
        """提取完整块内容（处理嵌套）"""
        lines = content[start_pos:].split('\n')
        result_lines = []
        depth = 0
        started = False
        
        for line in lines:
            result_lines.append(line)
            stripped = line.strip()
            if stripped.startswith('Begin Object'):
                depth += 1
                started = True
            elif stripped.startswith('End Object'):
                depth -= 1
                if started and depth == 0:
                    break
        
        return '\n'.join(result_lines)
    
    def parse_blueprint(self):
        """解析蓝图数据"""
        # 提取蓝图名称
        bp_match = re.search(r'Begin Blueprint Class=([^\s]+) Name="([^"]+)"', self.content)
        if bp_match:
            bp_name = bp_match.group(2)
        else:
            # 尝试从文件名推断
            bp_name = self.file_path.stem
        
        self.blueprint = BlueprintInfo(blueprint_name=bp_name)
        
        # 解析父类
        # 尝试多种格式: BlueprintGeneratedClass'"..."' 或 Class'"..."'
        parent_match = re.search(r'ParentClass=(?:BlueprintGeneratedClass|Class)\'"([^"]+)"\'', self.content)
        if parent_match:
            self.blueprint.parent_class = parent_match.group(1)
        
        # 解析变量
        self._parse_variables()
        
        # 解析函数
        self._parse_functions()
        
        print(f"✓ 解析完成")
        print(f"  变量数: {len(self.blueprint.variables)}")
        print(f"  函数数: {len(self.blueprint.functions)}")
    
    def _parse_variables(self):
        """解析蓝图变量 - 只解析用户自定义变量"""
        seen_vars: Set[str] = set()
        
        # 解析用户自定义变量（NewVariables）
        # 格式: NewVariables(0)=(VarName="ExpAddTime",VarType=(PinCategory="float"),...)
        newvar_pattern = r'NewVariables\(\d+\)=\(VarName="([^"]+)".*?VarType=\([^)]*PinCategory="([^"]+)"[^)]*\)'
        
        for match in re.finditer(newvar_pattern, self.content):
            var_name = match.group(1)
            var_type = match.group(2)
            
            if var_name in seen_vars:
                continue
            seen_vars.add(var_name)
            
            # 解析默认值
            default_value = None
            default_match = re.search(rf'{var_name}=([\d.]+)', self.content)
            if default_match:
                default_value = default_match.group(1)
            
            variable = BlueprintVariable(
                name=var_name,
                var_type=var_type,
                category="UserDefined",
                default_value=default_value,
                is_exposed=True
            )
            
            self.blueprint.variables.append(variable)
    
    def _parse_functions(self):
        """解析蓝图函数"""
        seen_funcs: Set[str] = set()
        
        # 1. 解析FunctionGraphs中的函数（包括Interface方法和普通函数）
        # 查找 FunctionGraphs
        func_graph_pattern = r'FunctionGraphs\(\d+\)=EdGraph\'"([^"]+)"\''
        
        for match in re.finditer(func_graph_pattern, self.content):
            graph_name = match.group(1)
            
            # 在图中查找函数
            graph_pattern = rf'Begin Object Class=/Script/Engine\.EdGraph Name="{graph_name}"'
            graph_match = re.search(graph_pattern, self.content)
            
            if graph_match:
                start_pos = graph_match.start()
                graph_content = self._extract_block_content(self.content, start_pos)
                
                # 查找函数入口 - 在K2Node_FunctionEntry节点中查找
                func_name = None
                parent_class = None
                is_interface = False
                
                # 首先找到K2Node_FunctionEntry节点，然后从中提取FunctionReference
                entry_pattern = r'Begin Object Name="(K2Node_FunctionEntry_\d+)"(.*?)End Object'
                
                for entry_match in re.finditer(entry_pattern, graph_content, re.DOTALL):
                    entry_content = entry_match.group(2)
                    
                    # 模式1: Interface方法
                    func_ref_match = re.search(r'FunctionReference=\(MemberParent=Class\'"([^"]+)"\',MemberName="([^"]+)"\)', entry_content)
                    if func_ref_match:
                        func_name = func_ref_match.group(2)
                        parent_class = func_ref_match.group(1)
                        is_interface = "UnLuaInterface" in parent_class or "Interface" in parent_class
                        break
                    
                    # 模式2: 普通函数
                    func_ref_match = re.search(r'FunctionReference=\(MemberName="([^"]+)"\)', entry_content)
                    if func_ref_match:
                        func_name = func_ref_match.group(1)
                        break
                
                # 如果还没找到，尝试在图中查找其他FunctionReference（兼容旧格式）
                if not func_name:
                    entry_pattern = r'FunctionReference=\(MemberParent=Class\'"([^"]+)"\',MemberName="([^"]+)"\)'
                    entry_match = re.search(entry_pattern, graph_content)
                    if entry_match:
                        func_name = entry_match.group(2)
                        parent_class = entry_match.group(1)
                        is_interface = "UnLuaInterface" in parent_class or "Interface" in parent_class
                
                if not func_name:
                    entry_pattern = r'FunctionReference=\(MemberName="([^"]+)"\)'
                    entry_match = re.search(entry_pattern, graph_content)
                    if entry_match:
                        func_name = entry_match.group(1)
                
                if not func_name or func_name in seen_funcs:
                    continue
                seen_funcs.add(func_name)
                
                func = BlueprintFunction(
                    name=func_name,
                    is_override=is_interface,
                    parent_class=parent_class
                )
                
                # 解析执行链路
                self._parse_function_graph_chain(graph_content, func)
                
                # 对于GetModuleName，解析ReturnValue的默认值
                if func_name == "GetModuleName":
                    return_value_match = re.search(r'PinName="ReturnValue".*?DefaultValue="([^"]+)"', graph_content)
                    if return_value_match:
                        func.description = f"ReturnValue: {return_value_match.group(1)}"
                
                self.blueprint.functions.append(func)
        
        # 2. 解析Interface实现的方法（兼容旧格式）
        interface_pattern = r'ImplementedInterfaces\(\d+\)=\(Interface=Class\'"([^"]+)"\',Graphs=\(EdGraph\'"([^"]+)"\'\)\)'
        
        for match in re.finditer(interface_pattern, self.content):
            graph_name = match.group(2)
            
            # 在图中查找函数 - 使用Begin Object Name="..."格式查找实际内容
            graph_pattern = rf'Begin Object Name="{graph_name}"'
            graph_match = re.search(graph_pattern, self.content)
            
            if graph_match:
                start_pos = graph_match.start()
                graph_content = self._extract_block_content(self.content, start_pos)
                
                # 查找函数入口
                entry_pattern = r'FunctionReference=\(MemberParent=Class\'"([^"]+)"\',MemberName="([^"]+)"\)'
                entry_match = re.search(entry_pattern, graph_content)
                
                if entry_match:
                    func_name = entry_match.group(2)
                    parent_class = entry_match.group(1)
                    
                    if func_name in seen_funcs:
                        continue
                    seen_funcs.add(func_name)
                    
                    func = BlueprintFunction(
                        name=func_name,
                        is_override=True,
                        parent_class=parent_class
                    )
                    
                    # 解析执行链路
                    self._parse_function_graph_chain(graph_content, func)
                    
                    # 对于GetModuleName，解析ReturnValue的默认值
                    if func_name == "GetModuleName":
                        return_value_match = re.search(r'PinName="ReturnValue".*?DefaultValue="([^"]+)"', graph_content)
                        if return_value_match:
                            func.description = f"ReturnValue: {return_value_match.group(1)}"
                    
                    self.blueprint.functions.append(func)
        
        # 2. 解析自定义事件 (K2Node_CustomEvent)
        custom_event_pattern = r'Begin Object Class=/Script/BlueprintGraph\.K2Node_CustomEvent Name="([^"]+)"'
        
        for match in re.finditer(custom_event_pattern, self.content):
            node_name = match.group(1)
            start_pos = match.start()
            
            # 提取节点块
            node_content = self._extract_block_content(self.content, start_pos)
            
            # 解析事件名称
            event_name = None
            name_match = re.search(r'CustomFunctionName="([^"]+)"', node_content)
            if name_match:
                event_name = name_match.group(1)
            else:
                # 从MemberReference解析
                ref_match = re.search(r'MemberName="([^"]+)".*MemberParent=.*WidgetBlueprintGeneratedClass', node_content)
                if ref_match:
                    event_name = ref_match.group(1)
            
            if not event_name or event_name in seen_funcs:
                continue
            
            seen_funcs.add(event_name)
            
            func = BlueprintFunction(
                name=event_name,
                is_event=True,
                is_custom_event=True
            )
            
            # 解析执行链路
            self._parse_execution_chain(event_name, func)
            
            self.blueprint.functions.append(func)
        
        # 3. 解析内置事件 (K2Node_Event)
        event_pattern = r'Begin Object Class=/Script/BlueprintGraph\.K2Node_Event Name="([^"]+)"'
        
        for match in re.finditer(event_pattern, self.content):
            node_name = match.group(1)
            start_pos = match.start()
            
            # 提取节点块
            node_content = self._extract_block_content(self.content, start_pos)
            
            # 解析事件名称
            event_name = None
            parent_class = None
            
            ref_match = re.search(r'EventReference=\(MemberParent=([^\']+)\'"([^"]+)"\',MemberName="([^"]+)"\)', node_content)
            if ref_match:
                parent_class = ref_match.group(2)
                event_name = ref_match.group(3)
            
            if not event_name or event_name in seen_funcs:
                continue
            
            seen_funcs.add(event_name)
            
            func = BlueprintFunction(
                name=event_name,
                is_event=True,
                is_override=True,
                parent_class=parent_class
            )
            
            self.blueprint.functions.append(func)
        
        # 4. 解析普通函数 (K2Node_FunctionEntry)
        func_entry_pattern = r'Begin Object Class=/Script/BlueprintGraph\.K2Node_FunctionEntry Name="([^"]+)"'
        
        for match in re.finditer(func_entry_pattern, self.content):
            node_name = match.group(1)
            start_pos = match.start()
            
            # 提取节点块
            node_content = self._extract_block_content(self.content, start_pos)
            
            # 解析函数名称
            func_name = None
            ref_match = re.search(r'FunctionReference=\(MemberName="([^"]+)"', node_content)
            if ref_match:
                func_name = ref_match.group(1)
            
            if not func_name or func_name in seen_funcs:
                continue
            
            seen_funcs.add(func_name)
            
            func = BlueprintFunction(name=func_name)
            
            self.blueprint.functions.append(func)
    
    def _parse_execution_chain(self, event_name: str, func: BlueprintFunction):
        """解析函数的执行链路"""
        # 查找Sequencer Events图中的执行链路
        # 首先找到事件对应的K2Node_CustomEvent
        # 使用更精确的正则：捕获节点名称，然后验证CustomFunctionName
        event_pattern = rf'Begin Object Class=/Script/BlueprintGraph\.K2Node_CustomEvent Name="([^"]+)"'
        
        for match in re.finditer(event_pattern, self.content):
            node_name = match.group(1)
            start_pos = match.start()
            
            # 提取节点内容
            event_content = self._extract_block_content(self.content, start_pos)
            
            # 验证是否是目标事件
            func_name_match = re.search(rf'CustomFunctionName="{event_name}"', event_content)
            if not func_name_match:
                continue
            
            # 查找LinkedTo连接 - 事件连接到哪个节点
            # 格式: PinName="then",...,LinkedTo=(K2Node_CallFunction_0 7FF78A0F470050FCA64C1094EB97FC85,)
            # 需要匹配 "then" 引脚的 LinkedTo
            linked_match = re.search(r'PinName="then".*?LinkedTo=\((K2Node_[^\s]+)[^)]*\)', event_content, re.DOTALL)
            if linked_match:
                next_node_name = linked_match.group(1)
                # 递归解析执行链
                self._trace_execution(next_node_name, func.execution_chain, set())
            
            break  # 只处理第一个匹配
    
    def _parse_function_graph_chain(self, graph_content: str, func: BlueprintFunction):
        """解析FunctionGraph中的执行链路"""
        # 查找函数入口节点 K2Node_FunctionEntry - 直接在graph_content中查找LinkedTo
        # 格式: Begin Object Name="K2Node_FunctionEntry_0" ... End Object
        entry_pattern = r'Begin Object Name="(K2Node_FunctionEntry_\d+)"(.*?)End Object'
        
        for match in re.finditer(entry_pattern, graph_content, re.DOTALL):
            entry_content = match.group(2)
            
            # 查找LinkedTo连接
            linked_match = re.search(r'LinkedTo=\((K2Node_[^\s]+)[^)]*\)', entry_content)
            if linked_match:
                next_node_name = linked_match.group(1)
                # 在graph_content中追踪执行链
                self._trace_execution_in_graph(next_node_name, func.execution_chain, set(), graph_content)
                break  # 只处理第一个入口
    
    def _trace_execution_in_graph(self, node_name: str, chain: List[ExecutionStep], visited: Set[str], graph_content: str):
        """在函数图中递归追踪执行链路"""
        if node_name in visited:
            return
        visited.add(node_name)
        
        # 在graph_content中查找这个节点 - 使用非贪婪匹配获取节点内容
        # 格式: Begin Object Name="K2Node_XXX" ... End Object
        node_pattern = rf'Begin Object Name="{node_name}"(.*?)End Object'
        match = re.search(node_pattern, graph_content, re.DOTALL)
        
        if not match:
            return
        
        node_content = match.group(1)
        
        # 判断节点类型并解析
        if 'K2Node_CallFunction' in node_content:
            # 解析函数调用
            func_ref_match = re.search(r'FunctionReference=\(MemberParent=(\w+)\'"([^"]+)"\',MemberName="([^"]+)"', node_content)
            if func_ref_match:
                parent_type = func_ref_match.group(1)
                parent_path = func_ref_match.group(2)
                method_name = func_ref_match.group(3)
                target = parent_path.split('/')[-1] if '/' in parent_path else parent_path
                
                chain.append(ExecutionStep(
                    step_type="CallFunction",
                    target=target,
                    method=method_name
                ))
        elif 'K2Node_GetDataTableRow' in node_content:
            # 解析GetDataTableRow
            chain.append(ExecutionStep(
                step_type="GetDataTableRow",
                target="DataTable",
                method="GetDataTableRow"
            ))
        elif 'K2Node_FunctionResult' in node_content:
            # 函数返回节点，结束追踪
            return
        
        # 查找下一个连接
        linked_match = re.search(r'LinkedTo=\((K2Node_[^\s]+)[^)]*\)', node_content)
        if linked_match:
            next_node_name = linked_match.group(1)
            self._trace_execution_in_graph(next_node_name, chain, visited, graph_content)
    
    def _trace_execution(self, node_name: str, chain: List[ExecutionStep], visited: Set[str]):
        """递归追踪执行链路"""
        if node_name in visited:
            return
        visited.add(node_name)
        
        # 在内容中查找这个节点
        node_pattern = rf'Begin Object Class=/Script/BlueprintGraph\.K2Node_CallFunction Name="{node_name}"'
        match = re.search(node_pattern, self.content)
        
        if not match:
            # 尝试其他节点类型
            node_pattern = rf'Begin Object Class=/Script/BlueprintGraph\.K2Node_VariableGet Name="{node_name}"'
            match = re.search(node_pattern, self.content)
            if match:
                # 解析VariableGet节点
                node_content = self._extract_block_content(self.content, match.start())
                var_match = re.search(r'VariableReference=\(MemberName="([^"]+)"', node_content)
                if var_match:
                    chain.append(ExecutionStep(
                        step_type="VariableGet",
                        target="self",
                        method=var_match.group(1)
                    ))
                return
            return
        
        # 解析CallFunction节点
        node_content = self._extract_block_content(self.content, match.start())
        
        # 获取函数引用信息 - 尝试多种格式
        method_name = None
        target = "self"
        
        # 格式1: FunctionReference=(MemberParent=Class'"..."',MemberName="...")
        func_ref_match = re.search(r'FunctionReference=\(MemberParent=(\w+)\'"([^"]+)"\',MemberName="([^"]+)"', node_content)
        if func_ref_match:
            parent_type = func_ref_match.group(1)
            parent_path = func_ref_match.group(2)
            method_name = func_ref_match.group(3)
            target = parent_path.split('/')[-1] if '/' in parent_path else parent_path
        else:
            # 格式2: FunctionReference=(MemberName="...",MemberGuid=...,bSelfContext=True)
            func_ref_match = re.search(r'FunctionReference=\(MemberName="([^"]+)"', node_content)
            if func_ref_match:
                method_name = func_ref_match.group(1)
                target = "self"
        
        if method_name:
            step = ExecutionStep(
                step_type="CallFunction",
                target=target,
                method=method_name
            )
            chain.append(step)
            
            # 查找下一个连接
            linked_match = re.search(r'LinkedTo=\((K2Node_[^\s]+)[^)]*\)', node_content)
            if linked_match:
                next_node_name = linked_match.group(1)
                self._trace_execution(next_node_name, chain, visited)
    
    def generate_report(self) -> str:
        """生成文本报告"""
        if not self.blueprint:
            return "未解析蓝图数据"
        
        lines = []
        lines.append("=" * 80)
        lines.append("UE T3D 蓝图分析报告")
        lines.append("=" * 80)
        lines.append(f"文件路径: {self.file_path}")
        lines.append(f"蓝图名称: {self.blueprint.blueprint_name}")
        if self.blueprint.parent_class:
            lines.append(f"父类: {self.blueprint.parent_class}")
        lines.append("")
        
        # 变量
        lines.append("-" * 80)
        lines.append(f"变量列表 ({len(self.blueprint.variables)}个)")
        lines.append("-" * 80)
        lines.append("")
        
        for var in self.blueprint.variables:
            lines.append(f"  [{var.category}] {var.name}: {var.var_type}")
            if var.is_exposed:
                lines.append(f"    暴露给外部: True")
        
        lines.append("")
        
        # 函数
        lines.append("-" * 80)
        lines.append(f"函数/事件列表 ({len(self.blueprint.functions)}个)")
        lines.append("-" * 80)
        lines.append("")
        
        for func in self.blueprint.functions:
            func_type = "函数"
            if func.is_event:
                func_type = "自定义事件" if func.is_custom_event else "事件"
            
            lines.append(f"  [{func_type}] {func.name}")
            
            if func.parent_class:
                lines.append(f"    覆盖自: {func.parent_class}")
            
            if func.execution_chain:
                lines.append(f"    执行链路:")
                for i, step in enumerate(func.execution_chain, 1):
                    lines.append(f"      {i}. [{step.step_type}] {step.target}.{step.method}")
            
            if func.description:
                lines.append(f"    描述: {func.description}")
            
            lines.append("")
        
        lines.append("=" * 80)
        lines.append("报告生成完成")
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def export_json(self, output_path: str):
        """导出JSON"""
        if not self.blueprint:
            print("未解析蓝图数据")
            return
        
        data = {
            "file_path": str(self.file_path),
            "blueprint": self.blueprint.to_dict()
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"✓ JSON数据已导出: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='UE T3D文件蓝图分析工具')
    parser.add_argument('file', help='T3D文件路径')
    parser.add_argument('-o', '--output', help='输出JSON文件路径')
    parser.add_argument('--json-only', action='store_true', help='仅输出JSON')
    
    args = parser.parse_args()
    
    analyzer = T3DBlueprintAnalyzer(args.file)
    
    if not analyzer.load_file():
        return 1
    
    analyzer.parse_blueprint()
    
    if not args.json_only:
        print(analyzer.generate_report())
    
    if args.output:
        analyzer.export_json(args.output)
    
    return 0


if __name__ == '__main__':
    exit(main())
