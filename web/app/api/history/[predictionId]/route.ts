import { NextResponse } from "next/server";

import { fetchPredictionDetail } from "@/lib/api";

export async function GET(
  _request: Request,
  context: { params: Promise<{ predictionId: string }> }
) {
  const { predictionId } = await context.params;
  try {
    return NextResponse.json(await fetchPredictionDetail(predictionId));
  } catch (error) {
    return NextResponse.json(
      {
        detail: error instanceof Error ? error.message : "Failed to fetch prediction detail"
      },
      { status: 502 }
    );
  }
}
