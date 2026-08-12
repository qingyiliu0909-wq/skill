#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
需求排期调度程序
基于优先级的贪心调度算法，生成甘特图可视化
"""

import json
import os
import argparse
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import rcParams
import numpy as np

# 配置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False


@dataclass
class TaskStep:
    """工序信息"""
    task_name: str
    step_name: str
    role: str
    duration: int
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    assigned_person: Optional[str] = None
    is_completed: bool = False


@dataclass
class Task:
    """需求信息"""
    name: str
    steps: List[str]
    durations: Dict[str, int]
    roles: Dict[str, str]
    assignments: Dict[str, str] = field(default_factory=dict)
    dependencies: Dict[str, List[str]] = field(default_factory=dict)
    bindings: Dict[str, str] = field(default_factory=dict)
    step_details: List[TaskStep] = field(default_factory=list)
    version: str = "1.0"
    priority: int = 50
    completed_steps: Dict[str, int] = field(default_factory=dict)


@dataclass
class Person:
    """人员信息"""
    name: str
    role: str
    available_time: int = 0


class ScheduleError(Exception):
    """调度错误"""
    pass


class DataValidationError(Exception):
    """数据验证错误"""
    pass


WEEKDAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']


def is_weekend(date: datetime) -> bool:
    """判断是否为周末（周六=5，周日=6）"""
    return date.weekday() >= 5


def add_workdays(start_date: datetime, workdays: int) -> datetime:
    """
    从开始日期增加指定工作日数，跳过周末
    
    Args:
        start_date: 开始日期
        workdays: 要增加的工作日数
        
    Returns:
        计算后的日期
    """
    if workdays == 0:
        return start_date
    
    if workdays < 0:
        current = start_date
        days_subtracted = 0
        while days_subtracted < abs(workdays):
            current -= timedelta(days=1)
            if not is_weekend(current):
                days_subtracted += 1
        return current
    
    current = start_date
    days_added = 0
    
    while days_added < workdays:
        current += timedelta(days=1)
        if not is_weekend(current):
            days_added += 1
    
    return current


def workdays_to_date(start_date: datetime, workdays: int) -> datetime:
    """
    将工作日数转换为实际日期
    
    Args:
        start_date: 项目开始日期（第0天）
        workdays: 工作日数（0表示开始日期当天）
        
    Returns:
        对应的实际日期
    """
    return add_workdays(start_date, workdays)


def workdays_to_natural_days(start_date: datetime, workdays: int) -> int:
    """
    将工作日数转换为自然日数（含周末）
    
    Args:
        start_date: 开始日期
        workdays: 工作日数
        
    Returns:
        自然日数
    """
    if workdays <= 0:
        return 0
    
    end_date = workdays_to_date(start_date, workdays)
    return (end_date - start_date).days


def format_duration_with_natural(workdays: int, start_date: datetime) -> str:
    """
    格式化工期显示，同时显示工作日和自然日
    
    Args:
        workdays: 工作日数
        start_date: 开始日期（用于计算自然日）
        
    Returns:
        格式化后的字符串，如 "45工作日(63天)"
    """
    natural_days = workdays_to_natural_days(start_date, workdays)
    return f"{workdays}工作日({natural_days}天)"


def format_date_with_weekday(date: datetime) -> str:
    """
    格式化日期，包含周几
    
    Args:
        date: 日期对象
        
    Returns:
        格式化后的字符串，如 "03/25 周二"
    """
    return f"{date.strftime('%m/%d')} {WEEKDAY_NAMES[date.weekday()]}"


def calculate_font_size(duration: int, text: str, base_size: int = 8, min_size: int = 5) -> int:
    """
    根据条形图宽度和文本长度计算自适应字体大小
    
    Args:
        duration: 条形图宽度（天数）
        text: 要显示的文本
        base_size: 基础字体大小
        min_size: 最小字体大小
        
    Returns:
        计算后的字体大小
    """
    return base_size


def wrap_text_for_bar(text: str, duration: int, max_chars_per_line: int = 6) -> str:
    """
    根据条形图宽度决定是否换行显示文本
    
    Args:
        text: 要显示的文本
        text: 条形图宽度（天数）
        max_chars_per_line: 每行最大字符数
        
    Returns:
        处理后的文本（可能包含换行符）
    """
    if len(text) <= 4:
        return text
    
    if '-' in text:
        parts = text.split('-', 1)
        if len(parts) == 2:
            return parts[0] + '\n' + parts[1]
    
    mid = (len(text) + 1) // 2
    return text[:mid] + '\n' + text[mid:]


def simplify_task_name(task_name: str) -> str:
    """
    简化需求名称，去掉"需求XX-"前缀
    
    Args:
        task_name: 完整的需求名称
        
    Returns:
        简化后的名称
    """
    if '-' in task_name:
        parts = task_name.split('-', 1)
        if len(parts) == 2 and parts[0].startswith('需求'):
            return parts[1]
    return task_name


def load_data(file_path: str) -> dict:
    """
    从JSON文件加载数据
    
    Args:
        file_path: JSON文件路径
        
    Returns:
        解析后的数据字典
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        raise DataValidationError(f"文件不存在: {file_path}")
    except json.JSONDecodeError as e:
        raise DataValidationError(f"JSON格式错误: {e}")
    
    return data


