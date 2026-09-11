import { afterEach, describe, expect, it, vi } from "vitest";

import { GET as getArtifact } from "./artifacts/route";
import { GET as getHistory } from "./history/route";
import { POST as postCurrentHour } from "./jobs/current-hour/route";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("web route handlers", () => {
  it.each(["", "other/file.png", "predictions/../secret"])(
    "rejects unsafe artifact key %j",
    async (key) => {
      const response = await getArtifact(
        new Request(`http://localhost/api/artifacts?key=${encodeURIComponent(key)}`)
      );
      expect(response.status).toBe(400);
      expect(await response.json()).toEqual({ detail: "Invalid artifact key" });
    }
  );

  it("streams valid artifacts with storage content type", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(new Uint8Array([1, 2, 3]), { headers: { "content-type": "image/png" } })
      )
    );

    const response = await getArtifact(
      new Request("http://localhost/api/artifacts?key=predictions%2Ffolder%2Fimage.png")
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("image/png");
    expect(Array.from(new Uint8Array(await response.arrayBuffer()))).toEqual([1, 2, 3]);
  });

  it("passes history query parameters through and returns JSON types", async () => {
    const payload = { items: [], page: 1, page_size: 10, total: 0, total_pages: 1 };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(payload))));

    const response = await getHistory(
      new Request("http://localhost/api/history?page=1&page_size=10")
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(payload);
  });

  it("creates a job for the current UTC hour with a stable string shape", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-07T13:42:51Z"));
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ job_id: "job-1", status: "queued" }))
      )
    );

    const response = await postCurrentHour();
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body).toEqual({
      job_id: "job-1",
      status: "queued",
      helioviewer_date: "2026-09-07 13:00:00"
    });
    expect(typeof body.job_id).toBe("string");
    expect(typeof body.helioviewer_date).toBe("string");
  });
});
