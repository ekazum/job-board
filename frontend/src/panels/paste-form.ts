import { createPosting, errorMessage } from "../api/api";
import type { Posting } from "../api/domain";
import { el } from "../ui/dom";

export interface PasteFormCallbacks {
  onCreated(posting: Posting): void;
  onDuplicate(posting: Posting): void;
  onError(message: string): void;
}

/** Form for a posting found anywhere else. The server stores it with source=manual, external_id=canonical URL. */
export class PasteForm {
  private readonly callbacks: PasteFormCallbacks;

  constructor(callbacks: PasteFormCallbacks) {
    this.callbacks = callbacks;
  }

  render(): HTMLFormElement {
    const company = el("input", { id: "paste-company", required: true, autocomplete: "off", autofocus: true });
    const title = el("input", { id: "paste-title", required: true, autocomplete: "off" });
    const url = el("input", { id: "paste-url", type: "url", required: true, placeholder: "https://…" });
    const text = el("textarea", { id: "paste-text", rows: "14", placeholder: "Paste the job description" });
    const submit = el("button", { type: "submit", class: "button-primary" }, "Add to board");
    const form = el(
      "form",
      { class: "paste-form" },
      this.field("Company", company),
      this.field("Title", title),
      this.field("URL", url),
      this.field("Description", text),
      el("div", { class: "field-actions" }, submit),
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this.submit(form, submit, { company, title, url, text });
    });
    return form;
  }

  private field(label: string, control: HTMLInputElement | HTMLTextAreaElement): HTMLElement {
    return el("label", { class: "field", for: control.id }, el("span", {}, label), control);
  }

  private async submit(
    form: HTMLFormElement,
    submit: HTMLButtonElement,
    fields: { company: HTMLInputElement; title: HTMLInputElement; url: HTMLInputElement; text: HTMLTextAreaElement },
  ): Promise<void> {
    submit.disabled = true;
    try {
      const { posting, created } = await createPosting({
        company: fields.company.value,
        title: fields.title.value,
        url: fields.url.value,
        text: fields.text.value,
      });
      if (created) {
        form.reset();
        fields.company.focus();
        this.callbacks.onCreated(posting);
      } else {
        this.callbacks.onDuplicate(posting);
      }
    } catch (error) {
      this.callbacks.onError(errorMessage(error));
    } finally {
      submit.disabled = false;
    }
  }
}