def validate_data(data: dict) -> None:
    """
    验证输入数据完整性
    
    Args:
        data: 输入数据字典
        
    Raises:
        DataValidationError: 数据验证失败
    """
    if 'tasks' not in data:
        raise DataValidationError("缺少 'tasks' 字段")
    
    if 'resources' not in data:
        raise DataValidationError("缺少 'resources' 字段")
    
    templates = data.get('templates', {})
    
    for task_name, task_info in data['tasks'].items():
        if 'template' in task_info:
            template_name = task_info['template']
            if template_name not in templates:
                raise DataValidationError(f"需求 '{task_name}' 引用的模板 '{template_name}' 不存在")
            
            template = templates[template_name]
            steps = template.get('steps', [])
            template_durations = template.get('durations', {})
            task_durations = task_info.get('durations', {})
            durations = {**template_durations, **task_durations}
            
            roles = template.get('roles', {})
            
            for step in steps:
                if step not in durations:
                    raise DataValidationError(f"需求 '{task_name}' 的工序 '{step}' 缺少时长定义")
                
                role = roles.get(step, step)
                if role not in data['resources'] or len(data['resources'][role]) == 0:
                    raise DataValidationError(f"角色 '{role}' 没有可用人员（需求: {task_name}, 工序: {step}）")
        else:
            if 'steps' not in task_info:
                raise DataValidationError(f"需求 '{task_name}' 缺少 'steps' 字段")
            if 'durations' not in task_info:
                raise DataValidationError(f"需求 '{task_name}' 缺少 'durations' 字段")
            if 'roles' not in task_info:
                raise DataValidationError(f"需求 '{task_name}' 缺少 'roles' 字段")
            
            for step in task_info['steps']:
                if step not in task_info['durations']:
                    raise DataValidationError(f"需求 '{task_name}' 的工序 '{step}' 缺少时长定义")
                if step not in task_info['roles']:
                    raise DataValidationError(f"需求 '{task_name}' 的工序 '{step}' 缺少角色定义")
            
            # 验证角色是否有对应人员
            role = task_info['roles'][step]
            if role not in data['resources'] or len(data['resources'][role]) == 0:
                raise DataValidationError(f"角色 '{role}' 没有可用人员（需求: {task_name}, 工序: {step}）")


