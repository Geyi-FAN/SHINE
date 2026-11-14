import dataclasses
import os
from pathlib import Path
from openpi.models import pi0_config
from openpi.training import config,optimizer,weight_loaders
from common import ROOT,read_config
from sym_paths import STORAGE

def make_config(run_name,fsdp_devices=4):
    c=read_config();base=config.get_config('pi05_libero')
    data=dataclasses.replace(base.data,assets=config.AssetsConfig(
        assets_dir=str(Path(c['initial_checkpoint'])/'assets'),asset_id=c['asset_id']))
    return dataclasses.replace(base,name='pi05_symbolic_v3r',exp_name=run_name,
        model=pi0_config.Pi0Config(pi05=True,action_dim=32,action_horizon=10,
                                  max_token_len=200,discrete_state_input=True),
        data=data,weight_loader=weight_loaders.CheckpointWeightLoader(str(Path(c['initial_checkpoint'])/'params')),
        batch_size=c['batch_size'],num_train_steps=c['total_steps'],seed=c['seed'],
        lr_schedule=optimizer.CosineDecaySchedule(warmup_steps=c['warmup_steps'],peak_lr=c['peak_lr'],
            decay_steps=c['lr_schedule_steps'],decay_lr=c['end_lr']),
        optimizer=optimizer.AdamW(clip_gradient_norm=c['gradient_clip'],weight_decay=c['weight_decay']),
        ema_decay=c['ema_decay'],fsdp_devices=fsdp_devices,wandb_enabled=False,
        checkpoint_base_dir=os.environ.get('CHECKPOINT_ROOT',str(STORAGE/'checkpoints')),
        assets_base_dir=str(ROOT/'assets'),keep_period=2809,save_interval=c['save_interval'],
        log_interval=c['log_interval'],policy_metadata=dict(variant=c['variant'],GT=True,
            oracle_subgoal=c['variant'] in ('E3','V3R'),history_image=False,state_dimension=8))

