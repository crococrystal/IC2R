// Edit item IDs and the tab icon in kubejs/config/ic2_creative.json.
var ic2CreativeLayout = JsonIO.read('kubejs/config/ic2_creative.json')
if (!ic2CreativeLayout || !ic2CreativeLayout.sections) {
  throw new Error('Missing kubejs/config/ic2_creative.json')
}

ModernTabs.setExampleTabEnabled(false)
ModernTabs.configureTab(ic2CreativeLayout.tab,
  new TabDesign().sectionsEnabled(true)
    .tabIconLocation('void_protocol:creative/mining_laser')
    .customTabTitel(new CustomTabTitel().dropShadow(false)))

var ic2CreativeOrder = {}
var ic2NextOrder = 0
var IC2TabVisibility = Java.loadClass('net.minecraft.world.item.CreativeModeTab$TabVisibility')
ic2CreativeLayout.sections.forEach(section => {
  section.items.forEach(id => {
    if (ic2CreativeOrder[id] !== undefined) throw new Error('Duplicate creative item: ' + id)
    ic2CreativeOrder[id] = ic2NextOrder++
    SectionedItems.addItemById(section.id, id)
  })
})

StartupEvents.modifyCreativeTab(ic2CreativeLayout.tab, event => {
  event.setIcon(Item.of(ic2CreativeLayout.icon))
  event.setDisplayName(Text.of(ic2CreativeLayout.title))
  var stacks = []
  event.removeFromParent(stack => {
    var rank = ic2CreativeOrder[String(stack.id)]
    stacks.push({ stack: stack, rank: rank === undefined ? ic2NextOrder : rank, index: stacks.length })
    return true
  })
  stacks.sort((a, b) => a.rank - b.rank || a.index - b.index)
  // Reuse every variant; search entries already exist and must not be added twice.
  event.add(stacks.map(entry => entry.stack), IC2TabVisibility.PARENT_TAB_ONLY)
})
console.info('[VOID Creative] Registered ' + ic2CreativeLayout.sections.length + ' IC2 sections; icon: ' + ic2CreativeLayout.icon)
