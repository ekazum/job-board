import { applyLocations, errorMessage, getProfile, getRescoreStatus, patchProfile, startRescore, uploadProfile } from "./api";
import { el } from "./dom";
import { formatDateTime, type Profile, type RescoreStatus } from "./domain";

const POLL_MS = 1000;
const ACCEPTED = ".pdf,.docx,.md,.txt";

export interface ProfileViewCallbacks {
  /** Postings moved (a saved location was applied, or Re-score all finished); the board should reload. */
  onPostingsChanged(): void;
  onInfo(message: string): void;
  onError(message: string): void;
}

/**
 * The candidate profile the LLM scorer and the location rule read: the location (a country or a city) with the
 * fully-remote toggle, the targets, a drop zone (or file picker) for the CV and its extracted text (editable), Save
 * (which applies the location to the stored postings), and Re-score all with a progress bar.
 */
export class ProfileView {
  readonly element: HTMLElement;
  private readonly callbacks: ProfileViewCallbacks;
  private readonly dropZone: HTMLElement;
  private readonly fileInput: HTMLInputElement;
  private readonly fileInfo: HTMLElement;
  private readonly cvText: HTMLTextAreaElement;
  private readonly targets: HTMLTextAreaElement;
  private readonly location: HTMLInputElement;
  private readonly locationCountry: HTMLElement;
  private readonly allowFullyRemote: HTMLInputElement;
  private readonly saveButton: HTMLButtonElement;
  private readonly rescoreButton: HTMLButtonElement;
  private readonly progress: HTMLProgressElement;
  private readonly progressText: HTMLElement;
  private polling: number | undefined;