class Scheduler:
    """调度器"""
    
    def __init__(self, data: dict, wip_limit: Optional[int] = None, buffer_ratio: float = 0.0):
        """
        初始化调度器
        
        Args:
            data: 输入数据
            wip_limit: WIP上限（同时进行中的需求数量）
            buffer_ratio: 项目缓冲比例
        """
        self.data = data
        self.wip_limit = wip_limit
        self.buffer_ratio = buffer_ratio
        
        if 'start_date' in data and data['start_date']:
            self.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d')
        else:
            self.start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        self.resources = data['resources']
        self.person_available_time: Dict[str, int] = {}
        for role, person_names in data['resources'].items():
            for person_name in person_names:
                if person_name not in self.person_available_time:
                    self.person_available_time[person_name] = 0
        
        self.templates = data.get('templates', {})
        
        self.tasks: Dict[str, Task] = {}
        for task_name, task_info in data['tasks'].items():
            task = self._create_task(task_name, task_info)
            self.tasks[task_name] = task
        
        if 'priority_order' in data and data['priority_order']:
            self.priority_order = data['priority_order']
        else:
            self.priority_order = self._auto_sort_tasks()
        
        self.schedule_result: List[TaskStep] = []
        self.project_end_time = 0
    
    def _create_task(self, task_name: str, task_info: dict) -> Task:
        """
        创建需求对象，支持模板引用
        
        Args:
            task_name: 需求名称
            task_info: 需求信息（可能包含模板引用）
            
        Returns:
            Task对象
        """
        def parse_completed_steps(raw_completed):
            if not raw_completed:
                return {}
            result = {}
            if isinstance(raw_completed, list):
                for step_name in raw_completed:
                    result[step_name] = 0
            elif isinstance(raw_completed, dict):
                for step_name, end_day in raw_completed.items():
                    result[step_name] = end_day if isinstance(end_day, int) else 0
            return result
        
        if 'template' in task_info:
            template_name = task_info['template']
            if template_name not in self.templates:
                raise DataValidationError(f"模板 '{template_name}' 不存在")
            
            template = self.templates[template_name]
            
            steps = template.get('steps', [])
            roles = template.get('roles', {})
            dependencies = template.get('dependencies', {})
            bindings = template.get('bindings', {})
            template_durations = template.get('durations', {})
            
            for step in steps:
                if step not in roles:
                    roles[step] = step
            
            task_durations = task_info.get('durations', {})
            durations = {**template_durations, **task_durations}
            assignments = task_info.get('assignments', {})
            version = task_info.get('version', '1.0')
            priority = task_info.get('priority', 50)
            completed_steps = parse_completed_steps(task_info.get('completed_steps'))
            
            return Task(
                name=task_name,
                steps=steps,
                durations=durations,
                roles=roles,
                assignments=assignments,
                dependencies=dependencies,
                bindings=bindings,
                version=version,
                priority=priority,
                completed_steps=completed_steps
            )
        else:
            completed_steps = parse_completed_steps(task_info.get('completed_steps'))
            return Task(
                name=task_name,
                steps=task_info['steps'],
                durations=task_info['durations'],
                roles=task_info['roles'],
                assignments=task_info.get('assignments', {}),
                dependencies=task_info.get('dependencies', {}),
                bindings=task_info.get('bindings', {}),
                version=task_info.get('version', '1.0'),
                priority=task_info.get('priority', 50),
                completed_steps=completed_steps
            )
    
    def _auto_sort_tasks(self) -> List[str]:
        """
        自动排序需求
        排序规则：版本号升序 + 优先级降序（数值越大越优先）
        """
        def sort_key(task_name):
            task = self.tasks[task_name]
            try:
                version_parts = [int(x) for x in task.version.split('.')]
            except:
                version_parts = [0]
            priority = task.priority
            return (version_parts, -priority)
        
        return sorted(self.tasks.keys(), key=sort_key)
    
    def days_to_date(self, days: int) -> str:
        """将工作日数转换为日期字符串（跳过周末）"""
        date = workdays_to_date(self.start_date, days)
        return date.strftime('%Y-%m-%d')
    
    def get_date_range(self) -> Tuple[str, str]:
        """获取项目开始和结束日期"""
        start = self.start_date.strftime('%Y-%m-%d')
        end_date = self.start_date + timedelta(days=self.project_end_time)
        end = end_date.strftime('%Y-%m-%d')
        return start, end
    
    def get_earliest_person(self, role: str, assigned_person: Optional[str] = None) -> Tuple[str, int]:
        """
        获取指定角色中最早可用的人员
        
        Args:
            role: 角色名称
            assigned_person: 指定的人员名称（可选）
            
        Returns:
            (人员名称, 可用时间)
        """
        if assigned_person:
            if role not in self.resources or assigned_person not in self.resources[role]:
                raise ScheduleError(f"指定的人员 '{assigned_person}' 不属于角色 '{role}'")
            return assigned_person, self.person_available_time[assigned_person]
        
        if role not in self.resources or not self.resources[role]:
            raise ScheduleError(f"角色 '{role}' 没有可用人员")
        
        candidates = self.resources[role]
        earliest_person = min(candidates, key=lambda p: self.person_available_time[p])
        return earliest_person, self.person_available_time[earliest_person]
    
    def get_active_task_count(self, current_time: int) -> int:
        """
        获取当前进行中的需求数量
        
        Args:
            current_time: 当前时间点
            
        Returns:
            进行中的需求数量
        """
        active_count = 0
        for task in self.tasks.values():
            if not task.step_details:
                continue
            
            # 检查该需求是否还有未完成的工序
            last_step = task.step_details[-1]
            if last_step.end_time is not None and last_step.end_time > current_time:
                active_count += 1
            elif last_step.end_time is None:
                # 工序尚未分配时间，说明还在进行中
                active_count += 1
        
        return active_count
    
    def get_step_dependencies(self, task: Task, step_name: str) -> List[str]:
        """
        获取工序的前置依赖
        如果没有显式定义，默认依赖前一个工序（串行）
        """
        if step_name in task.dependencies:
            return task.dependencies[step_name]
        step_idx = task.steps.index(step_name)
        if step_idx > 0:
            return [task.steps[step_idx - 1]]
        return []
    
    def get_ready_steps(self, task: Task, completed_steps: set) -> List[str]:
        """
        获取当前可以开始执行的工序（所有依赖都已完成）
        """
        ready = []
        for step in task.steps:
            if step in completed_steps:
                continue
            deps = self.get_step_dependencies(task, step)
            if all(dep in completed_steps for dep in deps):
                ready.append(step)
        return ready
    
    def get_step_end_time(self, task_name: str, step_name: str) -> int:
        """获取某个工序的结束时间"""
        for step in self.tasks[task_name].step_details:
            if step.step_name == step_name:
                return step.end_time
        return 0
    
    def get_step_assigned_person(self, task_name: str, step_name: str) -> Optional[str]:
        """获取某个工序的负责人"""
        for step in self.tasks[task_name].step_details:
            if step.step_name == step_name:
                return step.assigned_person
        return None
    
    def get_binding_person(self, task: Task, step_name: str) -> Optional[str]:
        """
        获取工序的绑定人员
        
        优先级：
        1. 显式指定的 assignments
        2. bindings 配置中绑定的源工序负责人
        3. 命名约定：工序名以"验收"结尾时，尝试绑定去掉"验收"后同名工序的负责人
        """
        if step_name in task.assignments:
            return task.assignments[step_name]
        
        binding_source = task.bindings.get(step_name)
        if binding_source:
            return self.get_step_assigned_person(task.name, binding_source)
        
        if step_name.endswith('验收'):
            source_step = step_name[:-2]
            if source_step in task.steps:
                return self.get_step_assigned_person(task.name, source_step)
        
        return None
    
    def schedule(self) -> None:
        """
        执行调度算法
        基于资源并行的贪心调度，最大化资源利用率
        """
        task_completed_steps: Dict[str, set] = {name: set() for name in self.tasks.keys()}
        
        for task_name, task in self.tasks.items():
            for step_name, end_day in task.completed_steps.items():
                if step_name not in task.steps:
                    continue
                
                role = task.roles.get(step_name, step_name)
                duration = task.durations.get(step_name, 0)
                
                if role in self.resources and self.resources[role]:
                    person = self.resources[role][0]
                else:
                    person = None
                
                start_time = end_day - duration if duration > 0 else end_day
                
                step_detail = TaskStep(
                    task_name=task_name,
                    step_name=step_name,
                    role=role,
                    duration=duration,
                    start_time=start_time,
                    end_time=end_day,
                    assigned_person=person,
                    is_completed=True
                )
                
                task.step_details.append(step_detail)
                self.schedule_result.append(step_detail)
                task_completed_steps[task_name].add(step_name)
        
        max_iterations = 10000
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            all_ready_steps = []
            
            for task_name in self.priority_order:
                task = self.tasks[task_name]
                ready_steps = self.get_ready_steps(task, task_completed_steps[task_name])
                
                for step_name in ready_steps:
                    role = task.roles[step_name]
                    duration = task.durations[step_name]
                    
                    deps = self.get_step_dependencies(task, step_name)
                    dep_end_time = max([self.get_step_end_time(task_name, dep) for dep in deps], default=0)
                    
                    all_ready_steps.append({
                        'task_name': task_name,
                        'step_name': step_name,
                        'role': role,
                        'duration': duration,
                        'dep_end_time': dep_end_time,
                        'priority': task.priority
                    })
            
            if not all_ready_steps:
                break
            
            all_ready_steps.sort(key=lambda x: (-x['priority'], x['dep_end_time']))
            
            scheduled_this_round = 0
            
            for step_info in all_ready_steps:
                task_name = step_info['task_name']
                step_name = step_info['step_name']
                role = step_info['role']
                duration = step_info['duration']
                dep_end_time = step_info['dep_end_time']
                
                task = self.tasks[task_name]
                assigned_person_name = self.get_binding_person(task, step_name)
                person, person_available = self.get_earliest_person(role, assigned_person_name)
                
                start_time = max(dep_end_time, person_available)
                end_time = start_time + duration
                
                step_detail = TaskStep(
                    task_name=task_name,
                    step_name=step_name,
                    role=role,
                    duration=duration,
                    start_time=start_time,
                    end_time=end_time,
                    assigned_person=person
                )
                
                task.step_details.append(step_detail)
                self.schedule_result.append(step_detail)
                
                self.person_available_time[person] = end_time
                task_completed_steps[task_name].add(step_name)
                scheduled_this_round += 1
            
            if scheduled_this_round == 0:
                break
            
            all_done = all(
                len(task_completed_steps[task_name]) >= len(self.tasks[task_name].steps)
                for task_name in self.tasks
            )
            if all_done:
                break
        
        if self.schedule_result:
            self.project_end_time = max(step.end_time for step in self.schedule_result)
    
    def get_schedule_dataframe(self) -> pd.DataFrame:
        """
        获取调度结果的DataFrame
        
        Returns:
            包含调度结果的DataFrame
        """
        rows = []
        for step in self.schedule_result:
            rows.append({
                '需求名称': step.task_name,
                '工序': step.step_name,
                '角色': step.role,
                '负责人': step.assigned_person,
                '开始日期': self.days_to_date(step.start_time),
                '结束日期': self.days_to_date(step.end_time),
                '时长(天)': step.duration
            })
        
        return pd.DataFrame(rows)
    
    def export_csv(self, output_path: str) -> None:
        """
        导出调度结果到CSV
        
        Args:
            output_path: 输出文件路径
        """
        df = self.get_schedule_dataframe()
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"调度结果已导出到: {output_path}")
    
    def get_commitment_end_time(self) -> int:
        """
        获取承诺完成时间（含缓冲）
        
        Returns:
            承诺完成时间
        """
        buffer = int(self.project_end_time * self.buffer_ratio)
        return self.project_end_time + buffer
    
    def print_summary(self) -> None:
        """打印调度摘要"""
        print("\n" + "=" * 80)
        print("调度结果摘要")
        print("=" * 80)
        
        print(f"项目开始日期: {self.start_date.strftime('%Y-%m-%d')}")
        
        df = self.get_schedule_dataframe()
        print(df.to_string(index=False))
        
        print("\n" + "-" * 80)
        natural_days = workdays_to_natural_days(self.start_date, self.project_end_time)
        print(f"项目总工期: {self.project_end_time} 工作日 ({natural_days} 自然日)")
        print(f"项目结束日期: {self.days_to_date(self.project_end_time)}")
        
        if self.buffer_ratio > 0:
            buffer_days = int(self.project_end_time * self.buffer_ratio)
            commitment = self.get_commitment_end_time()
            print(f"项目缓冲: {buffer_days} 天 ({self.buffer_ratio * 100}%)")
            print(f"承诺完成日期: {self.days_to_date(commitment)}")
        
        print("=" * 80)


