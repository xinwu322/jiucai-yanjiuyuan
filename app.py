"""韭研行情终端 · 桌面版入口。

单文件启动：python app.py
打包后：JiuYanQuote.exe
"""
import os
import sys


def _enable_dpi():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main():
    _enable_dpi()
    base = os.path.dirname(os.path.abspath(__file__))
    if base not in sys.path:
        sys.path.insert(0, base)
    from ui.window import App
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
