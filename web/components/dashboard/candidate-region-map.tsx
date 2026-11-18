"use client";

import { useMemo, useRef, useState } from "react";

import { ArtifactImage } from "@/components/dashboard/artifact-image";
import type { ActiveRegion } from "@/types/prediction";

const MAP_SIZE = 512;

type CandidateRegionComparisonProps = {
  originalPath?: string | null;
  candidatePath?: string | null;
  candidateLabel: string;
  regions: ActiveRegion[];
  selectedRank: number | null;
  onSelectRegion: (rank: number) => void;
};

type RegionOverlay = {
  rank: number;
  box: [number, number, number, number];
  polygon: string | null;
};

function regionOverlay(region: ActiveRegion): RegionOverlay | null {
  const bounds = region.bbox_resized;
  if (!bounds || bounds.length !== 4 || !bounds.every(Number.isFinite)) {
    return null;
  }

  const polygon = region.polygon_resized?.length
    ? region.polygon_resized
        .filter((point) => point.length === 2 && point.every(Number.isFinite))
        .map(([x, y]) => `${x},${y}`)
        .join(" ")
    : null;

  return {
    rank: region.rank,
    box: [bounds[0], bounds[1], bounds[2], bounds[3]],
    polygon
  };
}

export function CandidateRegionComparison({
  originalPath,
  candidatePath,
  candidateLabel,
  regions,
  selectedRank,
  onSelectRegion
}: CandidateRegionComparisonProps) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStart = useRef<{ pointerX: number; pointerY: number; x: number; y: number } | null>(null);
  const overlays = useMemo(
    () => regions.flatMap((region) => regionOverlay(region) ?? []),
    [regions]
  );

  return (
    <div className="candidateComparisonGrid">
      <figure className="candidateComparisonPanel">
        <ArtifactImage
          path={originalPath}
          label="SDO/HMI full-disk line-of-sight magnetogram"
          sizes="(max-width: 760px) calc(100vw - 52px), 33vw"
          eager
        />
        <figcaption>
          <strong>SDO/HMI full-disk line-of-sight magnetogram</strong>
        </figcaption>
      </figure>

      <figure className="candidateComparisonPanel">
        <ArtifactImage
          path={candidatePath}
          label={candidateLabel}
          sizes="(max-width: 760px) calc(100vw - 52px), 33vw"
          eager
        />
        <figcaption>
          <strong>Final candidate</strong>
        </figcaption>
      </figure>

      <figure className="candidateComparisonPanel candidateOverlayPanel">
        <div
          className={`candidateRegionCanvas ${isDragging ? "dragging" : ""}`}
          onWheel={(event) => {
            const nextZoom = Math.min(4, Math.max(1, zoom * (event.deltaY < 0 ? 1.15 : 1 / 1.15)));
            if (nextZoom !== zoom) event.preventDefault();
            setZoom(nextZoom);
            if (nextZoom === 1) setPan({ x: 0, y: 0 });
          }}
          onPointerDown={(event) => {
            if (zoom <= 1) return;
            if ((event.target as Element).closest(".candidateSelectTarget, .candidateZoomControls")) return;
            dragStart.current = { pointerX: event.clientX, pointerY: event.clientY, x: pan.x, y: pan.y };
            setIsDragging(true);
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            if (!dragStart.current) return;
            const limitX = event.currentTarget.clientWidth * (zoom - 1) / 2;
            const limitY = event.currentTarget.clientHeight * (zoom - 1) / 2;
            setPan({
              x: Math.max(-limitX, Math.min(limitX, dragStart.current.x + event.clientX - dragStart.current.pointerX)),
              y: Math.max(-limitY, Math.min(limitY, dragStart.current.y + event.clientY - dragStart.current.pointerY))
            });
          }}
          onPointerUp={() => { dragStart.current = null; setIsDragging(false); }}
          onPointerCancel={() => { dragStart.current = null; setIsDragging(false); }}
        >
          <div className="candidateZoomContent" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}>
          <ArtifactImage
            path={originalPath}
            label="Final candidate regions over the SDO/HMI full-disk line-of-sight magnetogram"
            sizes="(max-width: 760px) calc(100vw - 52px), 33vw"
            eager
          />
          {originalPath && overlays.length > 0 ? (
            <svg
              aria-label="Selectable candidate regions"
              role="group"
              className="candidateRegionOverlay"
              preserveAspectRatio="xMidYMid meet"
              viewBox={`0 0 ${MAP_SIZE} ${MAP_SIZE}`}
            >
              {overlays.map(({ rank, box: [x1, y1, x2, y2], polygon }) => (
                <g key={`${rank}-${x1}-${y1}`} className={selectedRank === rank ? "candidateOverlaySelected" : ""}>
                  {polygon ? <polygon className="candidateIntersectionPolygon" points={polygon} /> : null}
                  <rect
                    aria-label={`Select candidate region ${rank}`}
                    aria-pressed={selectedRank === rank}
                    className="candidateBoundingBox candidateSelectTarget"
                    height={Math.max(1, y2 - y1)}
                    width={Math.max(1, x2 - x1)}
                    x={x1}
                    y={y1}
                    role="button"
                    tabIndex={0}
                    onClick={() => onSelectRegion(rank)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSelectRegion(rank);
                      }
                    }}
                  />
                  <g className={`candidateBoxLabel ${selectedRank === rank ? "selected" : ""}`} transform={`translate(${x1}, ${Math.max(0, y1 - 20)})`}>
                    <rect height="20" rx="4" width="28" />
                    <text x="14" y="14" textAnchor="middle">{rank}</text>
                  </g>
                </g>
              ))}
            </svg>
          ) : null}
          </div>
          <div className="candidateZoomControls" aria-label="Magnetogram zoom controls">
            <button type="button" aria-label="Zoom in" onClick={() => setZoom((current) => Math.min(4, current * 1.25))}>+</button>
            <button type="button" aria-label="Zoom out" onClick={() => { const nextZoom = Math.max(1, zoom / 1.25); setZoom(nextZoom); if (nextZoom === 1) setPan({ x: 0, y: 0 }); }}>−</button>
            <button type="button" aria-label="Reset zoom and pan" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}>Reset</button>
          </div>
        </div>
        <figcaption>
          <strong>Candidate overlay</strong>
          <span>Select a boundary to inspect its saved region prediction.</span>
        </figcaption>
      </figure>
    </div>
  );
}
