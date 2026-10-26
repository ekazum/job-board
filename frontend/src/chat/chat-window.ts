import { deleteChat, errorMessage, getChatHistory, resumeChat, streamChat } from "../api/api";
import type { ChatLine } from "../api/domain";
import { el } from "../ui/dom";
import type { ChatStreamEvent } from "./chat-stream";

export interface ChatWindowCallbacks {
  /** The user clicked a #id the agent wrote. */
  onOpenPosting(id: number): void;
  /** A change the user confirmed was made (a card moved or closed, a note added, a scan started). */
  onBoardChanged(): void;
}

const THREAD_KEY = "job-board:chat-thread";
// **bold** (the model writes some Markdown) and #42 (a posting the user can open).
const MARKUP = /\*\*(.+?)\*\*|#(\d+)/g;
const TICK_MS = 1000;

type LineRole = ChatLine["role"] | "error";
/** Sends the request whose answer streams in, handing each event to onEvent. */
type AnswerRequest = (onEvent: (event: ChatStreamEvent) => void, signal: AbortSignal) => Promise<void>;

/**
 * The chat window: questions about the board answered by the agent from the board's own data. The answer streams in
 * as the model writes it, with a chip for each tool it uses; #42 in an answer opens that posting. When the agent asks
 * to change the board, a card lists the changes with Confirm and Cancel, and nothing changes until Confirm; sending a
 * message instead cancels them. The conversation is kept on the server (its id in this browser), so it is still here
 * after a reload, a waiting card included; New chat starts over.
 */
export class ChatWindow {
  readonly element: HTMLElement;
  private readonly callbacks: ChatWindowCallbacks;
  private readonly log: HTMLElement;
  private readonly input: HTMLTextAreaElement;
  private readonly sendButton: HTMLButtonElement;
  private readonly stopButton: HTMLButtonElement;
  private readonly status: HTMLElement;
  private threadId: string | null = loadThread();
  private loaded = false;
  private running: AbortController | null = null;
  private ticker: number | undefined;
  private confirmButtons: HTMLElement | null = null;

