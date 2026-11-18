// Keep the original nodes fixed. Place only the unresolved display nodes.
function nodeFootprint(node, radius) {
 const halfWidth = Math.max(radius + 12, Array.from(node.label).length * 6.5 + 8);
 return {left: node.x - halfWidth, right: node.x + halfWidth, top: node.y - radius - 12, bottom: node.y + radius + 29};
}
function enclose(rectangles, padding = 0) {
 return {
  left: Math.min(...rectangles.map(r => r.left)) - padding,
  right: Math.max(...rectangles.map(r => r.right)) + padding,
  top: Math.min(...rectangles.map(r => r.top)) - padding,
  bottom: Math.max(...rectangles.map(r => r.bottom)) + padding
 };
}
function overlaps(a, b) {
 return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}
function shift(rect, x, y) {
 return {left: rect.left + x, right: rect.right + x, top: rect.top + y, bottom: rect.bottom + y};
}
function placeAround(anchor, nodes, occupied) {
 const column = 112, row = 94;
 let placed = 0, ring = 0;
 // Search successive bands by distance, reserving room for circles and labels.
 while (placed < nodes.length) {
  ring++;
  const candidates = [];
  for (let j = -Math.ceil(ring * column / row); j <= Math.ceil(ring * column / row); j++) {
   for (let i = -ring; i <= ring; i++) {
    const x = i * column + (Math.abs(j) % 2) * column / 2, y = j * row;
    const distance = Math.hypot(x, y);
    if (distance > (ring - 1) * column && distance <= ring * column) candidates.push({x, y, distance});
   }
  }
  candidates.sort((a, b) => a.distance - b.distance || a.y - b.y || a.x - b.x);
  for (const candidate of candidates) {
   const node = nodes[placed];
   node.x = anchor.x + candidate.x;
   node.y = anchor.y + candidate.y;
   const footprint = nodeFootprint(node, 22);
   if (occupied.some(r => overlaps(r, footprint))) continue;
   occupied.push(footprint);
   placed++;
   if (placed === nodes.length) break;
  }
 }
}

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
   groups.set(parent, {parent, heading: row.cores.length ? null : heading, nodes: []});
  }
  const id = 'unresolved_L' + row.lineNo;
  const chars = Array.from(row.raw.trim());
  const label = chars.slice(0, 6).join('') + (chars.length > 6 ? '…' : '');
  const attr = {label, bridge, color: '#8190a8', unresolved: true, lineNo: row.lineNo, note: row.raw};
  attrs[id] = attr;
  groups.get(parent).nodes.push(attr);
  rowMappings.set(row.lineNo, {cores: bridge, attrs: [...row.attrs, id]});
 }

 const occupied = [
  ...Object.values(baseCores).map(node => nodeFootprint(node, 28)),
  ...Object.values(baseAttrs).map(node => nodeFootprint(node, 22))
 ];
 for (const group of groups.values()) {
  if (!group.heading) placeAround(cores[group.parent], group.nodes, occupied);
 }

 // Sections without a curated topic keep their own source heading. Spread those
 // groups around the map in transcript order, with room for each group's labels.
 const main = enclose(occupied, 55);
 const center = {x: (main.left + main.right) / 2, y: (main.top + main.bottom) / 2};
 const areas = [main];
 const headingGroups = [...groups.values()].filter(group => group.heading);
 headingGroups.forEach(({heading, nodes}, index) => {
  const anchor = {label: heading.label, x: 0, y: 0, color: '#8190a8', unresolved: true};
  const local = [nodeFootprint(anchor, 28)];
  placeAround(anchor, nodes, local);
  const footprint = enclose(local, 42);
  const angle = Math.PI * (.82 + 2 * index / headingGroups.length);
  let distance = 200;
  let x, y, area;
  do {
   x = Math.round(center.x + Math.cos(angle) * distance);
   y = Math.round(center.y + Math.sin(angle) * distance);
   area = shift(footprint, x, y);
   distance += 42;
  } while (areas.some(other => overlaps(area, other)));
  Object.assign(anchor, {x, y});
  cores[heading.id] = anchor;
  nodes.forEach(node => {node.x += x; node.y += y;});
  areas.push(area);
 });

 const frame = enclose([...areas, {left: 0, right: 1600, top: 0, bottom: 980}], 36);
 return {cores, attrs, rowMappings, bounds: {x: frame.left, y: frame.top, w: frame.right - frame.left, h: frame.bottom - frame.top}};
}
const inlineGraph = makeInlineGraph(cores, attrs, SOURCE_ROWS);
function graphCores() { return displayMode === 'source' ? inlineGraph.cores : cores; }
function graphAttrs() { return displayMode === 'source' ? inlineGraph.attrs : attrs; }
function sourceMapping(row) { return inlineGraph.rowMappings.get(row.lineNo) || row; }
function sceneBounds() { return displayMode === 'source' ? inlineGraph.bounds : {x: 0, y: 0, w: 1600, h: 980}; }
function clampToScene(x, y, w, h, bounds = sceneBounds()) {
 return {
  x: clamp(x, bounds.x, bounds.x + Math.max(0, bounds.w - w)),
  y: clamp(y, bounds.y, bounds.y + Math.max(0, bounds.h - h)), w, h
 };
}
