# Saved speech comparison with edited VTuber references

Read-only comparison of two saved three-topic/twelve-call groups and five edited reference topics. The same model/adapter/complete generation configuration/seed/history rule is verified, while topics and selected sequences differ. No new inference is run.

[Abstract result](result.md) and [aggregate numeric definitions](numeric_summary.json). compare_cpu.py takes --run pointing to a local directory with comparison_inputs.json and findings.json. Those actual input payloads and the rendered full24-output HTML remain local.

The program computes defined counts, verifies original source hashes, reuses actual-output annotation spans only after exact body concatenation, and independently parses every saved body from the comparison HTML. It does not assign a human quality score.
