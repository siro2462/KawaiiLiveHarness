# Unresolved source lines in the memory graph

The generic patcher adds an unresolved presentation layer to the supplied standalone HTML template. It retains the original embedded text, curated topic/attribute mappings and demo routes. Full HTML/source and heading/line lists remain local. [Result](result.md) / [counts](numeric_summary.json).

The patcher applies exact checked substitutions, reads the adjacent JS/CSS and refuses to overwrite its input or an existing output. A different template fails rather than silently changing data. Example with local material:

```text
python patch_graph.py --input source.html --output updated.html
node test_graph.cjs updated.html audit.json
```

The Node test uses an offline DOM simulation. It is not a browser, layout or screenshot test. No new model, generation or memory database writes.
