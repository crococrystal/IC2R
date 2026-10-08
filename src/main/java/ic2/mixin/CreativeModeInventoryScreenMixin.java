package ic2.mixin;

import ic2.core.Ic2CreativeTab;
import java.util.Collection;
import net.minecraft.client.gui.screens.inventory.CreativeModeInventoryScreen;
import net.minecraft.world.item.CreativeModeTab;
import net.minecraft.world.item.ItemStack;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

@Mixin(CreativeModeInventoryScreen.class)
public class CreativeModeInventoryScreenMixin {
  @Redirect(
      method = {"selectTab", "tryRefreshInvalidatedTabs"},
      at =
          @At(
              value = "INVOKE",
              target =
                  "Lnet/minecraft/world/item/CreativeModeTab;getDisplayItems()Ljava/util/Collection;"))
  private Collection<ItemStack> ic2$groupedDisplayItems(CreativeModeTab tab) {
    // Reserve header rows only in this screen; JEI and other consumers need real stacks.
    return tab instanceof Ic2CreativeTab grouped
        ? grouped.getGroupedDisplayItems()
        : tab.getDisplayItems();
  }
}
