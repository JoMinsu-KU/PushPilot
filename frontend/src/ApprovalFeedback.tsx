import { Icon } from './Icons';
import type { MissionApprovalFeedback } from './missionApproval';

/** Informational copy; no execution callback or local approval state. */
export function MissionApprovalMessage({ feedback }: { feedback: MissionApprovalFeedback }) {
  return <><div><Icon name="shield" size={16}/><h3>{feedback.title}</h3></div><p>{feedback.detail}</p></>;
}

/** Accepted approval is a status surface, never another command. */
export function ApprovedMissionButton() {
  return <button className="primary-button mission-approved-button" disabled><Icon name="check" size={18}/>Approved</button>;
}
