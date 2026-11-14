"""Sensor admission counterexamples; no models, network or robot actions."""

import copy
import unittest

from bootstrap_evidence import OBJECTS, BootstrapEvidence, EvidenceRow


def observation(frame):
    points = {}
    geometry = {}
    for index, entity in enumerate(OBJECTS):
        for key in ("K1", "K2", "K3"):
            points[(entity, key)] = dict(
                entity=entity,
                keypoint=key,
                frame=frame,
                source="yolo_image_only",
                det_confidence=0.9,
                keypoint_confidence=0.9,
                yx224=[20.0, 25.0 + index * 20.0],
            )
            geometry[entity + "." + key] = [0.0, 0.2 + index * 0.1, 0.9]
    return EvidenceRow(
        "episode",
        "main",
        frame,
        100.0,
        0.08,
        [0.5, 0.5, 1.2],
        [200.0, 200.0],
        points,
        geometry,
        dict(held="none"),
        dict(
            objects={obj: dict(supported=True) for obj in OBJECTS},
            native_goal_relations=dict(cheese_bowl=False),
        ),
    )


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.cache = BootstrapEvidence()
        self.rows = [observation(frame) for frame in (0, 4, 8, 12)]

    def decide(self, **kwargs):
        for row in self.rows:
            self.cache.append(row)
        arguments = dict(
            raw="put the cream cheese in the bowl",
            episode="episode",
            camera="main",
            frame=12,
            now=100.5,
            current_width=0.08,
            snapshot=dict(held_object="none"),
        )
        arguments.update(kwargs)
        return self.cache.decide(**arguments)

    def test_complete_fresh_evidence_admits_planning_without_completion(self):
        result = self.decide()
        self.assertFalse(result["inspect"])
        self.assertFalse(result["creates_completion"])
        self.assertEqual(result["facts"]["held_object"], "none")
        self.assertEqual(result["evidence_frames"], [0, 4, 8, 12])

    def test_open_hand_alone_does_not_pass(self):
        self.rows = self.rows[-1:]
        self.assertTrue(self.decide()["inspect"])

    def test_missing_points_depth_support_and_low_confidence_require_review(self):
        for failure in (
            "point",
            "depth",
            "support",
            "confidence",
            "cached",
            "wrong_frame",
        ):
            with self.subTest(failure=failure):
                self.setUp()
                row = self.rows[-1]
                if failure == "point":
                    del row.points[("cheese", "K1")]
                elif failure == "depth":
                    del row.geometry["bowl.K1"]
                elif failure == "support":
                    row.snapshot["objects"]["bowl"]["supported"] = None
                elif failure == "confidence":
                    row.points[("cheese", "K1")]["keypoint_confidence"] = 0.1
                elif failure == "cached":
                    row.points[("bowl", "K1")]["source"] = "cached"
                else:
                    row.points[("bowl", "K1")]["frame"] -= 4
                self.assertTrue(self.decide()["inspect"])

    def test_stale_wrong_episode_camera_closed_or_held_require_review(self):
        for change in (
            dict(now=103.0),
            dict(frame=20),
            dict(episode="other"),
            dict(camera="wrist"),
            dict(current_width=0.03),
            dict(snapshot=dict(held_object="cheese")),
        ):
            with self.subTest(change=change):
                self.setUp()
                self.assertTrue(self.decide(**change)["inspect"])

    def test_close_object_motion_or_ambiguous_containment_require_review(self):
        for failure in ("near_hand", "moving", "containment", "unknown_support"):
            with self.subTest(failure=failure):
                self.setUp()
                if failure == "near_hand":
                    for row in self.rows:
                        row.geometry["wine_bottle.K1"] = [0.5, 0.5, 1.15]
                elif failure == "moving":
                    self.rows[-1].points[("cheese", "K1")]["yx224"] = [30.0, 80.0]
                elif failure == "containment":
                    self.rows[-1].snapshot["native_goal_relations"]["cheese_bowl"] = (
                        None
                    )
                else:
                    self.rows[-1].snapshot["objects"]["wine_bottle"]["supported"] = None
                self.assertTrue(self.decide()["inspect"])

    def test_semantic_keep_inside_retains_visual_inspection(self):
        self.assertTrue(self.decide(raw="Keep the bowl inside the drawer")["inspect"])

    def test_no_snapshot_or_event_mutation(self):
        original = copy.deepcopy(self.rows)
        self.decide()
        self.assertEqual(self.rows, original)

    def test_same_frame_refresh_preserves_window(self):
        for row in self.rows:
            self.cache.append(row)
        self.cache.append(observation(12))
        self.assertEqual(len(self.cache.rows), 4)

    def test_reset_discards_observation_window(self):
        for row in self.rows:
            self.cache.append(row)
        self.cache.append(observation(0))
        self.assertEqual(len(self.cache.rows), 1)


if __name__ == "__main__":
    unittest.main()
