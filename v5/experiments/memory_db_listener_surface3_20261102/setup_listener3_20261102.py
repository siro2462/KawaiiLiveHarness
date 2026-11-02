"""Create an isolated listener-cue overlay. No model load, inference or DB write."""
from pathlib import Path
import json,shutil,hashlib,ast

BETA=Path(__file__).resolve().parent
OLD=BETA/'runs/memory_db_compact_surface3_20261101_v1'
HIST=BETA/'runs/memory_db_historical_prompt3_20261101_v1'
R=BETA/'runs/memory_db_listener_surface3_20261102_v1'
def read(p):return json.loads(p.read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert not R.exists(),'New run only; never overwrite or restart'
cfg=read(OLD/'protocol.json');assert read(OLD/'technical_audit.json')['status']=='pass'
assert read(OLD/'completion.json')['status']=='complete'
R.mkdir();E=R/'executed_source'
for name in ['executed_source','reference']:shutil.copytree(OLD/name,R/name)
for name in ['requests','deliveries','turns','cpu_temp','root_read']:(R/name).mkdir()
for name in ['samples.json','cpu_selections.json','unit_schedule.json','meaning_legend.json','reaction_style.txt','grouping_style.txt','unit_instruction.txt']:shutil.copy2(OLD/name,R/name)
shutil.copy2(OLD/'review_packet.json',R/'baseline_packet.json')
shutil.copy2(OLD/'output_annotations.json',R/'baseline_annotations.json')
shutil.copy2(OLD/'executed_source/compact_surface.py',R/'reference/baseline_compact_surface.py')
shutil.copy2(HIST/'root_read/thin_views.py',R/'root_read/thin_views.py')
shutil.copy2(BETA/'listener_probe_cpu_20261102.py',E/'listener_probe_cpu.py')
shutil.copy2(HIST/'publication_authorization_proof.json',R/'publication_authorization_proof.json')
cue='''【リスナーに向けて語る】
あなたは雑談ライブ配信中のVTuberです。リスナーに向かって、今回の出来事や考えを今思い出しながら、気持ちを込めて自然に語る。
与えられた内容に合うときだけ、「え、これどういうこと？」「いや、待って」のような自問や、「これ、どう思う？」のような語りかけを使ってよい。毎区間に必ず入れる必要はない。
短い反応、少し長い説明、言い切り、問いかけを混ぜ、文の長さに変化をつける。
自問や語りかけのために、新しい疑念・感情・出来事を足さない。リスナーのコメント・返答・共有している視界・実際にはない既出の話を作らない。今回の操作の意味と確実性は変えない。
'''
(R/'listener_style.txt').write_text(cue,encoding='utf-8')
def change(name,old,new):
 p=E/name;s=p.read_text('utf-8-sig');assert s.count(old)==1,(name,old[:80]);p.write_text(s.replace(old,new),encoding='utf-8')
change('compact_surface.py'," prompt=PREFIX+style+instruction+'\\n'"," prompt=PREFIX+style+instruction+'\\n'+(OUT/'listener_style.txt').read_text('utf-8')")
change('preflight_cpu.py'," check('empty held'"," from listener_probe_cpu import run_probe\n run_probe(proc,check)\n check('empty held'")
change('observe_cpu.py','A saved current group4 11/B compact group4 new11; presentation format/legends/source timing change','A saved compact11 with oral examples/sentence target fixed; B new11 adds listener/self-question block only; equal-history payload identical')
p=E/'finalize_cpu.py';s=p.read_text('utf-8-sig')
for old,new in [
 ('同じCPU40操作・4操作ずつ：DB詳細入力 vs 短い入力','同じCPU40操作・4操作ずつ：口語版 vs 語りかけ追加版'),
 ('同一LoRA・Memory・CPU順序・口語few-shot・初期空履歴・seed・1536token等の生成条件。','同一LoRA・Memory・CPU順序・口語few-shot3・2〜3文目安・初期空履歴・履歴ルール・seed・1536token等の生成条件。今回の変更はリスナーへの語りかけ・自問・緩急のブロック追加だけ。200〜300字目安は追加しない。'),
 ('現行版：DB詳細入力・4操作ずつ','基準：口語few-shotあり・4操作ずつ'),
 ('今回：短い入力・4操作ずつ','今回：語りかけ・自問追加・4操作ずつ'),
 ('今回：短い入力・採用順全文','今回：語りかけ・自問追加・採用順全文'),
 ('A saved current group4','A saved compact oral group4'),('B new compact group4','B new listener cue group4'),
 ('短いSurface入力・3件比較','語りかけSurface・3件比較')]:
 assert old in s,old;s=s.replace(old,new)
p.write_text(s,encoding='utf-8')
core=['common.py','driver_cpu.py','processor_cpu.py','gpu_worker.py','request_protocol.py','token_journal.py','dependency_probe.py','startup_probe.py','launch_once.py','full_stripe_runtime.py','cpu_selector.py','flow_apply.py','runtime.py','run_cpu.py','stripe_runtime.py','prepare_inputs.py','report_presence.py']
assert all(sha(E/n)==sha(OLD/'executed_source'/n) for n in core)
cfg.update(experiment=R.name,created_jst='2026-11-02',source_run=str(OLD),baseline_run=str(OLD),
 only_manipulated_variable='append listener/self-question/rhythm cue block; baseline oral examples and sentence target retained unchanged',
 comparison_scope='saved compact11 versus new listener11; historical257 output is a separate prior condition, not baseline A',
 listener_style_sha256=sha(R/'listener_style.txt'),max_calls=11,max_new_model_calls=11,
 frozen_files=dict(cfg['frozen_files']))
write(R/'protocol.json',cfg)
write(R/'setup_manifest.json',dict(source_run=str(OLD),unchanged_core={n:sha(OLD/'executed_source'/n) for n in core},
 dependency_source=str(OLD/'executed_source/token_journal.py'),dependency_sha256=sha(OLD/'executed_source/token_journal.py'),
 inherited_frozen_files=cfg['frozen_files'],source_model_generation=0))
(R/'history_decision.md').write_text('''# 変更前の履歴照合と実験判断

最新registryのchat_progress_20261101_v8と関連台帳節、10/25 v2の保存結果と全4実出力、10/31口語復帰の結果節、10/27 H06 C全8発話、11/1共通指示257字比較を照合した。古い全実入力/RAWの意味再採点ではない。提示GitHubファイルは接続ツールで取得してローカル保存版との一致を別proofへ記録する。

v2は聞き手への語りかけ/自問/再評価を増やしたが、全部成功・未入力心理・共有視界・位置・架空既出を追加した。口語復帰はM06の短い惜しさ等に効果があるが、省略/測定手順/頻度強化を伴った。H06 C4操作は短いまとまりの実例だが、一括Bより総合優位とは未確定。直前257字復元は入力を減らしたのに4操作本文中央値122→160字、比較軸/希望時点に改善と説明調/反復が混在した。短い指示が常に自然という根拠はない。

今回はユーザー提案のうち、語りかけ/自問/文の緩急の追加だけを、直接反応3例のあるcompact4操作版と比較する。基準Aは最新257字版ではなく保存compact11。少数3素材M06/M17/M23、B新最大11call。元Memoryは変更せず、操作順・保留1・LoRA61例8更新・4操作区切り・seed20260925・全GenerationConfig1536・初期空履歴・採用実本文last2/800字を固定。3few-shotと2〜3文目安はA/Bとも固定し、200〜300字目安は追加しない。文数指示の別対照やMemory短縮は今回行わない。

期待：リスナーを意識した短い問いや共有、内容に即した自問が、感情を説明するだけの回想を減らす可能性を検査できる。v2全体や人間並みの再現を約束しない。追加ブロック内の役割/自問/語りかけ/緩急/未支持追加への注意の個別寄与は未分離。実生成後の下流履歴も分岐する。

CPU成功条件：旧11実入力を公式Processorで完全再構築、同一旧実履歴で新旧model_input_parts/テーマ以降bytesが一字一致、新promptから追加blockだけを除くと旧prompt完全一致、全decodedにblock/全操作/確実性/希望時点・未実行/口語例/文数目安が届く。履歴採用/保留/素材リセット/改変request拒否も既存検査を通す。CPU旧履歴は比較だけで本生成に先読みしない。

生成は初期空履歴から各条件の実本文を採用して次へ返す固定列の逐次実現。意味による次操作の再選択ではない。新規Planner/alpha自由想起/Guard/学習/DL/品質retry/TTS/配備/Memory登録なし。旧run/元DB/model/他process/GPU lockを変更停止削除せずサブエージェントなし。障害は保全し無検査再起動なし。起動後は15分短時間予約へ、常駐や終了待ちなし。

完了後は全元資料/旧新22実入力decoded/RAW/本文/履歴をroot全文レビュー。語りかけ・自問の内容妥当性/直接反応/緩急/説明調/反復/意味保持/確実性/未支持追加を分離し、予定色でなく実本文から手動FET。1seed/既知3素材/元記憶+創作補完/条件既知設計者AI・人間0/実TTS0。字数や問いの数だけを品質合格にしない。全文はローカル、専用GitHubへ汎用PGと新規抽象結果・数値・現在地だけpushする。
''',encoding='utf-8')
write(R/'publication_scope.json',dict(remote='https://github.com/siro2462/KawaiiLiveHarness.git',branch='codex/v5-current-20261023',
 public='generic code/instructions and newly authored abstract records/numbers only',private_local=['Memory','real inputs','decoded','RAW','generated full text','comparison HTML','source DB/model/chat']))
for p in E.glob('*.py'):ast.parse(p.read_text('utf-8-sig'))
print(json.dumps(dict(status='created_unlaunched',run=str(R),listener_chars=len(cue),source_Memory_bytes_exact=sha(R/'samples.json')==sha(OLD/'samples.json'),unchanged_core=len(core),new_model_calls=0)))
