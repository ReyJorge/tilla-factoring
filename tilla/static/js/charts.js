document.addEventListener("DOMContentLoaded", () => {
  const canvas = document.getElementById("debtorVolumeChart");
  if (!canvas || typeof Chart === "undefined") return;
  const labels = JSON.parse(canvas.dataset.labels || "[]");
  const values = JSON.parse(canvas.dataset.values || "[]");
  const ctx = canvas.getContext("2d");
  new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Objem faktur (období)",
          data: values,
          backgroundColor: "rgba(200, 169, 106, 0.65)",
          borderColor: "#0d1b2a",
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
      },
      scales: {
        x: { ticks: { color: "#1f2937" } },
        y: { ticks: { color: "#1f2937" } },
      },
    },
  });
});
