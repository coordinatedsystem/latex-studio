"""An explicit user-triggered native .tex chooser, used by the local application."""
import json
import sys
import tkinter as tk
from tkinter import filedialog

root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)
chosen = filedialog.askopenfilename(title='选择 LaTeX 主文档', filetypes=[('LaTeX 主文档', '*.tex')])
root.destroy()
sys.stdout.reconfigure(encoding='utf-8')
print(json.dumps({'path': chosen}, ensure_ascii=False))
