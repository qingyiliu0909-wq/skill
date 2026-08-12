#!/usr/bin/env python3
"""
Repo Task Tool - 死链检查与修复工具
扫描、修复、报告一体化脚本
"""

import os
import re
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict


class RepoTaskTool:
    """死链检查与修复工具"""

    # 匹配 [[引用]] 模式的正则表达式
    WIKI_LINK_PATTERN = re.compile(r'\[\[([^\]]+)\]\]')

    def __init__(self, root_directory: str):
        """
        初始化工具

        Args:
            root_directory: 扫描的根目录路径
        """
        self.root_directory = Path(root_directory).resolve()
        self.dead_links: List[Dict] = []
        self.fix_results: List[Dict] = []
        self.total_files = 0
        self.total_links = 0

    def scan_and_fix(self, auto_fix: bool = False, output_json: str = None, output_md: str = None) -> Dict:
        """
        扫描并修复死链

        Args:
            auto_fix: 是否自动修复（不询问用户）
            output_json: JSON 报告输出路径
            output_md: Markdown 报告输出路径

        Returns:
            完整结果字典
        """
        # 1. 扫描死链
        print("正在扫描死链...")
        self._scan_all_files()

        # 2. 如果发现死链，执行修复
        if self.dead_links:
            if auto_fix:
                print(f"发现 {len(self.dead_links)} 个死链，正在自动修复...")
                self._fix_all_dead_links()
            else:
                # 显示修复计划并询问用户
                self._show_fix_plan()
                confirm = input("\n是否执行修复？(y/n): ")
                if confirm.lower() == 'y':
                    self._fix_all_dead_links()
        else:
            print("未发现死链")

        # 3. 生成结果
        result = self._generate_result()

        # 4. 输出报告
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
        """检查链接是否有效"""
        link_path = self._resolve_link_path(source_file, link)

        if not link_path.exists():
            dead_link = {
                'source_file': str(source_file.relative_to(self.root_directory)),
                'line': line_num,
                'dead_link': f'[[{link}]]',
                'target_path': str(link_path),
                'reason': self._classify_dead_link(link_path, link)
            }
            self.dead_links.append(dead_link)

    def _resolve_link_path(self, source_file: Path, link: str) -> Path:
        """解析链接路径"""
        # 清理链接（去除显示文本部分）
        if '|' in link:
            link = link.split('|')[0]

        # 尝试多种路径解析策略
        possible_paths = [
            source_file.parent / link,  # 相对于源文件
            self.root_directory / link,  # 相对于根目录
        ]

        # 如果链接只是文件名，在根目录下搜索
        if '/' not in link and '\\' not in link:
            for md_file in self.root_directory.rglob('*.md'):
                if md_file.stem == link or md_file.name == link:
                    possible_paths.append(md_file)

        # 检查每个可能的路径
        for path in possible_paths:
            if not path.suffix:
                path_with_ext = path.with_suffix('.md')
                if path_with_ext.exists():
                    return path_with_ext
            if path.exists():
                return path

        return possible_paths[0] if possible_paths else self.root_directory / link

    def _classify_dead_link(self, link_path: Path, link: str) -> str:
        """分类死链类型"""
        if '.wiki' in str(link_path):
            return 'DEAD_WIKI_LINK'
        return 'FILE_NOT_FOUND'

    def _show_fix_plan(self):
        """显示修复计划"""
        print(f"\n发现 {len(self.dead_links)} 个死链，修复计划如下：")
        for i, dead_link in enumerate(self.dead_links, start=1):
            strategy = self._get_fix_strategy(dead_link['reason'])
            print(f"{i}. {dead_link['source_file']} (行 {dead_link['line']})")
            print(f"   死链: {dead_link['dead_link']}")
            print(f"   类型: {dead_link['reason']}")
            print(f"   策略: {strategy}")

    def _get_fix_strategy(self, reason: str) -> str:
        """获取修复策略描述"""
        strategies = {
            'FILE_NOT_FOUND': '创建占位文件',
            'DEAD_WIKI_LINK': '删除引用行',
            'ORPHAN_REFERENCE': '提示用户手动处理'
        }
        return strategies.get(reason, '未知策略')

    def _fix_all_dead_links(self):
        """修复所有死链"""
        for dead_link in self.dead_links:
            fix_result = self._fix_dead_link(dead_link)
            self.fix_results.append(fix_result)

    def _fix_dead_link(self, dead_link: Dict) -> Dict:
        """修复单个死链"""
        reason = dead_link['reason']
        source_file = self.root_directory / dead_link['source_file']
        line_num = dead_link['line']
        dead_link_text = dead_link['dead_link']

        fix_result = {
            'source_file': dead_link['source_file'],
            'line': line_num,
            'dead_link': dead_link_text,
            'reason': reason,
            'action': '',
            'status': 'FAILED',
            'message': ''
        }

        try:
            if reason == 'FILE_NOT_FOUND':
                fix_result['action'] = 'CREATE_PLACEHOLDER'
                self._create_placeholder_file(dead_link)
                fix_result['status'] = 'SUCCESS'
                fix_result['message'] = f"已创建占位文件"

            elif reason == 'DEAD_WIKI_LINK':
                fix_result['action'] = 'REMOVE_LINK'
                self._remove_link_from_file(source_file, line_num, dead_link_text)
                fix_result['status'] = 'SUCCESS'
                fix_result['message'] = f"已删除引用"

            elif reason == 'ORPHAN_REFERENCE':
                fix_result['action'] = 'MANUAL_FIX_REQUIRED'
                fix_result['status'] = 'FAILED'
                fix_result['message'] = "需手动处理"

        except Exception as e:
            fix_result['message'] = f"修复失败: {str(e)}"

        return fix_result

    def _create_placeholder_file(self, dead_link: Dict):
        """创建占位文件"""
        target_path = Path(dead_link['target_path'])
        target_path.parent.mkdir(parents=True, exist_ok=True)

        placeholder_content = f"""# {target_path.stem}

> [!warning] 待完善
此文件为占位文件，内容待完善。

---

## 说明

此文件由 `repo_task_tool` 自动创建，用于修复死链引用。

**原始引用位置**：
- 文件：{dead_link['source_file']}
- 行号：{dead_link['line']}
- 引用：{dead_link['dead_link']}
"""

        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(placeholder_content)

    def _remove_link_from_file(self, source_file: Path, line_num: int, dead_link_text: str):
        """从文件中删除引用"""
        with open(source_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        if line_num <= len(lines):
            line = lines[line_num - 1]
            if dead_link_text in line:
                if line.strip() == dead_link_text:
                    lines[line_num - 1] = ''
                else:
                    lines[line_num - 1] = line.replace(dead_link_text, '')

        with open(source_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)

    def _generate_result(self) -> Dict:
        """生成完整结果"""
        return {
            'scan_result': 'DEAD_LINKS_FOUND' if self.dead_links else 'NO_DEAD_LINKS',
            'scan_time': datetime.now().isoformat(),
            'root_directory': str(self.root_directory),
            'total_files': self.total_files,
            'total_links': self.total_links,
            'dead_links_count': len(self.dead_links),
            'dead_links': self.dead_links,
            'fix_result': 'FIXES_APPLIED' if self.fix_results else 'NO_FIXES',
            'fix_time': datetime.now().isoformat(),
            'total_fixes': len(self.fix_results),
            'success_count': sum(1 for r in self.fix_results if r['status'] == 'SUCCESS'),
            'failed_count': sum(1 for r in self.fix_results if r['status'] == 'FAILED'),
            'fix_results': self.fix_results
        }

    def _save_json_report(self, result: Dict, output_file: str):
        """保存 JSON 报告"""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    def _save_markdown_report(self, result: Dict, output_file: str):
        """保存 Markdown 报告"""
        lines = [
            "# 死链检查报告",
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
            f"| 死链数量 | {result.get('dead_links_count', 0)} |",
            "",
            "---",
            "",
            "## 修复摘要",
            "",
            "| 项目 | 数值 |",
            "|------|------|",
            f"| 修复总数 | {result.get('total_fixes', 0)} |",
            f"| 成功数量 | {result.get('success_count', 0)} |",
            f"| 失败数量 | {result.get('failed_count', 0)} |",
            "",
        ]

        if result.get('dead_links'):
            lines.extend([
                "---",
                "",
                "## 死链详细列表",
                "",
                "| 序号 | 源文件 | 行号 | 死链 | 类型 |",
                "|------|--------|------|------|------|",
            ])

            for i, dead_link in enumerate(result['dead_links'], start=1):
                lines.append(
                    f"| {i} | {dead_link['source_file']} | {dead_link['line']} | "
                    f"`{dead_link['dead_link']}` | {dead_link['reason']} |"
                )

        if result.get('fix_results'):
            lines.extend([
                "",
                "---",
                "",
                "## 修复详细记录",
                "",
                "| 序号 | 源文件 | 行号 | 死链 | 操作 | 状态 | 说明 |",
                "|------|--------|------|------|------|------|------|",
            ])

            for i, fix_result in enumerate(result['fix_results'], start=1):
                lines.append(
                    f"| {i} | {fix_result['source_file']} | {fix_result['line']} | "
                    f"`{fix_result['dead_link']}` | {fix_result['action']} | "
                    f"{fix_result['status']} | {fix_result['message']} |"
                )

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='Repo Task Tool - 死链检查与修复工具')
    parser.add_argument('directory', help='扫描的目录路径')
    parser.add_argument('--fix', action='store_true', help='自动修复死链（不询问用户）')
    parser.add_argument('--json', help='JSON 报告输出路径')
    parser.add_argument('--md', help='Markdown 报告输出路径')

    args = parser.parse_args()

    # 创建工具并执行
    tool = RepoTaskTool(args.directory)
    result = tool.scan_and_fix(
        auto_fix=args.fix,
        output_json=args.json,
        output_md=args.md
    )

    # 输出简要结果
    print(f"\n扫描完成:")
    print(f"  - 扫描文件: {result['total_files']}")
    print(f"  - 总链接: {result['total_links']}")
    print(f"  - 死链数量: {result['dead_links_count']}")
    print(f"  - 修复成功: {result['success_count']}")
    print(f"  - 修复失败: {result['failed_count']}")

    # 返回状态码
    if result['dead_links_count'] > 0 and result['success_count'] == 0:
        sys.exit(1)  # 发现死链但未修复
    else:
        sys.exit(0)  # 无死链或已修复


if __name__ == '__main__':
    main()