import { errorMessage, patchPosting } from "./api";
import { el } from "./dom";
import {
  OUTCOME_LABELS,
  OUTCOMES,
  STATUS_LABELS,
  formatDate,
  isWebUrl,
  parseOutcome,
  type Posting,
  type PostingPatch,
} from "./domain";

export interface PostingDetailsCallbacks {
  onSaved(posting: Posting): void;
  onError(message: string): void;
}

/** Side-panel content for one posting: link, description, note, and the outcome of a closed posting. */
export class PostingDetails {
  private readonly callbacks: PostingDetailsCallbacks;

  constructor(callbacks: PostingDetailsCallbacks) {
    this.callbacks = callbacks;
  }

  render(posting: Posting): HTMLElement {
    const meta = el(
      "p",
      { class: "details-meta" },
      el("span", { class: `status-pill status-${posting.status}` }, STATUS_LABELS[posting.status]),
      posting.source === "manual" ? null : el("span", { class: "badge" }, posting.source),
      el("span", { class: "muted" }, `Added ${formatDate(posting.created_at)}`),
    );
    return el(
      "div",
      { class: "details" },
      el("p", { class: "details-company" }, posting.company),
      meta,
      isWebUrl(posting.url)
        ? el("a", { class: "details-link", href: posting.url, target: "_blank", rel: "noopener noreferrer" }, "Open posting ↗")
        : null,
      posting.status === "closed" ? this.outcomeField(posting) : null,
      el("h3", { class: "section-heading" }, "Description"),
      posting.text
        ? el("div", { class: "details-text" }, posting.text)
        : el("p", { class: "muted" }, "No description saved."),
      this.noteField(posting),
    );
  }

  private outcomeField(posting: Posting): HTMLElement {
    const select = el("select", { id: "details-outcome" });
    for (const outcome of OUTCOMES) {
      select.append(el("option", { value: outcome, selected: outcome === posting.outcome }, OUTCOME_LABELS[outcome]));
    }
    if (posting.outcome === null) {
      select.prepend(el("option", { value: "", selected: true, disabled: true }, "Choose…"));
    }
    select.addEventListener("change", () => {
      const outcome = parseOutcome(select.value);
      if (outcome !== null) {
        void this.save(posting.id, { outcome }, select);
      }
    });
    return el("label", { class: "field field-inline", for: "details-outcome" }, el("span", {}, "Outcome"), select);
  }

  private noteField(posting: Posting): HTMLElement {
    const textarea = el("textarea", { id: "details-note", rows: "5", placeholder: "Contacts, dates, next steps…" });
    textarea.value = posting.note;
    const status = el("span", { class: "muted save-status", "aria-live": "polite" });
    const button = el("button", { type: "button", class: "button-primary" }, "Save note");
    let savedNote = posting.note;
    const saveNote = async (): Promise<void> => {
      const note = textarea.value;
      if (await this.save(posting.id, { note }, button)) {
        savedNote = note;
        status.textContent = textarea.value === savedNote ? "Saved" : "Unsaved";
      }
    };
    button.addEventListener("click", () => void saveNote());
    textarea.addEventListener("input", () => {
      status.textContent = textarea.value === savedNote ? "" : "Unsaved";
    });
    textarea.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
        void saveNote();
      }
    });
    return el(
      "div",
      { class: "field" },
      el("label", { class: "section-heading", for: "details-note" }, "Note"),
      textarea,
      el("div", { class: "field-actions" }, button, status),
    );
  }

  /** PATCH and report back; the control is disabled while the request is in flight. */
  private async save(id: number, patch: PostingPatch, control: HTMLButtonElement | HTMLSelectElement): Promise<boolean> {
    control.disabled = true;
    try {
      this.callbacks.onSaved(await patchPosting(id, patch));
      return true;
    } catch (error) {
      this.callbacks.onError(errorMessage(error));
      return false;
    } finally {
      control.disabled = false;
    }
  }
}
