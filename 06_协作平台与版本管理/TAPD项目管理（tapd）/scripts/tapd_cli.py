#!/usr/bin/env python3
"""
TAPD CLI - TAPD需求单管理工具

提供 TAPD 需求单的创建、查询等功能。
所有代码自包含，不依赖外部 tapd 模块。

用法：
    python scripts/tapd_cli.py <command> [args]

命令：
    create <title> [options]    创建需求单，存在则返回现有链接
    list [options]              查询需求单列表
    search <keyword>            搜索需求单

环境变量：
    TAPD_USERNAME - TAPD 用户名（默认使用配置中的用户名）
    TAPD_PASSWORD - TAPD 密码
    TAPD_WORKSPACE_ID - 工作空间 ID
"""

import os
import sys
import json
import argparse
import base64
from urllib.parse import urlencode
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple, List

import requests


BASE_URL = "https://api.tapd.cn"
WEB_URL = "https://www.tapd.cn"
DEFAULT_WORKITEM_TYPE = "1131626021001000158"
DEFAULT_CATEGORY = "1131626021001002996"

DEFAULT_USERNAME = "gNxpkwrr"
DEFAULT_PASSWORD = "86EE396F-6733-051C-3BA9-1243A2E8AA36"
DEFAULT_WORKSPACE_ID = "31626021"


def get_config() -> Dict[str, str]:
    return {
        "username": os.environ.get("TAPD_USERNAME", DEFAULT_USERNAME),
        "password": os.environ.get("TAPD_PASSWORD", DEFAULT_PASSWORD),
        "workspace_id": os.environ.get("TAPD_WORKSPACE_ID", DEFAULT_WORKSPACE_ID)
    }


def build_story_url(workspace_id: str, story_id: str) -> str:
    return f"{WEB_URL}/tapd_fe/{workspace_id}/story/detail/{story_id}"


class TapdRequest:
    def __init__(
        self,
        method: str,
        url: str,
        params: Dict[str, Any] = None,
        data: Dict[str, Any] = None
    ):
        self.method = method.upper()
        self.url = url
        self.params = params or {}
        self.data = data or {}
        self.headers = {}

    def with_auth(self, username: str, api_key: str) -> "TapdRequest":
        pair = f"{username}:{api_key}"
        auth_token = base64.b64encode(pair.encode('utf-8')).decode('ascii')
        self.headers["Authorization"] = f"Basic {auth_token}"
        return self

    def with_form_urlencoded(self) -> "TapdRequest":
        self.headers["Content-Type"] = "application/x-www-form-urlencoded; charset=utf-8"
        body_string = "&".join(
            urlencode({k: str(v)}) for k, v in self.data.items()
        )
        self.data = body_string.encode('utf-8')
        return self


