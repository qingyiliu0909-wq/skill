---
name: excel-editing-checklist
description: 安全读取、编辑、生成或修复 xlsx/Excel 文件，并保留或统一表格格式。用于测试用例、QA模板、导入表、codexread分析表和配置表的内容修改、跨工作簿复制格式、白底表头修复、字体/边框/列宽/行高/冻结窗格/筛选范围校验，以及OOXML损坏排查。
---

# Excel 编辑注意事项

## 职责边界

本 skill 只负责 xlsx 的安全读写、格式保护和结构校验。测试用例的模块分析、前置条件、步骤、预期结果、包装文本、人工定稿与功能/回归口径，使用同目录的 `write-game-test-cases` skill；编辑测试用例工作簿时同时使用两个 skill。

## 工作流

1. 确认目标文件、模板文件、工作表、有效数据范围和编辑授权边界。
2. 记录修改前的文件时间、工作表名、单元格内容、列宽、行高、合并区域、冻结窗格、筛选范围和隐藏状态。
3. 内容编辑只改指定单元格；格式编辑先选同目录、同用途、人工确认达标的模板。
4. 保存到临时文件，重新打开验证后再替换目标；不要在验证失败的文件上继续编辑。
5. 全量核对内容和结构，不以 `style_id` 相同作为格式一致的证据。

若目标位于 `ExportDatas/datas`，同时遵循配置表修改 skill 的 SVN lock、导表和生成文件检查规则。

## QA测试用例约束

- 默认表头为第1行，正文从第2行开始；先以当前目录人工达标文件为准，不凭记忆创造格式。
- 仅调整格式时，修改前后所有单元格的值、公式、超链接和批注必须一致。
- 表头底色、字体、边框、列宽、行高、自动换行、顶端对齐、冻结窗格和筛选范围必须逐项核验。
- 筛选范围应覆盖实际非空数据行，不能沿用模板的旧末行。
- 冻结窗格必须读取模板或需求的明确值；保存后重新打开确认，避免意外变成当前活动单元格位置。
- 人工修改过的文件或用例默认不覆盖，除非用户明确要求；格式修复也不得顺带改文案。

## 跨工作簿样式复制

禁止在不同工作簿之间直接执行：

```python
target._style = copy(source._style)
```

`_style` 内部引用的是各自工作簿的字体、填充和边框索引。跨工作簿复制后，`style_id` 可能看似一致，但目标仍会显示原工作簿的宋体、蓝色填充或边框。

跨工作簿必须逐属性复制：

```python
from copy import copy

target.font = copy(source.font)
target.fill = copy(source.fill)
target.border = copy(source.border)
target.alignment = copy(source.alignment)
target.number_format = source.number_format
target.protection = copy(source.protection)
```

保存后重新打开文件，对比属性值，例如 `font.name`、`fill.fill_type`、四边 `border.style` 和 `alignment`；不要只比较 `_style` 或 `style_id`。

## 确定性脚本

格式修复优先使用 `scripts/xlsx_format_guard.py`：

```bash
python3 scripts/xlsx_format_guard.py audit target.xlsx --sheet 文档一
python3 scripts/xlsx_format_guard.py format-like target.xlsx template.xlsx output.xlsx --sheet 文档一 --columns A:G
```

`format-like` 会复制模板的列宽、表头格式、正文格式、行高、冻结窗格和网格线，按目标实际非空行更新筛选范围，并验证内容未改变。先输出到新文件；确认后再替换原文件。

## OOXML风险

若直接修改压缩包内XML，只做最小文本替换。通用XML库可能把 `x14ac/xr/xr2/xr3` 前缀改成 `ns1/ns2`，同时留下旧的 `mc:Ignorable`，导致Excel提示修复。

直接编辑XML后检查：

- `mc:Ignorable` 中每个前缀都有对应 `xmlns:<prefix>`。
- `x14ac:dyDescent`、`xr:uid` 等属性前缀未被改写。
- `workbook.xml`、`worksheet*.xml`、`styles.xml` 和共享字符串引用均有效。

## 修改后验证

每次写入至少确认：

1. `zipfile.testzip()` 返回 `None`。
2. 文件可被表格库重新打开，目标工作表和有效行数正确。
3. 内容修改符合目标；格式修改的内容快照完全不变。
4. 真实字体、字号、填充、边框、对齐、列宽和行高符合模板。
5. 合并区域、冻结窗格、筛选范围、隐藏行列和工作表可见性符合预期。
6. 如编辑过底层XML，共享字符串索引和命名空间完整。
7. 有条件时使用Excel或LibreOffice打开，确认无修复提示。

## 失败处理

若验证失败或Excel提示修复，停止追加编辑，保留原文件，从最近可打开版本重新应用最小变更。不要用第二次保存掩盖第一次格式或结构损坏。
