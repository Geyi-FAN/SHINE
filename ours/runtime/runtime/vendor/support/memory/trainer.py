"""Native OpenPI full finetuning with masked tails and reproducible resume.

Checkpoint indices denote COMPLETED updates. Dataset update n always uses schedule[n].
The inference params item is EMA; raw params and optimizer are retained for resume.
"""
import argparse
import dataclasses
import functools
import faulthandler
import json
import logging
import importlib.metadata
from pathlib import Path
import sys
import signal
import os
import time

import flax.nnx as nnx
import jax
import jax.numpy as jnp
import numpy as np
import optax
import orbax.checkpoint as ocp

from openpi.models import model as model_lib
from openpi.training import checkpoints, sharding, optimizer, utils as training_utils

from common import OPENPI, ROOT, read_config, sha256, source_hashes, write_json
from dataset import P1Data
from model_config import make_config

sys.path.insert(0, str(OPENPI / "scripts"))
import train as native_train


def initialize(config, rng, mesh, resume):
    """Native train-state semantics, but shard incoming weights before initialization.

    Native OpenPI replicates all FP32 checkpoint weights on every GPU while building
    the sharded optimizer. That transient copy alone can overflow a 24 GiB card.
    Input sharding avoids it without changing parameters, optimizer or arithmetic.
    """
    tx = optimizer.create_optimizer(config.optimizer, config.lr_schedule, weight_decay_mask=None)

    def init(key, partial=None):
        _, model_key = jax.random.split(key)
        model = config.model.create(model_key)
        if partial is not None:
            graphdef, values = nnx.split(model)
            values.replace_by_pure_dict(partial)
            model = nnx.merge(graphdef, values)
        values = nnx.state(model)
        return training_utils.TrainState(step=0, params=values, model_def=nnx.graphdef(model), tx=tx,
                                         opt_state=tx.init(values.filter(config.trainable_filter)),
                                         ema_decay=config.ema_decay, ema_params=values)

    shape = jax.eval_shape(init, rng)
    layout = sharding.fsdp_sharding(shape, mesh, log=False)
    if resume:
        return shape, layout
    partial = native_train._load_weights_and_validate(config.weight_loader, shape.params.to_pure_dict())
    replicated = jax.sharding.NamedSharding(mesh, jax.sharding.PartitionSpec())
    state = jax.jit(init, donate_argnums=(1,),
                    in_shardings=(replicated, layout.params.to_pure_dict()),
                    out_shardings=layout)(rng, partial)
    return state, layout


def masked_anchor_loss(chunked_loss, valid):
    return (chunked_loss * valid).sum(axis=-1) / jnp.maximum(valid.sum(axis=-1), 1)


def update(config, rng, state, batch, micro_batch):
    model = nnx.merge(state.model_def, state.params)
    model.train()
    n_micro = config.batch_size // micro_batch
    train_rng = jax.random.fold_in(rng, state.step)

    def loss_fn(model, key, b):
        obs = model_lib.Observation.from_dict({k: v for k, v in b.items() if k not in ("actions", "valid", "revision")})
        losses = masked_anchor_loss(model.compute_loss(key, obs, b["actions"], train=True), b["valid"])
        rev = b["revision"].astype(jnp.float32)
        info = jnp.stack([losses.sum(), (losses * rev).sum(), rev.sum(),
                          (losses * (1 - rev)).sum(), (1 - rev).sum()])
        return losses.mean(), info

    grad_fn = nnx.value_and_grad(loss_fn, argnums=nnx.DiffState(0, config.trainable_filter), has_aux=True)
    if n_micro == 1:
        (_, sums), grads = grad_fn(model, train_rng, batch)
    else:
        chunks = jax.tree.map(lambda v: v.reshape(n_micro, micro_batch, *v.shape[1:]), batch)
        keys = jax.random.split(train_rng, n_micro)
        zeros = jax.tree.map(jnp.zeros_like, state.params.filter(config.trainable_filter))

        def micro_step(carry, inputs):
            grad_sum, infos = carry
            key, b = inputs
            (_, info), gs = grad_fn(model, key, b)
            grad_sum = jax.tree.map(lambda x, y: x + y / n_micro, grad_sum, gs)
            return (grad_sum, infos + info), None

        (grads, sums), _ = jax.lax.scan(micro_step, (zeros, jnp.zeros(5)), (keys, chunks))

    params = state.params.filter(config.trainable_filter)
    updates, opt_state = state.tx.update(grads, state.opt_state, params)
    new_params = optax.apply_updates(params, updates)
    nnx.update(model, new_params)
    new_params = nnx.state(model)
    ema = jax.tree.map(lambda old, new: old * state.ema_decay + new * (1 - state.ema_decay),
                       state.ema_params, new_params)
    state = dataclasses.replace(state, step=state.step + 1, params=new_params, opt_state=opt_state, ema_params=ema)
    return state, dict(loss=sums[0] / config.batch_size,
                       revision_loss=sums[1] / jnp.maximum(sums[2], 1),
                       normal_loss=sums[3] / jnp.maximum(sums[4], 1),
                       grad_norm=optax.global_norm(grads))


