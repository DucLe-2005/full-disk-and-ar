import { PAGE_SIZE } from "@/lib/constants";
import { formatDateTime, formatTime, percent, predictionTone } from "@/lib/formatters";
import type { Prediction } from "@/types/prediction";
import { ArtifactImage } from "./artifact-image";

export function AttributionMap({ path, title, description, featured = false }: { path?: string | null; title: string; description: string; featured?: boolean }) {
  return <figure className={`attributionMap ${featured ? "featured" : ""}`}><ArtifactImage path={path} label={`${title} attribution map`} sizes="(max-width: 760px) calc(100vw - 56px), (max-width: 1180px) 45vw, 22vw" /><figcaption><strong>{title}</strong><span>{description}</span></figcaption></figure>;
}

export function ProbabilityBar({ value, tone = "flare" }: { value: number; tone?: "flare" | "quiet" }) {
  const clamped = Math.max(0, Math.min(1, value));
  return <div className="probabilityTrack" role="progressbar" aria-label={`${tone === "flare" ? "Flare" : "Region"} probability`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(clamped * 1000) / 10} aria-valuetext={percent(value)}><span className={`probabilityFill ${tone}`} style={{ width: `${clamped * 100}%` }} /></div>;
}

export function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong>{detail ? <small>{detail}</small> : null}</div>;
}

export function PredictionRow({ prediction, active, onSelect }: { prediction: Prediction; active: boolean; onSelect: () => void }) {
  return <button className={`historyItem ${active ? "active" : ""}`} type="button" onClick={onSelect}><span className="historyDate">{formatDateTime(prediction.requested_at).replace(" UTC", "")}</span><span className={`classPill ${predictionTone(prediction.predicted_class)}`}>{prediction.predicted_class}</span><strong>{percent(prediction.global_flare_probability)}</strong><small>{formatTime(prediction.requested_at)}</small><ProbabilityBar value={prediction.global_flare_probability} /></button>;
}

export function PredictionCard({ prediction, active, onSelect }: { prediction: Prediction; active: boolean; onSelect: () => void }) {
  return <button className={`catalogCard ${active ? "active" : ""}`} type="button" onClick={onSelect}><ArtifactImage path={prediction.full_disk_image_url} label="Full-Disk HMI Magnetogram" sizes="(max-width: 760px) calc(100vw - 52px), (max-width: 1180px) 30vw, 22vw" /><div className="catalogBody"><div><strong>{formatDateTime(prediction.requested_at)}</strong><span className={`classPill ${predictionTone(prediction.predicted_class)}`}>{prediction.predicted_class}</span></div><span>{percent(prediction.global_flare_probability)}</span><ProbabilityBar value={prediction.global_flare_probability} /></div></button>;
}

export function PaginationControls({ page, totalPages, totalRecords, onPageChange }: { page: number; totalPages: number; totalRecords: number; onPageChange: (page: number) => void }) {
  const first = totalRecords === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const last = Math.min(page * PAGE_SIZE, totalRecords);
  return <nav className="pagination" aria-label="Prediction history pages"><button type="button" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>Previous</button><span>{first}-{last} of {totalRecords}</span><button type="button" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>Next</button></nav>;
}
