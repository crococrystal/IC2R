package ic2.core.gametest;

import com.mojang.authlib.GameProfile;
import ic2.core.IC2;
import ic2.core.entity.block.ITntEntity;
import ic2.core.entity.block.NukeEntity;
import ic2.core.item.ElectricItemManager;
import ic2.core.ref.Ic2Items;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import net.minecraft.ChatFormatting;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.contents.TranslatableContents;
import net.minecraft.server.level.ClientInformation;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.item.ItemStack;
import net.neoforged.neoforge.gametest.GameTestHolder;
import net.neoforged.neoforge.gametest.PrefixGameTestTemplate;

@GameTestHolder("ic2")
@PrefixGameTestTemplate(false)
public class TranslationGameTests {
  private static final String TEMPLATE = "gametest/empty3x3x3";

  // Primed ITNT/Nuke entities had no entity.ic2.* lang keys, so death screens and F3 showed the
  // raw translation key (upstream ebc73b78). NeoForge loads mod en_us on the server, so getName
  // must resolve to a real name here.
  @GameTest(template = TEMPLATE, timeoutTicks = 20)
  public static void primedExplosiveEntitiesHaveTranslatedNames(GameTestHelper helper) {
    Entity itnt = new ITntEntity(helper.getLevel(), 0.0, 0.0, 0.0);
    Entity nuke = new NukeEntity(helper.getLevel(), 0.0, 0.0, 0.0, 1.0F, 0);

    assertTranslated(helper, itnt, "entity.ic2.itnt");
    assertTranslated(helper, nuke, "entity.ic2.nuke");
    helper.succeed();
  }

  @GameTest(template = TEMPLATE, timeoutTicks = 20)
  public static void serverMessagesPreserveClientTranslations(GameTestHelper helper) {
    List<Component> messages = new ArrayList<>();
    ServerPlayer player =
        new ServerPlayer(
            helper.getLevel().getServer(),
            helper.getLevel(),
            new GameProfile(UUID.randomUUID(), "translation-test"),
            ClientInformation.createDefault()) {
          @Override
          public void displayClientMessage(Component message, boolean actionBar) {
            messages.add(message);
          }
        };
    Component mode = Component.translatable("ic2.tooltip.mode.normal");
    Component original =
        Component.translatable("ic2.tooltip.mode", mode).withStyle(ChatFormatting.YELLOW);
    IC2.sideProxy.messagePlayer(player, original);
    helper.assertTrue(
        messages.getLast() == original, "message must preserve its key, args and style");

    IC2.sideProxy.messagePlayer(player, "ic2.tooltip.mode", mode);
    assertMessageKey(helper, messages.getLast(), "ic2.tooltip.mode");
    helper.assertTrue(
        ((TranslatableContents) messages.getLast().getContents()).getArgs()[0] == mode,
        "nested translation arguments must remain components");

    player.setItemInHand(
        InteractionHand.MAIN_HAND,
        ElectricItemManager.getCharged(Ic2Items.WIND_METER, Double.POSITIVE_INFINITY));
    Ic2Items.WIND_METER.use(helper.getLevel(), player, InteractionHand.MAIN_HAND);
    assertMessageKey(helper, messages.getLast(), "ic2.wind_meter.info");

    player.setItemInHand(InteractionHand.MAIN_HAND, new ItemStack(Ic2Items.FOAM_SPRAYER));
    Ic2GameTestUtil.pressModeSwitchKey(player);
    try {
      Ic2Items.FOAM_SPRAYER.use(helper.getLevel(), player, InteractionHand.MAIN_HAND);
    } finally {
      Ic2GameTestUtil.releaseModeSwitchKey(player);
    }
    assertMessageKey(helper, messages.getLast(), "ic2.tooltip.mode");
    Object modeArg = ((TranslatableContents) messages.getLast().getContents()).getArgs()[0];
    helper.assertTrue(
        modeArg instanceof Component, "sprayer mode must be a translatable component");
    assertMessageKey(helper, (Component) modeArg, "ic2.tooltip.mode.single");
    helper.succeed();
  }

  private static void assertMessageKey(GameTestHelper helper, Component message, String key) {
    helper.assertTrue(
        message.getContents() instanceof TranslatableContents contents
            && contents.getKey().equals(key),
        "server must send translation key " + key + " for the client language");
  }

  private static void assertTranslated(GameTestHelper helper, Entity entity, String key) {
    String name = entity.getName().getString();
    helper.assertTrue(
        !name.isEmpty() && !name.equals(key),
        "entity name for " + key + " must be translated, got \"" + name + "\"");
  }
}
