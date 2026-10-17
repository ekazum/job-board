import "./style.css";

import { errorMessage, getPostings } from "./api";
import { Board } from "./board";
import { CompaniesView } from "./companies-view";
import { el } from "./dom";
import type { Posting } from "./domain";
import { Notice } from "./notice";
import { OutcomeDialog } from "./outcome-dialog";
import { PasteForm } from "./paste-form";
import { PostingDetails } from "./posting-details";
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
const addButton = el("button", { type: "button", class: "button-primary topbar-action" }, "Add posting");
const boardRoot = el("main", { class: "board" });

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
    board.upsert(posting);
    notice.info(`Added “${posting.title}”`);
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

app.replaceChildren(
  el(
    "header",
    { class: "topbar" },
    el("h1", {}, "job-board"),
    el("nav", { class: "tabs", "aria-label": "Views" }, boardTab, companiesTab),
    addButton,
  ),
  boardRoot,
  companiesView.element,
);

function openDetails(posting: Posting): void {
  panel.show(detailsKey(posting), posting.title, details.render(posting));
}

async function loadPostings(): Promise<void> {
  try {
    board.load(await getPostings());
  } catch (error) {
    notice.error(`Could not load postings: ${errorMessage(error)}`);
  }
}

function markCurrent(tab: HTMLElement, current: boolean): void {
  if (current) {
    tab.setAttribute("aria-current", "page");
  } else {
    tab.removeAttribute("aria-current");
  }
}

/** #companies shows the Companies view; anything else shows the board. */
function showView(): void {
  const companies = window.location.hash === "#companies";
  boardRoot.hidden = companies;
  companiesView.element.hidden = !companies;
  markCurrent(boardTab, !companies);
  markCurrent(companiesTab, companies);
  if (companies) {
    void companiesView.load();
  }
}

addButton.addEventListener("click", () => panel.show("paste", "Add posting", pasteForm.render()));
window.addEventListener("hashchange", showView);

showView();
void loadPostings();
