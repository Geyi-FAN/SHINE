"""Planning prerequisites from current sensors; never emits task completion.

The window contains fresh image predictions, RGB-D and robot measurements only.
It is distinct from M1: it cannot supply a missing coordinate or certify a goal.
"""

from __future__ import annotations

import copy
import math
import re
from collections import deque
from dataclasses import dataclass
from typing import TypedDict

OBJECTS = ("bowl", "cheese", "wine_bottle", "plate")


def distance(a: list[float] | None, b: list[float] | None) -> float:
    if a is None or b is None:
        return math.inf
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


class GateDecision(TypedDict):
    inspect: bool
    reasons: list[str]
    evidence_frames: list[int]
    source: str
    creates_completion: bool
    facts: dict


@dataclass(frozen=True)
class EvidenceRow:
    episode: str
    camera: str
    frame: int
    captured_at: float
    width: float
    hand_xyz: list[float]
    hand_yx: list[float] | None
    points: dict
    geometry: dict
    holding: dict
    snapshot: dict


class BootstrapEvidence:
    """A bounded, causal observation window, not a second execution state."""

    def __init__(self, confidence: float = 0.35) -> None:
        self.confidence = confidence
        self.rows: deque[EvidenceRow] = deque(maxlen=16)
        self.scope: tuple[str, str] | None = None

    def append(self, row: EvidenceRow) -> None:
        scope = (row.episode, row.camera)
        if scope != self.scope or (self.rows and row.frame < self.rows[-1].frame):
            self.rows.clear()
            self.scope = scope
        elif self.rows and row.frame == self.rows[-1].frame:
            self.rows.pop()
        self.rows.append(row)

    def fresh_point(self, row: EvidenceRow, entity: str, key: str) -> dict | None:
        point = row.points.get((entity, key))
        if point is None or point.get("source") != "yolo_image_only":
            return None
        if point.get("entity") != entity or point.get("keypoint") != key:
            return None
        if point.get("frame") != row.frame:
            return None
        confidence = min(
            point.get("det_confidence", 0), point.get("keypoint_confidence", 0)
        )
        yx = point.get("yx224")
        if confidence < self.confidence or not isinstance(yx, list) or len(yx) != 2:
            return None
        if not all(math.isfinite(v) and 0 <= v <= 223 for v in yx):
            return None
        return point

    def decide(
        self,
        *,
        raw: str,
        episode: str,
        camera: str,
        frame: int,
        now: float,
        current_width: float,
        snapshot: dict,
    ) -> GateDecision:
        """Missing/contradictory facts require inspection, never a guessed value."""
        needs_relations = bool(
            re.search(r"\b(?:leave|keep)\s+the\s+\w+\s+(?:inside|in)\b", raw, re.I)
        )
        bowl_and_cheese = bool(
            re.search(r"\bbowl\b", raw, re.I) and re.search(r"\bcheese\b", raw, re.I)
        )
        legacy_needed = (
            snapshot.get("held_object") == "unknown"
            or bowl_and_cheese
            or needs_relations
        )
        result = GateDecision(
            inspect=legacy_needed,
            reasons=[],
            evidence_frames=[],
            source="current_rgbd_proprio_planning_prerequisites_v1",
            creates_completion=False,
            facts={},
        )
        if not legacy_needed:
            result["reasons"] = ["existing_path_does_not_require_bootstrap_inspection"]
            return result
        # Keep/leave containment is semantic. This optimization does not invent
        # the missing visual relation or bypass that existing inspection.
        if needs_relations:
            result["reasons"] = ["requested_containment_requires_visual_relation"]
            return result
        rows = list(self.rows)[-4:]
        reasons = result["reasons"]
        if self.scope != (episode, camera):
            reasons.append("episode_or_camera_mismatch")
        if len(rows) != 4:
            reasons.append("insufficient_observation_window")
        if reasons:
            return result
        last = rows[-1]
        if (
            frame - last.frame not in range(0, 5)
            or not 0 <= now - last.captured_at <= 1.5
        ):
            reasons.append("stale_observation")
        if rows[-1].frame - rows[0].frame < 9 or any(
            b.frame - a.frame > 4 for a, b in zip(rows, rows[1:])
        ):
            reasons.append("non_continuous_observation_window")
        if not math.isfinite(current_width) or current_width < 0.065:
            reasons.append("current_fingers_not_open")
        if any(
            not math.isfinite(row.width) or row.width < 0.065 or row.hand_yx is None
            for row in rows
        ):
            reasons.append("open_hand_not_sustained")
        if any(
            len(row.hand_xyz) != 3
            or not all(math.isfinite(v) for v in row.hand_xyz)
            or (
                row.hand_yx is not None
                and not all(math.isfinite(v) for v in row.hand_yx)
            )
            for row in rows
        ):
            reasons.append("invalid_robot_measurement")
        if snapshot.get("held_object") not in ("none", "unknown"):
            reasons.append("currently_held_object_conflicts")
        if any(row.holding.get("held") != "none" for row in rows):
            reasons.append("ownership_estimate_not_consistently_empty")
        if reasons:
            return result
        stable = {}
        for entity in OBJECTS:
            points = [self.fresh_point(row, entity, "K1") for row in rows]
            xyz = [row.geometry.get(entity + ".K1") for row in rows]
            if any(point is None for point in points) or any(
                value is None for value in xyz
            ):
                reasons.append("missing_fresh_point_or_depth:" + entity)
                continue
            points = [point for point in points if point is not None]
            xyz = [value for value in xyz if value is not None]
            if any(
                len(value) != 3 or not all(math.isfinite(v) for v in value)
                for value in xyz
            ):
                reasons.append("invalid_depth_geometry:" + entity)
                continue
            yx = [point["yx224"] for point in points]
            stationary = max(distance(a, b) for a in yx for b in yx) <= 3.0
            stationary = (
                stationary and max(distance(a, b) for a in xyz for b in xyz) <= 0.015
            )
            support = all(
                row.snapshot.get("objects", {}).get(entity, {}).get("supported") is True
                for row in rows
            )
            stable[entity] = stationary and support
            if not stable[entity]:
                reasons.append("support_or_stability_unknown:" + entity)
            distances = [distance(row.hand_xyz, value) for row, value in zip(rows, xyz)]
            pixels = [distance(row.hand_yx, point) for row, point in zip(rows, yx)]
            # Retain the original strict clearance for an ownership fast path.
            # A new release witness may be added only after separate validation;
            # an open gripper or old final-success badge is not that witness.
            if min(distances) < 0.12 or min(pixels) < 40:
                reasons.append("ownership_clearance_not_proven:" + entity)
        if max(distance(a.hand_xyz, b.hand_xyz) for a in rows for b in rows) > 0.015:
            reasons.append("hand_moving_during_prerequisite_window")
        if bowl_and_cheese:
            if self.fresh_point(last, "bowl", "K3") is None:
                reasons.append("missing_current_bowl_destination")
            relation = last.snapshot.get("native_goal_relations", {}).get("cheese_bowl")
            if relation is not False:
                reasons.append("cheese_containment_not_unambiguously_outside")
        if reasons:
            return result
        result.update(
            inspect=False,
            reasons=["fresh_complete_prerequisites"],
            evidence_frames=[row.frame for row in rows],
            facts=dict(
                held_object="none",
                supported=stable,
                cheese_bowl=False if bowl_and_cheese else None,
            ),
        )
        return result

    def export_rows(self) -> list[EvidenceRow]:
        return copy.deepcopy(list(self.rows))
