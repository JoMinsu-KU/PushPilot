"""Offline contact-relative path screening, not a rigid-body physics simulator.

The reported 45 x 18 mm vehicle and 15 mm rubber face inform a local clearance
margin. TCP-to-face offset cancels only for the SAME literal tool posture and
the SAME intended contact. Whole-arm, hose and deformed-rubber geometry remain
unmodelled. Never convert these results into physical qualification.
"""
from copy import deepcopy
import math

from backend.robot_control.mission_catalog import content_hash


def _contacts(row):
    return [s for s in row["stages"] if s["phase"] == "contact"]


def _direction(stage):
    v = [b-a for a,b in zip(stage["start_base"][:2],stage["target_base"][:2])]
    length = math.hypot(*v)
    if length <= 0:
        raise ValueError("A contact direction needs nonzero measured translation.")
    return [x/length for x in v]


def face_references(packet):
    """Explicit current-site EAST/NORTH/WEST contact examples, never map fitting."""
    b = packet["routes"]["B"]["steps"][0]
    c = packet["routes"]["C"]["steps"]
    north = next(s for s in c if s.get("signal_gate"))
    rows = [b,north,c[-1]]
    refs = []
    for step in rows:
        row = packet["primitives"][step["primitive_id"]]
        stage = _contacts(row)[-1]
        refs.append({"primitive_id":row["id"],"posture":stage["target_base"][2:],"normal":_direction(stage)})
    return refs


def _normal(row, refs):
    contacts = _contacts(row)
    if not contacts:
        return None
    matches = [r for r in refs if all(abs(a-b)<1e-6 for a,b in zip(r["posture"],contacts[-1]["target_base"][2:]))]
    if len(matches) != 1:
        return None
    return matches[0]["normal"]


def _project(stage, normal):
    v = [stage["target_base"][i]-stage["start_base"][i] for i in (0,1)]
    return sum(a*b for a,b in zip(v,normal)), abs(v[0]*normal[1]-v[1]*normal[0])


def audit(packet, refs):
    findings = []
    for code, route in packet["routes"].items():
        for step in route["steps"]:
            row = packet["primitives"][step["primitive_id"]]
            if not _contacts(row):
                continue
            normal = _normal(row,refs)
            if normal is None:
                findings.append({"route":code,"step":step["id"],"primitive":row["id"],"issue":"UNKNOWN_FACE_REFERENCE"})
                continue
            approaches = [s for s in row["stages"] if s["phase"]=="approach"]
            withdrawals = [s for s in row["stages"] if s["phase"]=="withdraw"]
            issues = []
            if approaches:
                forward, side = _project(approaches[-1],normal)
                if forward <= 0 or side > max(.1,forward*.1):
                    issues.append("LATERAL_FINAL_APPROACH")
            if withdrawals:
                forward, side = _project(withdrawals[0],normal)
                if -forward < 5.-1e-6 or side > .1:
                    issues.append("SIDEWAYS_WITHDRAWAL_BEFORE_CLEARANCE")
            else:
                issues.append("NO_WITHDRAWAL")
            for issue in issues:
                findings.append({"route":code,"step":step["id"],"primitive":row["id"],"issue":issue})
    return findings


