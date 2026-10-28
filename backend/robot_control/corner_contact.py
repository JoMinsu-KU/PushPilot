"""Nominal differential geometry for same-face corner-push experiments.

The car is a rigid rectangle, the pusher is a finite transverse segment and
the assumed force points along road-forward X. Geometry predicts neither
friction, rubber compliance nor the car's actual response. No motion authority
or measured contact qualification is produced here.
"""
from __future__ import annotations

import math


def _finite(value, name: str, *, positive=False) -> float:
    if (type(value) not in (int, float) or not math.isfinite(value)
            or abs(value) > 10000 or (positive and value <= 0)):
        raise ValueError(f"Invalid finite {name}.")
    return float(value)


def _overlap(car_width: float, pad_width: float, center_y: float) -> float:
    return max(0., min(car_width/2, center_y+pad_width/2)
               - max(-car_width/2, center_y-pad_width/2))


def rear_overlap_range(car_width_mm, pad_width_range_mm, south_shift_mm,
                       centering_uncertainty_mm=0.) -> dict:
    """Axis-aligned overlap under caller-supplied, unqualified width bounds.

    A constant tool-to-face offset cancels when the original same-orientation
    TCP contact is translated. An unknown original transverse centering bias
    does not cancel. These width bounds must not be presented as measurements.
    """
    car_width = _finite(car_width_mm, "car width", positive=True)
    if not isinstance(pad_width_range_mm, (list, tuple)) or len(pad_width_range_mm) != 2:
        raise ValueError("Supply minimum and maximum candidate pad width.")
    low, high = [_finite(value, "candidate pad width", positive=True)
                 for value in pad_width_range_mm]
    shift = _finite(south_shift_mm, "south shift")
    uncertainty = _finite(centering_uncertainty_mm, "centering uncertainty")
    if low > high or min(shift, uncertainty) < 0:
        raise ValueError("Widths must be ordered and distances nonnegative.")
    return {
        "minimum_overlap_mm": _overlap(car_width, low, shift+uncertainty),
        "maximum_overlap_mm": _overlap(car_width, high, max(0., shift-uncertainty)),
        "input_bounds_are_measured": False,
        "contact_qualified": False, "motion_authority": False,
    }


def _clip_y(vertices, boundary: float, keep_above: bool):
    if not vertices:
        return []
    result = []
    previous = vertices[-1]
    previous_inside = previous[1] >= boundary if keep_above else previous[1] <= boundary
    for current in vertices:
        inside = current[1] >= boundary if keep_above else current[1] <= boundary
        if inside != previous_inside:
            ratio = (boundary-previous[1])/(current[1]-previous[1])
            result.append((previous[0]+ratio*(current[0]-previous[0]), boundary))
        if inside:
            result.append(current)
        previous, previous_inside = current, inside
    return result


def east_first_contact(car_length_mm, car_width_mm, car_yaw_deg,
                       pad_center_y_mm, pad_width_mm) -> dict:
    """First nominal contact of an east-moving vertical face with a car.

    Coordinates use the CURRENT car center as origin and fixed road-forward
    X/road-left Y. Tool orientation remains the original east pushing pose.
    Positive torque means counterclockwise under the assumed eastward force.
    """
    length = _finite(car_length_mm, "car length", positive=True)
    width = _finite(car_width_mm, "car width", positive=True)
    yaw = _finite(car_yaw_deg, "car yaw")
    center = _finite(pad_center_y_mm, "pad transverse center")
    pad_width = _finite(pad_width_mm, "pad width", positive=True)
    if abs(yaw) > 180:
        raise ValueError("Car yaw must use -180..180 degrees.")
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    rectangle = [(x*c-y*s, x*s+y*c) for x, y in
                 ((-length/2, -width/2), (length/2, -width/2),
                  (length/2, width/2), (-length/2, width/2))]
    band = [center-pad_width/2, center+pad_width/2]
    clipped = _clip_y(_clip_y(rectangle, band[0], True), band[1], False)
    common = {"car_center_reference": "current_observed_car_center",
              "pad_y_band_mm": band, "force_assumption": "positive_road_x",
              "contact_qualified": False, "car_turn_qualified": False,
              "motion_authority": False}
    if not clipped:
        return {**common, "nominal_contact_exists": False,
                "first_contact_x_mm": None, "contact_y_range_mm": None,
                "nominal_torque_sign": "no_contact"}
    first_x = min(point[0] for point in clipped)
    ys = [point[1] for point in clipped if abs(point[0]-first_x) <= 1e-9]
    y_range = [min(ys), max(ys)]
    torque_range = [-y_range[1], -y_range[0]]
    sign = ("counterclockwise" if torque_range[0] > 1e-9 else
            "clockwise" if torque_range[1] < -1e-9 else "ambiguous_or_zero")
    return {**common, "nominal_contact_exists": True,
            "first_contact_x_mm": first_x, "contact_y_range_mm": y_range,
            "torque_per_unit_east_force_mm": torque_range,
            "nominal_torque_sign": sign}


def differential_contact_delta(reference_contact: dict, next_contact: dict,
                               observed_car_center_delta_road_mm,
                               next_pad_center_y_mm) -> dict:
    """Translate a genuine initial rear-centered same-face TCP reference.

    The input center delta needs independent observed provenance and bounded
    error in the caller. No pixel displacement is silently called millimeters.
    Returned X/Y are relative to the ORIGINAL same-orientation TCP contact.
    """
    if (not reference_contact.get("nominal_contact_exists")
            or not next_contact.get("nominal_contact_exists")):
        raise ValueError("Both nominal contact geometries must exist.")
    if (not isinstance(observed_car_center_delta_road_mm, (list, tuple))
            or len(observed_car_center_delta_road_mm) != 2):
        raise ValueError("Supply a separately observed two-dimensional car center delta.")
    dx, dy = [_finite(value, "observed car center delta")
              for value in observed_car_center_delta_road_mm]
    center_y = _finite(next_pad_center_y_mm, "next pad transverse center")
    reference_center = sum(reference_contact["pad_y_band_mm"])/2
    return {
        "delta_from_original_contact_tcp_road_mm": [
            dx+next_contact["first_contact_x_mm"]-reference_contact["first_contact_x_mm"],
            dy+center_y-reference_center],
        "orientation_must_equal_original_contact": True,
        "z_must_equal_original_contact": True,
        "requires_bounded_observed_car_center_delta": True,
        "requires_original_face_centering_review": True,
        "contact_qualified": False, "motion_authority": False,
    }
