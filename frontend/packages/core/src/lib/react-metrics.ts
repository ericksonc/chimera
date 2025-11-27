/**
 * Simple React-side metrics for debugging streaming performance.
 * Completely independent from Python metrics.
 */

export class ReactMetrics {
  private startTime: number | null = null;
  private lastLogTime: number | null = null;
  private charCount = 0;
  private updateCount = 0;
  private renderCount = 0;

  start() {
    this.startTime = performance.now();
    this.lastLogTime = this.startTime;
  }

  recordUpdate(deltaSize: number) {
    if (!this.startTime) {
      this.start();
    }

    this.charCount += deltaSize;
    this.updateCount++;

    const now = performance.now();
    const elapsed = (now - this.startTime!) / 1000;

    // Log every second
    if (now - this.lastLogTime! >= 1000) {
      const charPerSec = this.charCount / elapsed;
      console.log(
        `[REACT METRICS] ${elapsed.toFixed(1)}s | ${charPerSec.toFixed(0)} char/s | updates=${this.updateCount} | renders=${this.renderCount}`
      );
      this.lastLogTime = now;
    }
  }

  recordRender() {
    this.renderCount++;
  }

  logFinal() {
    if (!this.startTime) return;

    const elapsed = (performance.now() - this.startTime) / 1000;
    const charPerSec = this.charCount / elapsed;

    console.log(
      `[REACT FINAL] Duration=${elapsed.toFixed(1)}s | Chars=${this.charCount} | Rate=${charPerSec.toFixed(0)} char/s | Updates=${this.updateCount} | Renders=${this.renderCount}`
    );
  }
}
