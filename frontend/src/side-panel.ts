import { el } from "./dom";

/** Right-hand panel that shows one piece of content at a time (posting details or the paste form). */
export class SidePanel {
  private readonly node: HTMLElement;
  private readonly heading: HTMLElement;
  private readonly body: HTMLElement;
  private key: string | null = null;

  constructor(parent: HTMLElement) {
    const closeButton = el("button", { type: "button", class: "icon-button", "aria-label": "Close panel" }, "×");
    closeButton.addEventListener("click", () => this.close());
    this.heading = el("h2", { class: "panel-heading", id: "panel-heading" });
    this.body = el("div", { class: "panel-body" });
    this.node = el(
      "aside",
      { class: "panel", hidden: true, "aria-labelledby": "panel-heading" },
      el("header", { class: "panel-header" }, this.heading, closeButton),
      this.body,
    );
    document.addEventListener("keydown", (event) => {
      // Esc inside an open <dialog> belongs to the dialog.
      if (event.key === "Escape" && this.key !== null && document.querySelector("dialog[open]") === null) {
        this.close();
      }
    });
    parent.append(this.node);
  }

  /** The key passed to the last show(), or null when closed. */
  get openKey(): string | null {
    return this.key;
  }

  show(key: string, heading: string, content: HTMLElement): void {
    this.key = key;
    this.heading.textContent = heading;
    this.body.replaceChildren(content);
    this.body.scrollTop = 0;
    this.node.hidden = false;
    content.querySelector<HTMLElement>("[autofocus]")?.focus();
  }

  close(): void {
    this.key = null;
    this.node.hidden = true;
    this.body.replaceChildren();
  }
}
