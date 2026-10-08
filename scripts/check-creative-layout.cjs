const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const root = path.resolve(__dirname, '..')
const pack = path.join(root, 'modpack/void-protocol/kubejs')
const layout = JSON.parse(fs.readFileSync(path.join(pack, 'config/ic2_creative.json'), 'utf8'))
const ids = layout.sections.flatMap(section => section.items)
assert.equal(ids.length, 502)
assert.equal(new Set(ids).size, ids.length)
const groups = Object.fromEntries(layout.sections.map(section => [section.id, section.items]))
assert.equal(layout.sections.length, 11)
assert.deepEqual(groups['void_protocol:ic2_upgrades'], ids.filter(id => id.endsWith('_upgrade')))
assert.equal(groups['void_protocol:ic2_reactor_blocks'].length, 8)
assert.equal(groups['void_protocol:ic2_reactor'].length, 36)
assert(groups['void_protocol:ic2_machines'].includes('ic2:tank'))
assert(groups['void_protocol:ic2_machines'].includes('ic2:iridium_tank'))
assert(!groups['void_protocol:ic2_general'].some(id => id.endsWith('tank')))
for (const [priority, section] of layout.sections.entries()) {
  const design = JSON.parse(fs.readFileSync(path.join(pack, 'assets/void_protocol/moderntabs/sections', section.id.split(':')[1] + '.json'), 'utf8'))
  assert.equal(design.priority, priority)
  assert.equal(design.title.text.extra.find(part => part.translate).bold, false)
  assert.equal(design.title.text.extra[1].font, 'void_protocol:creative_icons', 'Icon precedes the title')
  assert(design.title.text.extra.at(-1).translate, 'Title follows the icon')
  assert.equal(design.title.color, design.title.secondary_color)
}
const font = JSON.parse(fs.readFileSync(path.join(pack, 'assets/void_protocol/font/creative_icons.json'), 'utf8'))
assert.equal(5 + font.providers[0].advances['\uE000'], 0, 'Cancel ModernTabs built-in left inset')
for (const provider of font.providers.filter(provider => provider.file)) {
  const [namespace, texture] = provider.file.split(':')
  assert(fs.existsSync(path.join(root, 'src/main/resources/assets', namespace, 'textures', texture)))
}

const source = fs.readFileSync(path.join(pack, 'startup_scripts/ic2_creative.js'), 'utf8')
let callback
let assigned = 0
let tabDesign
vm.runInNewContext(source, {
  JsonIO: { read: () => layout },
  Java: { loadClass: name => {
    assert.equal(name, 'net.minecraft.world.item.CreativeModeTab$TabVisibility')
    return { PARENT_TAB_ONLY: 'parent only' }
  } },
  ModernTabs: { setExampleTabEnabled() {}, configureTab(tab, design) { tabDesign = design } },
  TabDesign: function () {
    this.sectionsEnabled = () => this
    this.tabIconLocation = sprite => { this.sprite = sprite; return this }
    this.customTabTitel = title => { this.title = title; return this }
  },
  CustomTabTitel: function () { this.dropShadow = shadow => { this.shadow = shadow; return this } },
  SectionedItems: { addItemById() { assigned++ } },
  StartupEvents: { modifyCreativeTab(tab, listener) { assert.equal(tab, layout.tab); callback = listener } },
  Item: { of: id => id }, Text: { of: text => text }, console: { info() {} }
})
assert.equal(assigned, 502)
assert.equal(tabDesign.sprite, 'void_protocol:creative/mining_laser')
assert.equal(tabDesign.title.shadow, false)
assert.deepEqual(fs.readFileSync(path.join(pack, 'assets/void_protocol/textures/gui/sprites/creative/mining_laser.png')),
  fs.readFileSync(path.join(root, 'src/main/resources/assets/ic2/textures/item/tool/electric/mining_laser.png')))
let stacks = [{ id: 'other:unknown_a' }, { id: ids.at(-1) }, { id: ids[0], charge: 0 }, { id: ids[0], charge: 100 }, { id: ids[1] }, { id: 'other:unknown_b' }]
const originals = stacks.slice()
const search = stacks.slice()
const event = {
  setIcon() {}, setDisplayName(title) {
    assert.equal(title.bold, false)
    assert.equal(title.extra[0].text, '\uE010')
    assert.equal(title.extra[0].color, '#FFFFFF')
    assert.equal(title.extra[1].text, '\uE001')
    assert.equal(title.extra[2].text, layout.title)
  },
  removeFromParent(predicate) { stacks = stacks.filter(stack => !predicate(stack)) },
  add(values, visibility) {
    assert.equal(visibility, 'parent only', 'Search already contains these variants')
    stacks.push(...values)
  }
}
callback(event)
const expected = [originals[2], originals[3], originals[4], originals[1], originals[0], originals[5]]
assert.deepEqual(stacks, expected)
assert.deepEqual(search, originals)
callback(event)
assert.deepEqual(stacks, expected, 'Repeated creative rebuild must preserve the same variants and order')
console.log('Creative layout: 502 unique IDs, 11 sections; ordered variants and search entries preserved.')
