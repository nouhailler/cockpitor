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
import { App } from "../src/main";
import { AssistantView } from "../src/assistant";
import { MonitoringView } from "../src/monitoring";
import { Graph } from "../src/components";
import { setLanguage } from "../src/i18n";
afterEach(() => {
  cleanup();
  setLanguage("fr");
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
it("exchanges the bootstrap, uses the session only and revokes it on logout", async () => {
  const fetcher = vi.fn(async (url: string, options: any) => ({
    ok: true,
    json: async () => {
      if (url.endsWith("auth/options")) return { csrf_token: "csrf" };
      if (url.endsWith("auth/sessions"))
        return { token: "session-private", csrf_token: "csrf" };
      if (url.endsWith("settings"))
        return {
          settings: { language: "fr", theme: "dark", refresh_seconds: 3 },
        };
      if (url.endsWith("history")) return [];
      return {
        collected_at: new Date().toISOString(),
        hostname: "test",
        os: "Linux",
        uptime_seconds: 1,
        cpu_percent: 10,
        cpu_cores: [10],
        load: [0, 0, 0],
        memory: { total: 100, used: 50, available: 50, percent: 50 },
        swap: { total: 0, used: 0, percent: 0 },
        network: { received_bps: 0, sent_bps: 0 },
        disks: [],
        temperatures: [],
      };
    },
  }));
  vi.stubGlobal("fetch", fetcher);
  render(<App />);
  fireEvent.change(
    screen.getByLabelText("Jeton affiché par le lanceur local"),
    { target: { value: "bootstrap-private" } },
  );
  fireEvent.click(screen.getByText("Ouvrir le cockpit →"));
  const menu = await screen.findByRole("button", { name: "Menu" });
  expect(menu.getAttribute("aria-expanded")).toBe("false");
  expect(screen.queryByRole("navigation")).toBeNull();
  fireEvent.click(menu);
  expect(menu.getAttribute("aria-expanded")).toBe("true");
  for (const name of ["Observer", "Intégrations", "Application"])
    expect(screen.getByRole("region", { name })).toBeTruthy();
  fireEvent.keyDown(screen.getByRole("button", { name: "Fermer le menu" }), {
    key: "Escape",
  });
  expect(menu.getAttribute("aria-expanded")).toBe("false");
  expect(document.activeElement).toBe(menu);
  fireEvent.click(menu);
  await screen.findByRole("button", { name: "Déconnexion" });
  const login = fetcher.mock.calls.find(([url]) =>
    url.endsWith("auth/sessions"),
  );
  expect(JSON.parse(login![1].body).token).toBe("bootstrap-private");
  await waitFor(() => {
    const reads = fetcher.mock.calls.filter(([url]) =>
      url.endsWith("system/metrics"),
    );
    expect(reads.length).toBeGreaterThan(0);
    expect(reads[0][1].headers.Authorization).toBe("Bearer session-private");
  });
  expect(localStorage.getItem("token")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Déconnexion" }));
  await screen.findByText("Ouvrir le cockpit →");
  expect(fetcher.mock.calls.some(([url]) => url.endsWith("auth/logout"))).toBe(
    true,
  );
});
it("previews context separately and sends only explicitly selected observations", async () => {
  setLanguage("en");
  let sent: any;
  const fetcher = vi.fn(async (url: string, options: any) => ({
    ok: true,
    json: async () => {
      if (url.endsWith("ai/status"))
        return { ollama: { models: [{ name: "local-model" }] } };
      if (url.endsWith("ai/threads")) return { items: [] };
      if (url.endsWith("ai/context"))
        return { context_id: "a".repeat(32), context: { cpu_percent: 10 } };
      sent = JSON.parse(options.body);
      return { answer: "<img src=x onerror=alert(1)>", thread_id: null };
    },
  }));
  vi.stubGlobal("fetch", fetcher);
  render(<AssistantView token="session" csrf="csrf" />);
  await screen.findByRole("option", { name: "local-model" });
  fireEvent.click(screen.getByText("Preview system context"));
  await screen.findByText(/cpu_percent/);
  fireEvent.change(screen.getByLabelText("Your question"), {
    target: { value: "Explain memory" },
  });
  fireEvent.click(screen.getByText("Send to local Ollama"));
  await screen.findByText("<img src=x onerror=alert(1)>");
  expect(sent.context_id).toBeNull();
  expect(sent.retain).toBe(false);
  expect(document.querySelector("img")).toBeNull();
  expect(sent.history).toEqual([]);
  fireEvent.click(screen.getByText("Preview system context"));
  await screen.findByText(/cpu_percent/);
  fireEvent.click(
    screen.getByLabelText(
      "Include only these observations with the next message",
    ),
  );
  fireEvent.change(screen.getByLabelText("Your question"), {
    target: { value: "And CPU?" },
  });
  fireEvent.click(screen.getByText("Send to local Ollama"));
  await waitFor(() => expect(sent.context_id).toBe("a".repeat(32)));
  expect(sent.history).toHaveLength(2);
});
it("renders missing probes explicitly and selects persistent history periods", async () => {
  const unavailable = { status: "unavailable" };
  const fetcher = vi.fn(async (url: string) => ({
    ok: true,
    json: async () =>
      url.includes("trends")
        ? { items: [] }
        : {
            collected_at: new Date().toISOString(),
            network: {
              interfaces: [],
              listeners: [],
              listeners_status: "unavailable",
            },
            disks: unavailable,
            gpu: unavailable,
            updates: unavailable,
            time: unavailable,
            installed_services: unavailable,
            power: { status: "unavailable", items: [] },
            smart: [],
          },
  }));
  vi.stubGlobal("fetch", fetcher);
  render(<MonitoringView token="session" />);
  expect(
    await screen.findByRole("heading", { name: "Réseau et exposition" }),
  ).toBeTruthy();
  expect(
    screen.getAllByText("Outil absent, accès refusé ou données indisponibles.")
      .length,
  ).toBeGreaterThan(2);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "168" } });
  await waitFor(() =>
    expect(fetcher.mock.calls.some(([url]) => url.includes("hours=168"))).toBe(
      true,
    ),
  );
});
it("preserves gaps in persistent CPU and RAM history", () => {
  render(
    <Graph
      persistent
      history={[
        {
          collected_at: "2026-10-23T00:00:00Z",
          cpu_percent: 10,
          memory_percent: 20,
        },
        {
          collected_at: "2026-10-23T00:01:00Z",
          cpu_percent: 20,
          memory_percent: 30,
        },
        {
          collected_at: "2026-10-23T02:00:00Z",
          cpu_percent: 30,
          memory_percent: 40,
        },
      ]}
    />,
  );
  const path = document.querySelector(".line")!.getAttribute("d")!;
  expect(path.match(/M/g)).toHaveLength(2);
  expect(document.querySelector(".memory-line")).toBeTruthy();
});