class StoryApi:
    FIELD_MAP = {
        "description": "description",
        "owner": "owner",
        "iteration": "iteration_id",
        "developer": "developer",
        "tester": "tester",
        "reviewer": "reviewer"
    }

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id

    def list(self, keyword: str = "", limit: int = 100, offset: int = 0, parent_id: str = "") -> TapdRequest:
        params = {
            "workspace_id": self.workspace_id,
            "limit": limit,
            "offset": offset
        }
        if keyword:
            params["name"] = keyword
        if parent_id:
            params["parent_id"] = parent_id
        return TapdRequest(
            method="GET",
            url=f"{BASE_URL}/stories",
            params=params
        )

    def create(
        self,
        title: str,
        description: str = "",
        owner: str = "",
        iteration: str = "",
        developer: str = "",
        tester: str = "",
        reviewer: str = "",
        custom_fields: Dict[str, Any] = None,
        parent_id: str = ""
    ) -> TapdRequest:
        payload = {
            "name": title,
            "workspace_id": self.workspace_id,
            "workitem_type_id": DEFAULT_WORKITEM_TYPE,
            "category_id": DEFAULT_CATEGORY,
        }

        if parent_id:
            payload["parent_id"] = parent_id

        fields = {
            "description": description,
            "owner": owner,
            "iteration": iteration,
            "developer": developer,
            "tester": tester,
            "reviewer": reviewer
        }

        for key, value in fields.items():
            if value:
                target_key = self.FIELD_MAP.get(key, key)
                payload[target_key] = value

        if custom_fields:
            for key, value in custom_fields.items():
                if value:
                    if not key.startswith("cus_"):
                        key = f"cus_{key}"
                    payload[key] = value

        return TapdRequest(
            method="POST",
            url=f"{BASE_URL}/stories",
            data=payload
        )

    def update(
        self,
        story_id: str,
        description: str = "",
        owner: str = "",
        iteration: str = "",
        developer: str = "",
        tester: str = "",
        reviewer: str = "",
        custom_fields: Dict[str, Any] = None
    ) -> TapdRequest:
        payload = {
            "workspace_id": self.workspace_id,
            "id": story_id,
        }

        fields = {
            "description": description,
            "owner": owner,
            "iteration": iteration,
            "developer": developer,
            "tester": tester,
            "reviewer": reviewer
        }

        for key, value in fields.items():
            if value:
                target_key = self.FIELD_MAP.get(key, key)
                payload[target_key] = value

        if custom_fields:
            for key, value in custom_fields.items():
                if value:
                    if not key.startswith("cus_"):
                        key = f"cus_{key}"
                    payload[key] = value

        return TapdRequest(
            method="POST",
            url=f"{BASE_URL}/stories",
            data=payload
        )


@dataclass
class Story:
    id: str
    name: str
    url: str
    workspace_id: str


@dataclass
class StoryCreateResult:
    success: bool
    story: Optional[Story] = None
    error: str = ""


class TapdClient:
    def __init__(self, username: str, password: str, workspace_id: str):
        self.username = username
        self.password = password
        self.workspace_id = workspace_id
        self._story_api = StoryApi(workspace_id)

    def _send(self, payload: TapdRequest) -> dict:
        payload.with_auth(self.username, self.password)

        kwargs = {
            "url": payload.url,
            "headers": payload.headers,
            "timeout": 30
        }

        if payload.params:
            kwargs["params"] = payload.params
        if payload.data:
            payload.with_form_urlencoded()
            kwargs["data"] = payload.data

        if payload.method == "GET":
            response = requests.get(**kwargs)
        elif payload.method == "POST":
            response = requests.post(**kwargs)
        else:
            raise ValueError(f"Unsupported method: {payload.method}")

        return response.json()

    def list_stories(self, limit: int = 100, offset: int = 0, keyword: str = "", parent_id: str = ""):
        payload = self._story_api.list(keyword=keyword, limit=limit, offset=offset, parent_id=parent_id)
        result = self._send(payload)

        stories = []
        if result.get("data"):
            for item in result["data"]:
                story_data = item["Story"]
                data = {}
                for k, v in story_data.items():
                    if not v or v == "" or (v == "0" and k.startswith("custom_")):
                        continue
                    if k.startswith("children_id"):
                        continue
                    data[k] = v
                stories.append(data)
        return stories

    def create_story(
        self,
        title: str,
        description: str = "",
        owner: str = "",
        iteration: str = "",
        developer: str = "",
        tester: str = "",
        reviewer: str = "",
        custom_fields: dict = None,
        parent_id: str = ""
    ) -> StoryCreateResult:
        payload = self._story_api.create(
            title=title,
            description=description,
            owner=owner,
            iteration=iteration,
            developer=developer,
            tester=tester,
            reviewer=reviewer,
            custom_fields=custom_fields,
            parent_id=parent_id
        )
        result = self._send(payload)

        if result.get("status") == 1:
            story_data = result["data"]["Story"]
            story = Story(
                id=story_data["id"],
                name=story_data["name"],
                url=build_story_url(self.workspace_id, story_data["id"]),
                workspace_id=self.workspace_id
            )
            return StoryCreateResult(success=True, story=story)
        else:
            return StoryCreateResult(success=False, error=f"Create failed: {result}")

    def get_or_create_story(
        self,
        title: str,
        description: str = "",
        owner: str = "",
        iteration: str = "",
        developer: str = "",
        tester: str = "",
        reviewer: str = "",
        custom_fields: dict = None,
        parent_id: str = ""
    ) -> Tuple[Optional[Story], str]:
        existing = self.query_story(title)
        if existing:
            return existing, "already_exists"

        result = self.create_story(
            title, description, owner, iteration,
            developer, tester, reviewer, custom_fields,
            parent_id=parent_id
        )

        if result.success:
            return result.story, "created"
        else:
            return None, result.error

    def query_story(self, title: str) -> Optional[Story]:
        stories = self.list_stories(keyword=title, limit=100)
        if stories:
            for story_data in stories:
                if story_data.get("name") == title:
                    return Story(
                        id=story_data["id"],
                        name=story_data["name"],
                        url=build_story_url(self.workspace_id, story_data["id"]),
                        workspace_id=self.workspace_id
                    )
        return None

    def update_story(
        self,
        story_id: str,
        description: str = "",
        owner: str = "",
        iteration: str = "",
        developer: str = "",
        tester: str = "",
        reviewer: str = "",
        custom_fields: dict = None
    ) -> StoryCreateResult:
        payload = self._story_api.update(
            story_id=story_id,
            description=description,
            owner=owner,
            iteration=iteration,
            developer=developer,
            tester=tester,
            reviewer=reviewer,
            custom_fields=custom_fields
        )
        result = self._send(payload)

        if result.get("status") == 1:
            story_data = result["data"]["Story"]
            story = Story(
                id=story_data["id"],
                name=story_data["name"],
                url=build_story_url(self.workspace_id, story_data["id"]),
                workspace_id=self.workspace_id
            )
            return StoryCreateResult(success=True, story=story)
        else:
            return StoryCreateResult(success=False, error=f"Update failed: {result}")

    def get_story(self, story_id: str) -> Optional[Story]:
        stories = self.list_stories(limit=100)
        for story_data in stories:
            if story_data.get("id") == story_id:
                return Story(
                    id=story_data["id"],
                    name=story_data["name"],
                    url=build_story_url(self.workspace_id, story_data["id"]),
                    workspace_id=self.workspace_id
                )
        return None


