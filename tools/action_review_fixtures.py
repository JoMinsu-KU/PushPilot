"""Create original synthetic image pairs for explicit, hardware-free evaluation.

These diagrams are test inputs, not photographs, motion evidence or model results.
The three after-images share the same expectation and contain no verdict labels.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


EXPECTATION = (
    "For the simulated approach to junction C, the same white car should move right "
    "from PIZZA into the orange C APPROACH TARGET. Compare the depicted positions in "
    "BEFORE and AFTER. If it has not progressed, reject the expected outcome; if it "
    "cannot be located because of an occluder, request another observation. These "
    "are synthetic schematic evaluation inputs, not photographs or physical motion evidence."
)


def _text(image, text, position, scale=0.65, color=(66, 62, 57), thickness=1):
    cv2.putText(image, text, position, cv2.FONT_HERSHEY_SIMPLEX, scale, color,
                thickness, cv2.LINE_AA)


def _car(image, center):
    x, y = center
    points = np.array([
        [x - 63, y + 20], [x - 63, y - 19], [x - 43, y - 28],
        [x - 26, y - 43], [x + 28, y - 43], [x + 48, y - 28],
        [x + 64, y - 20], [x + 64, y + 20],
    ], dtype=np.int32)
    cv2.fillPoly(image, [points + (2, 4)], (158, 154, 149))
    cv2.fillPoly(image, [points], (255, 255, 255))
    cv2.polylines(image, [points], True, (85, 80, 74), 2, cv2.LINE_AA)
    _text(image, "CAR", (x - 23, y + 5), 0.6, thickness=2)


def image_bytes(phase: str, *, car_at_target=False, occluded=False) -> bytes:
    """Return a PNG of a controlled visual case with explicit synthetic labelling."""
    if phase not in {"BEFORE", "AFTER"}:
        raise ValueError("The image phase must be BEFORE or AFTER.")
    image = np.full((560, 960, 3), (245, 247, 249), dtype=np.uint8)
    cv2.rectangle(image, (0, 0), (959, 94), (255, 255, 255), -1)
    _text(image, "PUSHPILOT / SYNTHETIC EVALUATION", (32, 37), 0.77, thickness=2)
    _text(image, f"{phase}  |  Original schematic, no camera or robot", (32, 70), 0.59)
    cv2.rectangle(image, (65, 225), (895, 390), (220, 224, 228), -1)
    for x in range(80, 865, 65):
        cv2.line(image, (x, 312), (x + 32, 312), (252, 252, 252), 3)
    cv2.rectangle(image, (133, 245), (307, 366), (157, 168, 177), 2)
    cv2.rectangle(image, (613, 245), (787, 366), (42, 132, 232), 3)
    _text(image, "PIZZA / START", (132, 206), 0.65, thickness=2)
    _text(image, "C APPROACH TARGET", (572, 206), 0.65, thickness=2)
    _text(image, "Expected direction", (366, 432), 0.56)
    cv2.arrowedLine(image, (379, 462), (574, 462), (42, 132, 232), 4,
                    cv2.LINE_AA, tipLength=0.11)
    if occluded:
        cv2.rectangle(image, (110, 237), (830, 376), (104, 110, 115), -1)
        for x in range(125, 820, 28):
            cv2.line(image, (x, 245), (min(x + 110, 822), 368), (126, 132, 137), 3)
        _text(image, "FOREGROUND OCCLUDER", (305, 317), 0.65, (255, 255, 255), 2)
    else:
        _car(image, (700 if car_at_target else 220, 317))
    _text(image, "SIMULATION TEST INPUT - does not show physical execution", (32, 531), 0.58)
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise ValueError("Could not encode a synthetic evaluation fixture.")
    return encoded.tobytes()


def write_fixtures(directory: Path) -> dict[str, Path]:
    """Write a new fixture set; never overwrite existing evidence."""
    directory.mkdir(parents=True, exist_ok=True)
    images = {
        "before": image_bytes("BEFORE"),
        "success": image_bytes("AFTER", car_at_target=True),
        "no_progress": image_bytes("AFTER"),
        "occluded": image_bytes("AFTER", occluded=True),
    }
    paths = {}
    for name, data in images.items():
        path = directory / f"{name}.png"
        with path.open("xb") as handle:
            handle.write(data)
        paths[name] = path
    return paths
