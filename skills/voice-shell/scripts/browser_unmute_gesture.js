(function(root) {
  const emptyState = () => ({peaks: [], above: false, lastPeakAt: -Infinity, lastLevel: 0});

  const shouldKeepVizCapture = ({route, asrChosen, gestureEnabled, vizArmed}) =>
    !!vizArmed && (route !== 'off' || (!!asrChosen && !!gestureEnabled));

  function nextBrowserGesture(state, input) {
    if (!input.enabled || !input.active || input.inFlight) {
      return {state: emptyState(), triggered: false};
    }
    const level = Math.max(0, Number(input.level) || 0);
    const now = Number(input.now) || 0;
    const threshold = Number(input.threshold) || 0;
    const windowMs = Math.max(0, Number(input.windowMs) || 0);
    const peakCount = Math.max(1, Number(input.peakCount) || 1);
    const minGapMs = Math.max(0, Number(input.minGapMs) || 0);
    const minRise = Math.max(0, Number(input.minRise) || 0);
    const previous = state || emptyState();
    const above = level >= threshold;
    let next = {...previous, lastLevel: level};
    if (!above) return {state: {...next, above: false}, triggered: false};
    if (previous.above || level - previous.lastLevel < minRise || now - previous.lastPeakAt < minGapMs) {
      return {state: {...next, above: true}, triggered: false};
    }
    const peaks = previous.peaks.filter(at => now - at <= windowMs);
    peaks.push(now);
    if (peaks.length < peakCount) return {state: {...next, peaks, above: true, lastPeakAt: now}, triggered: false};
    return {state: emptyState(), triggered: true};
  }

  root.emptyBrowserGestureState = emptyState;
  root.nextBrowserGesture = nextBrowserGesture;
  root.shouldKeepVizCapture = shouldKeepVizCapture;
  if (typeof module !== 'undefined') module.exports = {emptyBrowserGestureState: emptyState, nextBrowserGesture, shouldKeepVizCapture};
})(typeof globalThis === 'undefined' ? this : globalThis);