it.each(["fr", "en"] as const)(
  "offers diagnostic questions without sending in %s",
  async (language) => {
    setLanguage(language);
    const fetcher = vi.fn(async (url: string) => ({
      ok: true,
      json: async () =>
        url.endsWith("ai/status")
          ? { ollama: { models: [{ name: "local-model" }] } }
          : { items: [] },
    }));
    vi.stubGlobal("fetch", fetcher);
    render(<AssistantView token="session" csrf="csrf" />);
    await screen.findByRole("option", { name: "local-model" });
    const question =
      language === "fr"
        ? "Quels contrôles en lecture seule proposer pour une machine lente ?"
        : "Which read-only checks would help diagnose a slow machine?";
    fireEvent.click(screen.getByRole("button", { name: question }));
    expect(
      (
        screen.getByLabelText(
          language === "fr" ? "Votre question" : "Your question",
        ) as HTMLTextAreaElement
      ).value,
    ).toBe(question);
    expect(
      fetcher.mock.calls.some(
        ([url]) => url.endsWith("ai/chat") || url.endsWith("ai/context"),
      ),
    ).toBe(false);
  },
);

it("shows localized observations with missing values and an explicit consent", async () => {
  setLanguage("en");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: true,
      json: async () => {
        if (url.endsWith("ai/status")) return { ollama: { models: [] } };
        if (url.endsWith("ai/context"))
          return {
            context_id: "b".repeat(32),
            context: {
              source: "system/metrics",
              collected_at: "2026-11-20T10:00:00Z",
              cpu_percent: 12.5,
              memory_percent: null,
            },
          };
        return { items: [] };
      },
    })),
  );
  render(<AssistantView token="session" csrf="csrf" />);
  fireEvent.click(screen.getByText("Preview system context"));
  await screen.findByText("CPU utilization");
  expect(screen.getByText("12.5 %")).toBeTruthy();
  expect(screen.getAllByText("Unavailable").length).toBe(2);
  expect(
    (
      screen.getByLabelText(
        "Include only these observations with the next message",
      ) as HTMLInputElement
    ).checked,
  ).toBe(false);
});

it.each(["invalid", "2000-01-01T00:00:00Z", "2099-01-01T00:00:00Z"])(
  "marks invalid, old or future monitoring timestamps as stale: %s",
  async (collected_at) => {
    setLanguage("en");
    const unavailable = { status: "unavailable" };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => ({
        ok: true,
        json: async () =>
          url.includes("trends")
            ? { items: [] }
            : {
                collected_at,
                network: {
                  interfaces: [],
                  listeners: [],
                  listeners_status: "unavailable",
                },
                disks: unavailable,
                gpu: unavailable,
                updates: unavailable,
                time: unavailable,
                installed_services: unavailable,
                power: { ...unavailable, items: [] },
                smart: [],
              },
      })),
    );
    render(<MonitoringView token="session" />);
    await screen.findByText(/Stale data/);
  },
);
