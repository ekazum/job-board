import Sortable from "sortablejs";

import { errorMessage, patchPosting } from "./api";
import { el } from "./dom";
import {
  OUTCOME_LABELS,
  STATUS_LABELS,
  STATUSES,
  byFit,
  byNewest,
  formatDate,
  parseStatus,
  type Posting,
  type PostingPatch,
  type Status,
} from "./domain";
import type { OutcomeDialog } from "./outcome-dialog";

export interface BoardCallbacks {
  onOpen(posting: Posting): void;
  onMoved(posting: Posting): void;
  onError(message: string): void;
}

/**
 * Four status columns. Cards are dragged between columns (PATCH status); order inside a column is
 * always newest first, so in-column reordering is disabled. Dropping into Closed asks for an outcome.
 */
export class Board {
  private postings: Posting[] = [];
  private readonly lists = new Map<Status, HTMLElement>();
  private readonly counts = new Map<Status, HTMLElement>();
  private totals: Record<Status, number> = { new: 0, applied: 0, interview: 0, closed: 0 };
  private readonly outcomeDialog: OutcomeDialog;
  private readonly callbacks: BoardCallbacks;

  constructor(root: HTMLElement, outcomeDialog: OutcomeDialog, callbacks: BoardCallbacks) {
    this.outcomeDialog = outcomeDialog;
    this.callbacks = callbacks;
    root.replaceChildren(...STATUSES.map((status) => this.column(status)));
  }

  load(postings: Posting[]): void {
    this.postings = [...postings].sort(byNewest);
    this.render();
  }

  /** Each column's unfiltered count, for the "shown / total" header. */
  setTotals(totals: Readonly<Record<string, number>>): void {
    for (const status of STATUSES) {
      this.totals[status] = totals[status] ?? 0;
    }
    this.render();
  }

  /** Insert a new posting or replace an existing one (keeping the totals in step with a move), then redraw. */
  upsert(posting: Posting): void {
    const index = this.postings.findIndex((existing) => existing.id === posting.id);
    const previous = index === -1 ? undefined : this.postings[index];
    if (previous === undefined) {
      this.postings.push(posting);
      this.totals[posting.status] += 1;
    } else {
      this.postings[index] = posting;
      this.totals[previous.status] -= 1;
      this.totals[posting.status] += 1;
    }
    this.postings.sort(byNewest);
    this.render();
  }

  private column(status: Status): HTMLElement {
    const list = el("div", { class: "column-list", "data-status": status });
    const count = el("span", { class: "column-count" }, "0");
    this.lists.set(status, list);
    this.counts.set(status, count);
    Sortable.create(list, {
      group: "postings",
      sort: false,
      animation: 150,
      ghostClass: "card-ghost",
      chosenClass: "card-chosen",
      // onEnd fires once, after SortableJS has finished with the DOM, so re-rendering here is safe.
      onEnd: (event) => void this.handleDrop(event),
    });
    return el(
      "section",
      { class: `column column-${status}`, "aria-label": STATUS_LABELS[status] },
      el("header", { class: "column-header" }, el("h2", {}, STATUS_LABELS[status]), count),
      list,
    );
  }

  private async handleDrop(event: Sortable.SortableEvent): Promise<void> {
    if (event.from === event.to) {
      return;
    }
    const posting = this.postings.find((candidate) => candidate.id === Number(event.item.dataset.id));
    const target = parseStatus(event.to.dataset.status);
    if (posting === undefined || target === null) {
      this.render();
      return;
    }
    const patch: PostingPatch = { status: target };
    if (target === "closed") {
      const outcome = await this.outcomeDialog.ask(posting);
      if (outcome === null) {
        this.render(); // cancelled: card returns to its column
        return;
      }
      patch.outcome = outcome;
    }
    event.item.classList.add("card-pending");
    try {
      const updated = await patchPosting(posting.id, patch);
      this.upsert(updated);
      this.callbacks.onMoved(updated);
    } catch (error) {
      this.callbacks.onError(errorMessage(error));
      this.render();
    }
  }

  private render(): void {
    for (const status of STATUSES) {
      const postings = this.postings.filter((posting) => posting.status === status);
      if (status === "new") {
        postings.sort(byFit);
      }
      this.lists.get(status)?.replaceChildren(...postings.map((posting) => this.card(posting)));
      const count = this.counts.get(status);
      if (count !== undefined) {
        count.textContent = `${postings.length} / ${Math.max(this.totals[status], postings.length)}`;
        count.title = "shown / total";
      }
    }
  }

  /** "fit 8" with the scorer's reason and gaps on hover; "unscored" when scoring failed or had no profile. */
  private fitBadge(posting: Posting): HTMLElement | null {
    const gaps = posting.fit_gaps?.length ? `
Gaps: ${posting.fit_gaps.join(", ")}` : "";
    const hover = `${posting.fit_reason ?? ""}${gaps}`.trim();
    if (posting.fit !== null && posting.fit !== undefined) {
      return el("span", { class: "badge badge-fit", title: hover || "LLM fit score" }, `fit ${posting.fit}`);
    }
    return posting.fit_reason ? el("span", { class: "badge badge-unscored", title: posting.fit_reason }, "unscored") : null;
  }

  private card(posting: Posting): HTMLElement {
    const card = el(
      "article",
      { class: "card", tabindex: "0", "data-id": String(posting.id) },
      el("h3", { class: "card-title" }, posting.title),
      el("p", { class: "card-company" }, posting.company),
      posting.location ? el("p", { class: "card-location", title: posting.location }, posting.location) : null,
      el(
        "div",
        { class: "card-meta" },
        posting.source === "manual" ? null : el("span", { class: "badge" }, posting.source),
        posting.country ? el("span", { class: "badge", title: "Country" }, posting.country) : null,
        posting.is_remote ? el("span", { class: "badge badge-remote" }, "Remote") : null,
        this.fitBadge(posting),
        posting.outcome === null
          ? null
          : el("span", { class: `badge outcome-${posting.outcome}` }, OUTCOME_LABELS[posting.outcome]),
        el("time", { class: "card-date", datetime: posting.created_at }, formatDate(posting.created_at)),
      ),
    );
    card.addEventListener("click", () => this.callbacks.onOpen(posting));
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        this.callbacks.onOpen(posting);
      }
    });
    return card;
  }
}
