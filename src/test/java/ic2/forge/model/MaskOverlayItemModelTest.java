package ic2.forge.model;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Collection;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Function;
import net.minecraft.client.renderer.texture.TextureAtlasSprite;
import net.minecraft.client.resources.model.BakedModel;
import net.minecraft.client.resources.model.Material;
import net.minecraft.client.resources.model.ModelBaker;
import net.minecraft.client.resources.model.ModelState;
import net.minecraft.client.resources.model.UnbakedModel;
import net.minecraft.resources.ResourceLocation;
import org.junit.jupiter.api.Test;

class MaskOverlayItemModelTest {
  @Test
  void resolvesBaseParentsBeforeBakingGeneratedItem() {
    ResourceLocation base = ResourceLocation.parse("ic2:item/obscurator_raw");
    AtomicBoolean resolved = new AtomicBoolean();
    UnbakedModel nested =
        new UnbakedModel() {
          @Override
          public Collection<ResourceLocation> getDependencies() {
            return List.of();
          }

          @Override
          public void resolveParents(Function<ResourceLocation, UnbakedModel> resolver) {
            resolved.set(true);
          }

          @Override
          public BakedModel bake(
              ModelBaker baker, Function<Material, TextureAtlasSprite> sprites, ModelState state) {
            return null;
          }
        };
    MaskOverlayItemModel model =
        new MaskOverlayItemModel(
            base, ResourceLocation.parse("ic2:item/tool/electric/obscurator_mask"), true, 0.001f);
    model.resolveParents(
        id -> {
          assertEquals(base, id);
          return nested;
        },
        null);
    assertTrue(resolved.get(), "nested generated model must resolve its parents before baking");
  }
}
