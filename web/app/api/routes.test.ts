import { afterEach, describe, expect, it, vi } from "vitest";

import { GET as getArtifact } from "./artifacts/route";
import { GET as getHistory } from "./history/route";
import { GET as getJobStatus } from "./jobs/[jobId]/route";

afterEach(() => {
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

  it("returns job stage and timing data without caching", async () => {
    const jobId = "ea37c987-ffb6-4a9d-93cb-5965cf84b6ae";
    const payload = { status: "running", current_stage: "full_disk", queue_wait_seconds: 12 };
    const fetchStatus = vi.fn().mockResolvedValue(Response.json(payload));
    vi.stubGlobal("fetch", fetchStatus);

    const result = await getJobStatus(new Request(`http://localhost/api/jobs/${jobId}`), {
      params: Promise.resolve({ jobId })
    });
    expect(result.headers.get("cache-control")).toBe("no-store");
    expect(await result.json()).toEqual(payload);
    expect(fetchStatus).toHaveBeenCalledWith(
      expect.stringContaining(`/predictions/jobs/${jobId}`),
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it.each([[404, 404], [503, 502]])(
    "maps upstream job status %s to %s",
    async (upstreamStatus, expectedStatus) => {
      const jobId = "ea37c987-ffb6-4a9d-93cb-5965cf84b6ae";
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: upstreamStatus })));
      const result = await getJobStatus(new Request(`http://localhost/api/jobs/${jobId}`), {
        params: Promise.resolve({ jobId })
      });
      expect(result.status).toBe(expectedStatus);
    }
  );
});
