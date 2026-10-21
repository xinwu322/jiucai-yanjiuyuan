# 打包为单文件 exe（Windows）

## 环境要求

- Python 3.10+，**必须带 tkinter**（`python -c "import tkinter"` 不报错即可）
- pip 依赖：`pytdx`、`pypinyin`、`pyinstaller`

## 步骤

```bat
python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt pyinstaller

pyinstaller --noconfirm --onefile --windowed --name 韭菜研究院 ^
  --add-data "core/bj_seed.json;core" ^
  --add-data "core/industry.json;core" ^
  --exclude-module matplotlib --exclude-module PIL --exclude-module scipy ^
  app.py
```

产物：`dist/韭菜研究院.exe`（约 33 MB）。

## 说明

- `--onefile` 打成单文件；`--windowed` 不带控制台窗口。
- 代码通过 `store.resource_dir()` 读取随包资源：打包后从 `sys._MEIPASS` 取，
  PyInstaller 会把 `--add-data` 的内容释放到临时目录。
- 单文件每次启动都要解压，冷启动约 2–4 秒；介意的话可以去掉 `--onefile` 用目录模式。
- 排除 `matplotlib` / `PIL` / `scipy` 能把体积从 ~90 MB 压到 ~33 MB，这三者项目都没用到。
- macOS / Linux 无法使用这个 exe，直接 `python app.py` 运行源码。

## 发布

exe 和 zip 不要提交进 Git 仓库（`.gitignore` 已排除），走 GitHub Releases：

Releases → Draft a new release → tag `v1.1` → 上传 zip → Publish。
