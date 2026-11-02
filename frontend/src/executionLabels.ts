/** Read-only titles for the reviewed site-trial primitives. These are action
 * intentions, not completion, vehicle-pose or motion-authority assertions.
 * Unknown/replaced recipes keep their server-provided labels. No numeric
 * C/B/D step position is used to guess an action on a different recipe.
 */
const actionTitles: Readonly<Record<string, string>> = Object.freeze({
  'B-delivery-group-1': 'Leave Pizza shop',
  'B-delivery-group-2': 'Continue to Office Building',
  'B-delivery-group-3': 'Continue to Office Building',
  'B-delivery-group-4': 'Continue to Office Building',
  'B-delivery-group-5': 'Approach Office Building',
  'B-delivery-group-6': 'Deliver at Office Building',

  // Shared C/D Pizza-front approach, first turn and northbound continuation.
  'D-fixed-plan-review-20261029T034234981825Z': 'Leave Pizza shop',
  'D-fixed-plan-review-20261029T034418293000Z': 'Approach South Junction',
  'D-fixed-plan-review-20261029T034547242944Z': 'Approach South Junction',
  'D-fixed-plan-review-20261029T034716442000Z': 'Approach South Junction',
  'D-fixed-plan-review-20261029T034845134379Z': 'Approach South Junction',
  'D-fixed-plan-review-20261029T035019375783Z': 'Approach South Junction',
  'empty:ba9c623a-6537-42c6-abaf-cc7a7154ab4b': 'Reposition the gripper',
  'wrist:c39c496b-b017-4282-822d-ce99bb1908f1': 'Orient gripper for the turn',
  'D-fixed-plan-review-20261029T040356680813Z': 'Begin the left turn',
  'D-fixed-plan-review-20261029T040618103199Z': 'Continue the left turn',
  'D-fixed-plan-review-20261029T040822582862Z': 'Continue the left turn',
  'D-fixed-plan-review-20261029T041036447126Z': 'Adjust the left turn',
  'D-fixed-plan-review-20261029T041620314128Z': 'Approach the signal stop',
  'D-fixed-plan-review-20261029T012151991079Z/signal-recontact': 'Recontact the car',
  'D-fixed-plan-review-20261029T012151991079Z/after-signal-recontact': 'Move forward after green',
  'D-fixed-plan-review-20261029T013453035241Z': 'Continue toward the junction',

  // Villa branch. Unloaded wrist/reposition stages do not turn the car.
  'NEW-C-right-wait-to-original-north3': 'Reposition the gripper',
  'C-original-NORTH3': 'Cross the junction',
  'C-upper-unloaded-WEST': 'Orient the gripper for Villa',
  'C-upper-WEST-corner': 'Begin the turn toward Villa',
  'C-upper-SW-arc2': 'Continue toward Villa',
  'C-upper-SW-arc3': 'Continue toward Villa',
  'C-upper-unloaded-NORTH': 'Orient the gripper',
  'C-upper-NORTH-center1': 'Move into the exit road',
  'C-upper-center2-20261028T225732224106Z': 'Continue into the exit road',
  'wrist:f81aa251-924f-46a6-a7e4-3716b58fe765': 'Orient the gripper for Villa',
  'C-west-course-review-20261028T231958806301Z': 'Deliver at Villa',

  // Hanok branch: the prefix is an unloaded move, not a vehicle push.
  'NEW-D-biased-nine-point-nine-extension/unloaded-prefix': 'Reposition the gripper',
  'NEW-D-biased-nine-point-nine-extension/contact-unit': 'Advance into the junction',
  'D-fixed-plan-review-20261029T050939781955Z': 'Turn right toward Hanok',
  'wrist:a5e741c4-0add-4e46-9308-d386868d25ee': 'Orient the gripper for Hanok',
  'D-fixed-plan-review-20261029T052256192986Z': 'Continue toward Hanok',
  'D-fixed-plan-review-20261029T052953417512Z': 'Approach Hanok',
  'D-fixed-plan-review-20261029T053715963799Z': 'Move toward Hanok frontage',
  'D-fixed-plan-review-20261029T055617515443Z': 'Deliver at Hanok',
});

function knownTitle(id: string): string | undefined {
  if (Object.hasOwn(actionTitles, id)) return actionTitles[id];
  // The service appends a command UUID to a repeated primitive row. Strip
  // only that recorded suffix and only when its base primitive is known.
  const repeated = /^(.*):(?:[0-9a-f]{32}|[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})$/i.exec(id);
  return repeated && Object.hasOwn(actionTitles, repeated[1]) ? actionTitles[repeated[1]] : undefined;
}

/** Returns a title only; the supplied telemetry object is never modified. */
export function executionStepLabel(step: Readonly<{ label: string; id: string; kind: string }>): string {
  const kind = step.kind.toLowerCase();
  if (kind === 'return' || kind === 'return_home') return 'Return to start';
  const title = knownTitle(step.id);
  if (title) return title;
  if (kind === 'signal_recontact') return 'Recontact the car';
  return step.label;
}
