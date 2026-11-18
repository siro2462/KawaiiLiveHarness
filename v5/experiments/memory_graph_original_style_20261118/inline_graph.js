// Display-only additions. The supplied graph data and coordinates are reused as-is.
function makeInlineGraph(baseCores, baseAttrs, rows) {
 const cores = {...baseCores}, attrs = {...baseAttrs};
 const rowMappings = new Map(), groups = new Map();
 let heading;
 for (const row of rows) {
  if (!heading || row.kind === 'heading') {
   heading = {label: row.section || '見出しなし', id: 'unresolved_topic_L' + row.lineNo};
  }
  if (row.kind !== 'speech' || (row.cores.length && row.attrs.length)) continue;
  const bridge = row.cores.length ? [...row.cores] : [heading.id];
  const parent = bridge[0];
  if (!groups.has(parent)) {
   groups.set(parent, {entries: [], heading: row.cores.length ? null : heading});
  }
  groups.get(parent).entries.push({row, bridge});
 }

 const addedAreaX = 1710, columnWidth = 142, rowHeight = 105, availableWidth = 2900;
 let left = addedAreaX, top = 85, shelfHeight = 0, maxX = 1600, maxY = 980;
 // Place the rows attached to curated topics first, close to the original map.
 const ordered = [...groups.values()].sort((a, b) => Number(!!a.heading) - Number(!!b.heading));
 for (const {entries, heading} of ordered) {
  const columns = Math.min(20, Math.ceil(Math.sqrt(entries.length * 1.4)));
  const width = Math.max(320, columns * columnWidth + 28);
  const height = 160 + Math.ceil(entries.length / columns) * rowHeight;
  if (left + width > addedAreaX + availableWidth) {
   left = addedAreaX;
   top += shelfHeight + 45;
   shelfHeight = 0;
  }
  if (heading) {
   cores[heading.id] = {
    label: heading.label, x: left + width / 2, y: top, color: '#8190a8', unresolved: true
   };
  }
  entries.forEach(({row, bridge}, i) => {
   const id = 'unresolved_L' + row.lineNo;
   const chars = Array.from(row.raw.trim());
   const excerpt = chars.slice(0, 6).join('') + (chars.length > 6 ? '…' : '');
   attrs[id] = {
    label: excerpt, x: left + 70 + i % columns * columnWidth,
    y: top + 112 + Math.floor(i / columns) * rowHeight, bridge,
    color: '#8190a8', unresolved: true, lineNo: row.lineNo, note: row.raw
   };
   rowMappings.set(row.lineNo, {cores: bridge, attrs: [...row.attrs, id]});
  });
  maxX = Math.max(maxX, left + width + 80);
  maxY = Math.max(maxY, top + height);
  left += width + 30;
  shelfHeight = Math.max(shelfHeight, height);
 }
 return {cores, attrs, rowMappings, addedAreaX, bounds: {w: maxX, h: maxY}};
}
const inlineGraph = makeInlineGraph(cores, attrs, SOURCE_ROWS);
function graphCores() { return displayMode === 'source' ? inlineGraph.cores : cores; }
function graphAttrs() { return displayMode === 'source' ? inlineGraph.attrs : attrs; }
function sourceMapping(row) { return inlineGraph.rowMappings.get(row.lineNo) || row; }
function sceneBounds() { return displayMode === 'source' ? inlineGraph.bounds : {w: 1600, h: 980}; }
