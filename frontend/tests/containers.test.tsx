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
import { ContainersView } from "../src/containers";
const now = new Date().toISOString();
const cid = "a".repeat(64);
const engines = [
  {
    name: "docker",
    status: "available",
    version: "test",
    containers: [
      {
        id: cid,
        name: "local-container",
        image: "local-image",
        state: "running",
        status: "Up",
        ports: [],
      },
    ],
  },
];
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("loads details, stats and safe logs from the selected engine", async () => {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      const data = url.includes("/stats")
        ? {
            cpu_percent: 150,
            memory_usage_bytes: 1073741824,
            memory_limit_bytes: 2147483648,
            note: "CPU par cœur",
            collected_at: now,
          }
        : url.includes("/logs?")
          ? {
              items: [
                { stream: "stderr", message: "<img src=x onerror=alert(1)>" },
              ],
              tty: false,
              ordering: "grouped_by_stream",
              collected_at: now,
            }
          : {
              id: cid,
              engine: "docker",
              name: "local-container",
              image: "local-image",
              created: now,
              state: {
                Status: "running",
                Running: true,
                ExitCode: 0,
                OOMKilled: false,
                StartedAt: now,
                FinishedAt: null,
              },
              tty: false,
              collected_at: now,
            };
      return { ok: true, json: async () => data };
    }),
  );
  render(<ContainersView engines={engines} token="test" refresh={0} />);
  fireEvent.click(screen.getByRole("button", { name: "local-container" }));
  expect(await screen.findByText("150.0 %")).toBeTruthy();
  expect(await screen.findByText("1.0 Gio")).toBeTruthy();
  expect(await screen.findByText("<img src=x onerror=alert(1)>")).toBeTruthy();
  expect(document.querySelector("img")).toBeNull();
  expect(
    calls.every((url) => url.startsWith(`/api/v1/containers/docker/${cid}`)),
  ).toBe(true);
  fireEvent.change(screen.getByLabelText("Lignes par flux"), {
    target: { value: "50" },
  });
  await waitFor(() =>
    expect(calls.some((url) => url.includes("tail=50"))).toBe(true),
  );
  expect(
    screen.queryByRole("button", { name: /redémarrer|arrêter/i }),
  ).toBeNull();
});
it("keeps stats failures independent from readable container logs", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: !url.includes("/stats"),
      json: async () =>
        url.includes("/stats")
          ? { error: { message: "Statistiques indisponibles dans cet état" } }
          : url.includes("/logs?")
            ? {
                items: [{ stream: "stdout", message: "readable log" }],
                tty: true,
                collected_at: now,
              }
            : {
                id: cid,
                engine: "docker",
                name: "local-container",
                image: "local-image",
                state: { Status: "exited", Running: false, ExitCode: 1 },
                collected_at: now,
              },
    })),
  );
  render(<ContainersView engines={engines} token="test" refresh={0} />);
  fireEvent.click(screen.getByRole("button", { name: "local-container" }));
  expect((await screen.findByRole("alert")).textContent).toContain(
    "Statistiques indisponibles",
  );
  expect(await screen.findByText("readable log")).toBeTruthy();
});
it("filters inventory and explains disabled engines", () => {
  render(
    <ContainersView
      engines={[
        ...engines,
        {
          name: "podman",
          status: "disabled",
          message: "Accès non activé",
          containers: [],
        },
      ]}
      token="test"
      refresh={0}
    />,
  );
  expect(screen.getByText("Accès non activé")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("État des conteneurs"), {
    target: { value: "stopped" },
  });
  expect(screen.queryByRole("button", { name: "local-container" })).toBeNull();
  expect(screen.getByText("Aucun conteneur correspondant.")).toBeTruthy();
});
