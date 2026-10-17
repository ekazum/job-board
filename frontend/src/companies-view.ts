import { createCompany, errorMessage, getCompanies, patchCompany, runDiscover, runScan } from "./api";
import { el } from "./dom";
import { PLATFORM_LABELS, byName, formatDateTime, type Company, type RunIssue } from "./domain";

export interface CompaniesViewCallbacks {
  /** A scan finished; the board should reload its postings. */
  onScanned(): void;
  onInfo(message: string): void;
  onError(message: string): void;
}

const COLUMNS = ["Name", "Platform", "Slug", "Verified", "Enabled"];

/**
 * Companies table with Add company, Discover and Scan. Discover and Scan run synchronously on the server
 * and can take minutes; both buttons stay disabled until the run returns (the server also refuses a second
 * run with 409).
 */
export class CompaniesView {
  readonly element: HTMLElement;
  private companies: Company[] = [];
  private readonly callbacks: CompaniesViewCallbacks;
  private readonly tbody: HTMLTableSectionElement;
  private readonly summary: HTMLElement;
  private readonly discoverButton: HTMLButtonElement;
  private readonly scanButton: HTMLButtonElement;

  constructor(callbacks: CompaniesViewCallbacks) {
    this.callbacks = callbacks;
    this.discoverButton = el("button", { type: "button", class: "button-primary" }, "Discover");
    this.scanButton = el("button", { type: "button", class: "button-primary" }, "Scan");
    this.discoverButton.addEventListener("click", () => void this.discover());
    this.scanButton.addEventListener("click", () => void this.scan());
    this.summary = el("section", { class: "run-summary", "aria-live": "polite", hidden: true });
    this.tbody = el("tbody");
    const head = el("thead", {}, el("tr", {}, ...COLUMNS.map((column) => el("th", { scope: "col" }, column))));
    this.element = el(
      "section",
      { class: "companies-view", "aria-label": "Companies" },
      el(
        "div",
        { class: "companies-toolbar" },
        this.addForm(),
        el("div", { class: "run-buttons" }, this.discoverButton, this.scanButton),
      ),
      el(
        "p",
        { class: "muted companies-hint" },
        "Discover finds each company's job board. Scan adds matching jobs to the board as New. Each can take a few minutes.",
      ),
      this.summary,
      el("div", { class: "table-wrap" }, el("table", { class: "companies-table" }, head, this.tbody)),
    );
    this.render();
  }

  async load(): Promise<void> {
    try {
      this.companies = (await getCompanies()).sort(byName);
      this.render();
    } catch (error) {
      this.callbacks.onError(`Could not load companies: ${errorMessage(error)}`);
    }
  }