def repair_local_clearances(packet, refs, *, backoff_mm=10., side_clearance_mm=25., workspace_bounds=None):
    """Adjust only terminal lateral approaches / initial lateral withdrawals.

    Preserve contacts, external endpoints, Z/Euler, and existing 20 mm caps.
    Side clearance = 9 mm half-car + 7.5 mm half-pad + 8.5 mm allowance.
    This is a local same-posture proxy, not proof of collision-free free space.
    Unsupported geometry remains a finding instead of receiving a guessed fix.
    """
    if backoff_mm != 10. or side_clearance_mm != 25.:
        raise ValueError("Changing the explicit current-site clearance assumptions needs a separate review.")
    before = audit(packet,refs)
    repairs = []
    blocked = []

    def shifted(p,n):
        return [p[0]-backoff_mm*n[0],p[1]-backoff_mm*n[1],*p[2:]]

    def segments(row, phase, points, label):
        result=[]
        for a,b in zip(points,points[1:]):
            if math.dist(a[:2],b[:2]) < 1e-9:
                continue
            # Keep literal shared vertices; no rounding or posture fitting.
            count=max(1,math.ceil(math.dist(a[:2],b[:2])/19.9))
            previous=list(a)
            for part in range(1,count+1):
                target=list(b) if part==count else [a[j]+(b[j]-a[j])*part/count for j in (0,1)]+list(a[2:])
                result.append({"id":row["id"]+"/"+label+"-"+str(len(result)+1),"phase":phase,
                    "start_base":previous,"target_base":target,"geometry_basis":"current_site_candidate",
                    "derivation":{"method":label,"source_geometry_sha256":row["geometry_sha256"]},
                    "original":{"request_id":None,"evidence":None,"supporting_segments":[]}})
                previous=target
        return result

    for row in packet["primitives"].values():
        normal=_normal(row,refs)
        if normal is None:
            continue
        old=deepcopy(row); stages=row["stages"]; changes=[]
        contact_indices=[i for i,s in enumerate(stages) if s["phase"]=="contact"]
        first,last=contact_indices[0],contact_indices[-1]
        # Shift the complete terminal tangential run behind the contact plane,
        # then approach normally. If the existing endpoint is close, move
        # outward first; never cut diagonally through the contact envelope.
        cut=first
        while cut>0 and stages[cut-1]["phase"]=="approach":
            forward,side=_project(stages[cut-1],normal)
            if abs(forward)>.1 or side<.1:
                break
            cut-=1
        if cut<first:
            entry=stages[cut]["start_base"]; target=stages[first]["start_base"]
            delta=[entry[i]-target[i] for i in (0,1)]
            side=abs(delta[0]*normal[1]-delta[1]*normal[0])
            if side>.1:
                outward=list(entry)
                extension=max(0.,side_clearance_mm-side)
                if extension<1e-9:
                    extension=0.
                for j in (0,1):
                    outward[j] += delta[j]/side*extension
                vertices=[entry,outward,shifted(outward,normal),shifted(entry,normal)]
                vertices += [shifted(s["target_base"],normal) for s in stages[cut:first]]
                vertices += [target]
                stages=stages[:cut]+segments(row,"approach",vertices,"normal-final-approach")+stages[first:]
                changes.append("NORMAL_FINAL_APPROACH")
        last=max(i for i,s in enumerate(stages) if s["phase"]=="contact")
        ws=stages[last+1:]
        if ws and all(s["phase"]=="withdraw" for s in ws):
            forward,side=_project(ws[0],normal)
            if abs(forward)<.1 and side>.1:
                anchor=ws[0]["start_base"]; run=[]
                for s in ws:
                    f,_=_project(s,normal)
                    if abs(f)>.1:
                        break
                    run.append(s)
                    d=[s["target_base"][i]-anchor[i] for i in (0,1)]
                    if abs(d[0]*normal[1]-d[1]*normal[0])>=side_clearance_mm:
                        break
                if run:
                    d=[run[-1]["target_base"][i]-anchor[i] for i in (0,1)]
                    if abs(d[0]*normal[1]-d[1]*normal[0])>=side_clearance_mm:
                        vertices=[anchor,shifted(anchor,normal)]
                        vertices += [shifted(s["target_base"],normal) for s in run]
                        vertices += [run[-1]["target_base"]]
                        stages=stages[:last+1]+segments(row,"withdraw",vertices,"normal-first-withdrawal")+ws[len(run):]
                        changes.append("NORMAL_FIRST_WITHDRAWAL")
        if changes:
            assert _contacts({"stages":stages})==_contacts(old)
            assert stages[0]["start_base"]==old["stages"][0]["start_base"]
            assert stages[-1]["target_base"]==old["stages"][-1]["target_base"]
            if workspace_bounds is not None:
                low,high=workspace_bounds
                if any(not lo<=x<=hi for s in stages for p in (s["start_base"],s["target_base"])
                       for lo,x,hi in zip(low,p[:3],high)):
                    blocked.append({"primitive":row["id"],"reason":"CANDIDATE_OUTSIDE_EXISTING_WORKSPACE",
                        "original_retained":True,"physical_clearance_verified":False})
                    continue
            row["clearance_source_stages"]=old["stages"]
            row["stages"]=stages
            row["repeatability_qualified"]=False
            row["original_verdict"]=None
            row["candidate_reason"]="Normal clearance before lateral travel; current-site proxy only, physical verification pending."
            row["geometry_sha256"]=content_hash({"kind":row["kind"],"stages":[{k:s[k] for k in ("phase","start_base","target_base")} for s in stages],"contact_travel_limit_mm":row["contact_travel_limit_mm"]})
            repairs.append({"primitive":row["id"],"changes":changes,"before_sha256":old["geometry_sha256"],"after_sha256":row["geometry_sha256"]})
    for route in packet["routes"].values():
        route["counts"]["route_stages"]=sum(len(packet["primitives"][s["primitive_id"]]["stages"]) for s in route["steps"])
    return {"method":"contact-relative fixed-posture geometric screening",
        "car_size_mm":[45.,18.,15.],"rubber_face_width_mm":15.,"backoff_mm":backoff_mm,
        "side_clearance_mm":side_clearance_mm,"before":before,"repairs":repairs,"blocked_repairs":blocked,"after":audit(packet,refs),
        "physical_collision_free_verified":False,
        "unmodelled":["actual vehicle pose and slip","rubber deformation","full gripper, arm and hose swept volume","changed-posture TCP-to-face offsets"]}
