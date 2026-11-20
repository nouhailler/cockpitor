// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { FilesView } from "../src/files";
import { BackupsView } from "../src/backups";
import { setLanguage } from "../src/i18n";
afterEach(() => {
  cleanup();
  setLanguage("fr");
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
it.each(["fr", "en"] as const)(
  "keeps filesystem opt-in explicit in %s",
  async (language) => {
    setLanguage(language);
    const fetcher = vi.fn(async () => ({
      ok: true,
      json: async () => ({ roots: [], configuration_error: false }),
    }));
    vi.stubGlobal("fetch", fetcher);
    render(<FilesView token="session" />);
    await screen.findByText(/LOCALCOCKPIT_FILE_ROOTS/);
    expect(screen.queryByRole("table")).toBeNull();
    expect(fetcher.mock.calls).toHaveLength(1);
  },
);
it("navigates only inside the selected root and renders file text safely", async () => {
  setLanguage("en");
  const fetcher = vi.fn(async (url: string) => ({
    ok: true,
    json: async () => {
      if (url.endsWith("options"))
        return {
          roots: [{ id: "docs", label: "Documents" }],
          configuration_error: false,
        };
      if (url.includes("preview"))
        return { text: "<img src=x onerror=alert(1)>", truncated: true };
      if (url.includes("path=folder"))
        return {
          items: [{ name: "notes.txt", kind: "file", size: 50 }],
          truncated: false,
        };
      return {
        items: [{ name: "folder", kind: "directory", size: null }],
        truncated: false,
      };
    },
  }));
  vi.stubGlobal("fetch", fetcher);
  render(<FilesView token="session" />);
  fireEvent.click(await screen.findByRole("button", { name: "Open" }));
  fireEvent.click(await screen.findByRole("button", { name: "Text preview" }));
  await screen.findByText("<img src=x onerror=alert(1)>");
  expect(document.querySelector("img")).toBeNull();
  expect(
    fetcher.mock.calls.some(
      ([url]) =>
        url.includes("root=docs") && url.includes("path=folder%2Fnotes.txt"),
    ),
  ).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Parent folder" }));
  await screen.findByRole("button", { name: "Open" });
});
it("requires reviewing and confirming a restore and invalidates it when edited", async () => {
  setLanguage("en");
  const restored = vi.fn();
  const fetcher = vi.fn(async (url: string, options: any) => ({
    ok: true,
    json: async () => {
      if (url.endsWith("prepare"))
        return {
          plan_id: "a".repeat(64),
          expires_seconds: 120,
          changes: [{ field: "language", before: "fr", after: "en" }],
        };
      if (url.endsWith("restore")) return { settings: { language: "en" } };
      return { items: [] };
    },
  }));
  vi.stubGlobal("fetch", fetcher);
  render(<BackupsView token="session" csrf="csrf" onRestored={restored} />);
  fireEvent.change(screen.getByLabelText("Backup content"), {
    target: { value: '{"backup":"review"}' },
  });
  fireEvent.click(screen.getByRole("button", { name: "Review differences" }));
  const review = await screen.findByRole("region", {
    name: "Restore differences",
  });
  expect(
    (
      within(review).getByRole("button", {
        name: "Restore preferences",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  expect(fetcher.mock.calls.some(([url]) => url.endsWith("restore"))).toBe(
    false,
  );
  fireEvent.change(screen.getByLabelText("Backup content"), {
    target: { value: '{"backup":"changed"}' },
  });
  expect(
    screen.queryByRole("region", { name: "Restore differences" }),
  ).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Review differences" }));
  await screen.findByRole("region", { name: "Restore differences" });
  fireEvent.click(
    screen.getByLabelText("I confirm replacing the reviewed preferences"),
  );
  fireEvent.click(screen.getByRole("button", { name: "Restore preferences" }));
  await waitFor(() =>
    expect(restored).toHaveBeenCalledWith({ language: "en" }),
  );
  const call = fetcher.mock.calls.find(([url]) => url.endsWith("restore"));
  expect(JSON.parse(call![1].body)).toEqual({
    plan_id: "a".repeat(64),
    confirmed: true,
  });
});
it("shows restoration failure without claiming success", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: !url.endsWith("prepare"),
      json: async () =>
        url.endsWith("prepare")
          ? { error: { message: "Sauvegarde invalide ou incompatible" } }
          : { items: [] },
    })),
  );
  const restored = vi.fn();
  render(<BackupsView token="session" csrf="csrf" onRestored={restored} />);
  fireEvent.change(screen.getByLabelText("Contenu de la sauvegarde"), {
    target: { value: "hostile" },
  });
  fireEvent.click(screen.getByText("Examiner les différences"));
  await screen.findByRole("alert");
  expect(restored).not.toHaveBeenCalled();
});