def generate_gantt_chart_by_person(schedule_result: List[TaskStep], 
                                    resources: Dict[str, List[str]],
                                    output_path: str = "schedule_gantt_by_person.png",
                                    title: str = "需求排期甘特图（按人员）",
                                    start_date: Optional[datetime] = None) -> None:
    """
    生成按人员维度的甘特图
    横轴：时间，纵轴：人员
    
    Args:
        schedule_result: 调度结果列表
        resources: 资源配置
        output_path: 输出文件路径
        title: 图表标题
        start_date: 项目开始日期
    """
    if not schedule_result:
        print("没有调度结果，无法生成甘特图")
        return
    
    person_roles = {}
    for role, persons in resources.items():
        base_role = role[:-2] if role.endswith('验收') else role
        for person in persons:
            if person not in person_roles:
                person_roles[person] = set()
            person_roles[person].add(base_role)
    
    for step in schedule_result:
        if step.assigned_person and step.assigned_person not in person_roles:
            person_roles[step.assigned_person] = {step.role}
    
    all_persons = [(person, '/'.join(sorted(roles))) for person, roles in person_roles.items()]
    
    person_total_days = {}
    person_natural_days = {}
    for step in schedule_result:
        if step.assigned_person is None:
            continue
        if step.assigned_person not in person_total_days:
            person_total_days[step.assigned_person] = 0
            person_natural_days[step.assigned_person] = 0
        
        person_total_days[step.assigned_person] += step.duration
        
        if start_date:
            natural_days = workdays_to_natural_days(start_date, step.duration)
            person_natural_days[step.assigned_person] += natural_days
    
    fig, ax = plt.subplots(figsize=(16, max(8, len(all_persons) * 0.8)))
    
    task_names = list(set(step.task_name for step in schedule_result))
    colors = plt.cm.Set3(np.linspace(0, 1, len(task_names)))
    task_colors = {name: colors[i] for i, name in enumerate(task_names)}
    
    y_positions = {person: i for i, (person, _) in enumerate(reversed(all_persons))}
    
    for step in schedule_result:
        if step.assigned_person is None:
            continue
        y_pos = y_positions[step.assigned_person]
        
        if step.is_completed:
            bar_color = '#CCCCCC'
            edge_color = '#888888'
            edge_linestyle = '--'
            alpha_value = 0.6
        else:
            bar_color = task_colors[step.task_name]
            edge_color = 'black'
            edge_linestyle = '-'
            alpha_value = 0.8
        
        ax.barh(
            y_pos, 
            step.duration, 
            left=step.start_time, 
            height=0.6,
            color=bar_color,
            edgecolor=edge_color,
            linewidth=0.5,
            linestyle=edge_linestyle,
            alpha=alpha_value
        )
        
        text = simplify_task_name(step.task_name)
        if step.is_completed:
            text = f"[已完成]\n{text}"
        
        font_size = calculate_font_size(step.duration, text)
        wrapped_text = wrap_text_for_bar(text, step.duration)
        
        ax.text(
            step.start_time + step.duration / 2,
            y_pos,
            wrapped_text,
            ha='center',
            va='center',
            fontsize=font_size,
            fontweight='bold'
        )
    
    ax.set_yticks(range(len(all_persons)))
    person_labels = []
    for person, role in reversed(all_persons):
        natural_days = person_natural_days.get(person, 0)
        person_labels.append(f"{person} ({role}) [{natural_days}天]")
    ax.set_yticklabels(person_labels)
    
    min_time = min(step.start_time for step in schedule_result)
    max_time = max(step.end_time for step in schedule_result)
    ax.set_xlim(min_time - 1, max_time + 1)
    ax.set_xlabel('时间', fontsize=12)
    ax.set_ylabel('人员 (角色)', fontsize=12)
    
    if start_date:
        date_ticks = list(range(min_time - 1, max_time + 2))
        date_labels = [format_date_with_weekday(workdays_to_date(start_date, d)) for d in date_ticks]
        ax.set_xticks(date_ticks)
        ax.set_xticklabels(date_labels, rotation=45, ha='right')
    
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)
    
    legend_patches = [mpatches.Patch(color=color, label=name) 
                      for name, color in task_colors.items()]
    ax.legend(handles=legend_patches, loc='upper right', fontsize=9)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"甘特图（按人员）已保存到: {output_path}")
    
    plt.close()


