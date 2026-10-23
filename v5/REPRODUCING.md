# 保存内容と復元条件

## CPUでこのスナップショットを確認する

```powershell
python -X utf8 -B v5/tools/verify_snapshot.py
python -X utf8 -B v5/tools/test_snapshot.py -v
```

ソースSHA/構文、保存された実履歴、単回提示、Flow依存順、JSON不正の拒否、DONE終端を標準ライブラリで確認する。生成品質試験や元環境のCPU251チェックの再実行ではない。

元のコードと直接照合する場合は `verify_snapshot.py --source-talk C:/NodeJS/KawaiiLive/work/astra/_talk` を使う。`SOURCE_MANIFEST.json`のsource-byte-preserving対象だけ元ソースSHAも検査する。

## 実行時の配置

今回のpushでは新規学習・GPU推論・環境インストールをしない。次は復元時の配置説明であり、自動的に起動する手順ではない。

1. `_talk/lora_v4_gemma_runtime/`と`_talk/lora_v4_multibase/`等は参照元と同じ相対階層に置く。
2. `v5/runtime/`は元runの`harness_beta/runs/current_continuous10_20261023_v1/executed_source/`のソースをbyte単位で保存している。実行用の新runを`_talk/harness_beta/runs/<new-name>/`として用意し、`executed_source/`へコピーする構造。
3. `common.py`は`ZIP_INCREMENTAL_RUN`からBETA/TALK/MULTI/GEMMAを解決する。PYTHONPATHには新run/executed_source、harness_beta、lora_v4_multibase、lora_v4_gemma_runtimeが必要。PowerShell7/UTF8、Python `-X utf8 -B`。
4. 元の`protocol.json`は全条件と外部430ファイルの絶対パスSHAを保持する凍結記録で、ローカルに保全されている。公開`PROTOCOL.json`/`MODELS.json`は条件記録であり、そのまま実行用protocolに差し替えるファイルではない。外部資産の配置と検査が必要。
5. Alpha.populateは合成fixtureに加えて元のreference ZIPも読む。その`v1_2.zip`は非公開外部資料で、このrepoには含めない。発話対象はfixtures namespaceだけで、reference由来を本人の確定Memoryへ昇格させない。
6. CPU公式Processorは元環境のCPU専用torchを使用し、GPU workerは既存ROCm環境を使用する。`prepare_cpu.py`の公式Processor/実起動検査を通るまでGPUを起動しない。これは外部モデル資産を必要とするためcloneだけでは動かない。
7. 元の入口は`run_cpu.py`。`driver_cpu.py`には継承した旧比較用mainも残るが、現行ではDriverクラスだけを利用する。旧mainは現行連続版の入口ではない。

モデルとadapterの配置・SHAは`MODELS.json`。モデル本体/LoRA/tokenizer/NF4 cache/元教師・配信ZIP/SQLite DB/依存パッケージ/環境や認証情報は含めていない。

## ソースを保存した時点

`v5/runtime/run_cpu.py`は不正Planで実験全体を止める既知の動作を含む。次回実行を成功させた変更や、長尺品質が保証された版ではない。保存した過去runをその場で修正したり、失敗を完了と書き換える処理はない。
