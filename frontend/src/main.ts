import "./style.css";

import { errorMessage, getLlmSettings, getPosting, getPostingFacets, getPostings } from "./api/api";
import { isArchived, type Posting, type PostingQuery } from "./api/domain";
import { ChatWindow } from "./chat/chat-window";
import { PasteForm } from "./panels/paste-form";
import { PostingDetails } from "./panels/posting-details";
import { SidePanel } from "./panels/side-panel";
import { ConfirmDialog } from "./ui/confirm-dialog";
import { el } from "./ui/dom";
import { Notice } from "./ui/notice";
import { OutcomeDialog } from "./ui/outcome-dialog";
import { ArchiveView } from "./views/archive-view";
import { Board } from "./views/board";
import { CompaniesView } from "./views/companies-view";
import { FilterBar } from "./views/filter-bar";
import { fromSearchParams, isEmpty, loadRemembered, remember, writeToUrl } from "./views/filter-url";
import { ProfileView } from "./views/profile-view";
import { SettingsView } from "./views/settings-view";

const app = document.querySelector<HTMLDivElement>("#app");
if (app === null) {
  throw new Error("#app element missing from index.html");
}

const notice = new Notice(document.body);
const panel = new SidePanel(document.body);
const outcomeDialog = new OutcomeDialog(document.body);
const confirmDialog = new ConfirmDialog(document.body);

const boardTab = el("a", { href: "#board", class: "tab" }, "Board");
const archiveTab = el("a", { href: "#archive", class: "tab" }, "Archive");
const companiesTab = el("a", { href: "#companies", class: "tab" }, "Companies");
const profileTab = el("a", { href: "#profile", class: "tab" }, "Profile");
const settingsTab = el("a", { href: "#settings", class: "tab" }, "Settings");
const addButton = el("button", { type: "button", class: "button-primary topbar-action" }, "Add posting");
const chatButton = el("button", { type: "button", class: "button-ghost", "aria-label": "Open the chat" }, "Chat");
const boardRoot = el("main", { class: "board" });
let filter: PostingQuery = {};

const detailsKey = (posting: Posting): string => `posting:${posting.id}`;

const details = new PostingDetails({
  onSaved: (posting) => board.upsert(posting),
  onRefresh: (posting) => {
    if (isArchived(posting)) {
      notice.info(`Moved to the Archive: ${posting.fit_reason ?? "not relevant"}`);
      void loadPostings();
    } else {
      board.upsert(posting);
    }
    openDetails(posting);
  },
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

const archiveView = new ArchiveView(confirmDialog, {
  onReopened: (posting) => {
    notice.info(`Re-opened “${posting.title}”`);
    void loadPostings();
  },
  onInfo: (message) => notice.info(message),
  onError: (message) => notice.error(message),
});

const profileView = new ProfileView({
  onPostingsChanged: () => void loadPostings(),
  onInfo: (message) => notice.info(message),
  onError: (message) => notice.error(message),
});

const settingsView = new SettingsView({
  onInfo: (message) => notice.info(message),
  onError: (message) => notice.error(message),
});

app.replaceChildren(
  el(
    "header",
    { class: "topbar" },
    el("h1", {}, "job-board"),
    el("nav", { class: "tabs", "aria-label": "Views" }, boardTab, archiveTab, companiesTab, profileTab, settingsTab),
    addButton,
    chatButton,
  ),
  boardView,
  archiveView.element,
  companiesView.element,
  profileView.element,
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

/** llm.threshold, so the board greys fits below it; without it the fits just show plain. */
async function loadThreshold(): Promise<void> {
  try {
    board.setThreshold((await getLlmSettings()).threshold);
  } catch {
    // the board works without it
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

/** The views besides the board, each behind its own tab and URL hash. */
const views = [
  { hash: "#archive", tab: archiveTab, view: archiveView },
  { hash: "#companies", tab: companiesTab, view: companiesView },
  { hash: "#profile", tab: profileTab, view: profileView },
  { hash: "#settings", tab: settingsTab, view: settingsView },
];

/** A view's hash shows that view (and loads it); anything else shows the board. */
function showView(): void {
  const current = views.find(({ hash }) => hash === window.location.hash);
  boardView.hidden = current !== undefined;
  markCurrent(boardTab, current === undefined);
  for (const entry of views) {
    const shown = entry === current;
    entry.view.element.hidden = !shown;
    markCurrent(entry.tab, shown);
    if (shown) {
      void entry.view.load();
    }
  }
}

const chatWindow = new ChatWindow({
  onOpenPosting: (id) => {
    getPosting(id).then(openDetails, (error: unknown) => notice.error(`Could not open #${id}: ${errorMessage(error)}`));
  },
  onBoardChanged: () => {
    void loadPostings();
    companiesView.followScan().catch((error: unknown) => notice.error(errorMessage(error)));
  },
});
document.body.append(chatWindow.element);

addButton.addEventListener("click", () => panel.show("paste", "Add posting", pasteForm.render()));
chatButton.addEventListener("click", () => chatWindow.toggle());
window.addEventListener("hashchange", showView);

filter = initialFilter();
filterBar.setQuery(filter);
writeToUrl(filter);
showView();
void loadPostings();
void loadThreshold();
