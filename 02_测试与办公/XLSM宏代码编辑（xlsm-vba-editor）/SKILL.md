---
name: xlsm-vba-editor
description: >
  Reliably modify VBA modules in xlsm files without corrupting Chinese text or line formatting.
  This skill should be used when the user asks to add, modify, or delete VBA code in .xlsm
  files that contain Chinese characters (comments, string literals, variable names).
  Triggers: "修改xlsm的VBA", "往xlsm里加宏", "修改模块代码", "注入VBA代码",
  "xlsm macro modify", "edit VBA in xlsm". NOT for reading/viewing VBA code.
agent_created: true
---

# XLSM VBA Editor

Modify VBA modules in `.xlsm` via PowerShell COM, preserving Chinese text and formatting.

## Core Principle

**Inline PowerShell strings only. Never read code from files for injection.**

PowerShell strings are UTF-16 native → COM passes through correctly.
File reads (`.bas` import, `AddFromString` from file) go through ANSI code-page → Chinese garbled.

## Available Scripts

Run these without loading into context. Use `scripts/` prefix in PowerShell tool calls.

| Script | Purpose |
|---|---|
| `scripts/open_xlsm.ps1 <path> [-ModuleName <name>]` | Open xlsm, list all VBA components and line counts |
| `scripts/find_line.ps1 <path> <module> <pattern> [-FirstOnly]` | Find line numbers by regex match |
| `scripts/inject_function.ps1 <path> <module> <funcfile> <line>` | Inject VBA code from a file at specified line |
| `scripts/check_vba.py <path> [-m <module>] [-c <string>]...` | Binary verification: check Chinese strings present in VBA |

## Workflow

### 1. Inspect the file

```powershell
.\scripts\open_xlsm.ps1 "D:\path\to\file.xlsm" -ModuleName "模块2"
```

### 2. Find insertion points

```powershell
.\scripts\find_line.ps1 "D:\path\to\file.xlsm" "模块2" "If Not AreValuesEqual" -FirstOnly
```

### 3. Insert/Replace/Delete lines

For small changes, use direct COM calls in PowerShell:

```powershell
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false; $excel.DisplayAlerts = $false
$wb = $excel.Workbooks.Open($xlsmPath)
$mod = $wb.VBProject.VBComponents.Item($moduleName).CodeModule

# Insert one line after line N
$mod.InsertLines($lineNum + 1, "    ' 这是中文注释")

# Replace a line
$mod.ReplaceLine($lineNum, "    NewContent")

# Delete N lines starting at L
$mod.DeleteLines($startLine, $count)

$wb.Save()
$wb.Close()
$excel.Quit()
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
```

For larger new functions, use `scripts/inject_function.ps1` with a text file.

### 4. Verify

```powershell
# Check timestamp changed (must NOT be equal before/after)
(Get-Item $xlsmPath).LastWriteTime

# Binary verification
python scripts/check_vba.py $xlsmPath -m "模块2" -c "表格列表" -c "不参与比对列" -c "IsSkipColumn"
```

## Key Rules

- **After inserting lines, line numbers shift.** Process from TOP to BOTTOM, track cumulative offset.
- **Always verify timestamp changed after save** — phantom saves happen silently.
- **PowerShell string escaping**: Use `""` for each `"` in VBA code. E.g. `"MsgBox ""Hello"""` produces `MsgBox "Hello"`.
- **Chinese comments inline**: `"' 中文注释"` — OK because UTF-16 in PowerShell memory.

## Lazy-Init Pattern

Module-level variables that depend on initialization: self-init on first use.

```vba
Function MyFunc() As Boolean
    If MyVar Is Nothing Then Set MyVar = ReadMyVar()
    ' ... use MyVar
End Function
```

## Creating UserForms with Chinese Controls

When the user asks to add a UserForm with Chinese-named controls to an xlsm, use Python win32com (not PowerShell) — PowerShell COM access to the Form Designer is unreliable.

### Prerequisites

```bash
python -m venv venv
pip install pywin32
```

