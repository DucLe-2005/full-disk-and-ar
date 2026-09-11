"use client";

import { useId, useMemo, useState } from "react";

import { ArtifactImage } from "@/components/dashboard/artifact-image";
import type { ActiveRegion } from "@/types/prediction";

const MAP_SIZE = 512;
const DEFAULT_RADIUS = 48;

type CandidateRegionMapProps = {
  path?: string | null;
  label: string;
  regions: ActiveRegion[];
};

function regionCenter(region: ActiveRegion): [number, number] | null {
  const center = region.center_resized;
  if (center?.length === 2 && center.every(Number.isFinite)) {
    return [center[0], center[1]];
  }

  const bounds = region.bbox_resized;
  if (bounds?.length === 4 && bounds.every(Number.isFinite)) {
    return [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2];
  }

  return null;
}

export function CandidateRegionMap({ path, label, regions }: CandidateRegionMapProps) {
  const [radius, setRadius] = useState(DEFAULT_RADIUS);
  const sliderId = useId();
  const centers = useMemo(
    () => regions.flatMap((region) => {
      const center = regionCenter(region);
      return center ? [{ center, rank: region.rank }] : [];
    }),
    [regions]
  );

  return (
    <div className="candidateRegionExplorer">
      <div className="candidateRegionCanvas">
        <ArtifactImage
          path={path}
          label={label}
          sizes="(max-width: 1180px) calc(100vw - 28px), calc((100vw - 374px) / 2)"
        />
        {path && centers.length > 0 ? (
          <svg
            aria-hidden="true"
            className="candidateRadiusOverlay"
            preserveAspectRatio="xMidYMid meet"
            viewBox={`0 0 ${MAP_SIZE} ${MAP_SIZE}`}
          >
            {centers.map(({ center: [x, y], rank }) => (
              <g key={`${rank}-${x}-${y}`}>
                <circle className="candidateRadiusCircle" cx={x} cy={y} r={radius} />
                <circle className="candidateCenterPoint" cx={x} cy={y} r="3.5" />
                <text className="candidateRankLabel" x={x} y={y - 8} textAnchor="middle">
                  {rank}
                </text>
              </g>
            ))}
          </svg>
        ) : null}
      </div>

      <div className="radiusControl">
        <div className="radiusControlLabel">
          <label htmlFor={sliderId}>Proposal radius</label>
          <output htmlFor={sliderId}>{radius} px</output>
        </div>
        <input
          aria-describedby={`${sliderId}-hint`}
          id={sliderId}
          max={256}
          min={8}
          onChange={(event) => setRadius(Number(event.target.value))}
          step={1}
          type="range"
          value={radius}
        />
        <span id={`${sliderId}-hint`}>
          Expand the circles to compare proposal centers with mapped M/X flare locations.
        </span>
      </div>
    </div>
  );
}
