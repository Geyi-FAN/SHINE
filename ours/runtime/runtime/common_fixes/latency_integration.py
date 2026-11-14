"""Explicit experiment hooks around the existing single-owner bridge.

Frozen code is not edited. Only bootstrap call admission changes; the existing
runner still generates and validates plans, completion events and all actions.
"""

from __future__ import annotations

import ast
import copy
import time

import numpy as np
from bootstrap_evidence import BootstrapEvidence, EvidenceRow


def install(bridge_class) -> None:
    if getattr(bridge_class, "_t7_latency_installed", False):
        return
    original_hooks = bridge_class.install_hooks
    original_build = bridge_class.build_run_function

    def hooks(bridge):
        from unified.transport import install as install_private_transport

        install_private_transport()
        original_hooks(bridge)
        bridge.bootstrap_evidence = BootstrapEvidence()
        original_monitor = bridge.mon_class
        collector = original_monitor(
            history={}, settings=bridge.runner.Settings(confidence=0.35)
        )
        collector.arm = "P1"
        bridge.bootstrap_collector = collector

        def record(mon, points, camera):
            sample = mon.samples[-1]
            bridge.bootstrap_evidence.append(
                EvidenceRow(
                    episode=bridge.state.episode,
                    camera=camera,
                    frame=bridge.physics_steps,
                    captured_at=bridge.capture_monotonic,
                    width=sample["width"],
                    hand_xyz=sample["eef_xyz"],
                    hand_yx=sample["eef_yx"],
                    points={
                        (p["entity"], p["keypoint"]): dict(
                            p, frame=bridge.physics_steps
                        )
                        for p in points
                    },
                    geometry=copy.deepcopy(mon.geometry),
                    holding=copy.deepcopy(mon.diagnostics["holding"]),
                    snapshot=copy.deepcopy(mon.snapshot),
                )
            )

        def collect(main, wrist, geometry, eef, qpos, hand_yx, observed, camera):
            frame = bridge.physics_steps
            if collector.last >= frame:
                return
            fresh = [dict(point, frame=frame) for point in observed]
            collector.supply(frame, main, wrist, geometry)
            collector.observe(frame, eef, qpos, hand_yx, fresh)
            record(collector, fresh, camera)

        class ObservedMonitor(original_monitor):
            def observe(self, *args):
                result = super().observe(*args)
                if bridge.saved_points is not None:
                    bridge.saved_points.scene.observe_robot_state(self.snapshot,self.samples[-1],bridge.physics_steps)
                row = self.rgb_rows[-1]
                sample = self.samples[-1]
                collect(
                    row["main"],
                    row["wrist"],
                    self.geometry,
                    sample["eef_xyz"],
                    args[2],
                    sample["eef_yx"],
                    row.get("image_points", []),
                    bridge.saved_points.camera_id,
                )
                return result

        bridge.mon_class = ObservedMonitor
        original_points = bridge.runner.Points

        def point_factory(*args, **kwargs):
            points = original_points(*args, **kwargs)
            if getattr(points, "_bootstrap_tap_installed", False):
                return points
            previous = points.observe

            def observe(image, frame, time_source="current", camera_id=None):
                result = previous(image, frame, time_source, camera_id)
                # Reuse Native's already scheduled image detections. Never run a
                # second YOLO or read environment state from a background worker.
                if time_source == "current" and bridge.route == "native":
                    from depth_sensor import read_depth, sensed_geometry
                    from sym_geometry import project

                    eef = np.asarray(bridge.obs["robot0_eef_pos"])
                    hand_yx, valid = project(bridge.env.sim, eef)
                    depth, calibration = read_depth(bridge.env)
                    observed = list(points.current.values())
                    geometry = sensed_geometry(observed, depth, calibration)
                    collect(
                        bridge.runner.resize(image),
                        bridge.runner.resize(
                            np.ascontiguousarray(
                                bridge.obs["robot0_eye_in_hand_image"][::-1, ::-1]
                            )
                        ),
                        geometry,
                        eef.tolist(),
                        np.asarray(bridge.obs["robot0_gripper_qpos"]).tolist(),
                        hand_yx.tolist() if valid else None,
                        observed,
                        points.camera_id,
                    )
                return result

            points.observe = observe
            points._bootstrap_tap_installed = True
            return points

        bridge.runner.Points = point_factory

        def gate(mon, recovery, raw):
            width = float(np.abs(bridge.obs["robot0_gripper_qpos"]).sum())
            decision = bridge.bootstrap_evidence.decide(
                raw=raw,
                episode=bridge.state.episode,
                camera=bridge.saved_points.camera_id,
                frame=bridge.physics_steps,
                now=time.monotonic(),
                current_width=width,
                snapshot=mon.snapshot,
            )
            bridge.log(
                "bootstrap_evidence_decision", identity=list(bridge.token()), **decision
            )
            recovery.events.append(
                dict(frame=mon.last, event="bootstrap_evidence_decision", **decision)
            )
            if decision["facts"]:
                # Explicit planning estimates only. Never write a completed
                # event, a final-success flag or a missing point coordinate.
                mon.snapshot["held_object"] = "none"
                mon.held = "none"
                for entity, supported in decision["facts"]["supported"].items():
                    mon.snapshot["objects"][entity]["supported"] = supported
                relation = decision["facts"]["cheese_bowl"]
                if relation is not None:
                    mon.snapshot["native_goal_relations"]["cheese_bowl"] = relation
                mon.snapshot["bootstrap_observation_evidence"] = decision
            return decision["inspect"]

        bridge.bootstrap_gate = gate
        from pending_preparation import install as install_pending_preparation

        install_pending_preparation(bridge, bridge.state)

    def build(bridge):
        original_build(bridge)
        path = bridge.root / "generated_kernel.py"
        tree = ast.parse(path.read_text())
        count = 0
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "needs_inspection"
            ):
                node.value = ast.parse(
                    "T7_BOOTSTRAP_GATE(mon, recovery, result['raw_user_message'])",
                    mode="eval",
                ).body
                count += 1
        if count != 1:
            raise ValueError(
                "Expected exactly one bootstrap inspection extension point"
            )
        ast.fix_missing_locations(tree)
        namespace = dict(
            bridge.run_function.__globals__, T7_BOOTSTRAP_GATE=bridge.bootstrap_gate
        )
        exec(compile(tree, str(path), "exec"), namespace)
        bridge.run_function = namespace["run"]
        path.write_text(ast.unparse(tree) + "\n")

    bridge_class.install_hooks = hooks
    bridge_class.build_run_function = build
    bridge_class._t7_latency_installed = True
