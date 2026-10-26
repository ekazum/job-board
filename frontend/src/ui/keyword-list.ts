import { el } from "./dom";

/**
 * An editable list of job-title keywords shown as chips. What is typed in the box is added as one entry on Enter or
 * Add, commas and spaces included, so a phrase ("Engineering Director") is never split; pasted lines become one entry
 * each. × removes an entry; repeats (ignoring case) are skipped.
 */
export class KeywordList {
  readonly element: HTMLElement;
  private readonly chips: HTMLElement;
  private readonly input: HTMLInputElement;
  private readonly emptyText: string;
  private keywords: string[] = [];

  constructor(id: string, label: string, placeholder: string, emptyText: string) {
    this.emptyText = emptyText;
    this.input = el("input", { id, type: "text", placeholder, autocomplete: "off" });
    this.input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        this.addTyped();
      }
    });
    const addButton = el("button", { type: "button", class: "button-ghost" }, "Add");
    addButton.addEventListener("click", () => this.addTyped());
    this.chips = el("ul", { class: "keyword-chips", "aria-label": label });
    this.element = el(
      "div",
      { class: "keyword-list" },
      el("label", { for: id }, label),
      this.chips,
      el("div", { class: "keyword-add" }, this.input, addButton),
    );
    this.render();
  }

  show(keywords: string[]): void {
    this.keywords = [];
    this.add(keywords);
  }

  /** The entries, after adding whatever is still typed in the box (so Save does not drop it). */
  collect(): string[] {
    this.addTyped();
    return [...this.keywords];
  }

  private addTyped(): void {
    this.add(this.input.value.split("\n"));
    this.input.value = "";
  }

  private add(entries: string[]): void {
    for (const entry of entries.map((value) => value.trim())) {
      if (entry && !this.keywords.some((keyword) => keyword.toLowerCase() === entry.toLowerCase())) {
        this.keywords.push(entry);
      }
    }
    this.render();
  }

  private remove(keyword: string): void {
    this.keywords = this.keywords.filter((kept) => kept !== keyword);
    this.render();
    this.input.focus();
  }

  private render(): void {
    if (this.keywords.length === 0) {
      this.chips.replaceChildren(el("li", { class: "keyword-empty" }, this.emptyText));
      return;
    }
    this.chips.replaceChildren(...this.keywords.map((keyword) => this.chip(keyword)));
  }

  private chip(keyword: string): HTMLElement {
    const removeButton = el("button", { type: "button", class: "keyword-remove", "aria-label": `Remove ${keyword}`, title: "Remove" }, "×");
    removeButton.addEventListener("click", () => this.remove(keyword));
    return el("li", { class: "keyword-chip" }, el("span", {}, keyword), removeButton);
  }
}
