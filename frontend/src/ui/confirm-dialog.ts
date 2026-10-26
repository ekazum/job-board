import { el } from "./dom";

/** Modal yes/no question for an action that cannot be undone. Resolves false on Cancel or Esc. */
export class ConfirmDialog {
  private readonly dialog: HTMLDialogElement;
  private readonly title: HTMLElement;
  private readonly message: HTMLElement;
  private readonly confirmButton: HTMLButtonElement;
  private pending: ((confirmed: boolean) => void) | null = null;

  constructor(parent: HTMLElement) {
    this.title = el("h2", { id: "confirm-dialog-title" });
    this.message = el("p", { class: "dialog-subtitle" });
    this.confirmButton = el("button", { type: "submit", value: "confirm", class: "button-danger" });
    // method="dialog": clicking a button closes the dialog with returnValue = that button's value.
    const form = el(
      "form",
      { method: "dialog", class: "dialog-body" },
      this.title,
      this.message,
      el(
        "div",
        { class: "dialog-actions" },
        el("button", { type: "submit", value: "", class: "button-ghost", autofocus: true }, "Cancel"),
        this.confirmButton,
      ),
    );
    this.dialog = el("dialog", { class: "outcome-dialog", "aria-labelledby": "confirm-dialog-title" }, form);
    this.dialog.addEventListener("close", () => this.settle(this.dialog.returnValue === "confirm"));
    parent.append(this.dialog);
  }

  ask(title: string, message: string, confirmLabel: string): Promise<boolean> {
    this.settle(false);
    this.title.textContent = title;
    this.message.textContent = message;
    this.confirmButton.textContent = confirmLabel;
    this.dialog.returnValue = "";
    this.dialog.showModal();
    return new Promise((resolve) => {
      this.pending = resolve;
    });
  }

  private settle(confirmed: boolean): void {
    const pending = this.pending;
    this.pending = null;
    pending?.(confirmed);
  }
}
