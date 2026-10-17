import { errorMessage, getPostings, patchPosting, purgeLocationRejects } from "./api";
import type { ConfirmDialog } from "./confirm-dialog";
import { el } from "./dom";
import { formatDate, isLocationReject, isWebUrl, type Posting } from "./domain";

export interface ArchiveViewCallbacks {
  /** A posting was re-opened; the board should reload. */
  onReopened(posting: Posting): void;
  onInfo(message: string): void;
  onError(message: string): void;
}

/**
 * Postings the LLM scorer or the location rule closed as not relevant, with the reason (and the scorer's gaps),
 * Re-open to put one back in New, and Purge rejects to delete the location rule's ones for good.
 */
export class ArchiveView {
  readonly element: HTMLElement;
  private readonly callbacks: ArchiveViewCallbacks;
  private readonly confirmDialog: ConfirmDialog;
  private readonly list: HTMLElement;
  private readonly count: HTMLElement;
  private readonly purgeButton: HTMLButtonElement;

  constructor(confirmDialog: ConfirmDialog, callbacks: ArchiveViewCallbacks) {
    this.callbacks = callbacks;
    this.confirmDialog = confirmDialog;
    this.list = el("div", { class: "archive-list" });
    this.count = el("span", { class: "muted" });
    this.purgeButton = el("button", { type: "button", class: "button-ghost archive-purge" }, "Purge rejects");
    this.purgeButton.addEventListener("click", () => void this.purge());
    this.element = el(
      "section",
      { class: "archive-view", "aria-label": "Archive" },
      el("div", { class: "archive-header" }, el("h2", { class: "settings-heading" }, "Archive"), this.count, this.purgeButton),
      el(
        "p",
        { class: "muted companies-hint" },
        "Jobs the LLM scored below the threshold, or outside the location set in your Profile. Re-open one to move it to New.",
      ),
      this.list,
    );
  }

  async load(): Promise<void> {
    try {
      this.render(await getPostings({ archived: true }));
    } catch (error) {
      this.callbacks.onError(`Could not load the archive: ${errorMessage(error)}`);
    }
  }

  private render(postings: Posting[]): void {
    this.showCount(postings.length);
    this.purgeButton.disabled = !postings.some(isLocationReject);
    if (postings.length === 0) {
      this.list.replaceChildren(el("p", { class: "muted empty" }, "Nothing archived."));
      return;
    }
    this.list.replaceChildren(...postings.map((posting) => this.item(posting)));
  }

  private showCount(count: number): void {
    this.count.textContent = `${count} job${count === 1 ? "" : "s"}`;
  }

  private item(posting: Posting): HTMLElement {
    const reopen = el("button", { type: "button", class: "button-ghost" }, "Re-open");
    const badge = isLocationReject(posting)
      ? el("span", { class: "badge badge-location" }, "location")
      : el("span", { class: "badge badge-fit" }, `fit ${posting.fit ?? "?"}`);
    const reason = isLocationReject(posting) ? (posting.fit_reason ?? "").replace(/^location: /, "") : (posting.fit_reason ?? "");
    const row = el(
      "article",
      { class: "archive-item" },
      el(
        "div",
        { class: "archive-main" },
        el(
          "h3",
          { class: "card-title" },
          isWebUrl(posting.url) ? el("a", { href: posting.url, target: "_blank", rel: "noopener noreferrer" }, posting.title) : posting.title,
        ),
        el("p", { class: "card-company" }, `${posting.company}${posting.location ? ` · ${posting.location}` : ""} · ${formatDate(posting.created_at)}`),
        el("p", { class: "archive-reason" }, badge, ` ${reason}`),
        posting.fit_gaps?.length ? el("p", { class: "muted archive-gaps" }, `Gaps: ${posting.fit_gaps.join(", ")}`) : null,
      ),
      reopen,
    );
    reopen.addEventListener("click", () => void this.reopen(posting, row, reopen));
    return row;
  }

  private async reopen(posting: Posting, row: HTMLElement, button: HTMLButtonElement): Promise<void> {
    button.disabled = true;
    try {
      const reopened = await patchPosting(posting.id, { status: "new" });
      row.remove();
      this.showCount(this.list.querySelectorAll(".archive-item").length);
      this.callbacks.onReopened(reopened);
    } catch (error) {
      button.disabled = false;
      this.callbacks.onError(errorMessage(error));
    }
  }

  /** Delete the location rule's rejects after asking; the scorer's rejects stay. */
  private async purge(): Promise<void> {
    const confirmed = await this.confirmDialog.ask(
      "Purge location rejects?",
      "Every job archived for its location is deleted for good. A later scan adds a job again if its board still lists it.",
      "Purge",
    );
    if (!confirmed) {
      return;
    }
    this.purgeButton.disabled = true;
    try {
      const { deleted } = await purgeLocationRejects();
      this.callbacks.onInfo(`Deleted ${deleted} job${deleted === 1 ? "" : "s"} archived for their location`);
      await this.load();
    } catch (error) {
      this.purgeButton.disabled = false;
      this.callbacks.onError(errorMessage(error));
    }
  }
}
