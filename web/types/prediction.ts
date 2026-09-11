export type ActiveRegion = {
  rank: number;
  probability: number;
  heatmap_score?: number | null;
  image_path?: string | null;
  bbox_original?: number[] | null;
  bbox_resized?: number[] | null;
  center_resized?: number[] | null;
  polygon_resized?: number[][] | null;
};

export type Heatmap = {
  method_name: string;
  image_path: string;
};

export type Prediction = {
  prediction_id: string;
  requested_at: string;
  timestamp: string;
  global_flare_probability: number;
  localized_probabilities: number[];
  predicted_class: string;
  jp2_image_url?: string | null;
  full_disk_image_url?: string | null;
  heatmap_url?: string | null;
  guided_gradcam_url?: string | null;
  integrated_gradients_url?: string | null;
  deepshap_url?: string | null;
  consensus_url?: string | null;
  final_hulls_url?: string | null;
  actual_flare_regions?: Record<string, unknown>[];
  actual_events_status?: "available" | "no_events" | "unavailable" | "overlay_unavailable" | null;
  actual_flare_overlay_url?: string | null;
  active_regions: ActiveRegion[];
  heatmaps: Heatmap[];
  raw_active_regions: Record<string, unknown>[];
};

export type PredictionHistoryPage = {
  items: Prediction[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};
