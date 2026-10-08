// Edit item IDs and the tab icon in kubejs/config/ic2_creative.json.
var ic2CreativeLayout = JsonIO.read('kubejs/config/ic2_creative.json')
if (!ic2CreativeLayout || !ic2CreativeLayout.sections) {
  throw new Error('Missing kubejs/config/ic2_creative.json')
}

ModernTabs.setExampleTabEnabled(false)
ModernTabs.configureTab(ic2CreativeLayout.tab,
  new TabDesign().sectionsEnabled(true))

ic2CreativeLayout.sections.forEach(section => {
  section.items.forEach(id => SectionedItems.addItemById(section.id, id))
})

StartupEvents.modifyCreativeTab(ic2CreativeLayout.tab, event => {
  event.setIcon(Item.of(ic2CreativeLayout.icon))
  event.setDisplayName(Text.of(ic2CreativeLayout.title))
})
console.info('[VOID Creative] Registered ' + ic2CreativeLayout.sections.length + ' IC2 sections; icon: ' + ic2CreativeLayout.icon)
