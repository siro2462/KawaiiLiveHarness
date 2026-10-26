from pathlib import Path
import re
from contract_runtime import validate
TEMPLATE=Path(__file__).with_name('surface_prompt_v3.txt').read_text(encoding='utf-8')
def render(row):
 validate(row)
 values=dict(history='\n\n'.join(f'[{i+1}] {x["text"]}' for i,x in enumerate(row['history'])) or 'なし',
  operation={'start':'話を始める','continue':'同じ出来事の続きを話す','related_shift':'関連する別の話題へ移る','topic_shift':'別の話題へ切り替える'}[row['operation']],
  relation_summary=row['relation']['summary'],facts='\n'.join(f'[{f["id"]}] {f["claim"]}' for f in row['facts']),
  flow=' → '.join(f'{s["label"]}（{", ".join(s["fact_ids"])}）' for s in row['flow']))
 assert all(TEMPLATE.count('{{'+k+'}}')==1 for k in values)
 return re.sub(r'\{\{(history|operation|relation_summary|facts|flow)\}\}',lambda m:values[m[1]],TEMPLATE)
