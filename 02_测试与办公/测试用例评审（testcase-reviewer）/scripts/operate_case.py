"""
    @description: 获取、操作用例平台上的case
    @author: 杨晨
    @date: 2026-06-11
    @version: 1.0
"""
import aiohttp
import asyncio
import argparse
import json
import sys
UNIVERSAL_KEY="QhcbYrK0axuzPTfLhJ0OttsMBLE0RxdC"
# BASE_URL="http://10.18.200.6:8898/api"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", type=str, required=True, help="执行的操作: gen_case_pool, add_review_record, add_review_records")
    parser.add_argument("--case-id", type=int, help="需要回写评审建议的 case id")
    parser.add_argument("--suggestion", type=str, help="需要回写的 HTML 格式评审建议")
    parser.add_argument("--records-json", type=str, help="批量回写记录 JSON，格式为 [{\"case_id\": 1, \"suggestion\": \"<p>...</p>\"}]")
    parser.add_argument("--records-file", type=str, help="批量回写记录 JSON 文件路径；使用 - 表示从 stdin 读取")
    args = parser.parse_args()
    if args.action == "add_review_record":
        if args.case_id is None:
            parser.error("【Review建议评论】case-id 是必要参数，请使用 --case-id 指定")
        if not args.suggestion:
            parser.error("【Review建议评论】suggestion 是必要参数，请使用 --suggestion 指定")
    if args.action == "add_review_records":
        if bool(args.records_json) == bool(args.records_file):
            parser.error("【Review建议评论】请且仅请通过 --records-json 或 --records-file 指定批量回写记录")
    return args

def load_review_records(records_json: str):
    try:
        raw_records = json.loads(records_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"批量回写记录不是合法 JSON: {exc}") from exc
    if not isinstance(raw_records, list) or not raw_records:
        raise ValueError("批量回写记录必须是非空数组")

    seen_case_ids = set()
    records = []
    for index, record in enumerate(raw_records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"第 {index} 条批量回写记录必须是对象")
        case_id = record.get("case_id")
        suggestion = record.get("suggestion")
        if not isinstance(case_id, int) or isinstance(case_id, bool):
            raise ValueError(f"第 {index} 条批量回写记录缺少整数 case_id")
        if case_id in seen_case_ids:
            raise ValueError(f"批量回写记录存在重复 case_id: {case_id}")
        if not isinstance(suggestion, str) or not suggestion.strip():
            raise ValueError(f"第 {index} 条批量回写记录缺少 suggestion")
        seen_case_ids.add(case_id)
        records.append((case_id, suggestion))
    return records

def load_review_records_from_args(args):
    if args.records_json:
        return load_review_records(args.records_json)
    if args.records_file == "-":
        return load_review_records(sys.stdin.read())
    with open(args.records_file, encoding="utf-8") as file:
        return load_review_records(file.read())

def gen_headers():
    return {
        "Authorization": "Bearer " + UNIVERSAL_KEY,
    }

async def get_all_subpath_ids(id_list: set, data: list):
    if not data:
        return id_list
    for item in data:
        if item["children"]:
            await get_all_subpath_ids(id_list, item["children"])
        else:
            id_list.add(item["id"])
    return id_list

async def get_all_path_ids():
    url = "http://10.18.200.6:8898/api/case/path"
    headers = gen_headers()
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            result = await response.json()
            data = result["data"]
            id_list = set()
            return await get_all_subpath_ids(id_list, data)

async def fetch_case(parent_id: int):
    url = "http://10.18.200.6:8898/api/case" 
    headers = gen_headers()
    params = {
        "parent_id": parent_id,
        "is_disabled": 'false',
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            result = await response.json()
            data = result["data"]
            return data

async def gen_case_pool(exclude_ids: list = []):
    all_path_ids = await get_all_path_ids()
    case_pool = []
    for path_id in all_path_ids:
        cases = await fetch_case(path_id)
        for case in cases:
            if case["id"] in exclude_ids:
                continue
            case_pool.append(case)
    return case_pool

async def add_review_record(case_id: int, suggestion: str):
    url = f"http://10.18.200.6:8898/api/case/pro/{case_id}"
    headers = gen_headers()
    data = {
        "suggestion": f"{suggestion}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.put(url, headers=headers, json=data) as response:
            return await response.json()

async def add_review_records(records):
    return await asyncio.gather(
        *(add_review_record(case_id, suggestion) for case_id, suggestion in records)
    )

async def run_action(args):
    if args.action == "gen_case_pool":
        return await gen_case_pool()
    if args.action == "add_review_record":
        return await add_review_record(args.case_id, args.suggestion)
    if args.action == "add_review_records":
        return await add_review_records(load_review_records_from_args(args))
    raise ValueError(f"action: {args.action} not found")

def main():
    args = parse_args()
    result = asyncio.run(run_action(args))
    if result is not None:
        print(result)

# def test():
#     case_pool = asyncio.run(gen_case_pool())
#     print(len(case_pool))

if __name__ == "__main__":
    main()