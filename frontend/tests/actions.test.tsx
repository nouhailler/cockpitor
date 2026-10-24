// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { ActionsView } from "../src/actions";
import { setLanguage } from "../src/i18n";
afterEach(() => {
  cleanup();
  setLanguage("fr");
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
const plan = {
  id: "a".repeat(32),
  action: "service.restart",
  target: "cron.service",
  engine: null,
  status: "prepared",
  fingerprint: "b".repeat(64),
  snapshot: { Id: "cron.service", configuration_fingerprint: "config" },
  expires_seconds: 120,
  approval_expires_seconds: 0,
  mode: "simulation",
  system_execution_enabled: false,
};
function mock(stale = false) {
  const calls: any[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options: any) => {
      calls.push([url, options]);
      return {
        ok: !(stale && url.endsWith("approve")),
        json: async () => {
          if (url.includes("operations")) return { items: [], total: 0 };
          if (url.endsWith("prepare")) return plan;
          if (url.endsWith("approve"))
            return stale
              ? {
                  error: {
                    message: "La cible a changé ; préparez un nouveau plan",
                  },
                }
              : {
                  plan: {
                    ...plan,
                    status: "approved",
                    approval_expires_seconds: 60,
                  },
                  approval_token: "private-approval-token",
                };
          if (url.endsWith("cancel")) return { ...plan, status: "cancelled" };
          return {
            plan: { ...plan, status: "simulated" },
            system_changed: false,
            commands_executed: false,
          };
        },
      };
    }),
  );
  return calls;
}
async function prepare() {
  fireEvent.change(screen.getByLabelText("Cible exacte"), {
    target: { value: "cron.service" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Préparer le plan de simulation" }),
  );
  await screen.findByRole("heading", {
    name: "Redémarrage de service · cron.service",
  });
}
it("requires plan review and explicit approval before simulation, without storing its token", async () => {
  const calls = mock();
  render(<ActionsView token="session" csrf="csrf" />);
  expect(
    screen.queryByRole("button", { name: "Lancer la simulation approuvée" }),
  ).toBeNull();
  await prepare();
  const approve = screen.getByRole("button", {
    name: "Approuver ce plan de simulation",
  });
  expect((approve as HTMLButtonElement).disabled).toBe(true);
  expect(
    (screen.getByLabelText("Cible exacte") as HTMLInputElement).disabled,
  ).toBe(true);
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(approve);
  const simulate = await screen.findByRole("button", {
    name: "Lancer la simulation approuvée",
  });
  expect(calls.some(([url]) => url.endsWith("simulate"))).toBe(false);
  fireEvent.click(simulate);
  await screen.findByText(
    "Simulation terminée : aucune commande de modification exécutée, aucun changement système.",
  );
  const body = JSON.parse(
    calls.find(([url]) => url.endsWith("simulate"))[1].body,
  );
  expect(body).toEqual({
    plan_id: plan.id,
    approval_token: "private-approval-token",
  });
  expect(
    calls.find(([url]) => url.endsWith("simulate"))[1].headers[
      "X-LocalCockpit-CSRF"
    ],
  ).toBe("csrf");
  expect(document.body.textContent).not.toContain("private-approval-token");
  expect(JSON.stringify(localStorage)).not.toContain("private-approval-token");
  expect(
    screen.queryByRole("button", { name: "Lancer la simulation approuvée" }),
  ).toBeNull();
});
it("discards approval flow when target revalidation fails", async () => {
  const calls = mock(true);
  render(<ActionsView token="session" csrf="csrf" />);
  await prepare();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(
    screen.getByRole("button", { name: "Approuver ce plan de simulation" }),
  );
  expect((await screen.findByRole("alert")).textContent).toContain(
    "La cible a changé",
  );
  expect(screen.queryByRole("checkbox")).toBeNull();
  expect(calls.some(([url]) => url.endsWith("simulate"))).toBe(false);
});
it("cancels a prepared plan and requires a new one", async () => {
  mock();
  render(<ActionsView token="session" csrf="csrf" />);
  await prepare();
  fireEvent.click(screen.getByRole("button", { name: "Annuler le plan" }));
  await screen.findByText("Plan annulé.");
  expect(screen.queryByRole("checkbox")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Nouveau plan" }));
  await waitFor(() =>
    expect(
      (screen.getByLabelText("Cible exacte") as HTMLInputElement).disabled,
    ).toBe(false),
  );
});
it("renders simulation-only controls and a clear disabled-execution message in English", async () => {
  setLanguage("en");
  mock();
  render(<ActionsView token="session" csrf="csrf" />);
  expect(
    screen.getByRole("heading", {
      name: "Controlled actions — simulation only",
    }),
  ).toBeTruthy();
  expect(screen.getByText(/System execution is disabled/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Execute" })).toBeNull();
  expect(screen.getByLabelText("Exact target")).toBeTruthy();
});
