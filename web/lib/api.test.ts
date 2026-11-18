import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchPredictionDetail, fetchPredictionHistory } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("backend API client", () => {
  it("forwards history queries and returns the typed payload", async () => {
    const payload = { items: [], page: 2, page_size: 10, total: 0, total_pages: 1 };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload)));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchPredictionHistory("page=2&predicted_class=1")).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/history/?page=2&predicted_class=1",
      { cache: "no-store" }
    );
  });

  it("URL-encodes prediction ids and reports upstream failures", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 404 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchPredictionDetail("id/with spaces")).rejects.toThrow(
      "Prediction detail request failed with 404"
    );
    expect(fetchMock.mock.calls[0][0]).toContain("id%2Fwith%20spaces");
  });
});
