"""
物理 RPA 方式逐页截图飞书文档，每屏保存为独立图片文件。
假设页面已登录（登录检查由 check_login.py 完成）。

用法：
    python scripts/physical_screenshot.py <url> [browser] [click_x] [click_y]
    browser: chrome 或 edge，默认 chrome
    click_x: 点击位置的水平比例（0.0~1.0），默认 0.6（窗口宽度的 60%）
    click_y: 点击位置的垂直比例（0.0~1.0），默认 0.5（窗口高度的 50%）

    不同飞书文档页面布局不同，如果 PageDown 不滚动，可能是焦点
    没有落在可滚动的内容区域。此时可调整 click_x/click_y 参数重试。
    常见参考值：
      - 标准文档页面：click_x=0.6 click_y=0.5（默认，避开左侧目录栏）
      - 有右侧面板的文档：click_x=0.4 click_y=0.5
      - Wiki 知识库页面：click_x=0.5 click_y=0.5

产物：
    {SKILL_DIR}/screenshots/feishu_page_001.jpg
    {SKILL_DIR}/screenshots/feishu_page_002.jpg
    ...
"""
import sys
import time
import hashlib
import os
from PIL import ImageGrab
import pyautogui
import pygetwindow as gw

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
DEFAULT_OUTPUT_DIR = os.path.join(SKILL_DIR, "screenshots")


def capture_feishu_by_physical_rpa(url=None, browser="chrome", output_dir=None,
                                    click_x_ratio=0.6, click_y_ratio=0.5):
    if url is None:
        if len(sys.argv) < 2:
            print("Error: Missing URL. Usage: python scripts/physical_screenshot.py <url> [chrome|edge] [click_x] [click_y]")
            return []
        url = sys.argv[1]
    if len(sys.argv) >= 3:
        browser = sys.argv[2]
    if len(sys.argv) >= 4:
        click_x_ratio = float(sys.argv[3])
    if len(sys.argv) >= 5:
        click_y_ratio = float(sys.argv[4])
    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR

    # 清理旧截图并创建输出目录
    if os.path.exists(output_dir):
        for f in os.listdir(output_dir):
            if f.startswith("feishu_page_") and f.endswith(".jpg"):
                os.remove(os.path.join(output_dir, f))
    os.makedirs(output_dir, exist_ok=True)

    browser_cmd = "chrome" if browser.lower() == "chrome" else "msedge"
    print(f"[*] 使用 {browser} 打开: {url}")
    os.system(f'start {browser_cmd} "{url}"')

    time.sleep(8)

    windows = [w for w in gw.getAllWindows() if 'Chrome' in w.title or 'Edge' in w.title]
    if not windows:
        print("[ERROR] 找不到浏览器窗口！")
        return []

    win = windows[0]
    try:
        if not win.isMaximized:
            win.maximize()
        win.activate()
        time.sleep(1)
    except Exception:
        pass

    # 点击文档内容区域以获取焦点（位置由 click_x_ratio / click_y_ratio 控制）
    safe_x = win.left + int(win.width * click_x_ratio)
    safe_y = win.top + int(win.height * click_y_ratio)

    print(f"[*] 点击位置: x={safe_x}, y={safe_y} (ratio: {click_x_ratio}, {click_y_ratio})")
    pyautogui.moveTo(safe_x, safe_y, duration=0.2)
    pyautogui.click()

    time.sleep(0.5)
    pyautogui.press('esc')
    time.sleep(0.5)

    print("[*] 焦点已锁定。!!! 警告 !!! 请松开鼠标和键盘，脚本正在物理接管屏幕！")

    saved_files = []
    last_hash = None
    max_scrolls = 30

    for i in range(max_scrolls):
        bbox = (win.left, win.top, win.right, win.bottom)
        img = ImageGrab.grab(bbox=bbox, all_screens=True)

        current_hash = hashlib.md5(img.tobytes()).hexdigest()

        if current_hash == last_hash:
            print(f"[*] 画面不再变化，已到达文档底部，共截取 {i} 屏。")
            break

        # 每屏保存为独立文件
        page_num = i + 1
        filename = f"feishu_page_{page_num:03d}.jpg"
        filepath = os.path.join(output_dir, filename)
        img.save(filepath, format="JPEG", quality=85)
        saved_files.append(filepath)
        last_hash = current_hash

        pyautogui.press('pagedown')
        print(f"  -> 已截取第 {page_num} 屏，保存为 {filename}")
        time.sleep(1.5)

    if not saved_files:
        print("[ERROR] 未能截取到任何画面！")
        return []

    print(f"\n[SUCCESS] 截图完成，共 {len(saved_files)} 页，保存在: {output_dir}")
    for f in saved_files:
        print(f"  - {os.path.basename(f)}")

    return saved_files


if __name__ == "__main__":
    capture_feishu_by_physical_rpa()
