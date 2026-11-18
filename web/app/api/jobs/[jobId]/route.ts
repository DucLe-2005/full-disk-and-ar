import { fetchPredictionJobStatus } from "@/lib/api";

export async function GET(request: Request, { params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  if (!/^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i.test(jobId)) {
    return Response.json({ detail: "Job not found" }, { status: 404 });
  }
  try {
    const response = await fetchPredictionJobStatus(jobId, request.signal);
    if (response.status === 404) {
      return Response.json({ detail: "Job not found" }, { status: 404 });
    }
    if (response.ok) {
      return Response.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
    }
  } catch {
    // The browser can retry a temporary upstream failure.
  }

  return Response.json({ detail: "Job status is temporarily unavailable" }, { status: 502 });
}