def generate_gantt_chart_by_task(schedule_result: List[TaskStep],
                                  output_path: str = "schedule_gantt_by_task.png",
                                  title: str = "需求排期甘特图（按需求）",
                                  start_date: Optional[datetime] = None,
                                  task_dependencies: Dict[str, Dict[str, List[str]]] = None,
                                  task_priorities: Dict[str, int] = None) -> None:
    """
    生成按需求维度的甘特图
    横轴：时间，纵轴：需求
    基于依赖关系的动态高度算法
    
    Args:
        schedule_result: 调度结果列表
        output_path: 输出文件路径
        title: 图表标题
        start_date: 项目开始日期
        task_dependencies: 每个需求的工序依赖关系 {task_name: {step_name: [dep_steps]}}
        task_priorities: 每个需求的优先级 {task_name: priority}
    """
    if not schedule_result:
        print("没有调度结果，无法生成甘特图")
        return
    
    task_names = list(set(step.task_name for step in schedule_result))
    
    if task_priorities:
        task_names_sorted = sorted(task_names, key=lambda x: -task_priorities.get(x, 0))
    else:
        def get_task_sort_key(name):
            if name.startswith('S'):
                return (0, name)
            elif name.startswith('A'):
                return (1, name)
            elif name.startswith('B'):
                return (2, name)
            elif name.startswith('C'):
                return (3, name)
            else:
                return (4, name)
        task_names_sorted = sorted(task_names, key=get_task_sort_key)
    
    task_duration = {}
    task_date_range = {}
    for task_name in task_names:
        task_steps_list = [s for s in schedule_result if s.task_name == task_name]
        if task_steps_list:
            min_start = min(s.start_time for s in task_steps_list)
            max_end = max(s.end_time for s in task_steps_list)
            task_duration[task_name] = max_end - min_start
            task_date_range[task_name] = (min_start, max_end)
        else:
            task_duration[task_name] = 0
            task_date_range[task_name] = (0, 0)
    
    fig, ax = plt.subplots(figsize=(16, max(8, len(task_names) * 1.5)))
    
    def get_base_step_name(step_name: str) -> str:
        if step_name.endswith('验收'):
            return step_name[:-2]
        return step_name
    
    step_names = list(set(get_base_step_name(step.step_name) for step in schedule_result))
    step_colors = plt.cm.Set3(np.linspace(0, 1, max(len(step_names), 3)))
    step_color_map = {name: step_colors[i % len(step_colors)] for i, name in enumerate(sorted(step_names))}
    
    def get_step_color(step_name: str):
        base_name = get_base_step_name(step_name)
        return step_color_map.get(base_name, 'gray')
    
    y_base = {name: i for i, name in enumerate(reversed(task_names_sorted))}
    
    from collections import defaultdict
    task_steps = defaultdict(list)
    for step in schedule_result:
        task_steps[step.task_name].append(step)
    
    def has_overlap(s1, s2):
        return not (s1.end_time <= s2.start_time or s1.start_time >= s2.end_time)
    
    def calculate_y_ranges(steps, dependencies):
        """
        基于依赖关系计算每个工序的 Y 范围
        
        算法：
        1. 根节点（无依赖）范围是 0-1
        2. 对于每个节点，看它有几个孩子节点（依赖它的节点）
        3. 如果只有一个孩子，孩子继承父节点的完整范围
        4. 如果有N个孩子，每个孩子分得父节点范围的 1/N
        5. 如果一个节点有多个父节点（多依赖），直接设为 0-1
        """
        step_by_name = {s.step_name: s for s in steps}
        step_deps = dependencies if dependencies else {}
        
        children = {s.step_name: [] for s in steps}
        for s in steps:
            for dep in step_deps.get(s.step_name, []):
                if dep in children:
                    children[dep].append(s.step_name)
        
        in_degree = {s.step_name: 0 for s in steps}
        for s in steps:
            for dep in step_deps.get(s.step_name, []):
                if dep in step_by_name:
                    in_degree[s.step_name] += 1
        
        topo_order = []
        queue = [name for name, deg in sorted(in_degree.items()) if deg == 0]
        while queue:
            current = queue.pop(0)
            topo_order.append(current)
            for child in children.get(current, []):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)
        
        step_range = {}
        
        for step_name in topo_order:
            step = step_by_name[step_name]
            deps = step_deps.get(step_name, [])
            valid_deps = [d for d in deps if d in step_by_name]
            
            if len(valid_deps) > 1:
                step_range[id(step)] = (0.0, 1.0)
            elif len(valid_deps) == 1:
                parent = valid_deps[0]
                parent_range = step_range[id(step_by_name[parent])]
                siblings = children[parent]
                
                if len(siblings) == 1:
                    step_range[id(step)] = parent_range
                else:
                    parent_height = parent_range[1] - parent_range[0]
                    slice_height = parent_height / len(siblings)
                    siblings_sorted = sorted(siblings)
                    idx = siblings_sorted.index(step_name)
                    new_start = parent_range[0] + idx * slice_height
                    new_end = parent_range[0] + (idx + 1) * slice_height
                    step_range[id(step)] = (new_start, new_end)
            else:
                step_range[id(step)] = (0.0, 1.0)
        
        return step_range
    
    for task_name, steps in task_steps.items():
        dependencies = task_dependencies.get(task_name, {}) if task_dependencies else {}
        
        final_ranges = calculate_y_ranges(steps, dependencies)
        
        for step in steps:
            y_pos = y_base[task_name]
            y_range = final_ranges.get(id(step), (0.0, 1.0))
            
            base_height = 0.6
            y_start = y_pos - base_height / 2 + y_range[0] * base_height
            y_end = y_pos - base_height / 2 + y_range[1] * base_height
            bar_height = (y_end - y_start) * 0.95
            y_center = (y_start + y_end) / 2
            
            if step.is_completed:
                bar_color = '#CCCCCC'
                edge_color = '#888888'
                edge_linewidth = 1.0
                edge_linestyle = '--'
                alpha_value = 0.6
            else:
                bar_color = get_step_color(step.step_name)
                edge_color = 'black'
                edge_linewidth = 0.5
                edge_linestyle = '-'
                alpha_value = 0.8
            
            ax.barh(
                y_center, 
                step.duration, 
                left=step.start_time, 
                height=bar_height,
                color=bar_color,
                edgecolor=edge_color,
                linewidth=edge_linewidth,
                linestyle=edge_linestyle,
                alpha=alpha_value
            )
            
            text = step.assigned_person
            if step.is_completed:
                text = f"[已完成]\n{text}"
            
            range_size = y_range[1] - y_range[0]
            base_font_size = 6 if range_size < 0.4 else (7 if range_size < 0.7 else 8)
            font_size = calculate_font_size(step.duration, text, base_font_size)
            wrapped_text = wrap_text_for_bar(text, step.duration, max_chars_per_line=5)
            
            ax.text(
                step.start_time + step.duration / 2,
                y_center,
                wrapped_text,
                ha='center',
                va='center',
                fontsize=font_size,
                fontweight='bold'
            )
    
    ax.set_yticks(range(len(task_names)))
    task_labels = []
    for name in reversed(task_names_sorted):
        if start_date and name in task_date_range:
            start_date_task = workdays_to_date(start_date, task_date_range[name][0])
            end_date_task = workdays_to_date(start_date, task_date_range[name][1])
            natural_days = (end_date_task - start_date_task).days
            task_labels.append(f"{name} [{natural_days}天]")
        else:
            task_labels.append(f"{name} [{task_duration[name]}天]")
    ax.set_yticklabels(task_labels)
    
    min_time = min(step.start_time for step in schedule_result)
    max_time = max(step.end_time for step in schedule_result)
    ax.set_xlim(min_time - 1, max_time + 1)
    ax.set_xlabel('时间', fontsize=12)
    ax.set_ylabel('需求名称', fontsize=12)
    
    if start_date:
        date_ticks = list(range(min_time - 1, max_time + 2))
        date_labels = [format_date_with_weekday(workdays_to_date(start_date, d)) for d in date_ticks]
        ax.set_xticks(date_ticks)
        ax.set_xticklabels(date_labels, rotation=45, ha='right')
    
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)
    
    legend_patches = [mpatches.Patch(color=color, label=name) 
                      for name, color in step_color_map.items()]
    ax.legend(handles=legend_patches, loc='upper right', fontsize=9, title='工序')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"甘特图（按需求）已保存到: {output_path}")
    
    plt.close()


