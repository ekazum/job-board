import { el } from "./dom";

const INFO_MS = 3000;
const ERROR_MS = 6000;

/** A transient status line at the bottom of the screen. */
export class Notice {
  private readonly node: HTMLElement;
  private timer: number | undefined;

  constructor(parent: HTMLElement) {
    this.node = el("div", { class: "notice", role: "status", "aria-live": "polite", hidden: true });
    parent.append(this.node);
  }

  info(message: string): void {
    this.show(message, "info", INFO_MS);
  }

  error(message: string): void {
    this.show(message, "error", ERROR_MS);
  }

  private show(message: string, tone: "info" | "error", durationMs: number): void {
    this.node.textContent = message;
    this.node.dataset.tone = tone;
    this.node.hidden = false;
    window.clearTimeout(this.timer);
    this.timer = window.setTimeout(() => {
      this.node.hidden = true;
    }, durationMs);
  }
}