  constructor(callbacks: ProfileViewCallbacks) {
    this.callbacks = callbacks;
    this.fileInput = el("input", { type: "file", accept: ACCEPTED, hidden: true });
    this.fileInput.addEventListener("change", () => {
      const file = this.fileInput.files?.[0];
      if (file !== undefined) {
        void this.upload(file);
      }
      this.fileInput.value = "";
    });
    this.fileInfo = el("p", { class: "muted" }, "No CV uploaded yet.");
    this.dropZone = el(
      "div",
      { class: "drop-zone", role: "button", tabindex: "0", "aria-label": "Upload CV" },
      el("strong", {}, "Drop your CV here"),
      el("span", { class: "muted" }, " or click to choose a .pdf, .docx, .md or .txt file (max 5 MB)"),
    );
    this.dropZone.addEventListener("click", () => this.fileInput.click());
    this.dropZone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        this.fileInput.click();
      }
    });
    this.dropZone.addEventListener("dragover", (event) => {
      event.preventDefault();
      this.dropZone.classList.add("drop-zone-active");
    });
    this.dropZone.addEventListener("dragleave", () => this.dropZone.classList.remove("drop-zone-active"));
    this.dropZone.addEventListener("drop", (event) => {
      event.preventDefault();
      this.dropZone.classList.remove("drop-zone-active");
      const file = event.dataTransfer?.files[0];
      if (file !== undefined) {
        void this.upload(file);
      }
    });
    this.cvText = el("textarea", { id: "profile-cv", rows: "16", placeholder: "Extracted CV text appears here; edit it freely." });
    this.targets = el("textarea", {
      id: "profile-targets",
      rows: "4",
      placeholder: "What you are looking for, e.g. AI research or ML engineering roles in Israel, senior level.",
    });
    this.location = el("input", { id: "profile-location", type: "text", placeholder: "A country or a city, e.g. Israel" });
    this.locationCountry = el("span", { class: "muted profile-country", "aria-live": "polite" });
    this.allowFullyRemote = el("input", { id: "profile-remote", type: "checkbox" });
    this.saveButton = el("button", { type: "button", class: "button-primary" }, "Save");
    this.saveButton.addEventListener("click", () => void this.save());
    this.rescoreButton = el("button", { type: "button", class: "button-ghost" }, "Re-score all");
    this.rescoreButton.addEventListener("click", () => void this.rescoreAll());
    this.progress = el("progress", { max: "1", value: "0", hidden: true });
    this.progressText = el("span", { class: "muted", "aria-live": "polite" });
    this.element = el(
      "section",
      { class: "profile-view", "aria-label": "Profile" },
      el("h2", { class: "settings-heading" }, "Profile"),
      el(
        "div",
        { class: "field profile-location" },
        el("label", { for: "profile-location" }, "Location"),
        this.location,
        this.locationCountry,
        el("label", { class: "filter-check", for: "profile-remote" }, this.allowFullyRemote, "Also allow fully remote jobs"),
        el("p", { class: "muted" }, "Jobs elsewhere go to the Archive without an LLM call. With no location set, every job does."),
      ),
      el("label", { class: "field", for: "profile-targets" }, el("span", {}, "Targets"), this.targets),
      this.dropZone,
      this.fileInput,
      this.fileInfo,
      el("label", { class: "field", for: "profile-cv" }, el("span", {}, "CV text"), this.cvText),
      el("div", { class: "field-actions" }, this.saveButton, this.rescoreButton, this.progress, this.progressText),
    );
  }

  async load(): Promise<void> {
    try {
      this.show(await getProfile());
      const status = await getRescoreStatus();
      if (status.running) {
        this.showProgress(status);
        this.poll();
      }
    } catch (error) {
      this.callbacks.onError(`Could not load the profile: ${errorMessage(error)}`);
    }
  }

  private show(profile: Profile): void {
    this.cvText.value = profile.cv_text;
    this.targets.value = profile.targets;
    this.location.value = profile.location;
    this.allowFullyRemote.checked = profile.allow_fully_remote;
    this.showCountry(profile);
    const uploaded = profile.uploaded_at ? `, uploaded ${formatDateTime(profile.uploaded_at)}` : "";
    if (profile.filename) {
      this.fileInfo.textContent = `${profile.filename}${uploaded}`;
    } else {
      this.fileInfo.textContent = profile.cv_text ? "Edited by hand (no file uploaded)." : "No CV uploaded yet.";
    }
  }

  /** What the saved location resolves to, so a typo shows before every job lands in the Archive. */
  private showCountry(profile: Profile): void {
    if (!profile.location) {
      this.locationCountry.textContent = "No location set: no job passes.";
    } else if (profile.country) {
      this.locationCountry.textContent = `Country: ${profile.country}`;
    } else {
      this.locationCountry.textContent = "Not a known country or city: jobs must mention it in their location, title or text.";
    }
  }

  private async upload(file: File): Promise<void> {
    this.dropZone.classList.add("drop-zone-busy");
    try {
      this.show(await uploadProfile(file));
      this.callbacks.onInfo(`Read ${file.name}. Check the text, add your targets, then Save.`);
    } catch (error) {
      this.callbacks.onError(errorMessage(error));
    } finally {
      this.dropZone.classList.remove("drop-zone-busy");
    }
  }

  /** Save, then apply the location to the stored postings (no LLM calls) and say how many moved. */
  private async save(): Promise<void> {
    this.saveButton.disabled = true;
    try {
      this.show(
        await patchProfile({
          cv_text: this.cvText.value,
          targets: this.targets.value,
          location: this.location.value,
          allow_fully_remote: this.allowFullyRemote.checked,
        }),
      );
      const { archived, restored } = await applyLocations();
      this.callbacks.onInfo(`Profile saved · ${archived} moved to the Archive, ${restored} back to New`);
      this.callbacks.onPostingsChanged();
    } catch (error) {
      this.callbacks.onError(errorMessage(error));
    } finally {
      this.saveButton.disabled = false;
    }
  }

  private async rescoreAll(): Promise<void> {
    this.rescoreButton.disabled = true;
    try {
      this.showProgress(await startRescore());
      this.poll();
    } catch (error) {
      this.callbacks.onError(errorMessage(error));
      this.rescoreButton.disabled = false;
    }
  }

  /** Ask for the progress every second until the run ends. */
  private poll(): void {
    window.clearTimeout(this.polling);
    this.polling = window.setTimeout(() => void this.pollOnce(), POLL_MS);
  }

  private async pollOnce(): Promise<void> {
    try {
      const status = await getRescoreStatus();
      this.showProgress(status);
      if (status.running) {
        this.poll();
        return;
      }
      this.rescoreButton.disabled = false;
      if (status.error) {
        this.callbacks.onError(`Re-score stopped: ${status.error}`);
      } else {
        this.callbacks.onInfo(`Re-scored ${status.done} postings`);
      }
      this.callbacks.onPostingsChanged();
    } catch (error) {
      this.rescoreButton.disabled = false;
      this.callbacks.onError(errorMessage(error));
    }
  }

  private showProgress(status: RescoreStatus): void {
    this.rescoreButton.disabled = status.running;
    this.progress.hidden = false;
    this.progress.max = Math.max(status.total, 1);
    this.progress.value = status.done;
    this.progressText.textContent = status.running ? `Scoring ${status.done} / ${status.total}…` : `${status.done} / ${status.total} scored`;
  }
}
