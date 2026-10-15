"""Read unchanged CPU Runtime/core definitions under an isolated namespace."""
import ast
import json
import re
import sqlite3
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from planner_policy import CONTRACT, parse_plan

TALK = Path(__file__).resolve().parent.parent
namespace = {'json':json,'re':re,'sqlite3':sqlite3,'unicodedata':unicodedata,
             'SequenceMatcher':SequenceMatcher,'parse_plan':parse_plan,'validate_plan':CONTRACT['validate_plan']}
for path,names in [(TALK/'lora_v4_planner_talk/runtime.py',{'Runtime','hard_failure'}),
                   (TALK/'lora_v4_runtime_ab/core.py',{'normal','sentences','cosine','dice','detect','compact','ranked_candidate'})]:
    tree=ast.parse(path.read_text(encoding='utf8'))
    selected=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    assert {n.name for n in selected}==names
    if path.name=='core.py':
        namespace['POLICY']=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id=='POLICY' for t in n.targets)))
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(path),'exec'),namespace)
Runtime=namespace['Runtime']
hard_failure=namespace['hard_failure']
detect=namespace['detect']
compact=namespace['compact']
ranked_candidate=namespace['ranked_candidate']
POLICY=namespace['POLICY']
normal=namespace['normal']
