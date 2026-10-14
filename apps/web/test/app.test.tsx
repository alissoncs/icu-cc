import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "../src/App";
import FitnessChart from "../src/components/FitnessChart";
import * as api from "../src/api";
import fitness from "../../../fixtures/api/fitness.json";
import detail from "../../../fixtures/api/activity_detail.json";
import week from "../../../fixtures/api/week.json";

vi.mock("../src/api", async (orig) => {
  const actual = await orig<typeof import("../src/api")>();
  return { ...actual, get: vi.fn(actual.get) };
});

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("FitnessChart", () => {
  it("draws one vertex per point per series", () => {
    render(<FitnessChart points={fitness.points} />);
    for (const k of ["ctl", "atl", "tsb"]) {
      const pts = screen.getByTestId(`line-${k}`).getAttribute("points")!.trim().split(" ");
      expect(pts).toHaveLength(fitness.points.length);
    }
    expect(screen.getByTestId("zero-line")).toBeInTheDocument();
  });
});

describe("screens", () => {
  it("form screen shows cards and chart", async () => {
    renderAt("/");
    expect(await screen.findByTestId("fitness-chart")).toBeInTheDocument();
    expect(screen.getByText("Condição (CTL)", { selector: "h2" })).toBeInTheDocument();
  });

  it("activity list renders rows and the days filter changes the query", async () => {
    renderAt("/atividades");
    const rows = await screen.findAllByTestId("activity-row");
    expect(rows.length).toBeGreaterThan(0);
    expect(api.get).toHaveBeenCalledWith("/api/activities?days=30");
    fireEvent.click(screen.getByRole("button", { name: "7 dias" }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/api/activities?days=7"));
    expect(screen.getByRole("button", { name: "7 dias" })).toHaveAttribute("aria-pressed", "true");
  });

  it("activity page renders warnings and all 7 zone rows", async () => {
    renderAt("/atividades/i1000");
    const w = await screen.findByTestId("warnings");
    expect(within(w).getByText(detail.warnings[0]!)).toBeInTheDocument();
    expect(screen.getAllByTestId("zone-row")).toHaveLength(7);
  });

  it("week page shows the distribution label", async () => {
    renderAt("/semana/2026-08-24");
    expect(await screen.findByTestId("model-label")).toHaveTextContent("Misto");
    expect(screen.getByText(week.distribution.assessment, { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Próxima semana/ })).toHaveAttribute("href", "/semana/2026-08-31");
  });

  it.each(["config_missing", "intervals_unauthorized"])("renders a friendly message for %s", async (code) => {
    vi.mocked(api.get).mockRejectedValueOnce(new api.ApiRequestError("x", code, 500));
    renderAt("/atividades");
    expect(await screen.findByRole("alert")).toHaveTextContent(/\.env/);
  });
});
