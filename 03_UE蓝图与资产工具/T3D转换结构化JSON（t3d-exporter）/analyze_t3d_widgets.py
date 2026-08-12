#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UE T3D文件控件分析工具
用于分析Unreal Engine导出的T3D格式文件中的控件结构和属性
"""

import re
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class WidgetSlot:
    """控件槽位信息"""
    slot_type: str  # CanvasPanelSlot, HorizontalBoxSlot等
    parent_name: str  # 父控件名称
    slot_name: str  # 槽位名称
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot_type": self.slot_type,
            "parent_name": self.parent_name,
            "slot_name": self.slot_name
        }


@dataclass
class WidgetInfo:
    """控件信息"""
    name: str
    widget_class: str
    display_label: Optional[str] = None
    text: Optional[str] = None  # TextBlock的文本内容
    is_variable: bool = False
    slot: Optional[WidgetSlot] = None
    
    # 通用属性
    visibility: Optional[str] = None
    render_opacity: Optional[float] = None
    color: Optional[Dict[str, float]] = None  # RGBA
    
    # 尺寸和位置
    size: Optional[Dict[str, float]] = None  # width, height
    position: Optional[Dict[str, float]] = None  # x, y
    
    # 字体信息 (TextBlock)
    font_size: Optional[int] = None
    font_family: Optional[str] = None
    
    # 图片/材质信息 (Image, ProgressBar)
    brush_resource: Optional[str] = None  # 材质或纹理路径
    
    # ProgressBar特有
    percent: Optional[float] = None
    
    # ListView特有
    entry_widget_class: Optional[str] = None  # EntryWidgetClass路径

    # 其他原始属性
    raw_properties: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "widget_class": self.widget_class,
            "display_label": self.display_label,
            "text": self.text,
            "is_variable": self.is_variable,
            "slot": self.slot.to_dict() if self.slot else None,
            "visibility": self.visibility,
            "render_opacity": self.render_opacity,
            "color": self.color,
            "size": self.size,
            "position": self.position,
            "font_size": self.font_size,
            "font_family": self.font_family,
            "brush_resource": self.brush_resource,
            "percent": self.percent,
            "entry_widget_class": self.entry_widget_class,
        }
        # 过滤掉None值
        return {k: v for k, v in result.items() if v is not None}


class T3DWidgetAnalyzer:
    """T3D文件控件分析器"""
    
    # UMG控件类型列表
    UMG_WIDGET_TYPES = [
        'Button', 'TextBlock', 'Image', 'ProgressBar', 'CanvasPanel',
        'HorizontalBox', 'VerticalBox', 'SizeBox', 'Overlay', 'ScaleBox',
        'WidgetSwitcher', 'ScrollBox', 'ListView', 'ComboBoxString',
        'EditableText', 'Slider', 'CheckBox', 'SpinBox', 'Border',
        'GridPanel', 'UniformGridPanel', 'WrapBox', 'Spacer',
        'InvalidationBox', 'RetainerBox', 'SafeZone', 'Viewport',
        'ContentWidget', 'NamedSlot', 'ExpandableArea',
        'CircularThrobber', 'Throbber', 'SpinBox'
    ]

    # 其他命名空间的控件类型 (需要特殊处理的派生类)
    OTHER_WIDGET_TYPES = [
        'NiagaraSystemWidget',  # NiagaraUIRenderer
        'EMListView',           # EM项目派生的ListView
        'EMScrollBox',          # EM项目派生的ScrollBox
        'UEMListView',          # UEM前缀的ListView
        'UListView',            # U前缀的ListView
    ]
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.content: str = ""
        self.widgets: List[WidgetInfo] = []
        self.widget_tree: Dict[str, Any] = {}
        
    def load_file(self) -> bool:
        """加载T3D文件"""
        encodings = ['utf-8', 'utf-16-le', 'gbk', 'latin-1']

        for encoding in encodings:
            try:
                with open(self.file_path, 'r', encoding=encoding) as f:
                    self.content = f.read()

                # 检查内容是否有效（避免ASCII文件被UTF-16LE错误解析）
                if encoding == 'utf-16-le' and len(self.content) > 100:
                    null_count = self.content.count('\x00')
                    if null_count > len(self.content) * 0.1:
                        raise UnicodeDecodeError(encoding, '', 0, 0, 'Invalid decoding result')

                print(f"  成功加载文件: {self.file_path}")
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
    
    def _parse_slot(self, slot_str: str) -> Optional[WidgetSlot]:
        """解析槽位信息"""
        # 格式: Slot=CanvasPanelSlot'"WBP_Fame_ProgressSmall_C:WidgetTree.CanvasPanel_59.CanvasPanelSlot_18"'
        match = re.search(r'(\w+)\'"[^:]+:WidgetTree\.(\w+)\.(\w+)"\'', slot_str)
        if match:
            return WidgetSlot(
                slot_type=match.group(1),
                parent_name=match.group(2),
                slot_name=match.group(3)
            )
        return None
    
    def _parse_color(self, color_str: str) -> Optional[Dict[str, float]]:
        """解析颜色值"""
        # 格式: (SpecifiedColor=(R=1.000000,G=0.653507,B=0.101190,A=1.000000))
        match = re.search(r'R=([\d.]+),G=([\d.]+),B=([\d.]+),A=([\d.]+)', color_str)
        if match:
            return {
                "r": float(match.group(1)),
                "g": float(match.group(2)),
                "b": float(match.group(3)),
                "a": float(match.group(4))
            }
        return None
    
    def _parse_text(self, text_str: str) -> Optional[str]:
        """解析文本内容"""
        # 格式: NSLOCTEXT("[...]", "[...]", "实际文本")
        # 使用非贪婪匹配处理第一个和第二个参数（可能包含方括号等特殊字符）
        match = re.search(r'NSLOCTEXT\(".*?",\s*".*?",\s*"([^"]+)"\)', text_str)
        if match:
            return match.group(1)
        return None
    
    def _parse_size(self, content: str) -> Optional[Dict[str, float]]:
        """解析尺寸信息"""
        # 从Brush或WidgetStyle中解析ImageSize
        match = re.search(r'ImageSize=\(X=([\d.]+),Y=([\d.]+)\)', content)
        if match:
            return {
                "width": float(match.group(1)),
                "height": float(match.group(2))
            }
        return None
    
    def _parse_brush_resource(self, content: str) -> Optional[str]:
        """解析Brush资源路径"""
        # 匹配ResourceObject=Texture2D'"..."' 或 ResourceObject=MaterialInstanceConstant'"..."'
        match = re.search(r'ResourceObject=(\w+)\'"([^"]+)"\'', content)
        if match:
            resource_type = match.group(1)
            resource_path = match.group(2)
            return f"{resource_type}:{resource_path}"
        return None
    
    def _parse_font_info(self, content: str) -> tuple:
        """解析字体信息"""
        font_size = None
        font_family = None

        # 解析Size
        size_match = re.search(r'Size=(\d+)', content)
        if size_match:
            font_size = int(size_match.group(1))

        # 解析FontObject
        font_match = re.search(r'FontObject=Font\'"([^"]+)"\'', content)
        if font_match:
            font_family = font_match.group(1)

        return font_size, font_family

    def _parse_entry_widget_class(self, content: str) -> Optional[str]:
        """解析ListView的EntryWidgetClass"""
        # 格式: EntryWidgetClass=WidgetBlueprintGeneratedClass'"/Game/.../WidgetName.WidgetName_C"'
        match = re.search(r'EntryWidgetClass=\w+\'"([^"]+)"\'', content)
        if match:
            return match.group(1)
        return None
    
    def parse_widgets(self):
        """解析所有控件"""
        # 构建控件类型正则 - 包括UMG和其他命名空间
        all_widget_types = self.UMG_WIDGET_TYPES + self.OTHER_WIDGET_TYPES
        widget_types_pattern = '|'.join(all_widget_types)
        
        # 匹配两种格式:
        # 1. /Script/UMG.* 或 /Script/其他命名空间.*
        # 2. /Game/.../WidgetName.WidgetName_C (用户自定义控件)
        patterns = [
            # 标准UMG控件
            rf'Begin Object Class=/Script/\w+\.({widget_types_pattern}) Name="([^"]+)"',
            # 用户自定义控件 - 匹配 /Game/.../WidgetName_C Name="..."
            r'Begin Object Class=/Game/[^\s]+\.([^\s]+)_C Name="([^"]+)"'
        ]
        
        # 用于去重的集合
        seen_widgets: set = set()
        
        # 收集所有匹配的控件
        all_matches = []
        for pattern in patterns:
            for match in re.finditer(pattern, self.content):
                all_matches.append(match)
        
        # 按位置排序，确保处理顺序一致
        all_matches.sort(key=lambda m: m.start())
        
        for match in all_matches:
            widget_type = match.group(1)
            widget_name = match.group(2)
            start_pos = match.start()
            
            # 提取控件块内容
            widget_content = self._extract_block_content(self.content, start_pos)
            
            # 解析Text (TextBlock) - 提前解析用于去重判断
            text = None
            text_match = re.search(r'Text=(NSLOCTEXT\([^)]+\))', widget_content)
            if text_match:
                text = self._parse_text(text_match.group(1))
            
            # 去重：基于控件名称和类型
            widget_key = (widget_name, widget_type)
            if widget_key in seen_widgets:
                # 如果已存在，检查当前控件是否有Text，如果有则更新
                if text:
                    # 找到已存在的控件并更新其text
                    for existing_widget in self.widgets:
                        if existing_widget.name == widget_name and existing_widget.widget_class == widget_type:
                            existing_widget.text = text
                            break
                continue
            seen_widgets.add(widget_key)
            
            # 创建控件信息对象
            widget = WidgetInfo(name=widget_name, widget_class=widget_type)
            widget.text = text
            
            # 解析DisplayLabel
            label_match = re.search(r'DisplayLabel="([^"]+)"', widget_content)
            if label_match:
                widget.display_label = label_match.group(1)
            
            # 解析is_variable
            widget.is_variable = 'bIsVariable=True' in widget_content
            
            # 解析Slot
            slot_match = re.search(r'Slot=(\w+\'"[^"]+"\')', widget_content)
            if slot_match:
                widget.slot = self._parse_slot(slot_match.group(1))
            
            # 解析Visibility
            visibility_match = re.search(r'Visibility=(\w+)', widget_content)
            if visibility_match:
                widget.visibility = visibility_match.group(1)
            
            # 解析RenderOpacity
            opacity_match = re.search(r'RenderOpacity=([\d.]+)', widget_content)
            if opacity_match:
                widget.render_opacity = float(opacity_match.group(1))
            
            # 解析Color
            color_match = re.search(r'ColorAndOpacity=\(([^)]+)\)', widget_content)
            if color_match:
                widget.color = self._parse_color(color_match.group(1))
            
            # 解析Size
            widget.size = self._parse_size(widget_content)
            
            # 解析Brush资源
            widget.brush_resource = self._parse_brush_resource(widget_content)
            
            # 解析字体信息 (TextBlock)
            font_match = re.search(r'Font=\(([^)]+)\)', widget_content)
            if font_match:
                widget.font_size, widget.font_family = self._parse_font_info(font_match.group(1))
            
            # 解析Percent (ProgressBar)
            percent_match = re.search(r'Percent=([\d.]+)', widget_content)
            if percent_match:
                widget.percent = float(percent_match.group(1))

            # 解析EntryWidgetClass (ListView/EMListView)
            widget.entry_widget_class = self._parse_entry_widget_class(widget_content)

            self.widgets.append(widget)
        
        print(f"  解析完成，共发现 {len(self.widgets)} 个控件")
    
    def build_widget_tree(self) -> List[Dict[str, Any]]:
        """构建嵌套控件树结构"""
        # 创建控件名称到控件对象的映射
        widget_map: Dict[str, WidgetInfo] = {w.name: w for w in self.widgets}
        
        # 创建树节点结构
        def build_tree_node(widget: WidgetInfo) -> Dict[str, Any]:
            """递归构建树节点"""
            node = widget.to_dict()
            
            # 查找子控件
            children = []
            for w in self.widgets:
                if w.slot and w.slot.parent_name == widget.name:
                    children.append(build_tree_node(w))
            
            if children:
                node["children"] = children
            
            return node
        
        # 找到根控件（没有父控件或父控件不在当前控件列表中的）
        tree: List[Dict[str, Any]] = []
        for widget in self.widgets:
            # 如果没有slot，或者是根级控件
            if not widget.slot:
                tree.append(build_tree_node(widget))
            else:
                # 检查父控件是否在当前解析的控件列表中
                parent_name = widget.slot.parent_name
                if parent_name not in widget_map:
                    # 父控件不在列表中，说明这是一个根级引用
                    tree.append(build_tree_node(widget))
        
        self.widget_tree = tree
        return tree
    
    def generate_report(self) -> str:
        """生成文本报告"""
        lines = []
        lines.append("=" * 80)
        lines.append("UE T3D 控件分析报告")
        lines.append("=" * 80)
        lines.append(f"文件路径: {self.file_path}")
        lines.append(f"控件总数: {len(self.widgets)}")
        lines.append("")
        
        # 按类型统计
        type_count: Dict[str, int] = {}
        for widget in self.widgets:
            wt = widget.widget_class
            type_count[wt] = type_count.get(wt, 0) + 1
        
        lines.append("控件类型分布:")
        for wt, count in sorted(type_count.items(), key=lambda x: -x[1]):
            lines.append(f"  - {wt}: {count}")
        lines.append("")
        
        # 详细控件信息
        lines.append("-" * 80)
        lines.append("控件详细信息")
        lines.append("-" * 80)
        lines.append("")
        
        for i, widget in enumerate(self.widgets, 1):
            lines.append(f"[{i}] {widget.name} ({widget.widget_class})")
            
            if widget.display_label:
                lines.append(f"    显示标签: {widget.display_label}")
            
            if widget.text:
                lines.append(f"    文本内容: {widget.text}")
            
            if widget.is_variable:
                lines.append(f"    是变量: True")
            
            if widget.slot:
                lines.append(f"    父控件: {widget.slot.parent_name} ({widget.slot.slot_type})")
            
            if widget.size:
                lines.append(f"    尺寸: {widget.size['width']} x {widget.size['height']}")
            
            if widget.color:
                c = widget.color
                lines.append(f"    颜色: RGBA({c['r']:.2f}, {c['g']:.2f}, {c['b']:.2f}, {c['a']:.2f})")
            
            if widget.font_size:
                lines.append(f"    字体大小: {widget.font_size}")
            
            if widget.font_family:
                lines.append(f"    字体: {widget.font_family}")
            
            if widget.brush_resource:
                lines.append(f"    资源: {widget.brush_resource}")
            
            if widget.percent is not None:
                lines.append(f"    进度: {widget.percent * 100:.0f}%")

            if widget.entry_widget_class:
                lines.append(f"    Entry控件类: {widget.entry_widget_class}")

            if widget.visibility:
                lines.append(f"    可见性: {widget.visibility}")
            
            if widget.render_opacity is not None:
                lines.append(f"    透明度: {widget.render_opacity}")
            
            lines.append("")
        
        lines.append("=" * 80)
        lines.append("报告生成完成")
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def export_json(self, output_path: str):
        """导出JSON"""
        # 构建控件树
        self.build_widget_tree()
        
        data = {
            "file_path": str(self.file_path),
            "total_widgets": len(self.widgets),
            "widget_tree": self.widget_tree
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"  JSON数据已导出: {output_path}")
    
    def get_summary(self) -> Dict[str, Any]:
        """获取汇总信息"""
        type_count: Dict[str, int] = {}
        for widget in self.widgets:
            wt = widget.widget_class
            type_count[wt] = type_count.get(wt, 0) + 1
        
        variable_widgets = [w.name for w in self.widgets if w.is_variable]
        text_widgets = [w.name for w in self.widgets if w.text]
        
        return {
            "total_widgets": len(self.widgets),
            "type_distribution": type_count,
            "variable_widgets": variable_widgets,
            "text_widgets": text_widgets
        }


def main():
    parser = argparse.ArgumentParser(description='UE T3D文件控件分析工具')
    parser.add_argument('file', help='T3D文件路径')
    parser.add_argument('-o', '--output', help='输出JSON文件路径')
    parser.add_argument('--json-only', action='store_true', help='仅输出JSON')
    parser.add_argument('--summary', action='store_true', help='显示汇总信息')
    
    args = parser.parse_args()
    
    analyzer = T3DWidgetAnalyzer(args.file)
    
    if not analyzer.load_file():
        return 1
    
    analyzer.parse_widgets()
    
    if args.summary:
        summary = analyzer.get_summary()
        print("\n" + "=" * 80)
        print("汇总统计信息")
        print("=" * 80)
        print(f"控件总数: {summary['total_widgets']}")
        print("\n控件类型分布:")
        for wt, count in sorted(summary['type_distribution'].items(), key=lambda x: -x[1]):
            print(f"  - {wt}: {count}")
        print(f"\n变量控件: {len(summary['variable_widgets'])}")
        for name in summary['variable_widgets']:
            print(f"  - {name}")
        print(f"\n带文本的控件: {len(summary['text_widgets'])}")
        for name in summary['text_widgets']:
            print(f"  - {name}")
        print("=" * 80)
    
    if not args.json_only:
        print(analyzer.generate_report())
    
    if args.output:
        analyzer.export_json(args.output)
    
    return 0


if __name__ == '__main__':
    exit(main())
