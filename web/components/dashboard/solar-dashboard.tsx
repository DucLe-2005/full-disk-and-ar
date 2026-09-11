"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";

import { ArtifactImage } from "@/components/dashboard/artifact-image";
import { RefreshIcon, SunIcon } from "@/components/dashboard/icons";
import { AttributionMap, Metric, PaginationControls, PredictionCard, PredictionRow, ProbabilityBar } from "@/components/dashboard/prediction-ui";
import { PAGE_SIZE } from "@/lib/constants";
import { formatDateTime, formatRequestedAtForMessage, formatTime, percent, predictionTone } from "@/lib/formatters";
import type { ClassFilter, LoadState, ViewMode } from "@/types/dashboard";
import type { Prediction, PredictionHistoryPage } from "@/types/prediction";

function findHeatmap(prediction: Prediction, methodName: string) {
  return prediction.heatmaps.find((heatmap) => heatmap.method_name === methodName)?.image_path;
}

export function SolarDashboard() {
  const [history, setHistory] = useState<Prediction[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<Prediction | null>(null);
  const [historyState, setHistoryState] = useState<LoadState>("idle");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [draftRangeStart, setDraftRangeStart] = useState("");
  const [draftRangeEnd, setDraftRangeEnd] = useState("");
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");
  const [rangeRequestVersion, setRangeRequestVersion] = useState(0);
  const [viewMode, setViewMode] = useState<ViewMode>("detail");
  const [classFilter, setClassFilter] = useState<ClassFilter>("all");
  const [lastLoadedAt, setLastLoadedAt] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [totalRecords, setTotalRecords] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const historyRequestId = useRef(0);
  const detailRequestId = useRef(0);

  async function refreshAndEnsureCurrentHour() {
    setStatusMessage(null);

    let refreshMessage: string | null = null;
    try {
      const response = await fetch("/api/jobs/current-hour", {
        method: "POST",
        cache: "no-store"
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail ?? `Current-hour job request failed with ${response.status}`);
      }

      const result = (await response.json()) as {
        status?: string;
        helioviewer_date?: string;
        requested_at?: string;
      };
      const requestedAt = formatRequestedAtForMessage(result.requested_at ?? result.helioviewer_date);

      if (result.status === "queued") {
        refreshMessage = `Queued prediction job for ${requestedAt}`;
      } else if (result.status === "prediction_exists") {
        refreshMessage = `Prediction already exists for ${requestedAt}`;
      } else if (result.status === "job_exists") {
        refreshMessage = `Prediction job already queued for ${requestedAt}`;
      }
    } catch (error) {
      refreshMessage = error instanceof Error ? error.message : "Could not sync current-hour prediction job";
    }

    const loadedHistory = await loadHistory(1);
    setPage(1);
    if (refreshMessage && loadedHistory !== null) {
      setStatusMessage(refreshMessage);
    }
  }

  async function loadHistory(requestedPage = page) {
    const requestId = ++historyRequestId.current;
    setHistoryState("loading");
    setStatusMessage(null);

    try {
      const params = new URLSearchParams({
        page: String(requestedPage),
        page_size: String(PAGE_SIZE)
      });
      if (rangeStart) {
        params.set("start_time", rangeStart);
      }
      if (rangeEnd) {
        params.set("end_time", rangeEnd);
      }
      if (classFilter !== "all") {
        params.set("predicted_class", classFilter === "flare" ? "1" : "0");
      }

      const response = await fetch(`/api/history?${params.toString()}`, {
        cache: "no-store"
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail ?? `History request failed with ${response.status}`);
      }

      const data = (await response.json()) as PredictionHistoryPage;
      if (requestId !== historyRequestId.current) {
        return null;
      }
      setHistory(data.items);
      setPage(data.page);
      setTotalRecords(data.total);
      setTotalPages(data.total_pages);
      setLastLoadedAt(new Date().toISOString());
      setSelectedId((current) => {
        if (current && data.items.some((prediction) => prediction.prediction_id === current)) {
          return current;
        }
        return data.items[0]?.prediction_id ?? null;
      });
      setHistoryState("idle");
      return data.items;
    } catch (error) {
      if (requestId !== historyRequestId.current) {
        return null;
      }
      setHistoryState("error");
      const message = error instanceof Error ? error.message : "Could not load history";
      setStatusMessage(message === "fetch failed" ? "Backend API unavailable" : message);
      return null;
    }
  }

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadHistory(page);
    }, 150);
    return () => window.clearTimeout(timeoutId);
  }, [classFilter, page, rangeEnd, rangeRequestVersion, rangeStart]);

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
    if (selectedDetail?.prediction_id === selectedId) {
      return selectedDetail;
    }
    const visibleSelection = history.find((prediction) => prediction.prediction_id === selectedId);
    return visibleSelection ?? history[0] ?? null;
  }, [history, selectedDetail, selectedId]);

  useEffect(() => {
    if (!selectedId) {
      setSelectedDetail(null);
      return;
    }

    const requestId = ++detailRequestId.current;
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

  function selectPrediction(prediction: Prediction) {
    setSelectedId(prediction.prediction_id);
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
            {lastLoadedAt ? `Last updated: ${formatTime(lastLoadedAt)}` : historyState === "error" ? "Last updated: unavailable" : "Last updated: --"}
          </span>
          <button
            className="refreshButton"
            type="button"
            disabled={historyState === "loading"}
            aria-label={historyState === "loading" ? "Refreshing predictions" : "Refresh predictions"}
            onClick={() => void refreshAndEnsureCurrentHour()}
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

          <div className="recordsCount"><span>Prediction history</span><strong>{totalRecords} records</strong></div>

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
          <PaginationControls page={page} totalPages={totalPages} totalRecords={totalRecords} onPageChange={setPage} />
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
                <PaginationControls page={page} totalPages={totalPages} totalRecords={totalRecords} onPageChange={setPage} />
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
                    <strong>{formatDateTime(selectedPrediction.requested_at)}</strong>
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

                <div className="observationGrid">
                  <section className="visualStage">
                    <div className="sectionHeader">
                      <div>
                        <span>Full-Disk HMI Magnetogram</span>
                      </div>
                      <span className={`classPill ${predictionTone(selectedPrediction.predicted_class)}`}>
                        {selectedPrediction.predicted_class}
                      </span>
                    </div>
                    <ArtifactImage
                      path={selectedPrediction.full_disk_image_url}
                      label="Full-Disk HMI Magnetogram"
                      sizes="(max-width: 1180px) calc(100vw - 28px), calc((100vw - 374px) / 2)"
                      eager
                    />
                  </section>

                  <section className="visualStage">
                    <div className="sectionHeader">
                      <div>
                        <span>Candidate Regions</span>
                        <strong>
                          {selectedPrediction.actual_flare_overlay_url
                            ? "Actual M/X flare locations mapped"
                            : selectedPrediction.actual_events_status === "no_events"
                              ? "No actual M/X flares in the next 24 hours"
                              : "Actual flare locations loading"}
                        </strong>
                      </div>
                    </div>
                    <ArtifactImage
                      path={selectedPrediction.actual_flare_overlay_url ?? selectedPrediction.final_hulls_url}
                      label={selectedPrediction.actual_flare_overlay_url ? "Candidate Regions with Actual Flare Events" : "Candidate Regions"}
                      sizes="(max-width: 1180px) calc(100vw - 28px), calc((100vw - 374px) / 2)"
                    />
                  </section>
                </div>

                <section className="attributionSection">
                  <div className="attributionHeader">
                    <div>
                      <span>Model interpretation</span>
                      <h2>Attribution maps</h2>
                    </div>
                    <p>Four complementary maps make the attribution evidence scannable at a glance.</p>
                  </div>

                  <div className="sourceMapsGrid">
                    <AttributionMap
                      path={attributionPaths?.guidedGradcam}
                      title="Guided Grad-CAM"
                      description="Localized gradient response"
                    />
                    <AttributionMap
                      path={attributionPaths?.integratedGradients}
                      title="Integrated Gradients"
                      description="Accumulated input contribution"
                    />
                    <AttributionMap
                      path={attributionPaths?.deepshap}
                      title="DeepLiftShap"
                      description="Baseline-relative contribution"
                    />
                    <AttributionMap
                      path={attributionPaths?.consensus}
                      title="Fused Attribution Map"
                      description="Element-wise product"
                    />
                  </div>
                </section>

                <section className="regionsSection">
                  <div className="sectionHeader">
                    <div>
                      <span>Active region spotlight</span>
                      <strong>Localized probability, heatmap score, and source coordinates</strong>
                    </div>
                  </div>

                  {selectedPrediction.active_regions.length ? (
                    <div className="regionGrid">
                      {selectedPrediction.active_regions.map((region) => (
                        <article className="regionCard" key={`${selectedPrediction.prediction_id}-${region.rank}`}>
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
                        </article>
                      ))}
                    </div>
                  ) : (
                    <div className="emptyState">No active regions saved</div>
                  )}
                </section>
              </>
            ) : (
              <div className="emptyState large">No prediction selected</div>
            )}
          </section>
        )}
      </section>
    </main>
  );
}