def generate_gantt_chart(schedule_result: List[TaskStep], 
                         resources: Dict[str, List[str]],
                         output_path: str = "schedule_gantt.png",
                         title: str = "需求排期甘特图",
                         start_date: Optional[datetime] = None,
                         task_dependencies: Dict[str, Dict[str, List[str]]] = None,
                         task_priorities: Dict[str, int] = None) -> None:
    """
    生成甘特图（同时生成按人员和按需求两个版本）
    
    Args:
        schedule_result: 调度结果列表
        resources: 资源配置
        output_path: 输出文件路径（基础路径，会自动添加后缀）
        title: 图表标题
        start_date: 项目开始日期
        task_dependencies: 每个需求的工序依赖关系
        task_priorities: 每个需求的优先级
    """
    if not schedule_result:
        print("没有调度结果，无法生成甘特图")
        return
    
    import os
    base_path, ext = os.path.splitext(output_path)
    
    generate_gantt_chart_by_person(
        schedule_result, 
        resources, 
        f"{base_path}_by_person{ext}",
        f"{title}（按人员）",
        start_date
    )
    
    generate_gantt_chart_by_task(
        schedule_result,
        f"{base_path}_by_task{ext}",
        f"{title}（按需求）",
        start_date,
        task_dependencies,
        task_priorities
    )