  private addForm(): HTMLFormElement {
    const name = el("input", { "aria-label": "Company name", placeholder: "Company", required: true, autocomplete: "off" });
    const domain = el("input", { "aria-label": "Domain", placeholder: "domain.com", required: true, autocomplete: "off" });
    const submit = el("button", { type: "submit", class: "button-ghost" }, "Add company");
    const form = el("form", { class: "add-company" }, name, domain, submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this.add(form, name, domain, submit);
    });
    return form;
  }

  private async add(form: HTMLFormElement, name: HTMLInputElement, domain: HTMLInputElement, submit: HTMLButtonElement): Promise<void> {
    submit.disabled = true;
    try {
      const { company, created } = await createCompany({ name: name.value, domain: domain.value });
      if (created) {
        this.upsert(company);
        form.reset();
        name.focus();
        this.callbacks.onInfo(`Added ${company.name}. Click Discover to find its job board.`);
      } else {
        this.callbacks.onInfo(`${company.name} is already in the list`);
      }
    } catch (error) {
      this.callbacks.onError(errorMessage(error));
    } finally {
      submit.disabled = false;
    }
  }

  private async discover(): Promise<void> {
    const result = await this.run(this.discoverButton, "Discovering…", runDiscover);
    if (result === null) {
      return;
    }
    this.showSummary(
      `Discover: ${result.companies} companies · ${result.verified} verified · ${result.unverified} unverified · ` +
        `${result.no_platform} no supported platform`,
      result.issues,
    );
    await this.load();
  }

  private async scan(): Promise<void> {
    const result = await this.run(this.scanButton, "Scanning…", runScan);
    if (result === null) {
      return;
    }
    this.showSummary(
      `Scan: ${result.companies} companies · ${result.jobs_seen.toLocaleString()} jobs seen · ` +
        `${result.matched.toLocaleString()} matched · ${result.added.toLocaleString()} added to New`,
      result.issues,
    );
    this.callbacks.onScanned();
  }

  /** Disable both run buttons while one run is in flight; null when it failed (already reported). */
  private async run<T>(button: HTMLButtonElement, busyLabel: string, call: () => Promise<T>): Promise<T | null> {
    const label = button.textContent ?? "";
    this.setRunning(true);
    button.textContent = busyLabel;
    try {
      return await call();
    } catch (error) {
      this.callbacks.onError(errorMessage(error));
      return null;
    } finally {
      button.textContent = label;
      this.setRunning(false);
    }
  }

  private setRunning(running: boolean): void {
    this.discoverButton.disabled = running;
    this.scanButton.disabled = running;
  }

  private showSummary(text: string, issues: RunIssue[]): void {
    const items = issues.map((issue) => el("li", {}, el("strong", {}, issue.company), `: ${issue.message}`));
    this.summary.replaceChildren(el("p", {}, text));
    if (items.length > 0) {
      this.summary.append(el("ul", { class: "run-issues" }, ...items));
    }
    this.summary.hidden = false;
  }

  private upsert(company: Company): void {
    const index = this.companies.findIndex((existing) => existing.id === company.id);
    if (index === -1) {
      this.companies.push(company);
    } else {
      this.companies[index] = company;
    }
    this.companies.sort(byName);
    this.render();
  }

  private render(): void {
    if (this.companies.length === 0) {
      const empty = el(
        "td",
        { colspan: String(COLUMNS.length), class: "muted empty" },
        "No companies yet. Add one above, or list them in config.yaml and click Discover.",
      );
      this.tbody.replaceChildren(el("tr", {}, empty));
      return;
    }
    this.tbody.replaceChildren(...this.companies.map((company) => this.row(company)));
  }

  private row(company: Company): HTMLTableRowElement {
    const toggle = el("input", {
      type: "checkbox",
      role: "switch",
      class: "switch",
      checked: company.enabled,
      "aria-label": `Scan ${company.name}`,
    });
    toggle.addEventListener("change", () => void this.setEnabled(company, toggle));
    return el(
      "tr",
      { class: company.enabled ? "" : "row-disabled" },
      el(
        "td",
        {},
        el("div", { class: "company-name" }, company.name),
        company.domain === null ? null : el("div", { class: "muted company-domain" }, company.domain),
      ),
      el("td", {}, this.platformCell(company)),
      el("td", {}, company.slug === null ? el("span", { class: "muted" }, "—") : el("code", {}, company.slug)),
      el(
        "td",
        {},
        company.verified
          ? el("span", { class: "verified", title: "The board's public API answered" }, "✓ Verified")
          : el("span", { class: "muted" }, "—"),
      ),
      el("td", {}, toggle),
    );
  }

  private platformCell(company: Company): HTMLElement {
    if (company.platform === null) {
      return el("span", { class: "muted" }, "Not discovered");
    }
    const checked = company.last_checked === null ? "" : `Checked ${formatDateTime(company.last_checked)}`;
    const label = PLATFORM_LABELS[company.platform];
    return el("span", { class: company.platform === "none" ? "muted" : "", title: checked }, label);
  }

  private async setEnabled(company: Company, toggle: HTMLInputElement): Promise<void> {
    toggle.disabled = true;
    try {
      this.upsert(await patchCompany(company.id, { enabled: toggle.checked }));
    } catch (error) {
      toggle.checked = !toggle.checked;
      toggle.disabled = false;
      this.callbacks.onError(errorMessage(error));
    }
  }
}