def get_client() -> TapdClient:
    config = get_config()
    return TapdClient(
        username=config["username"],
        password=config["password"],
        workspace_id=config["workspace_id"]
    )


def cmd_create(title: str, description: str = "", owner: str = "", iteration: str = "",
               developer: str = "", tester: str = "", reviewer: str = "", acceptor: str = "",
               parent_id: str = ""):
    client = get_client()

    custom_fields = {"验收人": acceptor} if acceptor else None

    story, status = client.get_or_create_story(
        title=title,
        description=description,
        owner=owner,
        iteration=iteration,
        developer=developer,
        tester=tester,
        reviewer=reviewer,
        custom_fields=custom_fields,
        parent_id=parent_id
    )

    if story:
        result = {
            "success": True,
            "story_url": story.url,
            "story_id": story.id,
            "message": f"{'已存在' if status == 'already_exists' else '创建成功'}: {story.url}"
        }
    else:
        result = {
            "success": False,
            "story_url": "",
            "message": f"失败: {status}"
        }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def cmd_list(limit: int = 100, offset: int = 0, name: str = "", parent_id: str = ""):
    client = get_client()
    stories = client.list_stories(limit=limit, offset=offset, keyword=name, parent_id=parent_id)

    result = {
        "success": True,
        "count": len(stories),
        "stories": stories
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def cmd_search(keyword: str):
    client = get_client()
    stories = client.list_stories(keyword=keyword, limit=100)

    result = {
        "success": True,
        "keyword": keyword,
        "count": len(stories),
        "stories": stories
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def cmd_update(
    story_id: str,
    description: str = "",
    owner: str = "",
    iteration: str = "",
    developer: str = "",
    tester: str = "",
    reviewer: str = "",
    acceptor: str = ""
):
    client = get_client()

    custom_fields = {"验收人": acceptor} if acceptor else None

    result = client.update_story(
        story_id=story_id,
        description=description,
        owner=owner,
        iteration=iteration,
        developer=developer,
        tester=tester,
        reviewer=reviewer,
        custom_fields=custom_fields
    )

    if result.success:
        output = {
            "success": True,
            "story_url": result.story.url,
            "story_id": result.story.id,
            "message": f"更新成功: {result.story.url}"
        }
    else:
        output = {
            "success": False,
            "story_url": "",
            "message": f"更新失败: {result.error}"
        }

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return output


def main():
    parser = argparse.ArgumentParser(description="TAPD CLI - TAPD需求单管理工具")
    parser.add_argument('command', choices=['create', 'list', 'search', 'update'], help='命令')
    parser.add_argument('args', nargs='*', help='命令参数')
    #sys.argv = [sys.argv[0], "list", "--limit", "100", "--parent_id", "1131626021001294327"]
    if len(sys.argv) < 2:
        parser.print_help()
        return

    args = parser.parse_args(sys.argv[1:2])
    remaining = sys.argv[2:]
    if args.command == 'create':
        parser = argparse.ArgumentParser(description='创建TAPD需求单')
        parser.add_argument('title', help='需求标题')
        parser.add_argument('--description', '-d', default='', help='需求描述')
        parser.add_argument('--owner', '-o', default='', help='负责人')
        parser.add_argument('--iteration', '-i', default='', help='迭代ID')
        parser.add_argument('--developer', default='', help='开发人员')
        parser.add_argument('--tester', default='', help='测试人员')
        parser.add_argument('--reviewer', default='', help='评审人员')
        parser.add_argument('--acceptor', default='', help='验收人')
        parser.add_argument('--parent_id', default='', help='父节点ID（挂靠到指定总单）')

        parsed = parser.parse_args(remaining)
        cmd_create(
            title=parsed.title,
            description=parsed.description,
            owner=parsed.owner,
            iteration=parsed.iteration,
            developer=parsed.developer,
            tester=parsed.tester,
            reviewer=parsed.reviewer,
            acceptor=parsed.acceptor,
            parent_id=parsed.parent_id
        )

    elif args.command == 'list':
        parser = argparse.ArgumentParser(description='查询TAPD需求单列表')
        parser.add_argument('--limit', '-l', type=int, default=100, help='单次获取数量')
        parser.add_argument('--offset', '-s', type=int, default=0, help='偏移量')
        parser.add_argument('--name', '-n', type=str, default='', help='按名字查询（模糊匹配）')
        parser.add_argument('--parent_id', '-p', type=str, default='', help='按父节点ID查询')

        parsed = parser.parse_args(remaining)
        cmd_list(limit=parsed.limit, offset=parsed.offset, name=parsed.name, parent_id=parsed.parent_id)

    elif args.command == 'search':
        parser = argparse.ArgumentParser(description='搜索TAPD需求单')
        parser.add_argument('keyword', help='搜索关键字')

        parsed = parser.parse_args(remaining)
        cmd_search(keyword=parsed.keyword)

    elif args.command == 'update':
        parser = argparse.ArgumentParser(description='更新TAPD需求单')
        parser.add_argument('story_id', help='需求单ID')
        parser.add_argument('--description', '-d', default='', help='需求描述')
        parser.add_argument('--owner', '-o', default='', help='负责人')
        parser.add_argument('--iteration', '-i', default='', help='迭代ID')
        parser.add_argument('--developer', default='', help='开发人员')
        parser.add_argument('--tester', default='', help='测试人员')
        parser.add_argument('--reviewer', default='', help='评审人员')
        parser.add_argument('--acceptor', default='', help='验收人')

        parsed = parser.parse_args(remaining)
        cmd_update(
            story_id=parsed.story_id,
            description=parsed.description,
            owner=parsed.owner,
            iteration=parsed.iteration,
            developer=parsed.developer,
            tester=parsed.tester,
            reviewer=parsed.reviewer,
            acceptor=parsed.acceptor
        )


if __name__ == '__main__':
    main()