  constructor(callbacks: ChatWindowCallbacks) {
    this.callbacks = callbacks;
    this.log = el("div", { class: "chat-log", "aria-live": "polite" });
    this.input = el("textarea", { class: "chat-input", rows: "2", placeholder: "Ask about your jobs…", "aria-label": "Message" });
    this.sendButton = el("button", { type: "submit", class: "button-primary" }, "Send");
    this.stopButton = el("button", { type: "button", class: "button-ghost", hidden: true }, "Stop");
    this.status = el("p", { class: "chat-status muted", hidden: true });
    const newButton = el("button", { type: "button", class: "button-ghost chat-new" }, "New chat");
    const closeButton = el("button", { type: "button", class: "icon-button", "aria-label": "Close chat" }, "×");
    const form = el("form", { class: "chat-form" }, this.input, this.sendButton, this.stopButton);
    this.element = el(
      "section",
      { class: "chat-window", hidden: true, "aria-label": "Chat" },
      el("header", { class: "chat-header" }, el("h2", { class: "chat-heading" }, "Chat"), newButton, closeButton),
      this.log,
      this.status,
      form,
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this.send();
    });
    this.input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        void this.send();
      }
    });
    this.stopButton.addEventListener("click", () => this.running?.abort());
    newButton.addEventListener("click", () => void this.startOver());
    closeButton.addEventListener("click", () => this.close());
  }

  toggle(): void {
    if (this.element.hidden) {
      this.open();
    } else {
      this.close();
    }
  }

  open(): void {
    this.element.hidden = false;
    this.input.focus();
    if (!this.loaded) {
      this.loaded = true;
      void this.loadHistory();
    }
  }

  close(): void {
    this.element.hidden = true;
  }

  /** The saved conversation (with the changes still waiting for a confirm), or a hint when there is none. */
  private async loadHistory(): Promise<void> {
    if (this.threadId === null) {
      this.showHint();
      return;
    }
    try {
      const history = await getChatHistory(this.threadId);
      for (const line of history.lines) {
        this.addLine(line.role, line.text);
      }
      if (history.pending.length > 0) {
        this.showConfirm(history.pending);
      }
    } catch {
      this.forgetThread(); // gone on the server (or unreadable): start fresh
      this.showHint();
    }
  }

  private async send(): Promise<void> {
    const text = this.input.value.trim();
    if (text === "" || this.running !== null) {
      return;
    }
    this.input.value = "";
    this.log.querySelector(".chat-hint")?.remove();
    this.settleConfirm("Cancelled: you sent a message instead"); // the server cancels the changes too
    this.addLine("user", text);
    await this.answer((onEvent, signal) => streamChat(text, this.threadId, onEvent, signal));
  }

  /** Confirm or cancel the changes on the card; the agent goes on from there. */
  private async resume(approve: boolean): Promise<void> {
    const threadId = this.threadId;
    if (threadId === null || this.running !== null) {
      return;
    }
    this.settleConfirm(approve ? "Confirmed" : "Cancelled");
    await this.answer((onEvent, signal) => resumeChat(threadId, approve, onEvent, signal));
  }

  /** Show an answer as it streams in: its text, a chip per tool, a card when it waits for a confirm. */
  private async answer(request: AnswerRequest): Promise<void> {
    const answer = this.addLine("assistant", "");
    const controller = new AbortController();
    this.setRunning(controller);
    let written = "";
    const onEvent = (event: ChatStreamEvent): void => {
      const { data } = event;
      if (event.event === "thread" && typeof data.thread_id === "string") {
        this.rememberThread(data.thread_id);
      } else if (event.event === "token" && typeof data.text === "string") {
        written += data.text;
        this.renderText(answer, written);
      } else if (event.event === "tool") {
        this.status.dataset.step = `using ${String(data.name)}`;
        const chip = this.chip(`${String(data.name)}…`);
        chip.dataset.pending = String(data.name);
        this.log.insertBefore(chip, answer);
      } else if (event.event === "tool_result") {
        this.showResult(String(data.name), String(data.summary));
        this.status.dataset.step = "writing the answer";
        if (data.changed === true) {
          this.callbacks.onBoardChanged();
        }
      } else if (event.event === "confirm" && Array.isArray(data.changes)) {
        this.showConfirm(data.changes.filter((change): change is string => typeof change === "string"));
      } else if (event.event === "error" && typeof data.message === "string") {
        this.addLine("error", data.message === "stopped" ? "Stopped." : `The answer stopped: ${data.message}`);
      }
    };
    try {
      await request(onEvent, controller.signal);
    } catch (error) {
      this.addLine("error", controller.signal.aborted ? "Stopped." : `Could not get an answer: ${errorMessage(error)}`);
    } finally {
      if (written === "") {
        answer.remove();
      }
      this.setRunning(null);
    }
  }

  /** The first chip still waiting for this tool's result shows it. */
  private showResult(name: string, summary: string): void {
    const chips = this.log.querySelectorAll<HTMLElement>(".chat-tool[data-pending]");
    const chip = [...chips].find((candidate) => candidate.dataset.pending === name);
    if (chip !== undefined) {
      chip.textContent = `${name} · ${summary}`;
      delete chip.dataset.pending;
    }
  }

  /** The card listing the changes the agent asks to make, with Confirm and Cancel. */
  private showConfirm(changes: string[]): void {
    this.settleConfirm("Cancelled");
    const list = el("ul", { class: "chat-confirm-list" });
    for (const change of changes) {
      const item = el("li", {});
      this.renderText(item, change);
      list.append(item);
    }
    const confirmButton = el("button", { type: "button", class: "button-primary" }, "Confirm");
    const cancelButton = el("button", { type: "button", class: "button-ghost" }, "Cancel");
    confirmButton.addEventListener("click", () => void this.resume(true));
    cancelButton.addEventListener("click", () => void this.resume(false));
    this.confirmButtons = el("div", { class: "chat-confirm-buttons" }, confirmButton, cancelButton);
    const heading = changes.length === 1 ? "Make this change?" : "Make these changes?";
    this.log.append(
      el(
        "div",
        { class: "chat-confirm", role: "group", "aria-label": heading },
        el("p", { class: "chat-confirm-heading" }, heading),
        list,
        this.confirmButtons,
      ),
    );
    this.scrollToEnd();
    confirmButton.focus();
  }

  /** The waiting card, if any, answered: its buttons give way to what happened. */
  private settleConfirm(outcome: string): void {
    this.confirmButtons?.replaceWith(el("p", { class: "chat-confirm-outcome muted" }, outcome));
    this.confirmButtons = null;
  }

  private async startOver(): Promise<void> {
    this.running?.abort();
    const old = this.threadId;
    this.forgetThread();
    this.confirmButtons = null;
    this.log.replaceChildren();
    this.showHint();
    this.input.focus();
    if (old !== null) {
      try {
        await deleteChat(old);
      } catch {
        // the old conversation stays on the server; nothing points to it any more
      }
    }
  }

  private setRunning(controller: AbortController | null): void {
    this.running = controller;
    this.sendButton.hidden = controller !== null;
    this.stopButton.hidden = controller === null;
    this.status.hidden = controller === null;
    window.clearInterval(this.ticker);
    if (controller === null) {
      return;
    }
    const started = Date.now();
    this.status.dataset.step = "thinking";
    const tick = (): void => {
      const seconds = Math.round((Date.now() - started) / 1000);
      this.status.textContent = `${this.status.dataset.step ?? "thinking"}… ${seconds} s`;
    };
    tick();
    this.ticker = window.setInterval(tick, TICK_MS);
  }

  private addLine(role: LineRole, text: string): HTMLElement {
    const line = role === "tool" ? this.chip(text) : el("div", { class: `chat-line chat-${role}` });
    if (role !== "tool") {
      this.renderText(line, text);
    }
    this.log.append(line);
    return line;
  }

  private chip(text: string): HTMLElement {
    const chip = el("div", { class: "chat-tool" }, text);
    this.log.append(chip);
    this.scrollToEnd();
    return chip;
  }

  /** The text with **bold** in bold and each #id as a button that opens that posting. */
  private renderText(node: HTMLElement, text: string): void {
    const parts: (Node | string)[] = [];
    let last = 0;
    for (const match of text.matchAll(MARKUP)) {
      parts.push(text.slice(last, match.index));
      const [whole, bold, id] = match;
      if (bold !== undefined) {
        parts.push(el("strong", {}, bold));
      } else {
        const link = el("button", { type: "button", class: "link-button", title: "Open this posting" }, whole);
        link.addEventListener("click", () => this.callbacks.onOpenPosting(Number(id)));
        parts.push(link);
      }
      last = match.index + whole.length;
    }
    parts.push(text.slice(last));
    node.replaceChildren(...parts);
    this.scrollToEnd();
  }

  private showHint(): void {
    this.log.append(
      el(
        "p",
        { class: "chat-hint muted" },
        "Ask about your board, e.g. “Which new jobs fit me best?”, or for a change, e.g. “Move #42 to Applied” (you confirm it first). On the local model an answer can take a minute or two.",
      ),
    );
  }

  private scrollToEnd(): void {
    this.log.scrollTop = this.log.scrollHeight;
  }

  private rememberThread(id: string): void {
    this.threadId = id;
    try {
      window.localStorage.setItem(THREAD_KEY, id);
    } catch {
      // Storage blocked: the conversation lasts until the page is reloaded.
    }
  }

  private forgetThread(): void {
    this.threadId = null;
    try {
      window.localStorage.removeItem(THREAD_KEY);
    } catch {
      // Storage blocked: nothing was saved.
    }
  }
}

function loadThread(): string | null {
  try {
    return window.localStorage.getItem(THREAD_KEY);
  } catch {
    return null;
  }
}
