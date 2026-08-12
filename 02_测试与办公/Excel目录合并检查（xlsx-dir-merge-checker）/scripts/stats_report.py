import re

# 读取结果文件
with open('missing_only_result.txt', 'r', encoding='utf-8') as f:
    content = f.read()

# 提取所有表名
tables = re.findall(r'\[表\] (.+)', content)

# 计算总数
total_missing = len(re.findall(r'类型: missing_row', content))

# 打印统计报告
print('=' * 60)
print('缺失行统计报告')
print(f'目录 A（主干）: C:\\Pan01\\demo\\EM_Build\\ExportDatas\\datas')
print(f'目录 B（分支）: D:\\OBT1.4Geili\\EM\\ExportDatas\\datas')
print('=' * 60)
print(f'存在缺失行的表数: {len(tables)} 个')
print(f'缺失行总数: {total_missing} 行')
print('=' * 60)
print()
print('各表缺失行数明细:')
print('-' * 60)

# 统计每个表的缺失行数
table_stats = []
for table in tables:
    # 找到该表的所有内容
    pattern = rf'\[表\] {re.escape(table)}(.*?)(?=\[表\]|\Z)'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        count = len(re.findall(r'类型: missing_row', match.group(1)))
        table_stats.append((table, count))

# 按缺失行数排序
table_stats.sort(key=lambda x: x[1], reverse=True)

# 输出
for table, count in table_stats:
    print(f'{table}: {count} 行')