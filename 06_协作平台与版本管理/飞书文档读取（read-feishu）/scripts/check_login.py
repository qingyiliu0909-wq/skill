"""
打开飞书文档 URL 并截取一张截图，供 agent 判断是否需要登录。

用法：
    python scripts/check_login.py <url> [browser]
    browser: chrome 或 edge，默认 chrome
"""
import sys
import time
import os
from PIL import ImageGrab
import pygetwindow as gw

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
DEFAULT_OUTPUT = os.path.join(SKILL_DIR, "feishu_login_check.jpg")


def check_login(url=None, browser="chrome", output_path=None):
    if url is None:
        if len(sys.argv) < 2:
            print("Error: Missing URL. Usage: python scripts/check_login.py <url> [chrome|edge]")
            return ""
        url = sys.argv[1]
    if len(sys.argv) >= 3:
        browser = sys.argv[2]
    if output_path is None:
        output_path = DEFAULT_OUTPUT

    browser_cmd = "chrome" if browser.lower() == "chrome" else "msedge"
    print(f"[*] 使用 {browser} 打开: {url}")
    os.system(f'start {browser_cmd} "{url}"')
    time.sleep(8)

    windows = [w for w in gw.getAllWindows() if 'Chrome' in w.title or 'Edge' in w.title]
    if not windows:
        print("[ERROR] 找不到浏览器窗口！")
        return ""

    win = windows[0]
    try:
        if not win.isMaximized:
            win.maximize()
        win.activate()
        time.sleep(1)
    except Exception:
        pass

    bbox = (win.left, win.top, win.right, win.bottom)
    img = ImageGrab.grab(bbox=bbox, all_screens=True)
    img.save(output_path, format="JPEG", quality=85)
    print(f"[SUCCESS] 登录检查截图已保存: {output_path}")
    print("[*] 请 agent 读取该截图，判断页面是否需要登录。")
    return output_path


if __name__ == "__main__":
    check_login()
