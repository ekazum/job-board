import "./style.css";

import { errorMessage, getPostingFacets, getPostings } from "./api";
import { Board } from "./board";
import { CompaniesView } from "./companies-view";
import { el } from "./dom";
import type { Posting, PostingQuery } from "./domain";
import { FilterBar } from "./filter-bar";
import { fromSearchParams, isEmpty, loadRemembered, remember, writeToUrl } from "./filter-url";
import { Notice } from "./notice";
import { OutcomeDialog } from "./outcome-dialog";
import { PasteForm } from "./paste-form";
import { PostingDetails } from "./posting-details";
import { SettingsView } from "./settings-view";
import { SidePanel } from "./side-panel";

const app = document.querySelector<HTMLDivElement>("#app");
if (app === null) {
  throw new Error("#app element missing from index.html");
}

const notice = new Notice(document.body);
const panel = new SidePanel(document.body);
const outcomeDialog = new OutcomeDialog(document.body);

const boardTab = el("a", { href: "#board", class: "tab" }, "Board");
const companiesTab = el("a", { href: "#companies", class: "tab" }, "Companies");
const settingsTab = el("a", { href: "#settings", class: "tab" }, "Settings");
const addButton = el("button", { type: "button", class: "button-primary topbar-action" }, "Add posting");
const boardRoot = el("main", { class: "board" });
let filter: PostingQuery = {};

const detailsKey = (posting: Posting): string => `posting:${posting.id}`;

const details = new PostingDetails({
  onSaved: (posting) => board.upsert(posting),
  onError: (message) => notice.error(message),
});

const board = new Board(boardRoot, outcomeDialog, {
  onOpen: (posting) => openDetails(posting),
  onMoved: (posting) => {
    if (panel.openKey === detailsKey(posting)) {
      openDetails(posting);
    }
  },
  onError: (message) => notice.error(message),
});

const pasteForm = new PasteForm({
  onCreated: (posting) => {
    notice.info(`Added “${posting.title}”`);
    void loadPostings();
  },
  onDuplicate: (posting) => {
    notice.info("Already on the board");
    openDetails(posting);
  },
  onError: (message) => notice.error(message),
});

const companiesView = new CompaniesView({
  onScanned: () => void loadPostings(),
  onInfo: (message) => notice.info(message),
  onError: (message) => notice.error(message),
});

const filterBar = new FilterBar({
  onChange: (query) => {
    filter = query;
    writeToUrl(filter);
    remember(filter);
    void loadPostings();
  },
});
const boardView = el("section", { class: "board-view", "aria-label": "Board" }, filterBar.element, boardRoot);

const settingsView = new SettingsView({
  onInfo: (message) => notice.info(message),
  onError: (message) => notice.error(message),
});

app.replaceChildren(
  el(
    "header",
    { class: "topbar" },
    el("h1", {}, "job-board"),
    el("nav", { class: "tabs", "aria-label": "Views" }, boardTab, companiesTab, settingsTab),
    addButton,
  ),
  boardView,
  companiesView.element,
  settingsView.element,
);

function openDetails(posting: Posting): void {
  panel.show(detailsKey(posting), posting.title, details.render(posting));
}

/** The filtered postings plus the facets (company and source lists, unfiltered column totals). */
async function loadPostings(): Promise<void> {
  try {
    const [postings, facets] = await Promise.all([getPostings(filter), getPostingFacets()]);
    filterBar.setFacets(facets);
    board.setTotals(facets.totals);
    board.load(postings);
  } catch (error) {
    notice.error(`Could not load postings: ${errorMessage(error)}`);
  }
}

/** The filter in the address bar wins (a reload or a shared link); otherwise the last one used in this browser. */
function initialFilter(): PostingQuery {
  const fromUrl = fromSearchParams(new URLSearchParams(window.location.search));
  return isEmpty(fromUrl) ? loadRemembered() : fromUrl;
}

function markCurrent(tab: HTMLElement, current: boolean): void {
  if (current) {
    tab.setAttribute("aria-current", "page");
  } else {
    tab.removeAttribute("aria-current");
  }
}

/** #companies and #settings show those views; anything else shows the board. */
function showView(): void {
  const companies = window.location.hash === "#companies";
  const settings = window.location.hash === "#settings";
  boardView.hidden = companies || settings;
  companiesView.element.hidden = !companies;
  settingsView.element.hidden = !settings;
  markCurrent(boardTab, !companies && !settings);
  markCurrent(companiesTab, companies);
  markCurrent(settingsTab, settings);
  if (companies) {
    void companiesView.load();
  }
  if (settings) {
    void settingsView.load();
  }
}

addButton.addEventListener("click", () => panel.show("paste", "Add posting", pasteForm.render()));
window.addEventListener("hashchange", showView);

filter = initialFilter();
filterBar.setQuery(filter);
writeToUrl(filter);
showView();
void loadPostings();
