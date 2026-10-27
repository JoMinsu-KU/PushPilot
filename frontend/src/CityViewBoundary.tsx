import { Component, type ReactNode } from 'react';

/** Keep a missing or stale optional 3D chunk from unmounting the workspace. */
export class CityViewBoundary extends Component<{children: ReactNode; onReturn: () => void}, {failed: boolean}> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <div className="no-recorded-frame" role="alert">
      <h2>Spatial 3D unavailable</h2>
      <p>The 3D viewer could not open. Camera and 2D routes remain available. Refresh the page to retry the model.</p>
      <button type="button" onClick={this.props.onReturn}>Return to Camera</button>
    </div> : this.props.children;
  }
}
