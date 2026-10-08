const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const path = require('node:path')

const heading = {
  copy() { return this },
  withStyle(color) { assert.equal(color, 'BLUE'); return this },
  equals(other) { return other?.text === 'section heading' && other?.color === 'BLUE' }
}
let listener
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../modpack/void-protocol/kubejs/client_scripts/creative_tooltips.js'), 'utf8'), {
  Java: { loadClass(name) {
    if (name.endsWith('.Sections')) return { get: id => id === 'loaded' ? { title: () => ({ text: () => heading }) } : null }
    if (name.endsWith('.SectionedItems')) return { sectionOf: item => item.section }
    if (name.endsWith('.ChatFormatting')) return { BLUE: 'BLUE' }
    return name
  } },
  NativeEvents: { onEvent(type, callback) {
    assert.equal(type, 'net.neoforged.neoforge.client.event.RenderTooltipEvent$GatherComponents')
    listener = callback
  } }
})
for (const section of ['loaded', 'missing', null]) {
  let rows = [{ text: 'item name' }, { text: 'section heading', color: 'BLUE' }, { text: '10 M/10 M EU' }, null, { text: 'section heading', color: 'GRAY' }]
  const original = rows.slice()
  listener({
    getItemStack: () => ({ getItem: () => ({ section }) }),
    getTooltipElements: () => ({ removeIf: predicate => { rows = rows.filter(row => !predicate({ left: () => ({ orElse: () => row }) })) } })
  })
  assert.deepEqual(rows, section === 'loaded' ? original.filter((_, i) => i !== 1) : original)
}
console.log('Creative tooltip filter: category removed; item details, custom components and unassigned items preserved.')
