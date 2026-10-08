package ic2.core.gametest;

import ic2.api.crops.CropCard;
import ic2.api.crops.Crops;
import ic2.api.item.ElectricItem;
import ic2.api.item.IElectricItem;
import ic2.core.IC2;
import ic2.core.Ic2ItemGroupType;
import ic2.core.item.BlockItemEnergyStorage;
import ic2.core.item.ItemCropSeed;
import ic2.core.item.armor.ItemArmorFluidTank;
import ic2.core.ref.Ic2Items;
import ic2.core.util.StackUtil;
import java.util.Collection;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.function.Supplier;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.world.item.CreativeModeTab;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.neoforged.neoforge.gametest.GameTestHolder;
import net.neoforged.neoforge.gametest.PrefixGameTestTemplate;

@GameTestHolder("ic2")
@PrefixGameTestTemplate(false)
public class CreativeTabGameTests {
  @GameTest(template = "gametest/empty3x3x3", timeoutTicks = 20)
  public static void singleTabPreservesEveryItemAndVariant(GameTestHelper helper) {
    CreativeModeTab tab = IC2.tabIc2General;
    long registeredTabs =
        BuiltInRegistries.CREATIVE_MODE_TAB.keySet().stream()
            .filter(id -> id.getNamespace().equals("ic2"))
            .count();
    helper.assertTrue(registeredTabs == 1, "IC2 must register exactly one creative tab");
    for (CreativeModeTab alias :
        List.of(
            IC2.tabIc2GeneratorsAndWiring,
            IC2.tabIc2Reactor,
            IC2.tabIc2Machines,
            IC2.tabIc2ToolsAndUtilities,
            IC2.tabIc2Combat,
            IC2.tabIc2Farming,
            IC2.tabIc2Materials)) {
      helper.assertTrue(alias == tab, "legacy category fields must refer to the single tab");
    }

    // Addons may list the same item in several categories; it must appear only once.
    Supplier<Item> duplicate = () -> Ic2Items.DIAMOND_DRILL;
    List<Supplier<Item>> farming = Ic2Items.CREATIVE_TAB_ITEMS.get(Ic2ItemGroupType.FARMING);
    farming.add(duplicate);
    try {
      tab.buildContents(
          new CreativeModeTab.ItemDisplayParameters(
              helper.getLevel().enabledFeatures(), true, helper.getLevel().registryAccess()));
    } finally {
      farming.remove(duplicate);
    }

    Collection<ItemStack> stacks = tab.getDisplayItems();
    helper.assertTrue(
        stacks.stream().noneMatch(ItemStack::isEmpty),
        "public creative inventory must expose only real items to JEI and other integrations");
    Set<Item> items = new HashSet<>();
    Ic2Items.CREATIVE_TAB_ITEMS
        .values()
        .forEach(category -> category.forEach(supplier -> items.add(supplier.get())));
    helper.assertTrue(items.size() == 502, "fork must preserve all 502 original creative items");
    int expectedStacks = items.size() + Crops.instance.getCrops().size();
    for (Item item : items) {
      assertContains(helper, stacks, new ItemStack(item));
      if (item instanceof IElectricItem electricItem) {
        expectedStacks++;
        helper.assertTrue(
            stacks.stream()
                .anyMatch(
                    stack ->
                        stack.is(item)
                            && ElectricItem.manager.getCharge(stack.copy())
                                == electricItem.getMaxCharge(stack)),
            "missing fully charged variant of " + BuiltInRegistries.ITEM.getKey(item));
      }
      if (item instanceof BlockItemEnergyStorage storage) {
        expectedStacks++;
        helper.assertTrue(
            stacks.stream()
                .anyMatch(
                    stack ->
                        stack.is(item)
                            && StackUtil.getTag(stack) != null
                            && StackUtil.getTag(stack).getDouble("energy") == storage.maxEnergy),
            "missing fully charged energy storage " + BuiltInRegistries.ITEM.getKey(item));
      }
      if (item instanceof ItemArmorFluidTank tank) {
        expectedStacks++;
        helper.assertTrue(
            stacks.stream()
                .anyMatch(stack -> stack.is(item) && tank.getCharge(stack) == tank.getMaxCharge()),
            "missing filled tank armor " + BuiltInRegistries.ITEM.getKey(item));
      }
    }
    for (CropCard crop : Crops.instance.getCrops()) {
      assertContains(helper, stacks, ItemCropSeed.generateItemStackFromValues(crop, 1, 1, 1, 4));
    }
    helper.assertTrue(
        stacks.size() == expectedStacks, "creative tab has missing or duplicate stacks");
    helper.assertTrue(
        tab.getClass() == CreativeModeTab.class,
        "IC2 must expose a standard flat tab; section rendering belongs to the modpack");
    helper.assertTrue(
        tab.getSearchTabDisplayItems().stream().noneMatch(ItemStack::isEmpty)
            && tab.getSearchTabDisplayItems().size() == expectedStacks,
        "search must preserve every real item and variant without separator stacks");
    tab.buildContents(
        new CreativeModeTab.ItemDisplayParameters(
            helper.getLevel().enabledFeatures(), true, helper.getLevel().registryAccess()));
    helper.assertTrue(
        tab.getDisplayItems().size() == expectedStacks,
        "rebuilding the flat tab must not accumulate item variants");
    helper.succeed();
  }

  private static void assertContains(
      GameTestHelper helper, Collection<ItemStack> stacks, ItemStack expected) {
    helper.assertTrue(
        stacks.stream().anyMatch(stack -> ItemStack.isSameItemSameComponents(stack, expected)),
        "missing creative item " + expected);
  }
}
