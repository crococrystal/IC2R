package ic2.core;

import ic2.core.proxy.EnvProxy;
import ic2.core.proxy.SideProxy;
import ic2.core.proxy.SideProxyClient;
import ic2.core.proxy.SideProxyServer;
import ic2.core.sound.SoundManager;
import ic2.core.util.Keyboard;
import ic2.core.util.Log;
import ic2.core.util.PriorityExecutor;
import ic2.core.util.SideGateway;
import ic2.forge.EnvProxyForge;
import net.minecraft.advancements.AdvancementHolder;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.util.RandomSource;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.CreativeModeTab;
import net.minecraft.world.level.Level;
import org.apache.logging.log4j.LogManager;

public class IC2 {
  public static final EnvProxy envProxy;
  public static final SideProxy sideProxy;
  public static final Log log;
  public static final SideGateway network;
  public static final Keyboard keyboard;
  public static final SoundManager soundManager;
  public static final CreativeModeTab tabIc2General;
  public static final CreativeModeTab tabIc2GeneratorsAndWiring;
  public static final CreativeModeTab tabIc2Reactor;
  public static final CreativeModeTab tabIc2Machines;
  public static final CreativeModeTab tabIc2ToolsAndUtilities;
  public static final CreativeModeTab tabIc2Combat;
  public static final CreativeModeTab tabIc2Farming;
  public static final CreativeModeTab tabIc2Materials;
  public static final PriorityExecutor threadPool;
  public static final RandomSource random;
  public static boolean initialized;
  public static boolean suddenlyHoes;
  public static boolean seasonal;

  static {
    envProxy = createEnvProxy();
    sideProxy = createSideProxy();
    log = new Log(LogManager.getLogger("ic2"));
    network = new SideGateway();
    keyboard = sideProxy.getKeyboard();
    soundManager = sideProxy.getSoundManager();
    tabIc2General =
        envProxy.createItemGroup(
            getIdentifier("general"),
            new ItemGroupIconSupplier(Ic2ItemGroupType.GENERAL),
            Ic2ItemGroupType.GENERAL);
    // Keep the public category fields compatible with addons while registering one tab.
    tabIc2GeneratorsAndWiring = tabIc2General;
    tabIc2Reactor = tabIc2General;
    tabIc2Machines = tabIc2General;
    tabIc2ToolsAndUtilities = tabIc2General;
    tabIc2Combat = tabIc2General;
    tabIc2Farming = tabIc2General;
    tabIc2Materials = tabIc2General;
    threadPool = new PriorityExecutor(Math.max(Runtime.getRuntime().availableProcessors(), 2));
    random = RandomSource.createNewThreadLocalInstance();
    initialized = false;
    suddenlyHoes = false;
    seasonal = false;
  }

  public static int getSeaLevel(Level world) {
    return world.getSeaLevel();
  }

  public static int getWorldMaxHeight(Level world) {
    return world.getHeight();
  }

  public static int getWorldMinHeight(Level world) {
    return world.getMinBuildHeight();
  }

  public static ResourceLocation getIdentifier(String name) {
    return ResourceLocation.fromNamespaceAndPath("ic2", name);
  }

  public static void grantAdvancement(Player player, String path) {
    if (player instanceof ServerPlayer sp) {
      AdvancementHolder adv =
          sp.server.getAdvancements().get(ResourceLocation.fromNamespaceAndPath("ic2", path));
      if (adv != null) {
        sp.getAdvancements().award(adv, "impossible");
      }
    }
  }

  private static EnvProxy createEnvProxy() {
    return new EnvProxyForge();
  }

  private static SideProxy createSideProxy() {
    return envProxy.isClientEnv() ? new SideProxyClient() : new SideProxyServer();
  }
}
