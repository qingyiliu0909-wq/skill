import subprocess
import json
import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description='创建飞书文档')
    parser.add_argument('--wiki-node', required=True, help='飞书知识库节点 token')
    parser.add_argument('--title', required=True, help='文档标题')
    parser.add_argument('--markdown-file', required=True, help='Markdown 内容文件路径')

    args = parser.parse_args()

    with open(args.markdown_file, 'r', encoding='utf-8') as f:
        markdown_content = f.read()

    invoke_args = {
        "wiki_node": args.wiki_node,
        "title": args.title,
        "markdown": markdown_content
    }

    script_path = r"d:\AI\n8n\.trae\skills\lark-mcp\scripts\lark_mcp.py"
    cmd = ["python", script_path, "invoke", "feishu_create_doc", json.dumps(invoke_args)]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

if __name__ == "__main__":
    main()