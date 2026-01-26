const statusIndicator = document.getElementById("status-indicator");
const moduleList = document.getElementById("module-list");
const planForm = document.getElementById("plan-form");
const planOutput = document.getElementById("plan-output");
const timeWindow = document.getElementById("time-window");

const renderStatus = (ok) => {
  statusIndicator.textContent = ok ? "API online" : "API offline";
  statusIndicator.style.color = ok ? "#1f8a70" : "#c0392b";
};

const renderModules = (modules) => {
  moduleList.innerHTML = "";
  modules.forEach((module) => {
    const card = document.createElement("div");
    card.className = "module-card";
    card.innerHTML = `
      <label>
        <input type="checkbox" value="${module.id}" />
        ${module.name}
      </label>
      <span class="module-meta">Resolution: ${module.resolution}</span>
      <span class="module-meta">${module.focus}</span>
    `;
    moduleList.appendChild(card);
  });
};

const renderPlan = (plan) => {
  planOutput.innerHTML = `
    <strong>${plan.summary}</strong>
    <p class="muted">Time window: ${plan.time_window}</p>
    <p class="muted">Modules: ${plan.modules.join(", ")}</p>
    <ul>
      ${plan.next_steps.map((step) => `<li>${step}</li>`).join("")}
    </ul>
  `;
};

const renderError = (message) => {
  planOutput.innerHTML = `<p class="muted">${message}</p>`;
};

const loadHealth = async () => {
  try {
    const response = await fetch("/api/health");
    renderStatus(response.ok);
  } catch (error) {
    renderStatus(false);
  }
};

const loadModules = async () => {
  try {
    const response = await fetch("/api/modules");
    const data = await response.json();
    renderModules(data.modules ?? []);
  } catch (error) {
    renderError("Unable to load modules. Check the API service.");
  }
};

planForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const selectedModules = Array.from(
    document.querySelectorAll("#module-list input:checked")
  ).map((input) => input.value);

  try {
    const response = await fetch("/api/plan", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        modules: selectedModules,
        time_window: timeWindow.value.trim(),
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      renderError(data.error ?? "Unable to generate plan.");
      return;
    }
    renderPlan(data);
  } catch (error) {
    renderError("Unable to reach the API.");
  }
});

loadHealth();
loadModules();
