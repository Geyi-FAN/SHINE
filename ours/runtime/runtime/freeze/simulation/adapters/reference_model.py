"""Use the existing third image slot for a fixed episode-initial main view.

Parameter paths, flow matching, noise/time RNG, and inference remain native Pi0.
Only the added reference gets main-camera augmentation rather than wrist-camera
augmentation. No global OpenPI patches are used, so experiment A is unaffected.
"""
import dataclasses

from flax import nnx
import jax

from openpi.models import model as model_lib, pi0, pi0_config

REFERENCE_SLOT = "right_wrist_0_rgb"
REFERENCE_SEMANTIC_KEY = "episode_initial_base_rgb"


def preprocess_reference(rng, observation, *, train=False):
    images = dict(observation.images)
    masks = dict(observation.image_masks)
    images[REFERENCE_SEMANTIC_KEY] = images.pop(REFERENCE_SLOT)
    masks[REFERENCE_SEMANTIC_KEY] = masks.pop(REFERENCE_SLOT)
    semantic = dataclasses.replace(observation, images=images, image_masks=masks)
    processed = model_lib.preprocess_observation(
        rng, semantic, train=train,
        image_keys=("base_0_rgb", "left_wrist_0_rgb", REFERENCE_SEMANTIC_KEY),
    )
    # Main and reference use the same official transform chain and per-sample RNG.
    # Current main/wrist transforms therefore remain exactly those of experiment A.
    images = dict(processed.images)
    masks = dict(processed.image_masks)
    images[REFERENCE_SLOT] = images.pop(REFERENCE_SEMANTIC_KEY)
    masks[REFERENCE_SLOT] = masks.pop(REFERENCE_SEMANTIC_KEY)
    return dataclasses.replace(processed, images=images, image_masks=masks)


class ReferencePi0(pi0.Pi0):
    def compute_loss(self, rng, observation, actions, *, train=False):
        preprocess_rng = jax.random.split(rng, 3)[0]
        observation = preprocess_reference(preprocess_rng, observation, train=train)
        # Native loss uses the SAME noise/time RNG. train=False only suppresses
        # its already-applied image augmentation; model.train() is unchanged.
        return super().compute_loss(rng, observation, actions, train=False)


@dataclasses.dataclass(frozen=True)
class ReferencePi0Config(pi0_config.Pi0Config):
    def create(self, rng):
        return ReferencePi0(self, rngs=nnx.Rngs(rng))
