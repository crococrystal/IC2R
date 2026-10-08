var TooltipSections = Java.loadClass('de.Roboter007.moderntabs.section.Sections')
var TooltipSectionedItems = Java.loadClass('de.Roboter007.moderntabs.section.item.SectionedItems')
var TooltipFormatting = Java.loadClass('net.minecraft.ChatFormatting')

// ModernTabs adds this after ItemTooltipEvent, so filter at the rendering event.
NativeEvents.onEvent(Java.loadClass('net.neoforged.neoforge.client.event.RenderTooltipEvent$GatherComponents'), event => {
  var sectionId = TooltipSectionedItems.sectionOf(event.getItemStack().getItem())
  if (sectionId === null) return
  var section = TooltipSections.get(sectionId)
  if (section === null) return
  // Rhino needs the exact signature to distinguish the enum and varargs overloads.
  var heading = section.title().text().copy()['withStyle(net.minecraft.ChatFormatting)'](TooltipFormatting.BLUE)
  event.getTooltipElements().removeIf(element => heading.equals(element.left().orElse(null)))
})
