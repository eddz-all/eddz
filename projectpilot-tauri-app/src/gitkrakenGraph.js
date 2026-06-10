import React from "react";
import { createRoot } from "react-dom/client";
import GraphContainer, {
  changesZone,
  commitAuthorZone,
  commitDateTimeZone,
  commitMessageZone,
  commitNodeType,
  commitShaZone,
  commitZone,
  graphCommitDescDisplayModes,
  mergeNodeType,
  refZone
} from "@gitkraken/gitkraken-components";
import "@gitkraken/gitkraken-components/dist/styles.css";
import "./gitkrakenGraph.css";

export function createGitKrakenGraphRenderer({ displayValue, parseTimestamp, setToast }) {
  const payloads = new Map();
  const roots = new Map();
  const resizeObservers = new Map();
  let renderSerial = 0;

  function register(repo) {
    const mountId = `gitkraken-graph-${++renderSerial}`;
    payloads.set(mountId, repo);
    return mountId;
  }

  function reset() {
    renderSerial = 0;
    payloads.clear();
  }

  function mount() {
    const activeMounts = new Set();
    document.querySelectorAll("[data-gitkraken-graph]").forEach((mountElement) => {
      const mountId = mountElement.dataset.gitkrakenGraph;
      const repo = payloads.get(mountId);
      if (!mountId || !repo) return;

      activeMounts.add(mountElement);
      let root = roots.get(mountElement);
      if (!root) {
        root = createRoot(mountElement);
        roots.set(mountElement, root);
      }

      const shell = document.querySelector(`[data-gitkraken-graph-shell="${CSS.escape(mountId)}"]`);
      const renderGraph = () => {
        try {
          root.render(React.createElement(GitKrakenCommitGraph, {
            repo,
            containerWidth: Math.round(mountElement.getBoundingClientRect().width)
          }));
          shell?.classList.add("gitkraken-graph-mounted");
          shell?.classList.remove("gitkraken-graph-error");
        } catch (error) {
          console.error("GitKraken graph render failed", error);
          shell?.classList.remove("gitkraken-graph-mounted");
          shell?.classList.add("gitkraken-graph-error");
        }
      };

      renderGraph();

      if (!resizeObservers.has(mountElement) && "ResizeObserver" in window) {
        const observerState = { lastWidth: Math.round(mountElement.getBoundingClientRect().width) };
        const observer = new ResizeObserver((entries) => {
          const nextWidth = Math.round(entries[0]?.contentRect?.width || 0);
          if (Math.abs(nextWidth - observerState.lastWidth) < 8) return;
          observerState.lastWidth = nextWidth;
          renderGraph();
        });
        observer.observe(mountElement);
        resizeObservers.set(mountElement, { observer, observerState });
      }
    });

    for (const [mountElement, root] of roots.entries()) {
      if (activeMounts.has(mountElement) && document.body.contains(mountElement)) continue;
      root.unmount();
      roots.delete(mountElement);
      resizeObservers.get(mountElement)?.observer.disconnect();
      resizeObservers.delete(mountElement);
    }
  }

  function GitKrakenCommitGraph({ repo, containerWidth }) {
    const rows = toGraphRows(repo);
    const rowsStats = rows.reduce((accumulator, row) => {
      if (row.stats) {
        accumulator[row.sha] = row.stats;
      }
      return accumulator;
    }, {});

    return React.createElement(GraphContainer, {
      graphRows: rows,
      columnsSettings: graphColumns(containerWidth),
      repoPath: repo.repo_path || repo.project_path || "",
      rowsStats,
      shaLength: 7,
      platform: "darwin",
      graphCommitDescDisplayMode: graphCommitDescDisplayModes.NEVER,
      highlightRowsOnRefHover: true,
      showRemoteNamesOnRefs: true,
      suppressNonRefRowTooltips: true,
      useAuthorInitialsForAvatars: true,
      getExternalIcon,
      formatCommitDateTime,
      formatCommitMessage,
      onDoubleClickGraphRow: (_event, row) => {
        setToast(`Commit ${displayValue(row?.sha || "").slice(0, 7)}`);
      }
    });
  }

  function graphColumns(containerWidth) {
    const width = Number(containerWidth) || 0;
    if (width < 980) {
      return {
        [commitZone]: { width: 42, isHidden: false, mode: "compact", order: 0 },
        [commitMessageZone]: { width: 440, isHidden: false, order: 1 },
        [refZone]: { width: 260, isHidden: false, order: 2 },
        [commitAuthorZone]: { width: 92, isHidden: true, order: 3 },
        [commitDateTimeZone]: { width: 96, isHidden: true, order: 4 },
        [commitShaZone]: { width: 64, isHidden: false, order: 5 },
        [changesZone]: { width: 72, isHidden: true, order: 6 }
      };
    }

    if (width < 1220) {
      return {
        [commitZone]: { width: 46, isHidden: false, mode: "compact", order: 0 },
        [commitMessageZone]: { width: 500, isHidden: false, order: 1 },
        [refZone]: { width: 310, isHidden: false, order: 2 },
        [commitAuthorZone]: { width: 108, isHidden: true, order: 3 },
        [commitDateTimeZone]: { width: 92, isHidden: true, order: 4 },
        [commitShaZone]: { width: 68, isHidden: false, order: 5 },
        [changesZone]: { width: 72, isHidden: true, order: 6 }
      };
    }

    return {
      [commitZone]: { width: 50, isHidden: false, mode: "compact", order: 0 },
      [commitMessageZone]: { width: 540, isHidden: false, order: 1 },
      [refZone]: { width: 360, isHidden: false, order: 2 },
      [commitAuthorZone]: { width: 124, isHidden: true, order: 3 },
      [commitDateTimeZone]: { width: 92, isHidden: false, order: 4 },
      [commitShaZone]: { width: 70, isHidden: false, order: 5 },
      [changesZone]: { width: 72, isHidden: true, order: 6 }
    };
  }

  function getExternalIcon(iconKey) {
    const safeIconKey = String(iconKey || "unknown").replace(/[^a-z0-9_-]/gi, "-");
    return React.createElement("span", {
      key: safeIconKey,
      className: `gitkraken-icon gitkraken-icon-${safeIconKey}`,
      "aria-hidden": "true"
    });
  }

  function formatCommitMessage(commitMessage) {
    return {
      summary: displayValue(commitMessage || "")
    };
  }

  function formatCommitDateTime(value) {
    const seconds = Number(value);
    if (!Number.isFinite(seconds) || seconds <= 0) return "";
    return relativeTimeFromTimestamp(seconds * 1000);
  }

  function toGraphRows(repo) {
    return (repo.commits || []).map((commit, index) => {
      const refs = Array.isArray(commit.refs) ? commit.refs : [];
      const heads = refs
        .filter((ref) => ref.type === "branch")
        .map((ref) => ({
          id: ref.full_name || `refs/heads/${ref.name}`,
          name: ref.name,
          isCurrentHead: Boolean(ref.is_head || commit.is_head),
          upstream: ref.upstream ? { name: ref.upstream, id: `refs/remotes/${ref.upstream}` } : undefined
        }));
      const remotes = refs
        .filter((ref) => ref.type === "remote")
        .map((ref) => {
          const name = String(ref.name || "");
          const [owner, ...rest] = name.split("/");
          return {
            id: ref.full_name || `refs/remotes/${name}`,
            name: rest.join("/") || name,
            owner: rest.length ? owner : "origin",
            current: Boolean(ref.is_head)
          };
        });
      const tags = refs
        .filter((ref) => ref.type === "tag")
        .map((ref) => ({
          id: ref.full_name || `refs/tags/${ref.name}`,
          name: ref.name,
          annotated: false
        }));

      return {
        sha: String(commit.hash || commit.sha || commit.short_hash || `commit-${index}`),
        parents: (commit.parents || []).map(String),
        author: displayValue(commit.author || "ProjectPilot"),
        email: displayValue(commit.email || "projectpilot@example.local"),
        date: commitTimestampSeconds(commit, index),
        message: displayValue(commit.subject || commit.message || commit.summary || "Commit"),
        type: commit.is_merge || (commit.parents || []).length > 1 ? mergeNodeType : commitNodeType,
        heads,
        remotes,
        tags,
        stats: commit.stats || undefined
      };
    });
  }

  function commitTimestampSeconds(commit, index) {
    const rawDate = commit.date || commit.commit_date || commit.timestamp || commit.created_at;
    const parsed = parseTimestamp(rawDate);
    if (parsed) {
      return Math.floor(parsed / 1000);
    }

    const relative = String(commit.relative_time || "");
    const now = Date.now();
    const match = relative.match(/(\d+)\s*(minute|minutes|min|hour|hours|day|days|week|weeks|month|months|year|years)/i);
    if (!match) {
      return Math.floor((now - index * 3600000) / 1000);
    }

    const value = Number(match[1]);
    const unit = match[2].toLowerCase();
    const multiplier =
      unit.startsWith("min") ? 60000 :
      unit.startsWith("hour") ? 3600000 :
      unit.startsWith("day") ? 86400000 :
      unit.startsWith("week") ? 604800000 :
      unit.startsWith("month") ? 2592000000 :
      unit.startsWith("year") ? 31536000000 :
      3600000;
    return Math.floor((now - value * multiplier) / 1000);
  }

  function relativeTimeFromTimestamp(timestamp) {
    const diff = Math.max(0, Date.now() - Number(timestamp));
    const minute = 60000;
    const hour = 60 * minute;
    const day = 24 * hour;
    if (diff < minute) return "now";
    if (diff < hour) return `${Math.round(diff / minute)}m ago`;
    if (diff < day) return `${Math.round(diff / hour)}h ago`;
    return `${Math.round(diff / day)}d ago`;
  }

  return {
    mount,
    register,
    reset
  };
}