class AssetProvider:
    def __init__(self, config):
        self.config = config.data.create(config.assets_dirs, config.model)

    def data_config(self):
        return self.config


def memory_stats():
    return [{"device": str(d), **{k: int(v) for k, v in (d.memory_stats() or {}).items()
                                 if isinstance(v, (int, np.integer))}} for d in jax.local_devices()]


def parameter_probe(state):
    # Probe every parameter tensor, including vision, language and action modules.
    # Read a scalar from a LOCAL shard. Flattening a globally sharded tensor eagerly
    # can all-gather its entire embedding matrix just to inspect one element.
    return np.asarray([float(x.addressable_shards[0].data[(0,) * x.ndim])
                       for x in jax.tree.leaves(state.params)], dtype=np.float32)


def checkpoint_manager(directory, keep_period, resume):
    """Native checkpoint format, with bounded concurrent serialization memory."""
    if directory.exists() and not resume:
        raise FileExistsError(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manager = ocp.CheckpointManager(directory, item_handlers={
        "assets": checkpoints.CallbackHandler(),
        "train_state": ocp.PyTreeCheckpointHandler(save_concurrent_gb=4, restore_concurrent_gb=4),
        "params": ocp.PyTreeCheckpointHandler(save_concurrent_gb=4, restore_concurrent_gb=4),
    }, options=ocp.CheckpointManagerOptions(max_to_keep=2, keep_period=keep_period,
                create=False, async_options=ocp.AsyncOptions(timeout_secs=7200)))
    return manager, resume and manager.latest_step() is not None


def main():
    faulthandler.register(signal.SIGUSR1, all_threads=True)
    p = argparse.ArgumentParser()
    p.add_argument("--run-name", default=read_config()["experiment"])
    p.add_argument("--fsdp-devices", type=int, default=4)
    p.add_argument("--micro-batch", type=int, default=64)
    p.add_argument("--stop-after", type=int, help="Stop at this completed update; schedule horizon is unchanged")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--profile", action="store_true")
    p.add_argument("--check-update", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True)
    # Suppress verbose sharding leaf-by-leaf listings without changing the native init path.
    logging.getLogger("openpi.training.sharding").setLevel(logging.WARNING)
    cfg = make_config(args.run_name, args.fsdp_devices)
    if cfg.batch_size % args.micro_batch or args.micro_batch % jax.device_count():
        raise ValueError("Micro batch must divide global batch and be divisible by device count")
    if jax.device_count() != len(os.environ["CUDA_VISIBLE_DEVICES"].split(",")) or any(d.platform != "gpu" for d in jax.devices()):
        raise RuntimeError("Expected the requested CUDA devices; refusing CPU fallback or partial GPU initialization")
    data = P1Data()
    assert len(data.schedule) == cfg.num_train_steps
    from common import VARIANT
    from schema import ROOT as DATA_ROOT
    mesh = sharding.make_mesh(args.fsdp_devices)
    data_sharding = jax.sharding.NamedSharding(mesh, jax.sharding.PartitionSpec(sharding.DATA_AXIS))
    replicated = jax.sharding.NamedSharding(mesh, jax.sharding.PartitionSpec())
    jax.config.update("jax_compilation_cache_dir", str(ROOT / ".jax_cache"))
    run_dir = Path(cfg.checkpoint_dir)
    identity = dict(config_sha256=sha256(ROOT / "configs" / f"{VARIANT}.json"),
                    manifest_sha256=sha256(DATA_ROOT / "train/episodes.json"),
                    anchors_sha256=sha256(DATA_ROOT / "cache/anchors.npz"),
                    batches_sha256=sha256(DATA_ROOT / "cache/batches.npy"),
                    tokens_sha256=sha256(DATA_ROOT / "cache" / f"tokens_{VARIANT}.npy"),
                    token_mask_sha256=sha256(DATA_ROOT / "cache" / f"token_masks_{VARIANT}.npy"),
                    norm_sha256=data.preparation["norm_sha256"], source_sha256=source_hashes(),
                    initial_checkpoint=str(cfg.weight_loader.params_path),
                    variant=VARIANT, micro_batch=args.micro_batch, fsdp_devices=args.fsdp_devices,
                    device_count=jax.device_count(), seed=cfg.seed,
                    versions={name: importlib.metadata.version(name)
                              for name in ("jax", "jaxlib", "flax", "optax", "orbax-checkpoint", "numpy")})
    assert sha256(Path(read_config()['initial_checkpoint']) / 'assets/physical-intelligence/libero/norm_stats.json') == identity['norm_sha256']
    if args.resume:
        old = json.loads((run_dir / "identity.json").read_text())
        if old != identity:
            raise ValueError("Resume identity mismatch: config, code, dataset, seed or execution layout changed")
    # Orbax's replica-parallel host transfer slices replicated buffers through a
    # cached single-device JIT, which can dispatch to the wrong CUDA device with
    # JAX 0.5.3. Save one replica of each shard; checkpoint contents stay identical.
    ocp.type_handlers.register_type_handler(
        jax.Array, ocp.type_handlers.ArrayHandler(use_replica_parallel=False), override=True)
    manager, resuming = checkpoint_manager(run_dir, cfg.keep_period, args.resume)
    write_json(run_dir / "identity.json", identity)
    write_json(run_dir / "run_config.json", {**read_config(), "fsdp_devices": args.fsdp_devices,
                                             "micro_batch": args.micro_batch, "total_steps": cfg.num_train_steps,
                                             "steps_per_epoch": data.preparation["steps_per_epoch"]})
    assets = AssetProvider(cfg)
    train_rng, init_rng = jax.random.split(jax.random.key(cfg.seed))
    logging.info("Initializing FULL train state on %s; FSDP=%d; micro/global=%d/%d",
                 jax.devices(), args.fsdp_devices, args.micro_batch, cfg.batch_size)
    state, state_sharding = initialize(cfg, init_rng, mesh, resume=resuming)
    if resuming:
        state = checkpoints.restore_state(manager, state, assets)
        # Host-backed checkpoints are explicitly placed in the original layout.
        state = jax.device_put(state, state_sharding)
    jax.block_until_ready(state)
    n_params = sum(x.size for x in jax.tree.leaves(state.params))
    n_trainable = sum(x.size for x in jax.tree.leaves(state.params.filter(cfg.trainable_filter)))
    assert n_params == n_trainable, "P1 must be full finetuning"
    logging.info("Parameters: %s, trainable: %s", f"{n_params:,}", f"{n_trainable:,}")
    start = int(jax.device_get(state.step))
    if resuming:
        assert start == manager.latest_step(), "Completed-step/checkpoint mismatch"
    stop = min(args.stop_after or cfg.num_train_steps, cfg.num_train_steps)
    probe_before = parameter_probe(state) if args.check_update else None
    compiled = jax.jit(functools.partial(update, cfg, micro_batch=args.micro_batch),
                       in_shardings=(replicated, state_sharding, data_sharding),
                       out_shardings=(state_sharding, replicated), donate_argnums=(1,))
    metrics_file = ROOT / "logs" / f"{args.run_name}.jsonl"
    last_save = manager.latest_step()
    timings = []
    for step, host_batch in data.batches(start, stop):
        t0 = time.monotonic()
        batch = jax.tree.map(lambda x: jax.make_array_from_process_local_data(data_sharding, x), host_batch)
        with sharding.set_mesh(mesh):
            state, info = compiled(train_rng, state, batch)
        vals = {k: float(v) for k, v in jax.device_get(info).items()}
        elapsed = time.monotonic() - t0
        if not all(np.isfinite(v) for v in vals.values()):
            raise FloatingPointError(f"Nonfinite training metrics at update {step + 1}: {vals}")
        done = step + 1
        if step >= start + 5:
            timings.append(elapsed)
        record = dict(step=done, epoch=done / data.preparation["steps_per_epoch"],
                       seconds=elapsed, learning_rate=float(cfg.lr_schedule.create()(step)), **vals)
        with metrics_file.open("a") as f:
            f.write(json.dumps(record) + "\n")
        if done % cfg.log_interval == 0 or done == start + 1 or done == stop:
            rate = float(np.mean(timings[-100:])) if timings else None
            record["estimated_remaining_hours"] = (cfg.num_train_steps - done) * rate / 3600 if rate is not None else None
            record["status"] = "training"
            record["total_steps"] = cfg.num_train_steps
            record["memory"] = memory_stats()
            write_json(ROOT / "reports" / f"{args.run_name}_progress.json", record)
            logging.info("UPDATE %d/%d epoch=%.3f loss=%.6f rev=%.6f normal=%.6f seconds=%.3f ETA=%s",
                         done, cfg.num_train_steps, record["epoch"], vals["loss"], vals["revision_loss"],
                         vals["normal_loss"], elapsed, "warming_up" if rate is None else f"{record['estimated_remaining_hours']:.2f}h")
        save = done % cfg.save_interval == 0 or done % cfg.keep_period == 0 or done == stop
        if save and not args.profile:
            logging.info("Saving native shards with bounded serialization concurrency")
            checkpoints.save_state(manager, state, assets, done)
            # Sampling resumes from state.step, never from a prefetched loader cursor.
            manager.wait_until_finished()
            last_save = done
            logging.info("Checkpoint committed: %s", run_dir / str(done))
    if args.check_update:
        after = parameter_probe(state)
        changed = int(np.count_nonzero(after != probe_before))
        if changed == 0:
            raise AssertionError("No probed parameters changed")
        write_json(ROOT / "reports" / f"{args.run_name}_parameter_update.json",
                   dict(probed_tensors=len(after), changed_tensors=changed,
                        max_probe_change=float(np.max(np.abs(after - probe_before))),
                        total_parameters=n_params, trainable_parameters=n_trainable))
    result = dict(status="completed" if stop == cfg.num_train_steps else "short_run_completed",
                  completed_updates=stop, total_steps=cfg.num_train_steps,
                  checkpoint=str(run_dir / str(last_save)) if last_save is not None else None,
                  steady_step_seconds=float(np.mean(timings)) if timings else None,
                  memory=memory_stats(), trainable_parameters=n_trainable)
    write_json(ROOT / "reports" / f"{args.run_name}_finished.json", result)
    if stop == cfg.num_train_steps:
        write_json(run_dir / "COMPLETED.json", result)
    manager.close()
    logging.info("Finished: %s", result)


if __name__ == "__main__":
    main()
