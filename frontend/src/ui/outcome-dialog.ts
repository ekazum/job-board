import { OUTCOME_LABELS, OUTCOMES, parseOutcome, type Outcome, type Posting } from "../api/domain";
import { el } from "./dom";

/** Modal that asks how a posting ended when it is dropped into Closed. Resolves null on Cancel or Esc. */
export class OutcomeDialog {
  private readonly dialog: HTMLDialogElement;
  private readonly subtitle: HTMLElement;
  private pending: ((outcome: Outcome | null) => void) | null = null;

  constructor(parent: HTMLElement) {
    this.subtitle = el("p", { class: "dialog-subtitle" });
    const choices = OUTCOMES.map((outcome) =>
      el("button", { type: "submit", value: outcome, class: `outcome-choice outcome-${outcome}` }, OUTCOME_LABELS[outcome]),
    );
    // method="dialog": clicking a button closes the dialog with returnValue = that button's value.
    const form = el(
      "form",
      { method: "dialog", class: "dialog-body" },
      el("h2", { id: "outcome-dialog-title" }, "How did it end?"),
      this.subtitle,
      el("div", { class: "outcome-choices" }, ...choices),
      el(
        "div",
        { class: "dialog-actions" },
        el("button", { type: "submit", value: "", class: "button-ghost", autofocus: true }, "Cancel"),
      ),
    );
    this.dialog = el("dialog", { class: "outcome-dialog", "aria-labelledby": "outcome-dialog-title" }, form);
    this.dialog.addEventListener("close", () => this.settle(parseOutcome(this.dialog.returnValue)));
    parent.append(this.dialog);
  }

  ask(posting: Posting): Promise<Outcome | null> {
    this.settle(null);
    this.subtitle.textContent = `${posting.title} · ${posting.company}`;
    this.dialog.returnValue = "";
    this.dialog.showModal();
    return new Promise((resolve) => {
      this.pending = resolve;
    });
  }

  private settle(outcome: Outcome | null): void {
    const pending = this.pending;
    this.pending = null;
    pending?.(outcome);
  }
}
