package ic2.core;

import ic2.core.ref.Ic2Items;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import net.minecraft.world.item.CreativeModeTab;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;

public final class Ic2CreativeTab extends CreativeModeTab {
  private List<ItemStack> groupedDisplayItems = List.of();
  private Map<Integer, Ic2ItemGroupType> headerRows = Map.of();

  public Ic2CreativeTab(Builder builder) {
    super(builder);
  }

  @Override
  public void buildContents(ItemDisplayParameters parameters) {
    super.buildContents(parameters);
    Map<Item, Ic2ItemGroupType> itemGroups = new HashMap<>();
    Ic2Items.CREATIVE_TAB_ITEMS.forEach(
        (group, items) -> items.forEach(item -> itemGroups.putIfAbsent(item.get(), group)));
    EnumMap<Ic2ItemGroupType, List<ItemStack>> sections = new EnumMap<>(Ic2ItemGroupType.class);
    for (ItemStack stack : super.getDisplayItems()) {
      sections
          .computeIfAbsent(
              itemGroups.getOrDefault(stack.getItem(), Ic2ItemGroupType.GENERAL),
              group -> new ArrayList<>())
          .add(stack);
    }

    List<ItemStack> display = new ArrayList<>();
    Map<Integer, Ic2ItemGroupType> headers = new LinkedHashMap<>();
    sections.forEach(
        (group, stacks) -> {
          headers.put(display.size() / 9, group);
          // Empty slots reserve a full header row without adding obtainable separator items.
          display.addAll(Collections.nCopies(9, ItemStack.EMPTY));
          display.addAll(stacks);
          display.addAll(Collections.nCopies((9 - display.size() % 9) % 9, ItemStack.EMPTY));
        });
    groupedDisplayItems = List.copyOf(display);
    headerRows = Collections.unmodifiableMap(headers);
  }

  public List<ItemStack> getGroupedDisplayItems() {
    return groupedDisplayItems;
  }

  public Map<Integer, Ic2ItemGroupType> getHeaderRows() {
    return headerRows;
  }

  public int getFirstVisibleRow(List<ItemStack> visible) {
    for (int slot = 0; slot < visible.size(); slot++) {
      ItemStack stack = visible.get(slot);
      if (!stack.isEmpty()) {
        int index = groupedDisplayItems.indexOf(stack);
        int offset = index - slot;
        return index >= 0 && offset >= 0 && offset % 9 == 0 ? offset / 9 : -1;
      }
    }
    return -1;
  }
}
