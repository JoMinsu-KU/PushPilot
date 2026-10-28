"""Preview directly taught BASE roads from a private JSON input; never dispatch.

Input fields: points [{id, pose_base_mm_deg, observation_sha256}] and optional
start with the same fields. Without a current start only junction proposals
and taught goals are returned. No map file, receiver, token or camera is opened.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from backend.robot_control.taught_roads import TaughtPoint, propose_taught_roads


def preview(data):
    if type(data) is not dict or set(data)-{'points','start'}:
        raise ValueError('Supply only current taught points and an optional fresh start.')
    def make(row):
        if type(row) is not dict or set(row)!={'id','pose_base_mm_deg','observation_sha256'}:
            raise ValueError('Each point needs its exact identifier, BASE pose and observation hash.')
        return TaughtPoint(**row)
    roads=propose_taught_roads(tuple(make(row) for row in data['points']))
    out={'schema':'pushpilot.taught-roads-preview.v1','coordinate_frame':'BASE',
         'south_junction_proposed_xy_mm':roads.south_junction_xy,
         'north_junction_proposed_xy_mm':roads.north_junction_xy,
         'frontage_disagreement_deg':roads.frontage_disagreement_deg,
         'goals':{p.id:p.pose_base_mm_deg for p in roads.points if p.id in {'B','C','D'}},
         'connector_assumption':'perpendicular_to_the_average_taught_frontage_direction',
         'start_required':'start' not in data,'map_transform_used':False,
         'execution_ready':False,'motion_issued':False,'automatic_replay':False}
    if 'start' in data:
        start=make(data['start'])
        out['routes']={goal:roads.route_preview(goal,start) for goal in 'BCD'}
    return out


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    args=parser.parse_args()
    if args.input.stat().st_size>65536:
        raise ValueError('Private teaching input exceeds 64 KiB.')
    data=json.loads(args.input.read_text(encoding='utf-8'),parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite input.')))
    print(json.dumps(preview(data),allow_nan=False,indent=2))


if __name__=='__main__':
    main()
