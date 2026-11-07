import re, json
from pathlib import Path
p = Path('main.py')
code = p.read_text(encoding='utf-8')
code = code.replace('print(\"  • Rendering video with ULTRA-STABLE NATIVE LYRICS ENGINE...\")', 'print(\"  • Rendering video...\")')
code = code.replace('print(\"  • Rendering video with BOXLESS FLOATING TEXT...\")', 'print(\"  • Rendering video...\")')
p.write_text(code, encoding='utf-8')
print('Fixed Syntax Error!')