def generate_gantt_chart_html(schedule_result: List[TaskStep],
                               resources: Dict[str, List[str]],
                               output_path: str = "schedule_gantt.html",
                               title: str = "需求排期甘特图") -> None:
    """
    生成交互式HTML甘特图（使用Plotly）
    
    Args:
        schedule_result: 调度结果列表
        resources: 资源配置
        output_path: 输出文件路径
        title: 图表标题
    """
    try:
        import plotly.figure_factory as ff
        import plotly.express as px
        import plotly.graph_objects as go
    except ImportError:
        print("Plotly未安装，跳过HTML甘特图生成。使用: pip install plotly")
        return
    
    if not schedule_result:
        print("没有调度结果，无法生成甘特图")
        return
    
    # 准备数据
    df_data = []
    for step in schedule_result:
        df_data.append({
            'Task': f"{step.assigned_person} ({step.role})",
            'Start': step.start_time,
            'Finish': step.end_time,
            'Resource': step.task_name,
            'Step': step.step_name
        })
    
    df = pd.DataFrame(df_data)
    
    # 获取所有需求名称
    task_names = list(set(step.task_name for step in schedule_result))
    colors = px.colors.qualitative.Set3[:len(task_names)]
    color_map = {name: colors[i % len(colors)] for i, name in enumerate(task_names)}
    
    # 创建甘特图
    fig = ff.create_gantt(
        df,
        index_col='Resource',
        colors=color_map,
        title=title,
        show_colorbar=True,
        group_tasks=True,
        showgrid_x=True,
        showgrid_y=True
    )
    
    # 更新布局
    fig.update_layout(
        xaxis_title='时间 (天)',
        yaxis_title='人员 (角色)',
        font=dict(size=12),
        height=max(600, len(set(df['Task'])) * 40)
    )
    
    # 保存HTML
    fig.write_html(output_path)
    print(f"交互式甘特图已保存到: {output_path}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='需求排期调度程序 - 基于优先级的贪心调度算法',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python schedule.py --data data.json
  python schedule.py --data data.json --config config.json
  python schedule.py --data data.json --wip 3 --buffer 0.2
  python schedule.py --data data.json --output result.csv --gantt schedule.png
        '''
    )
    
    parser.add_argument(
        '--data', '-d',
        type=str,
        required=True,
        help='输入数据文件路径 (JSON格式，包含tasks和start_date)'
    )
    
    parser.add_argument(
        '--config', '-c',
        type=str,
        default=None,
        help='配置文件路径 (JSON格式，包含templates和resources，默认: config.json)'
    )
    
    parser.add_argument(
        '--wip', '-w',
        type=int,
        default=None,
        help='WIP上限（同时进行中的需求数量）'
    )
    
    parser.add_argument(
        '--buffer', '-b',
        type=float,
        default=0.0,
        help='项目缓冲比例 (如 0.2 表示20%%)'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='schedule_result.csv',
        help='CSV输出文件路径 (默认: schedule_result.csv)'
    )
    
    parser.add_argument(
        '--gantt', '-g',
        type=str,
        default='schedule_gantt.png',
        help='甘特图输出文件路径 (默认: schedule_gantt.png)'
    )
    
    parser.add_argument(
        '--html',
        type=str,
        default=None,
        help='交互式HTML甘特图输出路径 (可选)'
    )
    
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='静默模式，不打印详细信息'
    )
    
    parser.add_argument(
        '--deadline',
        type=str,
        default=None,
        help='项目截止日期，格式: YYYY-MM-DD（从截止日期反推开始时间）'
    )
    
    args = parser.parse_args()
    
    try:
        data = load_data(args.data)
        
        config_path = args.config
        if config_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            default_config = os.path.join(script_dir, 'config.json')
            if os.path.exists(default_config):
                config_path = default_config
        
        if config_path:
            config = load_data(config_path)
            if 'templates' not in data and 'templates' in config:
                data['templates'] = config['templates']
            if 'resources' not in data and 'resources' in config:
                data['resources'] = config['resources']
        
        validate_data(data)
        
        deadline_str = data.get('deadline') or args.deadline
        
        if deadline_str:
            deadline_date = datetime.strptime(deadline_str, '%Y-%m-%d')
            
            if 'start_date' in data:
                del data['start_date']
            
            temp_scheduler = Scheduler(
                data=data,
                wip_limit=args.wip,
                buffer_ratio=args.buffer
            )
            temp_scheduler.schedule()
            total_workdays = temp_scheduler.project_end_time
            
            def subtract_workdays(end_date: datetime, workdays: int) -> datetime:
                current = end_date
                days_subtracted = 0
                while days_subtracted < workdays:
                    current -= timedelta(days=1)
                    if not is_weekend(current):
                        days_subtracted += 1
                return current
            
            calculated_start_date = subtract_workdays(deadline_date, total_workdays)
            data['start_date'] = calculated_start_date.strftime('%Y-%m-%d')
            temp_start_date = datetime.strptime(data['start_date'], '%Y-%m-%d')
            natural_days = workdays_to_natural_days(temp_start_date, total_workdays)
            print(f"截止日期: {deadline_str}")
            print(f"反推开始日期: {data['start_date']} (总工期: {total_workdays}工作日 / {natural_days}自然日)")
        
        scheduler = Scheduler(
            data=data,
            wip_limit=args.wip,
            buffer_ratio=args.buffer
        )
        
        # 执行调度
        scheduler.schedule()
        
        # 打印结果
        if not args.quiet:
            scheduler.print_summary()
        
        # 导出CSV
        scheduler.export_csv(args.output)
        
        # 收集依赖关系
        task_dependencies = {}
        for task_name, task in scheduler.tasks.items():
            task_dependencies[task_name] = task.dependencies
        
        # 收集优先级
        task_priorities = {}
        for task_name, task in scheduler.tasks.items():
            task_priorities[task_name] = task.priority
        
        natural_days = workdays_to_natural_days(scheduler.start_date, scheduler.project_end_time)
        
        generate_gantt_chart(
            scheduler.schedule_result,
            data['resources'],
            args.gantt,
            title=f"需求排期甘特图 ({scheduler.project_end_time}工作日 / {natural_days}自然日)",
            start_date=scheduler.start_date,
            task_dependencies=task_dependencies,
            task_priorities=task_priorities
        )
        
        # 生成HTML甘特图（可选）
        if args.html:
            generate_gantt_chart_html(
                scheduler.schedule_result,
                data['resources'],
                args.html,
                title="需求排期甘特图"
            )
        
        print("\n调度完成!")
        
    except (DataValidationError, ScheduleError) as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"未知错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
