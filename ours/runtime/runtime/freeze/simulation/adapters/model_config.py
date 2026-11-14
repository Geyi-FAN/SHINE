import dataclasses
from pathlib import Path
import os

from openpi.models import pi0_config
from openpi.training import config, optimizer, weight_loaders

from common import ROOT, read_config
from reference_model import ReferencePi0Config
from reference_inputs import ReferenceLiberoDataConfig


def make_config(run_name, fsdp_devices=4):
    c = read_config()
    steps_epoch = c["total_steps"]
    base = config.get_config("pi05_libero")
    data = ReferenceLiberoDataConfig(**{f.name: getattr(base.data, f.name)
                                     for f in dataclasses.fields(base.data)})
    if not c["historical_input"]:
        data = base.data
    data = dataclasses.replace(data, assets=config.AssetsConfig(
        assets_dir=str(Path(c["initial_checkpoint"]) / "assets"), asset_id=c["asset_id"]))
    return dataclasses.replace(
        base, name="pi05_memory_ad", exp_name=run_name,
        model=ReferencePi0Config(pi05=True, action_dim=c["action_dim"], action_horizon=c["action_horizon"],
                                  max_token_len=c["max_token_len"], discrete_state_input=c["discrete_state_input"]),
        data=data, weight_loader=weight_loaders.CheckpointWeightLoader(str(Path(c["initial_checkpoint"]) / "params")),
        batch_size=c["batch_size"], num_train_steps=c["total_steps"], seed=c["seed"],
        lr_schedule=optimizer.CosineDecaySchedule(warmup_steps=c["warmup_steps"], peak_lr=c["peak_lr"],
                                                 decay_steps=c["lr_schedule_steps"], decay_lr=c["end_lr"]),
        optimizer=optimizer.AdamW(clip_gradient_norm=c["gradient_clip"], weight_decay=c["weight_decay"]),
        ema_decay=c["ema_decay"], fsdp_devices=fsdp_devices, wandb_enabled=False,
        checkpoint_base_dir=os.environ.get("CHECKPOINT_ROOT", str(ROOT / "checkpoints")), assets_base_dir=str(ROOT / "assets"),
        keep_period=steps_epoch, save_interval=c["save_interval"], log_interval=c["log_interval"],
        policy_metadata={"experiment": run_name, "input": c["input"], "history": c["historical_input"],
                         "discrete_state_input": True, "state_dimension": 8,
                         "variant": c["variant"], "GT": c["ground_truth"],
                         "reference": c["reference_image"], "reference_slot": "right_wrist_0_rgb",
                         "required_reference_key": "observation/initial_image"},
    )
