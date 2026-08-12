#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UE T3D文件动画分析工具
用于分析Unreal Engine导出的T3D格式文件中的动画数据
"""

import re
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class AnimationEvent:
    """动画事件信息"""
    event_name: str
    trigger_frame: int  # 帧数（原始值）
    trigger_time: float  # 秒数（转换后）

    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_name": self.event_name,
            "trigger_frame": self.trigger_frame,
            "trigger_time": self.trigger_time
        }


@dataclass
class WidgetAnimation:
    """Widget动画信息"""
    name: str
    events: List[AnimationEvent] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
        }
        if self.events:
            result["events"] = [e.to_dict() for e in self.events]
        return result


class T3DAnimationAnalyzer:
    """T3D文件动画分析器"""
    
    # UE时间单位：每秒60000帧（即1帧 = 1/60000秒）
    FRAMES_PER_SECOND = 60000
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.content: str = ""
        self.animations: List[WidgetAnimation] = []
        
    def load_file(self) -> bool:
        """加载T3D文件，尝试多种编码"""
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

                print(f"✓ 成功加载文件: {self.file_path}")
                print(f"  文件大小: {len(self.content):,} 字符")
                print(f"  使用编码: {encoding}")
                return True
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"✗ 加载文件失败: {e}")
                return False

        print(f"✗ 无法使用任何已知编码加载文件")
        return False
    
    def _extract_block_content(self, content: str, start_pos: int) -> str:
        """提取从start_pos开始的完整块内容（处理嵌套）"""
        lines = content[start_pos:].split('\n')
        result_lines = []
        depth = 0
        
        for line in lines:
            result_lines.append(line)
            stripped = line.strip()
            
            if stripped.startswith('Begin Object'):
                depth += 1
            elif stripped.startswith('End Object'):
                depth -= 1
                if depth == 0:
                    break
        
        return '\n'.join(result_lines)
    
    def _frame_to_seconds(self, frame: int) -> float:
        """将帧数转换为秒数"""
        return frame / self.FRAMES_PER_SECOND
    
    def parse_animations(self):
        """解析动画数据"""
        # 查找所有 WidgetAnimation 定义
        anim_start_pattern = r'Begin Object Class=/Script/UMG\.WidgetAnimation Name="([^"]+)"'
        
        for match in re.finditer(anim_start_pattern, self.content):
            anim_name = match.group(1)
            anim_start_pos = match.start()
            
            # 过滤掉动画实例（带_INST后缀的）
            if anim_name.endswith('_INST'):
                continue
            
            # 提取完整的动画块
            anim_content = self._extract_block_content(self.content, anim_start_pos)
            
            animation = WidgetAnimation(name=anim_name)
            
            # 解析Events
            self._parse_events(anim_content, animation)
            
            # 保留所有动画（包括没有事件的）
            self.animations.append(animation)
        
        print(f"✓ 解析完成，共发现 {len(self.animations)} 个动画")
    
    def _build_event_name_mapping(self) -> Dict[str, str]:
        """建立K2Node_CustomEvent名称到CustomFunctionName的映射"""
        mapping = {}
        
        # 查找所有K2Node_CustomEvent定义
        # 格式: Begin Object Class=/Script/BlueprintGraph.K2Node_CustomEvent Name="K2Node_CustomEvent_X"
        #       CustomFunctionName="EventName"
        custom_event_pattern = r'Begin Object Class=/Script/BlueprintGraph\.K2Node_CustomEvent Name="([^"]+)".*?CustomFunctionName="([^"]+)"'
        
        for match in re.finditer(custom_event_pattern, self.content, re.DOTALL):
            node_name = match.group(1)  # K2Node_CustomEvent_0
            function_name = match.group(2)  # StartAddExp / EndAddExp
            mapping[node_name] = function_name
        
        return mapping
    
    def _parse_events(self, content: str, animation: WidgetAnimation):
        """解析Events轨道中的事件"""
        # 建立事件名称映射
        event_name_mapping = self._build_event_name_mapping()
        
        # 查找EventChannel定义
        # 格式: EventChannel=(KeyTimes=((),(Value=30000)),KeyValues=(...))
        # 使用非贪婪匹配处理嵌套括号
        event_channel_pattern = r'EventChannel=\(KeyTimes=\((.*?)\),KeyValues=\((.*?)\)\)'
        
        for match in re.finditer(event_channel_pattern, content):
            key_times_str = match.group(1)
            key_values_str = match.group(2)
            
            # 解析时间 - 包括空值()和Value=xxx
            # 空值()表示0，Value=xxx表示具体帧数
            times = []
            time_matches = list(re.finditer(r'(?:Value=(\d+)|\(\))', key_times_str))
            for tm in time_matches:
                if tm.group(1):
                    times.append(int(tm.group(1)))
                else:
                    times.append(0)  # 空值视为0帧
            
            # 解析事件名称（从K2Node_CustomEvent中提取）
            events = []
            for event_match in re.finditer(r'K2Node_CustomEvent\'"([^"]+)"', key_values_str):
                full_path = event_match.group(1)
                # 提取事件节点名称，格式如: WBP_Fame_ProgressSmall:Sequencer Events.K2Node_CustomEvent_1
                if 'K2Node_CustomEvent' in full_path:
                    node_name = full_path.split('.')[-1]
                    # 通过映射获取真实的函数名
                    event_name = event_name_mapping.get(node_name, node_name)
                    events.append(event_name)
            
            # 将时间和事件配对
            for i, event_name in enumerate(events):
                if i < len(times):
                    trigger_frame = times[i]
                elif times:
                    trigger_frame = times[-1]  # 使用最后一个时间
                else:
                    trigger_frame = 0  # 默认值
                
                # 转换为秒数
                trigger_time = self._frame_to_seconds(trigger_frame)
                
                animation.events.append(AnimationEvent(
                    event_name=event_name,
                    trigger_frame=trigger_frame,
                    trigger_time=trigger_time
                ))
    
    def generate_report(self) -> str:
        """生成文本报告"""
        lines = []
        lines.append("=" * 80)
        lines.append("UE T3D 动画分析报告")
        lines.append("=" * 80)
        lines.append(f"文件路径: {self.file_path}")
        lines.append(f"动画总数: {len(self.animations)}")
        lines.append("")
        
        for i, anim in enumerate(self.animations, 1):
            lines.append("-" * 80)
            lines.append(f"动画 {i}: {anim.name}")
            lines.append("-" * 80)
            
            # Events信息
            if anim.events:
                lines.append(f"  Events数量: {len(anim.events)}")
                lines.append("  Events列表:")
                for event in anim.events:
                    lines.append(f"    - {event.event_name} (时间: {event.trigger_time:.2f}秒 / {event.trigger_frame}帧)")
            
            lines.append("")
        
        lines.append("=" * 80)
        lines.append("报告生成完成")
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def export_json(self, output_path: str):
        """导出JSON格式数据"""
        data = {
            "file_path": str(self.file_path),
            "total_animations": len(self.animations),
            "animations": [anim.to_dict() for anim in self.animations]
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"✓ JSON数据已导出: {output_path}")
    
    def get_summary(self) -> Dict[str, Any]:
        """获取汇总统计信息"""
        total_events = sum(len(anim.events) for anim in self.animations)
        
        # 统计所有绑定的控件
        # 统计所有事件名称
        all_events: set = set()
        for anim in self.animations:
            for event in anim.events:
                all_events.add(event.event_name)
        
        return {
            "total_animations": len(self.animations),
            "total_events": total_events,
            "unique_events": len(all_events),
            "all_event_names": sorted(list(all_events))
        }


def main():
    parser = argparse.ArgumentParser(description='UE T3D文件动画分析工具')
    parser.add_argument('file', help='T3D文件路径')
    parser.add_argument('-o', '--output', help='输出JSON文件路径')
    parser.add_argument('-w', '--widget', help='按控件名筛选')
    parser.add_argument('--json-only', action='store_true', help='仅输出JSON，不输出文本报告')
    parser.add_argument('--summary', action='store_true', help='显示汇总统计信息')
    
    args = parser.parse_args()
    
    # 创建分析器
    analyzer = T3DAnimationAnalyzer(args.file)
    
    # 加载文件
    if not analyzer.load_file():
        return 1
    
    # 解析动画
    analyzer.parse_animations()
    
    # 显示汇总信息
    if args.summary:
        summary = analyzer.get_summary()
        print("\n" + "=" * 80)
        print("汇总统计信息")
        print("=" * 80)
        print(f"动画总数: {summary['total_animations']}")
        print(f"绑定总数: {summary['total_bindings']}")
        print(f"Events总数: {summary['total_events']}")
        print(f"唯一控件数: {summary['unique_widgets']}")
        print(f"唯一Events数: {summary['unique_events']}")
        print("\n所有控件名称:")
        for widget_name in summary['all_widget_names']:
            print(f"  - {widget_name}")
        print("\n所有Events名称:")
        for event_name in summary['all_event_names']:
            print(f"  - {event_name}")
        print("=" * 80)
    
    # 应用筛选
    animations_to_show = analyzer.animations
    if args.widget:
        animations_to_show = analyzer.filter_by_widget(args.widget)
        print(f"\n按控件名 '{args.widget}' 筛选，找到 {len(animations_to_show)} 个动画")
    
    # 输出文本报告
    if not args.json_only:
        if args.widget:
            # 临时替换动画列表以生成报告
            original_animations = analyzer.animations
            analyzer.animations = animations_to_show
            print(analyzer.generate_report())
            analyzer.animations = original_animations
        else:
            print(analyzer.generate_report())
    
    # 导出JSON
    if args.output:
        analyzer.export_json(args.output)
    
    return 0


if __name__ == '__main__':
    exit(main())
