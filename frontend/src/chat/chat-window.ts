import { deleteChat, errorMessage, getChatHistory, streamChat } from "../api/api";
import type { ChatLine } from "../api/domain";
import { el } from "../ui/dom";
import type { ChatStreamEvent } from "./chat-stream";

export interface ChatWindowCallbacks {
  /** The user clicked a #id the agent wrote. */
  onOpenPosting(id: number): void;
}

const THREAD_KEY = "job-board:chat-thread";
// **bold** (the model writes some Markdown) and #42 (a posting the user can open).
const MARKUP = /\*\*(.+?)\*\*|#(\d+)/g;
const TICK_MS = 1000;

type LineRole = ChatLine["role"] | "error";

/**
 * The chat window: questions about the board answered by the agent from the board's own data. The answer streams in
 * as the model writes it, with a chip for each tool it uses; #42 in an answer opens that posting. The conversation is
 * kept on the server (its id in this browser), so it is still here after a reload; New chat starts over.
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

  /** The saved conversation, or a hint when there is none. */
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
    this.addLine("user", text);
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
        this.log.insertBefore(this.chip(`${String(data.name)}…`), answer);
      } else if (event.event === "tool_result") {
        const chips = this.log.querySelectorAll<HTMLElement>(".chat-tool");
        const last = chips[chips.length - 1];
        if (last !== undefined) {
          last.textContent = `${String(data.name)} · ${String(data.summary)}`;
        }
        this.status.dataset.step = "writing the answer";
      } else if (event.event === "error" && typeof data.message === "string") {
        this.addLine("error", data.message === "stopped" ? "Stopped." : `The answer stopped: ${data.message}`);
      }
    };
    try {
      await streamChat(text, this.threadId, onEvent, controller.signal);
    } catch (error) {
      this.addLine("error", controller.signal.aborted ? "Stopped." : `Could not get an answer: ${errorMessage(error)}`);
    } finally {
      if (written === "") {
        answer.remove();
      }
      this.setRunning(null);
    }
  }

  private async startOver(): Promise<void> {
    this.running?.abort();
    const old = this.threadId;
    this.forgetThread();
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
        "Ask about your board, e.g. “Which new jobs fit me best?” or “What gaps keep coming up?”. On the local model an answer can take a minute or two.",
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
