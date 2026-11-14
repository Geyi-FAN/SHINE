"""Inference adapter: callers must supply the frozen initial main image."""
import dataclasses

import numpy as np
from openpi import transforms
from openpi.policies import libero_policy
from openpi.training import config

from reference_model import REFERENCE_SLOT


@dataclasses.dataclass(frozen=True)
class ReferenceInputs(transforms.DataTransformFn):
    model_type: object

    def __call__(self, data):
        if "observation/initial_image" not in data:
            raise ValueError("Missing fixed episode-initial main image: observation/initial_image")
        inputs = libero_policy.LiberoInputs(self.model_type)(data)
        reference = libero_policy._parse_image(data["observation/initial_image"])
        if reference.dtype != np.uint8 or reference.ndim != 3 or reference.shape[-1] != 3:
            raise ValueError("initial_image must be an RGB image")
        inputs["image"][REFERENCE_SLOT] = reference
        inputs["image_mask"][REFERENCE_SLOT] = np.True_
        return inputs


@dataclasses.dataclass(frozen=True)
class ReferenceLiberoDataConfig(config.LeRobotLiberoDataConfig):
    def create(self, assets_dirs, model_config):
        native = super().create(assets_dirs, model_config)
        return dataclasses.replace(native, data_transforms=transforms.Group(
            inputs=[ReferenceInputs(model_config.model_type)],
            outputs=native.data_transforms.outputs,
        ))
