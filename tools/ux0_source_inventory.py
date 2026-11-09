#!/usr/bin/env python3
"""Generate a deterministic source inventory for the UX0 architecture audit."""
from __future__ import annotations
import ast, json, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'app_source'; TESTS=ROOT/'tests'

def expr(node):
    try:return ast.unparse(node)
    except Exception:return '<unparseable>'
def literal_kw(call,name):
    for kw in call.keywords:
        if kw.arg==name:
            try:return ast.literal_eval(kw.value)
            except Exception:return expr(kw.value)
    return None

def scan_file(path):
    raw=path.read_text(encoding='utf-8'); tree=ast.parse(raw,filename=str(path))
    result={'classes':[],'methods':[],'ui_commands':[],'bindings':[],'timers':[],'workers':[],'windows':[]}
    class Stack(ast.NodeVisitor):
        def __init__(self):self.scope=[]
        def visit_ClassDef(self,node):
            result['classes'].append({'name':node.name,'bases':[expr(b) for b in node.bases],'line':node.lineno})
            self.scope.append(node.name);self.generic_visit(node);self.scope.pop()
        def visit_FunctionDef(self,node):
            result['methods'].append({'name':'.'.join(self.scope+[node.name]),'line':node.lineno})
            self.scope.append(node.name);self.generic_visit(node);self.scope.pop()
        visit_AsyncFunctionDef=visit_FunctionDef
        def visit_Call(self,node):
            fn=expr(node.func); record={'line':node.lineno,'scope':'.'.join(self.scope)}
            if fn.endswith(('.add_command','.add_checkbutton','.add_radiobutton')):
                result['ui_commands'].append({**record,'surface':fn,'label':literal_kw(node,'label'),'command':literal_kw(node,'command')})
            elif re.search(r'(?:ttk\.|tk\.)?(?:Button|Checkbutton|Radiobutton)$',fn):
                result['ui_commands'].append({**record,'surface':fn,'label':literal_kw(node,'text'),'textvariable':literal_kw(node,'textvariable'),'command':literal_kw(node,'command')})
            if fn.endswith('.bind') and node.args:
                result['bindings'].append({**record,'event':expr(node.args[0]),'handler':expr(node.args[1]) if len(node.args)>1 else None})
            if fn.endswith(('.after','.after_idle')):
                result['timers'].append({**record,'call':fn,'delay':expr(node.args[0]) if node.args else None,'callback':expr(node.args[1]) if len(node.args)>1 else None})
            if fn in ('threading.Thread','Thread','concurrent.futures.ThreadPoolExecutor','ThreadPoolExecutor') or fn.endswith('.Thread'):
                result['workers'].append({**record,'kind':fn,'name':literal_kw(node,'name'),'target':literal_kw(node,'target')})
            if fn in ('subprocess.Popen','Popen','EncoderPipe') or fn.endswith('.Popen'):
                result['workers'].append({**record,'kind':fn,'target':expr(node.args[0]) if node.args else None})
            if fn in ('tk.Toplevel','Toplevel') or fn.endswith('.Toplevel'):
                result['windows'].append({**record,'kind':fn})
            self.generic_visit(node)
    Stack().visit(tree);return result

def dataclass_fields(path):
    tree=ast.parse(path.read_text(encoding='utf-8'));out={}
    for node in tree.body:
        if isinstance(node,ast.ClassDef) and any((isinstance(d,ast.Name) and d.id=='dataclass') or (isinstance(d,ast.Attribute) and d.attr=='dataclass') or (isinstance(d,ast.Call) and expr(d.func).endswith('dataclass')) for d in node.decorator_list):
            fields=[]
            for item in node.body:
                if isinstance(item,ast.AnnAssign) and isinstance(item.target,ast.Name):fields.append(item.target.id)
            if fields:out[node.name]=fields
    return out

files={}
for path in sorted(SRC.glob('*.py')):files[str(path.relative_to(ROOT))]=scan_file(path)
tests=[]
for path in sorted(TESTS.glob('test_*.py')):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith('test_'):
            tests.append({'file':str(path.relative_to(ROOT)),'name':node.name,'line':node.lineno})
payload={
  'schema':'neospector/ux0-source-inventory-v1',
  'source_files':files,
  'project_dataclasses':dataclass_fields(SRC/'sequencer_model.py'),
  'tests':tests,
  'counts':{
      'python_source_files':len(files),
      'ui_command_sites':sum(len(v['ui_commands']) for v in files.values()),
      'binding_sites':sum(len(v['bindings']) for v in files.values()),
      'timer_sites':sum(len(v['timers']) for v in files.values()),
      'worker_sites':sum(len(v['workers']) for v in files.values()),
      'toplevel_sites':sum(len(v['windows']) for v in files.values()),
      'test_methods':len(tests),
  }
}
out=ROOT/'docs/UX0_SOURCE_INVENTORY.json';out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(out);print(json.dumps(payload['counts'],indent=2))
