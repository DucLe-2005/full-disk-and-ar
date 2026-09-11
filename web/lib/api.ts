import type { Prediction, PredictionHistoryPage } from "@/types/prediction";

const backendBaseUrl = process.env.FASTAPI_BASE_URL ?? "http://localhost:8000";

export async function fetchPredictionHistory(query: string): Promise<PredictionHistoryPage> {
  const suffix = query ? `?${query}` : "";
  const response = await fetch(`${backendBaseUrl}/history/${suffix}`, {
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(`History request failed with ${response.status}`);
  }

  return response.json();
}

export async function fetchPredictionDetail(predictionId: string): Promise<Prediction> {
  const response = await fetch(`${backendBaseUrl}/history/${encodeURIComponent(predictionId)}`, {
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(`Prediction detail request failed with ${response.status}`);
  }

  return response.json();
}

export async function createPredictionJob(helioviewerDate: string) {
  const response = await fetch(`${backendBaseUrl}/predictions/jobs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      helioviewer_date: helioviewerDate
    }),
    cache: "no-store"
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Create job request failed with ${response.status}`);
  }

  return response.json();
}