### Python Script Template

```python
import sys, os, win32com.client, pythoncom
pythoncom.CoInitialize()
excel = win32com.client.Dispatch('Excel.Application')
excel.Visible = False; excel.DisplayAlerts = False

xlsmPath = r"D:\path\to\file.xlsm"
wb = excel.Workbooks.Open(xlsmPath)
vbProj = wb.VBProject

# --- Add a Standard Module ---
newMod = vbProj.VBComponents.Add(1)  # vbext_ct_StdModule
newMod.Name = "模块名"
newMod.CodeModule.AddFromString("""Option Explicit
' 中文注释
Dim 中文变量 As String
Public Sub 中文方法()
    ' 中文注释
End Sub
""")

# --- Add a UserForm ---
userForm = vbProj.VBComponents.Add(3)  # vbext_ct_MSForm
userForm.Name = "窗体中文名"
designer = userForm.Designer
designer.Caption = "窗体标题"

# Add a Label control
lbl = designer.Controls.Add("Forms.Label.1")
lbl.Name = "标签中文名"
lbl.Caption = "标签文字"
lbl.Left = 20; lbl.Top = 10; lbl.Width = 100; lbl.Height = 20

# Add a TextBox control
txt = designer.Controls.Add("Forms.TextBox.1")
txt.Name = "输入框中文名"
txt.Text = "默认值"
txt.Left = 90; txt.Top = 48; txt.Width = 100; txt.Height = 20

# Add a CommandButton
btn = designer.Controls.Add("Forms.CommandButton.1")
btn.Name = "按钮中文名"
btn.Caption = "按钮文字"
btn.Left = 20; btn.Top = 150; btn.Width = 80; btn.Height = 28

# Add code to the form
formCode = """' 窗体代码 —— 中文注释
Dim 窗体变量 As Long
Private Sub 计算按钮_Click()
    ' 点击事件处理
    Dim 局部变量 As Double
    局部变量 = Val(输入框中文名.Text)
End Sub
"""
userForm.CodeModule.AddFromString(formCode)

# --- Save ---
wb.Save()
wb.Close(False)
excel.Quit()
pythoncom.CoUninitialize()
```

### Important Notes

- **Form Name vs Control Name**: `userForm.Name` renames the form component; `lbl.Name` renames each control. Both support full Unicode.
- **Control Types**: `"Forms.Label.1"`, `"Forms.TextBox.1"`, `"Forms.CommandButton.1"`, `"Forms.ComboBox.1"`, `"Forms.ListBox.1"`, `"Forms.CheckBox.1"`, `"Forms.OptionButton.1"`, `"Forms.Frame.1"`
- **Font properties**: Set via `lbl.Font.Name = "微软雅黑"`, `lbl.Font.Size = 14`, `lbl.Font.Bold = True`
- **MultiLine TextBox**: `txt.MultiLine = True; txt.ScrollBars = 2` (2 = fmScrollBarsVertical)
- **ForeColor**: Use decimal or hex like `lbl.ForeColor = 0x808080`
- **Do NOT set `designer.Width` / `designer.Height`** — these are read-only on the designer object.
- **Use Python**, not PowerShell, for form creation — PowerShell struggles with the Form Designer COM interface.
- When setting Chinese Caption/Text strings in Python source, use Unicode escapes (e.g. `"\u653b\u51fb\u529b"` for "攻击力") to avoid encoding issues with GBK stdout.

## Verification

```python
# Use check_vba.py from the skill
python scripts/check_vba.py <xlsm_path> -m "模块名" -c "中文关键词"
```

## Anti-Patterns

| Never do | Why |
|---|---|
| `Import("file.bas")` | ANSI code page → Chinese garbled |
| `AddFromString($codeFromFile)` | Corrupts line endings + garbles Chinese |
| `.bas` file write → edit → re-import | Unrecoverable double-encoding corruption |
| Replace entire module | Original Chinese lost permanently |
| Skip timestamp check after save | COM may report success but file unchanged |
