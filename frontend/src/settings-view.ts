import { errorMessage, getLlmSettings, setLlmProvider, testLlm } from "./api";
import { el } from "./dom";
import type { LlmSettingsView, LlmTestResult } from "./domain";

export interface SettingsViewCallbacks {
  onInfo(message: string): void;
  onError(message: string): void;
}

/**
 * LLM settings: the active provider and model from config.yaml, a drop-down that switches provider (the server
 * rewrites llm.provider and reloads), and a Test button that sends one tiny prompt and shows latency and the raw
 * answer.
 */
export class SettingsView {
  readonly element: HTMLElement;
  private readonly callbacks: SettingsViewCallbacks;
  private readonly providerSelect: HTMLSelectElement;
  private readonly details: HTMLElement;
  private readonly testButton: HTMLButtonElement;
  private readonly result: HTMLElement;

  constructor(callbacks: SettingsViewCallbacks) {
    this.callbacks = callbacks;
    this.providerSelect = el("select", { id: "llm-provider", "aria-label": "LLM provider" });
    this.providerSelect.addEventListener("change", () => void this.switchProvider(this.providerSelect.value));
    this.details = el("dl", { class: "settings-details" });
    this.testButton = el("button", { type: "button", class: "button-primary" }, "Test");
    this.testButton.addEventListener("click", () => void this.test());
    this.result = el("section", { class: "llm-result", "aria-live": "polite", hidden: true });
    this.element = el(
      "section",
      { class: "settings-view", "aria-label": "Settings" },
      el("h2", { class: "settings-heading" }, "LLM"),
      el(
        "div",
        { class: "settings-row" },
        el("label", { for: "llm-provider" }, "Provider"),
        this.providerSelect,
        this.testButton,
      ),
      this.details,
      this.result,
    );
  }

  async load(): Promise<void> {
    try {
      this.show(await getLlmSettings());
    } catch (error) {
      this.callbacks.onError(`Could not load settings: ${errorMessage(error)}`);
    }
  }

  private show(settings: LlmSettingsView): void {
    this.providerSelect.replaceChildren(
      ...settings.providers.map((name) => el("option", { value: name, selected: name === settings.provider }, name)),
    );
    const key = settings.api_key_env.toUpperCase() === "NONE" ? "not needed" : `${settings.api_key_env} ${settings.api_key_set ? "(set in .env)" : "(missing in .env)"}`;
    const rows: [string, string][] = [
      ["Model", settings.model],
      ["Endpoint", settings.base_url],
      ["API key", key],
      ["Concurrency", String(settings.concurrency)],
      ["JSON mode", settings.json_mode ? "on" : "off"],
      ["Threshold", String(settings.threshold)],
      ["Text sent", `${settings.max_text_chars.toLocaleString()} characters`],
    ];
    this.details.replaceChildren(...rows.flatMap(([term, value]) => [el("dt", {}, term), el("dd", {}, value)]));
    this.details.classList.toggle("key-missing", !settings.api_key_set);
  }

  private async switchProvider(provider: string): Promise<void> {
    this.providerSelect.disabled = true;
    try {
      this.show(await setLlmProvider(provider));
      this.result.hidden = true;
      this.callbacks.onInfo(`Switched to ${provider} (saved in config.yaml)`);
    } catch (error) {
      this.callbacks.onError(errorMessage(error));
      await this.load();
    } finally {
      this.providerSelect.disabled = false;
    }
  }

  private async test(): Promise<void> {
    this.testButton.disabled = true;
    this.testButton.textContent = "Testing…";
    try {
      this.showResult(await testLlm());
    } catch (error) {
      this.callbacks.onError(errorMessage(error));
    } finally {
      this.testButton.disabled = false;
      this.testButton.textContent = "Test";
    }
  }

  private showResult(result: LlmTestResult): void {
    const status = result.ok
      ? el("p", { class: "llm-ok" }, `✓ ${result.provider} · ${result.model} answered in ${result.latency_ms.toLocaleString()} ms`)
      : el("p", { class: "llm-failed" }, `✗ ${result.provider} · ${result.model}: ${result.error ?? "failed"} (${result.latency_ms.toLocaleString()} ms)`);
    this.result.replaceChildren(status);
    if (result.raw) {
      this.result.append(el("pre", { class: "llm-raw" }, this.pretty(result.raw)));
    }
    this.result.hidden = false;
  }

  /** The raw answer, indented when it is JSON (shown as received otherwise). */
  private pretty(raw: string): string {
    try {
      return JSON.stringify(JSON.parse(raw), null, 2);
    } catch {
      return raw;
    }
  }
}
