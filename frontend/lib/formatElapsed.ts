// "0:42" for a running timer. Used by Assistant and JobAnalysisView.
export function formatElapsed(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
