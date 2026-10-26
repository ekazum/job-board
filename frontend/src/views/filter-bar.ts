import type { PostingFacets, PostingQuery, Source } from "../api/domain";
import { el } from "../ui/dom";

const DEBOUNCE_MS = 250;

export interface FilterBarCallbacks {
  onChange(query: PostingQuery): void;
}

/**
 * Search (title, or title + description), a location search, company and source pickers, a minimum-fit slider
 * (0 = any), and Clear. Typing is debounced 250 ms; every other control reports at once.
 */
export class FilterBar {
  readonly element: HTMLElement;
  private readonly callbacks: FilterBarCallbacks;
  private readonly search: HTMLInputElement;
  private readonly inText: HTMLInputElement;
  private readonly location: HTMLInputElement;
  private readonly companies: HTMLElement;
  private readonly sources: HTMLElement;
  private readonly companySummary: HTMLElement;
  private readonly sourceSummary: HTMLElement;
  private readonly minFit: HTMLInputElement;
  private readonly minFitLabel: HTMLElement;
  private query: PostingQuery = {};
  private timer: number | undefined;
  private locationTimer: number | undefined;

  constructor(callbacks: FilterBarCallbacks) {
    this.callbacks = callbacks;
    this.search = el("input", { type: "search", placeholder: "Search titles…", "aria-label": "Search", class: "filter-search" });
    this.search.addEventListener("input", () => {
      window.clearTimeout(this.timer);
      this.timer = window.setTimeout(() => this.update({ q: this.search.value }), DEBOUNCE_MS);
    });
    this.inText = el("input", { type: "checkbox", id: "filter-in-text" });
    this.inText.addEventListener("change", () => this.update({ in_text: this.inText.checked }));
    this.location = el("input", { type: "search", placeholder: "Location…", "aria-label": "Location", class: "filter-location" });
    this.location.addEventListener("input", () => {
      window.clearTimeout(this.locationTimer);
      this.locationTimer = window.setTimeout(() => this.update({ location: this.location.value }), DEBOUNCE_MS);
    });
    this.companies = el("div", { class: "multi-options" });
    this.sources = el("div", { class: "multi-options" });
    this.companySummary = el("summary", {}, "Companies");
    this.sourceSummary = el("summary", {}, "Sources");
    this.minFit = el("input", { type: "range", min: "0", max: "10", step: "1", value: "0", "aria-label": "Minimum fit" });
    this.minFitLabel = el("span", { class: "filter-fit-label" }, "Fit: any");
    this.minFit.addEventListener("input", () => {
      const value = Number(this.minFit.value);
      this.update({ min_fit: value > 0 ? value : null });
    });
    const clear = el("button", { type: "button", class: "button-ghost" }, "Clear");
    clear.addEventListener("click", () => this.setQuery({}, true));
    this.element = el(
      "div",
      { class: "filter-bar", role: "search" },
      this.search,
      el("label", { class: "filter-check", for: "filter-in-text" }, this.inText, "search description"),
      this.location,
      el("details", { class: "multi" }, this.companySummary, this.companies),
      el("details", { class: "multi" }, this.sourceSummary, this.sources),
      el("label", { class: "filter-fit" }, this.minFitLabel, this.minFit),
      clear,
    );
  }

  /** Show a filter (from the URL or the last session) without typing it; notify only when asked. */
  setQuery(query: PostingQuery, notify = false): void {
    this.query = { ...query };
    this.search.value = query.q ?? "";
    this.inText.checked = query.in_text ?? false;
    this.location.value = query.location ?? "";
    this.minFit.value = String(query.min_fit ?? 0);
    this.syncChoices();
    if (notify) {
      this.callbacks.onChange(this.query);
    }
  }

  /** Offer the companies and sources that currently have postings (selected ones stay listed). */
  setFacets(facets: PostingFacets): void {
    const companies = [...new Set([...facets.companies, ...(this.query.company ?? [])])];
    const sources = [...new Set<Source>([...facets.sources, ...(this.query.source ?? [])])];
    this.companies.replaceChildren(...companies.map((name) => this.option(name, "company")));
    this.sources.replaceChildren(...sources.map((name) => this.option(name, "source")));
    this.syncChoices();
  }

  private option(value: string, kind: "company" | "source"): HTMLElement {
    const box = el("input", { type: "checkbox", value });
    box.dataset.kind = kind;
    box.addEventListener("change", () => this.update(kind === "company" ? { company: this.checked("company") } : { source: this.checked("source") as Source[] }));
    return el("label", { class: "multi-option" }, box, value);
  }

  private checked(kind: "company" | "source"): string[] {
    const list = kind === "company" ? this.companies : this.sources;
    return [...list.querySelectorAll<HTMLInputElement>("input:checked")].map((box) => box.value);
  }

  private update(change: Partial<PostingQuery>): void {
    this.query = { ...this.query, ...change };
    this.syncChoices();
    this.callbacks.onChange(this.query);
  }

  /** Tick the selected options and show counts and the fit value. */
  private syncChoices(): void {
    const companies = new Set(this.query.company ?? []);
    const sources = new Set<string>(this.query.source ?? []);
    for (const box of this.companies.querySelectorAll<HTMLInputElement>("input")) {
      box.checked = companies.has(box.value);
    }
    for (const box of this.sources.querySelectorAll<HTMLInputElement>("input")) {
      box.checked = sources.has(box.value);
    }
    this.companySummary.textContent = companies.size ? `Companies (${companies.size})` : "Companies";
    this.sourceSummary.textContent = sources.size ? `Sources (${sources.size})` : "Sources";
    const minFit = this.query.min_fit ?? 0;
    this.minFitLabel.textContent = minFit > 0 ? `Fit ≥ ${minFit}` : "Fit: any";
  }
}
