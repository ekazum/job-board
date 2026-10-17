import { createCompany, errorMessage, getCompanies, patchCompany, runDiscover, runScan } from "./api";
import { el } from "./dom";
import { PLATFORM_LABELS, byName, formatDateTime, isWebUrl, type Company, type RunSummary } from "./domain";

export interface CompaniesViewCallbacks {
  /** A scan finished; the board should reload its postings. */
  onScanned(): void;
  onInfo(message: string): void;
  onError(message: string): void;
}

const COLUMNS = ["Name", "Platform", "Slug", "Careers URL", "Verified", "Enabled"];

/**
 * Companies table with Add company, Discover and Scan. The careers URL of each company is editable in place
 * (Discover fetches it first). Discover and Scan answer when the run is done; both buttons stay disabled until
 * then (the server also refuses a second run with 409). A company's last error is shown under its platform.
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
    this.discoverButton.addEventListener("click", () => void this.run("Discover", this.discoverButton, runDiscover));
    this.scanButton.addEventListener("click", () => void this.run("Scan", this.scanButton, runScan));
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
        "Discover finds each company's job board, starting from its careers URL. Scan adds matching jobs to the board as New.",
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
    const careersUrl = el("input", {
      type: "url",
      "aria-label": "Careers URL (optional)",
      placeholder: "https://… careers page (optional)",
      autocomplete: "off",
      class: "careers-input",
    });
    const submit = el("button", { type: "submit", class: "button-ghost" }, "Add company");
    const form = el("form", { class: "add-company" }, name, domain, careersUrl, submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this.add(form, { name, domain, careersUrl }, submit);
    });
    return form;
  }

  private async add(
    form: HTMLFormElement,
    fields: { name: HTMLInputElement; domain: HTMLInputElement; careersUrl: HTMLInputElement },
    submit: HTMLButtonElement,
  ): Promise<void> {
    submit.disabled = true;
    try {
      const { company, created } = await createCompany({
        name: fields.name.value,
        domain: fields.domain.value,
        careers_url: fields.careersUrl.value || null,
      });
      if (created) {
        this.upsert(company);
        form.reset();
        fields.name.focus();
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

  /** Run Discover or Scan with both buttons disabled; show {ok, failed, duration} and reload. */
  private async run(label: string, button: HTMLButtonElement, call: () => Promise<RunSummary>): Promise<void> {
    const text = button.textContent ?? label;
    this.setRunning(true);
    button.textContent = `${label} running…`;
    try {
      const summary = await call();
      const failed = summary.failed === 0 ? "" : " · failed companies show their error in red below";
      this.summary.textContent = `${label}: ${summary.ok} ok · ${summary.failed} failed · ${summary.duration_s} s${failed}`;
      this.summary.hidden = false;
      await this.load();
      if (label === "Scan") {
        this.callbacks.onScanned();
      }
    } catch (error) {
      this.callbacks.onError(errorMessage(error));
    } finally {
      button.textContent = text;
      this.setRunning(false);
    }
  }

  private setRunning(running: boolean): void {
    this.discoverButton.disabled = running;
    this.scanButton.disabled = running;
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
      el("td", { class: "careers-cell" }, this.careersUrlField(company)),
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
    const cell = el("div", { class: "platform-cell" });
    if (company.platform === null) {
      cell.append(el("span", { class: "muted" }, "Not discovered"));
    } else {
      const checked = company.last_checked === null ? "" : `Checked ${formatDateTime(company.last_checked)}`;
      cell.append(el("span", { class: company.platform === "none" ? "muted" : "", title: checked }, PLATFORM_LABELS[company.platform]));
    }
    if (company.last_error !== null) {
      cell.append(el("div", { class: "company-error", title: company.last_error }, company.last_error));
    }
    return cell;
  }

  /** An inline URL field; Enter or leaving the field saves a changed value (empty clears it). */
  private careersUrlField(company: Company): HTMLElement {
    const input = el("input", {
      type: "url",
      class: "careers-input",
      placeholder: "https://…",
      "aria-label": `Careers URL of ${company.name}`,
    });
    input.value = company.careers_url ?? "";
    const save = (): void => {
      const value = input.value.trim();
      if (value !== (company.careers_url ?? "")) {
        void this.setCareersUrl(company, input, value);
      }
    };
    input.addEventListener("change", save);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        input.blur();
      }
    });
    const link =
      company.careers_url !== null && isWebUrl(company.careers_url)
        ? el("a", { href: company.careers_url, target: "_blank", rel: "noopener noreferrer", class: "careers-open", title: "Open" }, "↗")
        : null;
    return el("div", { class: "careers-field" }, input, link);
  }

  private async setCareersUrl(company: Company, input: HTMLInputElement, value: string): Promise<void> {
    input.disabled = true;
    try {
      this.upsert(await patchCompany(company.id, { careers_url: value || null }));
      this.callbacks.onInfo(value ? `Saved careers URL for ${company.name}` : `Cleared careers URL for ${company.name}`);
    } catch (error) {
      input.value = company.careers_url ?? "";
      input.disabled = false;
      this.callbacks.onError(errorMessage(error));
    }
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
