"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";

import { ArtifactImage } from "@/components/dashboard/artifact-image";
import { AttributionComparison, attributionMethods } from "@/components/dashboard/attribution-comparison";
import { CandidateRegionComparison } from "@/components/dashboard/candidate-region-map";
import { RefreshIcon, SunIcon } from "@/components/dashboard/icons";
import { Metric, PaginationControls, PredictionCard, PredictionRow, ProbabilityBar } from "@/components/dashboard/prediction-ui";
import { PAGE_SIZE } from "@/lib/constants";
import { formatDateTime, percent, predictionTone } from "@/lib/formatters";
import type { ClassFilter, LoadState, ViewMode } from "@/types/dashboard";
import type { Prediction, PredictionHistoryPage } from "@/types/prediction";

function findHeatmap(prediction: Prediction, methodName: string) {
  return prediction.heatmaps.find((heatmap) => heatmap.method_name === methodName)?.image_path;
}

export function SolarDashboard() {
  const [history, setHistory] = useState<Prediction[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<Prediction | null>(null);
  const [selectedRegionRank, setSelectedRegionRank] = useState<number | null>(null);
  const [historyState, setHistoryState] = useState<LoadState>("loading");
  const [live, setLive] = useState(true);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [draftRangeStart, setDraftRangeStart] = useState("");
  const [draftRangeEnd, setDraftRangeEnd] = useState("");
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");
  const [rangeRequestVersion, setRangeRequestVersion] = useState(0);
  const [viewMode, setViewMode] = useState<ViewMode>("detail");
  const [classFilter, setClassFilter] = useState<ClassFilter>("all");
  const [page, setPage] = useState(1);
  const [totalRecords, setTotalRecords] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const detailRequestId = useRef(0);
  const pinnedPrediction = useRef<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let pending = false;

    async function loadHistory(background = false) {
      if (pending) return;
      pending = true;
      if (!background) {
        setHistoryState("loading");
        setStatusMessage(null);
      }

      try {
        const params = new URLSearchParams({
          page: String(live ? 1 : page),
          page_size: String(live ? 24 : PAGE_SIZE)
        });
        if (!live) {
          if (rangeStart) params.set("start_time", rangeStart);
          if (rangeEnd) params.set("end_time", rangeEnd);
          if (classFilter !== "all") {
            params.set("predicted_class", classFilter === "flare" ? "1" : "0");
          }
        }
        const response = await fetch(`/api/history?${params.toString()}`, {
          cache: "no-store",
          signal: controller.signal
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail ?? `History request failed with ${response.status}`);
        }
        const data = (await response.json()) as PredictionHistoryPage;
        if (controller.signal.aborted) return;
        setHistory(data.items);
        setTotalRecords(data.total);
        setTotalPages(data.total_pages);
        if (!data.items.some((item) => item.prediction_id === pinnedPrediction.current)) {
          pinnedPrediction.current = null;
        }
        setSelectedId(pinnedPrediction.current ?? data.items[0]?.prediction_id ?? null);
        setStatusMessage(null);
        setHistoryState("idle");
      } catch (error) {
        if (controller.signal.aborted) return;
        setHistoryState("error");
        setStatusMessage(error instanceof Error ? error.message : "Could not load predictions");
      } finally {
        pending = false;
      }
    }

    const initial = window.setTimeout(() => void loadHistory(), 0);
    const interval = live ? window.setInterval(() => void loadHistory(true), 60_000) : undefined;
    return () => {
      controller.abort();
      window.clearTimeout(initial);
      window.clearInterval(interval);
    };
  }, [classFilter, live, page, rangeEnd, rangeRequestVersion, rangeStart]);

  function switchFeed(nextLive: boolean) {
    if (nextLive === live) return;
    pinnedPrediction.current = null;
    setSelectedId(null);
    setSelectedDetail(null);
    setHistory([]);
    setTotalPages(1);
    setTotalRecords(0);
    setHistoryState("loading");
    setLive(nextLive);
  }

  function applyDateRange() {
    if (draftRangeStart && draftRangeEnd && draftRangeStart > draftRangeEnd) {
      setHistoryState("error");
      setStatusMessage("The start of the date range must be before its end");
      return;
    }

    setRangeStart(draftRangeStart);
    setRangeEnd(draftRangeEnd);
    setPage(1);
    setRangeRequestVersion((version) => version + 1);
  }

  function clearDateRange() {
    setDraftRangeStart("");
    setDraftRangeEnd("");
    setRangeStart("");
    setRangeEnd("");
    setPage(1);
    setRangeRequestVersion((version) => version + 1);
  }

  const selectedPrediction = useMemo(() => {
    if (selectedDetail && selectedDetail.prediction_id === selectedId) {
      return selectedDetail;
    }
    const visibleSelection = history.find((prediction) => prediction.prediction_id === selectedId);
    return visibleSelection ?? (selectedId ? null : history[0] ?? null);
  }, [history, selectedDetail, selectedId]);

  useEffect(() => {
    const requestId = ++detailRequestId.current;
    if (!selectedId) {
      setSelectedDetail(null);
      setSelectedRegionRank(null);
      return;
    }

    setSelectedRegionRank(null);
    setSelectedDetail(null);
    void (async () => {
      try {
        const response = await fetch(`/api/history/${encodeURIComponent(selectedId)}`, {
          cache: "no-store"
        });
        if (!response.ok) {
          throw new Error(`Prediction detail request failed with ${response.status}`);
        }
        const detail = (await response.json()) as Prediction;
        if (requestId === detailRequestId.current) {
          setSelectedDetail(detail);
        }
      } catch {
        // The history item remains visible if the supplemental detail request
        // or solar-events service is temporarily unavailable.
      }
    })();
  }, [selectedId]);

  const attributionPaths = selectedPrediction
    ? {
        guidedGradcam:
          selectedPrediction.guided_gradcam_url ?? findHeatmap(selectedPrediction, "Guided Grad-CAM"),
        integratedGradients:
          selectedPrediction.integrated_gradients_url ??
          findHeatmap(selectedPrediction, "Integrated Gradients"),
        deepshap: selectedPrediction.deepshap_url ?? findHeatmap(selectedPrediction, "DeepLiftShap"),
        consensus:
          findHeatmap(selectedPrediction, "Proposal Heatmap") ??
          selectedPrediction.consensus_url ??
          findHeatmap(selectedPrediction, "Consensus") ??
          selectedPrediction.heatmap_url
      }
    : null;
  const attributionChoices = attributionPaths ? attributionMethods(attributionPaths) : [];

  function selectPrediction(prediction: Prediction) {
    pinnedPrediction.current = prediction.prediction_id;
    setSelectedId(prediction.prediction_id);
    setSelectedRegionRank(null);
    setViewMode("detail");
  }

  function handleViewTabKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>) {
    const tabs: ViewMode[] = ["detail", "catalog"];
    const currentIndex = tabs.indexOf(viewMode);
    let nextIndex = currentIndex;

    if (event.key === "ArrowRight") {
      nextIndex = (currentIndex + 1) % tabs.length;
    } else if (event.key === "ArrowLeft") {
      nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = tabs.length - 1;
    } else {
      return;
    }

    event.preventDefault();
    const nextView = tabs[nextIndex];
    setViewMode(nextView);
    document.getElementById(`view-tab-${nextView}`)?.focus();
  }

  return (
    <main className="appShell">
      <header className="topbar">
        <div className="brand">
          <span className="brandMark"><SunIcon /></span>
          <div className="brandCopy">
            <span>Heliophysics intelligence</span>
            <h1>Solar flare monitor</h1>
          </div>
        </div>
        <div className="toolbar" aria-label="Prediction controls">
          <span className="lastUpdated">
            {live && history[0] ? `Latest forecast · ${formatDateTime(history[0].requested_at)}` : null}
          </span>
          <button
            className="refreshButton"
            type="button"
            disabled={historyState === "loading"}
            aria-label={historyState === "loading" ? "Refreshing predictions" : "Refresh predictions"}
            onClick={() => setRangeRequestVersion((version) => version + 1)}
          >
            <RefreshIcon />
            <span>Refresh</span>
          </button>
          <div className="viewToggle" role="tablist" aria-label="View mode">
            <button
              id="view-tab-detail"
              className={viewMode === "detail" ? "selected" : ""}
              type="button"
              role="tab"
              aria-selected={viewMode === "detail"}
              aria-controls="view-panel-detail"
              tabIndex={viewMode === "detail" ? 0 : -1}
              onKeyDown={handleViewTabKeyDown}
              onClick={() => setViewMode("detail")}
            >
              Detail
            </button>
            <button
              id="view-tab-catalog"
              className={viewMode === "catalog" ? "selected" : ""}
              type="button"
              role="tab"
              aria-selected={viewMode === "catalog"}
              aria-controls="view-panel-catalog"
              tabIndex={viewMode === "catalog" ? 0 : -1}
              onKeyDown={handleViewTabKeyDown}
              onClick={() => setViewMode("catalog")}
            >
              Catalog
            </button>
          </div>
        </div>
      </header>

      {statusMessage ? (
        <section className={`statusBanner ${historyState === "error" ? "error" : ""}`} role="status" aria-live="polite">
          <span>{statusMessage}</span>
        </section>
      ) : null}

      <section className="workspace">
        <aside className="historyPanel">
          <div className="viewToggle" role="group" aria-label="Forecast feed">
            <button type="button" aria-pressed={live} className={live ? "selected" : ""} onClick={() => switchFeed(true)}>
              Live
            </button>
            <button type="button" aria-pressed={!live} className={!live ? "selected" : ""} onClick={() => switchFeed(false)}>
              History
            </button>
          </div>
          {!live && (
            <fieldset className="rangeFilter">
              <legend>Date range <span>UTC</span></legend>
              <div className="dateRange">
                <label className="srOnly" htmlFor="range-start">Start date and time</label>
                <input
                  id="range-start"
                  type="datetime-local"
                  value={draftRangeStart}
                  onChange={(event) => setDraftRangeStart(event.target.value)}
                />
                <span aria-hidden="true">to</span>
                <label className="srOnly" htmlFor="range-end">End date and time</label>
                <input
                  id="range-end"
                  type="datetime-local"
                  value={draftRangeEnd}
                  onChange={(event) => setDraftRangeEnd(event.target.value)}
                />
              </div>
              <label htmlFor="class-filter">Class filter</label>
              <select
                id="class-filter"
                value={classFilter}
                onChange={(event) => {
                  setClassFilter(event.target.value as ClassFilter);
                  setPage(1);
                }}
              >
                <option value="all">All</option>
                <option value="flare">Flare</option>
                <option value="non-flare">Non-flare</option>
              </select>
              <div className="filterActions">
                <button className="primaryAction" type="button" onClick={applyDateRange}>
                  Apply filters
                </button>
                <button type="button" onClick={clearDateRange} disabled={!draftRangeStart && !draftRangeEnd}>
                  Clear
                </button>
              </div>
            </fieldset>
          )}

          <div className="recordsCount">
            <span>{live ? "Latest forecasts" : "Prediction history"}</span>
            <strong>{live ? history.length : totalRecords} forecasts</strong>
          </div>

          {historyState === "loading" && !history.length ? <div className="emptyState">Loading predictions</div> : null}
          {historyState === "error" && !history.length ? <div className="emptyState">API unavailable</div> : null}
          {!history.length && historyState === "idle" ? <div className="emptyState">No predictions stored</div> : null}

          <div className="historyList">
            {history.map((prediction) => (
              <PredictionRow
                key={prediction.prediction_id}
                prediction={prediction}
                active={prediction.prediction_id === selectedPrediction?.prediction_id}
                onSelect={() => selectPrediction(prediction)}
              />
            ))}
          </div>
          {!live && <PaginationControls page={page} totalPages={totalPages} totalRecords={totalRecords} onPageChange={setPage} />}
        </aside>

        {viewMode === "catalog" ? (
          <section
            className="catalogPanel"
            id="view-panel-catalog"
            role="tabpanel"
            aria-labelledby="view-tab-catalog"
            tabIndex={0}
          >
            {history.length ? (
              <>
                <div className="catalogGrid">
                  {history.map((prediction) => (
                    <PredictionCard
                      key={prediction.prediction_id}
                      prediction={prediction}
                      active={prediction.prediction_id === selectedPrediction?.prediction_id}
                      onSelect={() => selectPrediction(prediction)}
                    />
                  ))}
                </div>
                {!live && <PaginationControls page={page} totalPages={totalPages} totalRecords={totalRecords} onPageChange={setPage} />}
              </>
            ) : (
              <div className="emptyState large">No predictions to display</div>
            )}
          </section>
        ) : (
          <section
            className="detailPanel"
            id="view-panel-detail"
            role="tabpanel"
            aria-labelledby="view-tab-detail"
            tabIndex={0}
          >
            {selectedPrediction ? (
              <>
                <div className="eventHeader">
                  <div className="eventTitle">
                    <div>
                      <h2>{selectedPrediction.is_backfill ? "Backfilled forecast" : "Forecast"} for the next 24 hours</h2>
                      <strong>{formatDateTime(selectedPrediction.requested_at)}</strong>
                    </div>
                  </div>
                  <div className="eventMeta">
                    {selectedPrediction.observed_at && (
                      <span>Magnetogram <strong>{formatDateTime(selectedPrediction.observed_at)}</strong></span>
                    )}
                    <span className={`classPill ${predictionTone(selectedPrediction.predicted_class)}`}>{selectedPrediction.predicted_class}</span>
                  </div>
                </div>
                <div className="summaryGrid">
                  <Metric
                    label="Global Flare Probability"
                    value={percent(selectedPrediction.global_flare_probability)}
                  />
                  <Metric
                    label="Predicted class"
                    value={selectedPrediction.predicted_class}
                  />
                  <Metric
                    label="Localized regions"
                    value={String(selectedPrediction.active_regions.length)}
                  />
                  <Metric label="Data source" value="SDO / HMI" />
                </div>

                <section className="candidateComparisonSection" aria-labelledby="candidate-comparison-title">
                  <div className="candidateComparisonHeader">
                    <div>
                      <h2 id="candidate-comparison-title">Candidate region alignment</h2>
                    </div>
                    <span className={`classPill ${predictionTone(selectedPrediction.predicted_class)}`}>
                      {selectedPrediction.predicted_class}
                    </span>
                  </div>
                  <CandidateRegionComparison
                    originalPath={selectedPrediction.full_disk_image_url}
                    candidatePath={selectedPrediction.final_hulls_url}
                    candidateLabel="Final candidate regions"
                    regions={selectedPrediction.active_regions}
                    selectedRank={selectedRegionRank}
                    onSelectRegion={setSelectedRegionRank}
                  />
                  {selectedPrediction.active_regions.length ? (
                    <div className="candidateInspection">
                      <div className="candidateList" role="group" aria-label="Candidate regions">
                        {selectedPrediction.active_regions.map((region) => (
                          <button
                            className={`candidateListItem ${selectedRegionRank === region.rank ? "selected" : ""}`}
                            key={`${selectedPrediction.prediction_id}-candidate-${region.rank}`}
                            type="button"
                            aria-pressed={selectedRegionRank === region.rank}
                            onClick={() => setSelectedRegionRank(region.rank)}
                          >
                            <span>Region {region.rank}</span>
                            <strong>{percent(region.probability)}</strong>
                            <small>Proposal rank {region.rank}</small>
                          </button>
                        ))}
                      </div>
                      {(() => {
                        const region = selectedPrediction.active_regions.find((item) => item.rank === selectedRegionRank);
                        if (!region) {
                          return <p className="candidateInspectorHint">Select a region on the map or in the list to inspect its saved patch and scores.</p>;
                        }
                        return (
                          <div className="regionInspector" aria-live="polite">
                            <ArtifactImage path={region.image_path} label={`Selected region ${region.rank} patch`} sizes="(max-width: 760px) calc(100vw - 52px), 260px" />
                            <div className="regionInspectorBody">
                              <h3>Region {region.rank}</h3>
                              <p>Candidate proposal rank {region.rank}</p>
                              <dl>
                                <div><dt>Flare probability</dt><dd>{percent(region.probability)}</dd></div>
                                <div><dt>Heatmap score</dt><dd>{region.heatmap_score == null ? "Unavailable" : region.heatmap_score.toFixed(4)}</dd></div>
                                <div><dt>Bounding box</dt><dd>{region.bbox_original?.join(", ") ?? "Unavailable"}</dd></div>
                              </dl>
                            </div>
                          </div>
                        );
                      })()}
                    </div>
                  ) : <div className="emptyState">No candidate regions were saved for this prediction.</div>}
                </section>

                <section className="attributionSection">
                  <div className="attributionHeader">
                    <div>
                      <span>Model interpretation</span>
                      <h2>Attribution maps</h2>
                    </div>
                  </div>

                  <AttributionComparison methods={attributionChoices} />
                </section>

                <section className="regionsSection">
                  <div className="sectionHeader">
                    <div>
                      <span>Active regions</span>
                    </div>
                  </div>

                  {selectedPrediction.active_regions.length ? (
                    <div className="regionGrid">
                      {selectedPrediction.active_regions.map((region) => (
                        <button
                          className={`regionCard ${selectedRegionRank === region.rank ? "selected" : ""}`}
                          key={`${selectedPrediction.prediction_id}-${region.rank}`}
                          type="button"
                          aria-pressed={selectedRegionRank === region.rank}
                          onClick={() => setSelectedRegionRank(region.rank)}
                        >
                          <ArtifactImage
                            path={region.image_path}
                            label={`Active region ${region.rank}`}
                            sizes="(max-width: 760px) calc(100vw - 52px), (max-width: 1180px) 45vw, 24vw"
                          />
                          <div className="regionBody">
                            <div className="regionTitle">
                              <strong>Region {region.rank}</strong>
                              <span>{percent(region.probability)}</span>
                            </div>
                            <ProbabilityBar value={region.probability} tone="quiet" />
                            <dl>
                              <div>
                                <dt>Heatmap</dt>
                                <dd>{region.heatmap_score == null ? "n/a" : region.heatmap_score.toFixed(4)}</dd>
                              </div>
                              <div>
                                <dt>Box</dt>
                                <dd>{region.bbox_original?.join(", ") ?? "n/a"}</dd>
                              </div>
                            </dl>
                          </div>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="emptyState">No active regions saved</div>
                  )}
                </section>
              </>
            ) : (
              <div className="emptyState large">{selectedId ? "Prediction details are loading or unavailable" : "No prediction selected"}</div>
            )}
          </section>
        )}
      </section>
    </main>
  );
}
