(() => {
  "use strict";

  const channel = "grillmester-visual-companion";
  const screen = window.__grillmesterVisualCompanionScreen;
  const selected = new Map();
  const indicator = document.getElementById("indicator");
  const indicatorText = document.getElementById("indicator-text");
  const choices = Array.from(document.querySelectorAll(".option, .card"));
  let persistenceStatus = "idle";
  let pendingEvent = null;

  choices.forEach((element, index) => {
    element.dataset.vcChoiceId = `choice-${index + 1}`;
    if (!element.hasAttribute("tabindex")) element.setAttribute("tabindex", "0");
    element.setAttribute("role", "button");
    element.setAttribute("aria-pressed", "false");
    // Inline handlers are blocked by CSP. Remove legacy attributes so the DOM
    // describes the delegated interaction accurately.
    element.removeAttribute("onclick");
  });

  function visibleLabel(element) {
    return (
      element.querySelector("h3, .content h3")?.textContent ||
      element.textContent ||
      "Valg"
    )
      .replace(/\s+/g, " ")
      .trim()
      .substring(0, 120);
  }

  function postSelection(type, choice) {
    if (!/^[a-f0-9]{32}$/.test(screen || "")) return;
    persistenceStatus = "saving";
    pendingEvent = { type, choice };
    parent.postMessage(
      {
        channel,
        version: 1,
        event: { type, choice, screen },
      },
      "*",
    );
  }

  function updateIndicator() {
    if (!indicator || !indicatorText) return;
    if (selected.size === 0) {
      indicator.classList.remove("visible");
      indicatorText.textContent = "Valgt";
      return;
    }
    indicator.classList.add("visible");
    const names = Array.from(selected.values());
    const selection =
      names.length === 1 ? `Valgt: ${names[0]}` : `${names.length} valgt`;
    const status = persistenceStatus === "saving"
      ? " · lagrer …"
      : persistenceStatus === "saved"
        ? " · lagret"
        : persistenceStatus === "failed"
          ? " · ikke lagret — si valget i chatten"
          : "";
    indicatorText.textContent = selection + status;
  }

  function toggleSelect(element) {
    const choice = element.dataset.vcChoiceId;
    if (!/^choice-[1-9][0-9]{0,3}$/.test(choice || "")) return;
    const container = element.closest(".options, .cards");
    const isMulti = container?.hasAttribute("data-multiselect") || false;

    if (!isMulti && container) {
      container.querySelectorAll(".option, .card").forEach((other) => {
        if (other === element) return;
        other.classList.remove("selected");
        other.setAttribute("aria-pressed", "false");
        selected.delete(other.dataset.vcChoiceId);
      });
    }

    element.classList.toggle("selected");
    const isSelected = element.classList.contains("selected");
    element.setAttribute("aria-pressed", String(isSelected));
    if (isSelected) {
      selected.set(choice, visibleLabel(element));
      postSelection("click", choice);
    } else {
      selected.delete(choice);
      postSelection("deselect", choice);
    }
    updateIndicator();
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest("a, area");
    if (link) {
      event.preventDefault();
      return;
    }
    const choice = event.target.closest(".option, .card");
    if (!choice) return;
    event.preventDefault();
    toggleSelect(choice);
  }, true);

  for (const eventName of ["auxclick", "contextmenu"]) {
    document.addEventListener(
      eventName,
      (event) => {
        if (!event.target.closest("a, area")) return;
        event.preventDefault();
      },
      true,
    );
  }

  document.addEventListener("submit", (event) => event.preventDefault(), true);

  document.addEventListener("keydown", (event) => {
    const choice = event.target.closest(".option, .card");
    if (!choice || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault();
    toggleSelect(choice);
  });

  window.addEventListener("message", (message) => {
    if (message.source !== parent || !message.data) return;
    if (message.data.channel !== channel || message.data.version !== 1) return;
    if (message.data.command === "refreshing") {
      const toast = document.getElementById("refresh-indicator");
      toast?.classList.add("visible");
      return;
    }
    if (
      message.data.command !== "selection-status" ||
      message.data.screen !== screen ||
      !pendingEvent ||
      message.data.type !== pendingEvent.type ||
      message.data.choice !== pendingEvent.choice ||
      (message.data.status !== "saved" && message.data.status !== "failed")
    ) return;
    persistenceStatus = message.data.status;
    pendingEvent = null;
    updateIndicator();
  });
})();
