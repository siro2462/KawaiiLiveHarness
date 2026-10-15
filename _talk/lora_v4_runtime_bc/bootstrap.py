"""Only imports frozen CPU modules. No model is instantiated by import."""
import importlib.util,json,os,sys,time,traceback,shutil,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'lora_v4_runtime_ab'
V4=ROOT.parent/'lora_v4_planner_talk'
SOURCE=ROOT.parent/'lora_v4_runtime_ablation'
SOURCE_RUN=SOURCE/'runs/ablation_10m_20261007'
OUT=ROOT/'runs/bc_consistency_10m_20261008'
sys.path.insert(0,str(OLD));sys.path.insert(0,str(V4))
spec=importlib.util.spec_from_file_location('frozen_runtime_run',OLD/'run.py')
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
from common import read,write,sha,now,Lock,SEED,MODEL,RUN,TALK,rows
from contracts import planner_prompt,talk_prompt,fallback_prompt,parse_plan,validate_plan
from runtime import Runtime,hard_failure,obtain_plan
from core import POLICY,compact,detect,ranked_candidate
TARGET=2700
ARMS={'B_CONTROL':(True,False,False),'C_HISTORY':(False,True,False),
      'BC':(True,True,False),'BC_IMPROVED':(True,True,False)}
LABELS={'B_CONTROL':'B CONTROL','C_HISTORY':'C HISTORY',
        'BC':'B+C','BC_IMPROVED':'B+C+改善'}
