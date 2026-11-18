"use client";

import { useState } from "react";

import { ArtifactImage } from "@/components/dashboard/artifact-image";
type AttributionMethod = {
  key: string;
  title: string;
  path?: string | null;
  description: string;
};

export function AttributionComparison({ methods }: { methods: AttributionMethod[] }) {
  const [primaryKey, setPrimaryKey] = useState(methods[0]?.key ?? "");
  const [comparisonKey, setComparisonKey] = useState<string | null>(null);
  const [comparisonMode, setComparisonMode] = useState(false);
  const [zoom, setZoom] = useState(1);
  const primary = methods.find((method) => method.key === primaryKey) ?? methods[0];
  const comparison = methods.find((method) => method.key === comparisonKey && method.key !== primary?.key);

  function selectMethod(key: string) {
    if (comparisonMode) {
      if (key !== primaryKey) setComparisonKey(key);
      return;
    }
    setPrimaryKey(key);
    if (comparisonKey === key) setComparisonKey(null);
  }

  return (
    <div className="attributionExplorer">
      <div className="attributionToolbar">
        <p>Select a map to inspect it at full size. Compare two methods side by side.</p>
        <div className="attributionActions">
          <button type="button" aria-label="Zoom in on attribution maps" onClick={() => setZoom((current) => Math.min(3, current * 1.2))}>+</button>
          <button type="button" aria-label="Zoom out on attribution maps" onClick={() => setZoom((current) => Math.max(1, current / 1.2))}>−</button>
          <button type="button" aria-label="Reset attribution map zoom" onClick={() => setZoom(1)}>Reset</button>
          <button
            className={`compareToggle ${comparisonMode ? "active" : ""}`}
            type="button"
            aria-pressed={comparisonMode}
            onClick={() => {
              setComparisonMode((enabled) => !enabled);
              setComparisonKey(null);
            }}
          >
            {comparisonMode ? "Choose a second map" : "Compare methods"}
          </button>
        </div>
      </div>
      <div className={`attributionFocusGrid ${comparison ? "comparing" : ""}`}>
        {primary ? (
          <figure className="attributionFocusPanel">
            <div className="attributionFocusViewport"><div className="attributionFocusImage" style={{ transform: `scale(${zoom})` }}><ArtifactImage path={primary.path} label={`${primary.title} attribution map`} sizes="(max-width: 760px) 100vw, 60vw" /></div></div>
            <figcaption><strong>{primary.title}</strong><span>{primary.description}</span></figcaption>
          </figure>
        ) : null}
        {comparison ? (
          <figure className="attributionFocusPanel">
            <div className="attributionFocusViewport"><div className="attributionFocusImage" style={{ transform: `scale(${zoom})` }}><ArtifactImage path={comparison.path} label={`${comparison.title} attribution map`} sizes="(max-width: 760px) 100vw, 45vw" /></div></div>
            <figcaption><strong>{comparison.title}</strong><span>{comparison.description}</span></figcaption>
          </figure>
        ) : null}
      </div>
      <div className="sourceMapsGrid" aria-label="Attribution methods">
        {methods.map((method) => {
          const selected = method.key === primaryKey || method.key === comparisonKey;
          return (
            <button
              className={`attributionMethod ${selected ? "selected" : ""} ${comparisonMode && method.key !== primaryKey ? "comparisonChoice" : ""}`}
              type="button"
              key={method.key}
              aria-pressed={selected}
              onClick={() => selectMethod(method.key)}
            >
              <ArtifactImage path={method.path} label={`${method.title} preview`} sizes="(max-width: 760px) calc(100vw - 52px), 22vw" />
              <span className="attributionMethodCopy"><strong>{method.title}</strong><small>{method.description}</small></span>
            </button>
          );
        })}
      </div>
      {comparisonMode && !comparison ? <p className="comparisonHint" role="status">Choose a second method below. The primary map stays selected for comparison.</p> : null}
    </div>
  );
}

export function attributionMethods(paths: {
  guidedGradcam?: string | null;
  integratedGradients?: string | null;
  deepshap?: string | null;
  consensus?: string | null;
}): AttributionMethod[] {
  return [
    { key: "guided-gradcam", title: "Guided Grad-CAM", path: paths.guidedGradcam, description: "Localized gradient response" },
    { key: "integrated-gradients", title: "Integrated Gradients", path: paths.integratedGradients, description: "Accumulated input contribution" },
    { key: "deepliftshap", title: "DeepLiftShap", path: paths.deepshap, description: "Baseline-relative contribution" },
    { key: "fused", title: "Fused Attribution Map", path: paths.consensus, description: "Three-method region intersection" }
  ];
}
