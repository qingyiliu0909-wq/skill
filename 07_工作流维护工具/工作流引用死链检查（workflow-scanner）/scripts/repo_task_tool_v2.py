#!/usr/bin/env python3
"""
Repo Task Tool v2 - 改进版死链检查工具
支持Obsidian智能链接解析，区分真死链和路径问题
"""

import os
import re
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple


class RepoTaskToolV2:
    """改进版死链检查工具 - 支持Obsidian智能解析"""

    # 匹配 [[引用]] 模式的正则表达式
    WIKI_LINK_PATTERN = re.compile(r'\[\[([^\]]+)\]\]')

    # 链接状态常量
    STATUS_OK = 'OK'  # 链接正常
    STATUS_PATH_ISSUE = 'PATH_ISSUE'  # 路径不规范，但文件存在
    STATUS_DEAD_LINK = 'DEAD_LINK'  # 文件不存在（真死链）

    def __init__(self, root_directory: str):
        """
        初始化工具

        Args:
            root_directory: 扫描的根目录路径（vault根目录）
        """
        self.root_directory = Path(root_directory).resolve()
        self.link_issues: List[Dict] = []
        self.total_files = 0
        self.total_links = 0

        # 统计数据
        self.ok_count = 0
        self.path_issue_count = 0
        self.dead_link_count = 0

    def scan(self, output_json: str = None, output_md: str = None) -> Dict:
        """
        扫描链接，不执行修复，只生成报告

        Args:
            output_json: JSON 报告输出路径
            output_md: Markdown 报告输出路径

        Returns:
            完整结果字典
        """
        print("正在扫描链接...")
        self._scan_all_files()

        # 生成结果
        result = self._generate_result()

        # 输出报告
        if output_json:
            self._save_json_report(result, output_json)
            print(f"JSON 报告已保存: {output_json}")

        if output_md:
            self._save_markdown_report(result, output_md)
            print(f"Markdown 报告已保存: {output_md}")

        return result

    def _scan_all_files(self):
        """扫描所有 .md 文件"""
        md_files = list(self.root_directory.rglob('*.md'))
        self.total_files = len(md_files)

        for md_file in md_files:
            self._scan_file(md_file)

    def _scan_file(self, md_file: Path):
        """扫描单个文件"""
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            for line_num, line in enumerate(lines, start=1):
                matches = self.WIKI_LINK_PATTERN.findall(line)
                for match in matches:
                    self.total_links += 1
                    self._check_link(md_file, line_num, match)
        except Exception as e:
            print(f"Error reading file {md_file}: {e}")

    def _check_link(self, source_file: Path, line_num: int, link: str):
        """
        检查链接状态（改进版：支持Obsidian智能解析）

        Args:
            source_file: 源文件路径
            line_num: 行号
            link: 链接内容
        """
        # 第一步：尝试标准路径解析
        standard_path = self._resolve_standard_path(source_file, link)

        if standard_path.exists():
            # 路径正确，链接正常
            self.ok_count += 1
            return

        # 第二步：判断链接类型
        # 如果链接包含路径分隔符，说明用户明确指定了路径
        # 如果该路径不存在，应判定为死链
        clean_link = link.split('|')[0]
        has_explicit_path = '/' in clean_link or '\\' in clean_link

        if has_explicit_path:
            # 明确指定了路径，但路径不存在 → 真死链
            self.dead_link_count += 1
            issue = {
                'source_file': str(source_file.relative_to(self.root_directory)),
                'line': line_num,
                'link': f'[[{link}]]',
                'status': self.STATUS_DEAD_LINK,
                'target': clean_link,
                'message': '明确指定的路径不存在'
            }
            self.link_issues.append(issue)
            return

        # 第三步：链接只包含文件名，尝试Obsidian智能解析
        obsidian_path = self._resolve_obsidian_link(link)

        if obsidian_path:
            # 文件存在，但路径不规范
            self.path_issue_count += 1
            issue = {
                'source_file': str(source_file.relative_to(self.root_directory)),
                'line': line_num,
                'link': f'[[{link}]]',
                'status': self.STATUS_PATH_ISSUE,
                'standard_path': str(standard_path),
                'actual_path': str(obsidian_path.relative_to(self.root_directory)),
                'message': '路径不规范，但Obsidian可以解析'
            }
            self.link_issues.append(issue)
        else:
            # 文件不存在，真正的死链
            self.dead_link_count += 1
            issue = {
                'source_file': str(source_file.relative_to(self.root_directory)),
                'line': line_num,
                'link': f'[[{link}]]',
                'status': self.STATUS_DEAD_LINK,
                'target': clean_link,
                'message': '目标文件不存在'
            }
            self.link_issues.append(issue)

    def _resolve_standard_path(self, source_file: Path, link: str) -> Path:
        """
        标准路径解析（原逻辑）

        Args:
            source_file: 源文件路径
            link: 链接内容

        Returns:
            解析后的路径
        """
        # 清理链接（去除显示文本部分）
        if '|' in link:
            link = link.split('|')[0]

        # 尝试多种路径解析策略
        possible_paths = [
            source_file.parent / link,  # 相对于源文件
            self.root_directory / link,  # 相对于根目录
        ]

        # 检查每个可能的路径
        for path in possible_paths:
            if not path.suffix:
                path_with_ext = path.with_suffix('.md')
                if path_with_ext.exists():
                    return path_with_ext
            if path.exists():
                return path

        # 返回第一个可能的路径（用于后续检查）
        return possible_paths[0] if possible_paths else self.root_directory / link

    def _resolve_obsidian_link(self, link: str) -> Optional[Path]:
        """
        Obsidian智能链接解析（新增）

        Obsidian的解析规则：
        1. 提取文件名（去除路径和显示文本）
        2. 在整个vault中搜索匹配的文件

        Args:
            link: 链接内容

        Returns:
            找到的文件路径，如果找不到则返回None
        """
        # 清理链接
        clean_link = link.split('|')[0]  # 去除显示文本
        clean_link = clean_link.split('/')[-1]  # 去除路径，只保留文件名
        clean_link = clean_link.split('\\')[-1]  # Windows路径分隔符

        # 去除.md后缀（如果有）
        if clean_link.endswith('.md'):
            clean_link = clean_link[:-3]

        # 在整个vault中搜索匹配的文件
        for md_file in self.root_directory.rglob('*.md'):
            if md_file.stem == clean_link:
                return md_file

        return None

    def _generate_result(self) -> Dict:
        """生成完整结果"""
        return {
            'scan_time': datetime.now().isoformat(),
            'root_directory': str(self.root_directory),
            'total_files': self.total_files,
            'total_links': self.total_links,
            'statistics': {
                'ok_count': self.ok_count,
                'path_issue_count': self.path_issue_count,
                'dead_link_count': self.dead_link_count
            },
            'issues': self.link_issues,
            'recommendation': self._generate_recommendation()
        }

    def _generate_recommendation(self) -> str:
        """生成处理建议"""
        if self.dead_link_count == 0 and self.path_issue_count == 0:
            return "所有链接都正常，无需处理。"

        recommendations = []

        if self.dead_link_count > 0:
            recommendations.append(
                f"发现 {self.dead_link_count} 个真正的死链（文件不存在），建议：\n"
                "1. 创建缺失的文件\n"
                "2. 或删除这些链接引用"
            )

        if self.path_issue_count > 0:
            recommendations.append(
                f"发现 {self.path_issue_count} 个路径问题（文件存在但路径不规范），建议：\n"
                "1. Obsidian可以正常解析这些链接，无需立即处理\n"
                "2. 如果需要标准化，可以修正相对路径"
            )

        return "\n\n".join(recommendations)

    def _save_json_report(self, result: Dict, output_file: str):
        """保存 JSON 报告"""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    def _save_markdown_report(self, result: Dict, output_file: str):
        """保存 Markdown 报告"""
        lines = [
            "# Wiki链接扫描报告（改进版）",
            "",
            f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "---",
            "",
            "## 扫描摘要",
            "",
            "| 项目 | 数值 |",
            "|------|------|",
            f"| 扫描目录 | {result.get('root_directory', 'N/A')} |",
            f"| 扫描文件数 | {result.get('total_files', 0)} |",
            f"| 总链接数 | {result.get('total_links', 0)} |",
            f"| 正常链接 | {result['statistics']['ok_count']} |",
            f"| 路径问题 | {result['statistics']['path_issue_count']} |",
            f"| 真死链 | {result['statistics']['dead_link_count']} |",
            "",
            "---",
            "",
            "## 处理建议",
            "",
            result.get('recommendation', '无'),
        ]

        # 添加详细问题列表
        if result.get('issues'):
            # 真死链
            dead_links = [i for i in result['issues'] if i['status'] == self.STATUS_DEAD_LINK]
            if dead_links:
                lines.extend([
                    "",
                    "---",
                    "",
                    "## 真正的死链（文件不存在）",
                    "",
                    "| 序号 | 源文件 | 行号 | 链接 | 目标 |",
                    "|------|--------|------|------|------|",
                ])

                for i, issue in enumerate(dead_links, start=1):
                    lines.append(
                        f"| {i} | {issue['source_file']} | {issue['line']} | "
                        f"`{issue['link']}` | {issue['target']} |"
                    )

            # 路径问题
            path_issues = [i for i in result['issues'] if i['status'] == self.STATUS_PATH_ISSUE]
            if path_issues:
                lines.extend([
                    "",
                    "---",
                    "",
                    "## 路径问题（文件存在但路径不规范）",
                    "",
                    "| 序号 | 源文件 | 行号 | 链接 | 实际文件 |",
                    "|------|--------|------|------|---------|",
                ])

                for i, issue in enumerate(path_issues, start=1):
                    lines.append(
                        f"| {i} | {issue['source_file']} | {issue['line']} | "
                        f"`{issue['link']}` | {issue['actual_path']} |"
                    )

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Repo Task Tool v2 - 改进版死链检查工具',
        epilog='注意：此版本只扫描不修复，支持Obsidian智能解析'
    )
    parser.add_argument('directory', help='扫描的目录路径（vault根目录）')
    parser.add_argument('--json', help='JSON 报告输出路径')
    parser.add_argument('--md', help='Markdown 报告输出路径')

    args = parser.parse_args()

    # 创建工具并执行
    tool = RepoTaskToolV2(args.directory)
    result = tool.scan(
        output_json=args.json,
        output_md=args.md
    )

    # 输出简要结果
    print(f"\n扫描完成:")
    print(f"  - 扫描文件: {result['total_files']}")
    print(f"  - 总链接: {result['total_links']}")
    print(f"  - 正常链接: {result['statistics']['ok_count']}")
    print(f"  - 路径问题: {result['statistics']['path_issue_count']}")
    print(f"  - 真死链: {result['statistics']['dead_link_count']}")

    # 返回状态码
    if result['statistics']['dead_link_count'] > 0:
        sys.exit(1)  # 发现死链
    else:
        sys.exit(0)  # 无死链


if __name__ == '__main__':
    main()