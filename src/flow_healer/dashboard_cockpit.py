from __future__ import annotations

from datetime import UTC, datetime
from html import escape
import json
from pathlib import Path
from typing import Any

from .config import AppConfig
from .service import FlowHealerService
from .store import SQLiteStore


def queue_payload(config: AppConfig, service: FlowHealerService) -> dict[str, Any]:
    status_rows = service.cached_status_rows(None)
    repo_status_map = {
        str(row.get("repo") or "").strip(): row
        for row in status_rows
        if str(row.get("repo") or "").strip()
    }
    rows: list[dict[str, Any]] = []
    for repo in config.repos:
        repo_name = str(repo.repo_name or "").strip()
        if not repo_name:
            continue
        repo_row = repo_status_map.get(repo_name, {})
        explanation_map = {
            str(item.get("issue_id") or "").strip(): item
            for item in (repo_row.get("issue_explanations") or [])
            if str(item.get("issue_id") or "").strip()
        }
        store = SQLiteStore(config.repo_db_path(repo_name))
        store.bootstrap()
        try:
            issues = store.list_healer_issues(limit=500)
        finally:
            store.close()
        for issue in issues:
            issue_id = str(issue.get("issue_id") or "").strip()
            rows.append(
                _queue_row_from_issue(
                    issue=issue,
                    repo_name=repo_name,
                    repo_row=repo_row,
                    explanation=explanation_map.get(issue_id),
                )
            )
    rows.sort(key=_queue_sort_key)
    return {
        "rows": rows,
        "views": _build_views(rows),
        "summary": _build_summary(rows),
        "generated_at": _now_label(),
    }


def issue_detail_payload(
    config: AppConfig,
    service: FlowHealerService,
    *,
    repo_name: str,
    issue_id: str,
) -> dict[str, Any]:
    normalized_repo = str(repo_name or "").strip()
    normalized_issue = str(issue_id or "").strip()
    if not normalized_repo or not normalized_issue:
        return {"found": False, "repo": {}, "issue": {}, "attempts": [], "activity": []}

    status_rows = service.cached_status_rows(None)
    repo_row = next((row for row in status_rows if str(row.get("repo") or "").strip() == normalized_repo), {})
    repo_settings = next((repo for repo in config.repos if repo.repo_name == normalized_repo), None)
    if repo_settings is None:
        return {"found": False, "repo": {}, "issue": {}, "attempts": [], "activity": []}

    store = SQLiteStore(config.repo_db_path(normalized_repo))
    store.bootstrap()
    try:
        issue = store.get_healer_issue(normalized_issue)
        attempts = store.list_healer_attempts(issue_id=normalized_issue, limit=25)
    finally:
        store.close()
    if issue is None:
        return {"found": False, "repo": {}, "issue": {}, "attempts": [], "activity": []}

    explanation = next(
        (
            item
            for item in (repo_row.get("issue_explanations") or [])
            if str(item.get("issue_id") or "").strip() == normalized_issue
        ),
        {},
    )
    issue_view = _queue_row_from_issue(issue=issue, repo_name=normalized_repo, repo_row=repo_row, explanation=explanation)
    issue_view["body"] = str(issue.get("body") or "")
    issue_view["labels"] = list(issue.get("labels") or [])
    issue_view["author"] = str(issue.get("author") or "")
    issue_view["output_targets"] = list(issue.get("output_targets") or [])
    issue_view["feedback_context"] = str(issue.get("feedback_context") or "")
    issue_view["workspace_path"] = str(issue.get("workspace_path") or "")
    issue_view["branch_name"] = str(issue.get("branch_name") or "")

    # Import lazily to avoid circular import during module initialization.
    from .web_dashboard import _collect_activity, _collect_recent_logs

    logs = _collect_recent_logs(config, max_lines=180)
    activity = _collect_activity(config, service, logs=logs, status_rows=status_rows, limit=240)
    attempt_ids = {str(item.get("attempt_id") or "").strip() for item in attempts if str(item.get("attempt_id") or "").strip()}
    pr_id = str(issue.get("pr_number") or "").strip()
    related_activity = [
        item
        for item in activity
        if str(item.get("repo") or "").strip() == normalized_repo
        and (
            str(item.get("issue_id") or "").strip() == normalized_issue
            or str(item.get("attempt_id") or "").strip() in attempt_ids
            or (pr_id and str(item.get("pr_id") or "").strip() == pr_id)
        )
    ][:40]
    return {
        "found": True,
        "repo": {
            "name": normalized_repo,
            "path": str(repo_row.get("path") or repo_settings.healer_repo_path),
            "paused": bool(repo_row.get("paused")),
            "trust": dict(repo_row.get("trust") or {}),
            "policy": dict(repo_row.get("policy") or {}),
        },
        "issue": issue_view,
        "attempts": attempts,
        "activity": related_activity,
        "generated_at": _now_label(),
    }


def render_dashboard(config: AppConfig, service: FlowHealerService, notice: str) -> str:
    initial_queue = queue_payload(config, service)
    # Import lazily to avoid circular import at module import time.
    from .web_dashboard import _overview_payload

    initial = json.dumps(
        {
            "queue": initial_queue,
            "overview": _overview_payload(config, service),
        },
        default=str,
    ).replace("</", "<\\/")
    repo_options = "".join(
        f"<option value='{escape(repo.repo_name)}'>{escape(repo.repo_name)}</option>" for repo in config.repos
    )
    notice_html = (
        f"<div class='mb-6 rounded-2xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-100 shadow-lg shadow-amber-950/30'>{escape(notice)}</div>"
        if notice
        else ""
    )
    return f"""
<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Flow Healer Dashboard</title>
  <link rel='preconnect' href='https://fonts.googleapis.com'>
  <link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>
  <link href='https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap' rel='stylesheet'>
  <script src='https://cdn.tailwindcss.com'></script>
  <script defer src='https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js'></script>
  <script>
    tailwind.config = {{
      theme: {{
        extend: {{
          fontFamily: {{
            display: ['Space Grotesk', 'ui-sans-serif', 'system-ui', 'sans-serif'],
            mono: ['IBM Plex Mono', 'SFMono-Regular', 'ui-monospace', 'monospace']
          }},
        }}
      }}
    }}
  </script>
  <style>
    :root {{
      color-scheme: dark;
      --fh-bg: #0a0d13;
      --fh-panel: #11151d;
      --fh-panel-soft: #171c25;
      --fh-panel-mute: #1d2430;
      --fh-border: #dbe4f0;
      --fh-border-soft: #344256;
      --fh-text: #eff4fb;
      --fh-muted: #95a3b8;
      --fh-shadow: rgba(0, 0, 0, 0.45);
      --fh-atmosphere:
        radial-gradient(circle at top left, rgba(56, 189, 248, 0.12), transparent 30%),
        radial-gradient(circle at top right, rgba(34, 197, 94, 0.08), transparent 24%),
        linear-gradient(180deg, #0a0d13 0%, #0f141c 52%, #0b0f15 100%);
    }}
    :root[data-theme='light'] {{
      color-scheme: light;
      --fh-bg: #edf3f9;
      --fh-panel: #ffffff;
      --fh-panel-soft: #f8fbff;
      --fh-panel-mute: #edf2f8;
      --fh-border: #0f172a;
      --fh-border-soft: #64748b;
      --fh-text: #111827;
      --fh-muted: #475569;
      --fh-shadow: rgba(15, 23, 42, 0.18);
      --fh-atmosphere:
        radial-gradient(circle at top left, rgba(14, 165, 233, 0.10), transparent 28%),
        radial-gradient(circle at top right, rgba(16, 185, 129, 0.08), transparent 22%),
        linear-gradient(180deg, #f7fbff 0%, #eef3f9 52%, #e7edf5 100%);
    }}
    body {{
      margin: 0;
      background: var(--fh-bg);
      color: var(--fh-text);
      font-family: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif;
    }}
    .app-atmosphere {{
      background: var(--fh-atmosphere);
    }}
    .dashboard-root .panel {{
      background: color-mix(in srgb, var(--fh-panel) 86%, transparent);
      border: 1px solid color-mix(in srgb, var(--fh-border-soft) 60%, transparent);
      box-shadow: 0 22px 50px var(--fh-shadow);
      border-radius: 1.25rem;
    }}
  </style>
</head>
<body class='min-h-screen'>
  <div class='app-atmosphere absolute inset-0 -z-10'></div>
  <main
    class='dashboard-root mx-auto max-w-[1680px] px-4 py-6 sm:px-6 lg:px-8'
    x-data='dashboardApp()'
    x-init='init()'
    @keydown.window.escape='closeOverlays()'
    @keydown.window.prevent.slash='focusSearch()'
    @keydown.window.arrow-down.prevent='selectNextIssue()'
    @keydown.window.arrow-up.prevent='selectPreviousIssue()'
    @keydown.window.enter.prevent='openSelectedIssue()'
  >
    {notice_html}

    <header class='panel mb-6 px-5 py-5'>
      <div class='flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between'>
        <div class='space-y-3'>
          <div class='inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.28em] text-cyan-200'>
            <span class='inline-block h-2 w-2 rounded-full bg-cyan-300'></span>
            Linear-Light Cockpit
          </div>
          <div>
            <h1 class='font-display text-3xl font-semibold tracking-tight text-white sm:text-4xl'>Flow Healer Dashboard</h1>
            <p class='mt-2 max-w-3xl text-sm text-slate-300'>
              Issue queue first, detail second, system health as a supporting surface instead of the main event.
            </p>
          </div>
        </div>
        <div class='flex flex-wrap items-center gap-3'>
          <div class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-400'>Queue Rows</div>
            <div class='mt-2 text-lg font-semibold text-white' x-text='queueRows.length'></div>
          </div>
          <button @click='toggleCommandPalette()' class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-medium text-slate-100 transition hover:bg-white/10'>Command Palette</button>
          <button @click='refresh()' class='rounded-2xl border border-cyan-400/20 bg-cyan-400/15 px-4 py-3 text-sm font-medium text-cyan-100 transition hover:bg-cyan-400/20'>Refresh</button>
          <button @click='toggleTheme()' class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-medium text-slate-100 transition hover:bg-white/10'>Dark / Light</button>
        </div>
      </div>
    </header>

    <section class='grid grid-cols-1 gap-5 xl:grid-cols-[260px_minmax(0,1.15fr)_minmax(380px,0.9fr)]'>
      <aside class='panel p-4'>
        <div class='mb-4'>
          <div class='text-[11px] uppercase tracking-[0.24em] text-slate-500'>Saved Views</div>
          <h2 class='mt-2 text-xl font-semibold text-white'>Issue Queue</h2>
          <p class='mt-2 text-sm text-slate-400'>Switch between focused views without leaving the queue.</p>
        </div>
        <div class='space-y-2'>
          <template x-for='view in queueViews' :key='view.id'>
            <button
              type='button'
              @click='selectView(view.id)'
              :class='selectedView === view.id ? "border-cyan-300/40 bg-cyan-400/10 text-cyan-100" : "border-white/10 bg-white/5 text-slate-200 hover:bg-white/10"'
              class='flex w-full items-center justify-between rounded-2xl border px-3 py-3 text-left text-sm transition'
            >
              <span x-text='view.label'></span>
              <span class='rounded-full bg-black/20 px-2 py-0.5 text-xs' x-text='view.count'></span>
            </button>
          </template>
        </div>
        <div class='mt-5 rounded-2xl border border-white/10 bg-white/5 p-3'>
          <label class='block'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-500'>Repo</div>
            <select x-model='repoFilter' class='mt-2 w-full bg-transparent text-sm text-white outline-none'>
              <option value=''>All repos</option>
              {repo_options}
            </select>
          </label>
        </div>
        <button type='button' @click='showSystemHealth = !showSystemHealth' class='mt-5 flex w-full items-center justify-between rounded-2xl border border-white/10 bg-white/5 px-3 py-3 text-left text-sm text-slate-100 transition hover:bg-white/10'>
          <span>System Health</span>
          <span x-text='showSystemHealth ? "Hide" : "Show"'></span>
        </button>
        <div x-show='showSystemHealth' x-transition.opacity class='mt-3 space-y-3'>
          <template x-for='row in rows' :key='`health-${{row.repo || "repo"}}`'>
            <div class='rounded-2xl border border-white/10 bg-slate-950/30 p-3'>
              <div class='flex items-center justify-between gap-2'>
                <div class='text-sm font-medium text-white' x-text='row.repo || "Repo"'></div>
                <span class='rounded-full border px-2 py-1 text-[11px] uppercase tracking-[0.2em]' :class='trustBadgeClass((row.trust || {{}}).state || "")' x-text='formatTrustState((row.trust || {{}}).state || "")'></span>
              </div>
              <p class='mt-2 text-sm text-slate-300' x-text='(row.trust || {{}}).summary || "No trust summary available."'></p>
              <p class='mt-2 text-xs text-slate-400' x-text='(row.policy || {{}}).summary || "No policy summary available."'></p>
            </div>
          </template>
        </div>
      </aside>

      <section class='panel overflow-hidden'>
        <div class='border-b border-white/10 px-5 py-5'>
          <div class='flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between'>
            <div>
              <div class='text-[11px] uppercase tracking-[0.24em] text-slate-500'>Queue</div>
              <h2 class='mt-2 text-2xl font-semibold text-white'>Issue Queue</h2>
              <p class='mt-2 text-sm text-slate-400'>Use the keyboard or click into an issue to keep all the context together.</p>
            </div>
            <div class='grid grid-cols-2 gap-3 lg:grid-cols-4'>
              <div class='rounded-2xl border border-white/10 bg-white/5 px-3 py-3'>
                <div class='text-[11px] uppercase tracking-[0.2em] text-slate-500'>Total</div>
                <div class='mt-2 text-lg font-semibold text-white' x-text='queueSummary.total || 0'></div>
              </div>
              <div class='rounded-2xl border border-white/10 bg-white/5 px-3 py-3'>
                <div class='text-[11px] uppercase tracking-[0.2em] text-slate-500'>Running</div>
                <div class='mt-2 text-lg font-semibold text-amber-200' x-text='queueSummary.running || 0'></div>
              </div>
              <div class='rounded-2xl border border-white/10 bg-white/5 px-3 py-3'>
                <div class='text-[11px] uppercase tracking-[0.2em] text-slate-500'>Blocked</div>
                <div class='mt-2 text-lg font-semibold text-rose-200' x-text='queueSummary.blocked || 0'></div>
              </div>
              <div class='rounded-2xl border border-white/10 bg-white/5 px-3 py-3'>
                <div class='text-[11px] uppercase tracking-[0.2em] text-slate-500'>PR Open</div>
                <div class='mt-2 text-lg font-semibold text-emerald-200' x-text='queueSummary.pr_open || 0'></div>
              </div>
            </div>
          </div>
          <div class='mt-5 grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1.4fr)_220px_auto]'>
            <label class='rounded-2xl border border-white/10 bg-white/5 px-3 py-2'>
              <div class='text-[11px] uppercase tracking-[0.24em] text-slate-500'>Search</div>
              <input x-ref='queueSearch' x-model='searchText' type='text' placeholder='Issue id, title, failure hint, repo...' class='mt-2 w-full bg-transparent text-sm text-white outline-none placeholder:text-slate-500'>
            </label>
            <div class='rounded-2xl border border-white/10 bg-white/5 px-3 py-2'>
              <div class='text-[11px] uppercase tracking-[0.24em] text-slate-500'>Selected View</div>
              <div class='mt-2 text-sm text-white' x-text='selectedViewLabel'></div>
            </div>
            <button type='button' @click='clearFilters()' class='rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-medium text-slate-200 transition hover:bg-white/10'>Clear filters</button>
          </div>
        </div>

        <div class='px-5 py-4'>
          <div class='mb-3 flex items-center justify-between gap-3 text-xs text-slate-400'>
            <div x-text='`${{filteredQueueRows.length}} visible • ${{queueRows.length}} total`'></div>
            <div x-text='lastUpdatedLabel'></div>
          </div>
          <div class='space-y-2'>
            <template x-for='item in filteredQueueRows' :key='`queue-${{item.repo}}-${{item.issue_id}}`'>
              <button
                type='button'
                @click='openIssueDetail(item.issue_id, item.repo)'
                :class='selectedIssueId === item.issue_id && selectedRepo === item.repo ? "border-cyan-300/40 bg-cyan-400/10" : "border-white/10 bg-slate-950/20 hover:bg-white/5"'
                class='flex w-full items-start gap-4 rounded-[24px] border px-4 py-4 text-left transition'
              >
                <div class='mt-1 h-2.5 w-2.5 rounded-full' :class='statusDotClass(item.state)'></div>
                <div class='min-w-0 flex-1'>
                  <div class='flex flex-wrap items-center gap-2'>
                    <span class='rounded-full border px-2 py-1 text-[11px] uppercase tracking-[0.2em]' :class='stateBadgeClass(item.state)' x-text='item.state_label'></span>
                    <span class='rounded-full border border-white/10 bg-white/5 px-2 py-1 text-[11px] uppercase tracking-[0.2em] text-slate-300' x-text='item.repo'></span>
                    <template x-if='item.pr_badge'>
                      <span class='rounded-full border border-emerald-300/20 bg-emerald-400/10 px-2 py-1 text-[11px] text-emerald-100' x-text='item.pr_badge'></span>
                    </template>
                  </div>
                  <div class='mt-3 flex items-start justify-between gap-4'>
                    <div class='min-w-0'>
                      <div class='text-base font-semibold text-white' x-text='`#${{item.issue_id}} ${{item.title}}`'></div>
                      <p class='mt-2 text-sm text-slate-400' x-text='item.failure_summary || item.explanation_summary || "No failure hint recorded."'></p>
                    </div>
                    <div class='text-right text-xs text-slate-500'>
                      <div x-text='item.updated_at || "Unknown"'></div>
                      <div class='mt-2' x-text='item.recommended_action || ""'></div>
                    </div>
                  </div>
                </div>
              </button>
            </template>
          </div>

          <div class='mt-5 rounded-[24px] border border-white/10 bg-white/5 p-4 lg:hidden'>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-500'>Activity Cards</div>
            <p class='mt-2 text-sm text-slate-400'>Tap any card for full context.</p>
          </div>
        </div>
      </section>

      <aside class='panel p-5'>
        <div class='flex items-start justify-between gap-3'>
          <div>
            <div class='text-[11px] uppercase tracking-[0.24em] text-slate-500'>Issue Detail</div>
            <h2 class='mt-2 text-2xl font-semibold text-white'>Issue Detail</h2>
            <p class='mt-2 text-sm text-slate-400'>Overview, attempts, validation, activity, and actions live together.</p>
          </div>
        </div>
        <div class='mt-5 flex flex-wrap gap-2'>
          <template x-for='tab in detailTabs' :key='tab.id'>
            <button type='button' @click='selectedDetailTab = tab.id' :class='selectedDetailTab === tab.id ? "border-cyan-300/40 bg-cyan-400/10 text-cyan-100" : "border-white/10 bg-white/5 text-slate-300 hover:bg-white/10"' class='rounded-full border px-3 py-2 text-xs font-medium transition' x-text='tab.label'></button>
          </template>
        </div>

        <template x-if='!selectedIssueDetail || !selectedIssueDetail.found'>
          <div class='mt-5 rounded-[24px] border border-dashed border-white/10 bg-white/5 p-5 text-sm text-slate-400'>
            Choose an issue from the queue to load the right-side detail pane.
          </div>
        </template>

        <template x-if='selectedIssueDetail && selectedIssueDetail.found'>
          <div class='mt-5 space-y-4'>
            <section x-show='selectedDetailTab === "overview"' class='rounded-[24px] border border-white/10 bg-white/5 p-4'>
              <div class='flex flex-wrap items-center gap-2'>
                <span class='rounded-full border px-2 py-1 text-[11px] uppercase tracking-[0.2em]' :class='stateBadgeClass((selectedIssueDetail.issue || {{}}).state || "")' x-text='(selectedIssueDetail.issue || {{}}).state || "unknown"'></span>
                <span class='rounded-full border border-white/10 bg-white/5 px-2 py-1 text-[11px] uppercase tracking-[0.2em] text-slate-300' x-text='`#${{(selectedIssueDetail.issue || {{}}).issue_id || ""}}`'></span>
                <template x-if='(selectedIssueDetail.issue || {{}}).pr_badge'>
                  <span class='rounded-full border border-emerald-300/20 bg-emerald-400/10 px-2 py-1 text-[11px] text-emerald-100' x-text='(selectedIssueDetail.issue || {{}}).pr_badge'></span>
                </template>
              </div>
              <h3 class='mt-3 text-xl font-semibold text-white' x-text='(selectedIssueDetail.issue || {{}}).title || "Issue"'></h3>
              <p class='mt-2 text-sm text-slate-300' x-text='(selectedIssueDetail.issue || {{}}).explanation_summary || (selectedIssueDetail.issue || {{}}).failure_summary || "No issue summary available."'></p>
              <div class='mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2'>
                <div class='rounded-2xl border border-white/10 bg-slate-950/30 px-3 py-3'>
                  <div class='text-[11px] uppercase tracking-[0.2em] text-slate-500'>Recommended action</div>
                  <div class='mt-2 text-sm text-cyan-100' x-text='(selectedIssueDetail.issue || {{}}).recommended_action || "observe_issue"'></div>
                </div>
                <div class='rounded-2xl border border-white/10 bg-slate-950/30 px-3 py-3'>
                  <div class='text-[11px] uppercase tracking-[0.2em] text-slate-500'>Repo Trust</div>
                  <div class='mt-2 text-sm text-white' x-text='((selectedIssueDetail.repo || {{}}).trust || {{}}).summary || "No trust summary available."'></div>
                </div>
              </div>
              <div class='mt-4 rounded-2xl border border-white/10 bg-slate-950/30 px-3 py-3'>
                <div class='text-[11px] uppercase tracking-[0.2em] text-slate-500'>Issue contract</div>
                <pre class='mt-2 overflow-auto whitespace-pre-wrap font-mono text-xs leading-6 text-slate-200' x-text='(selectedIssueDetail.issue || {{}}).body || ""'></pre>
              </div>
            </section>

            <section x-show='selectedDetailTab === "attempts"' class='rounded-[24px] border border-white/10 bg-white/5 p-4'>
              <h3 class='text-sm font-semibold uppercase tracking-[0.22em] text-slate-300'>Attempts</h3>
              <div class='mt-4 space-y-3'>
                <template x-for='attempt in (selectedIssueDetail.attempts || [])' :key='attempt.attempt_id'>
                  <div class='rounded-2xl border border-white/10 bg-slate-950/30 px-3 py-3'>
                    <div class='flex items-center justify-between gap-3'>
                      <div class='text-sm font-medium text-white' x-text='attempt.attempt_id'></div>
                      <span class='rounded-full border px-2 py-1 text-[11px] uppercase tracking-[0.2em]' :class='stateBadgeClass(attempt.state || "")' x-text='attempt.state || "unknown"'></span>
                    </div>
                    <p class='mt-2 text-sm text-slate-300' x-text='attempt.failure_reason || attempt.failure_class || "No failure details recorded."'></p>
                  </div>
                </template>
              </div>
            </section>

            <section x-show='selectedDetailTab === "validation"' class='rounded-[24px] border border-white/10 bg-white/5 p-4'>
              <h3 class='text-sm font-semibold uppercase tracking-[0.22em] text-slate-300'>Validation</h3>
              <div class='mt-4 space-y-3'>
                <template x-for='attempt in (selectedIssueDetail.attempts || [])' :key='`validation-${{attempt.attempt_id}}`'>
                  <div class='rounded-2xl border border-white/10 bg-slate-950/30 px-3 py-3'>
                    <div class='text-xs uppercase tracking-[0.2em] text-slate-500' x-text='attempt.attempt_id'></div>
                    <pre class='mt-2 overflow-auto whitespace-pre-wrap font-mono text-xs leading-6 text-slate-200' x-text='JSON.stringify(attempt.test_summary || {{}}, null, 2)'></pre>
                  </div>
                </template>
              </div>
            </section>

            <section x-show='selectedDetailTab === "activity"' class='rounded-[24px] border border-white/10 bg-white/5 p-4'>
              <h3 class='text-sm font-semibold uppercase tracking-[0.22em] text-slate-300'>Activity</h3>
              <div class='mt-4 space-y-3'>
                <template x-for='item in (selectedIssueDetail.activity || [])' :key='item.id'>
                  <div class='rounded-2xl border border-white/10 bg-slate-950/30 px-3 py-3'>
                    <div class='flex items-center justify-between gap-3'>
                      <div class='text-sm font-medium text-white' x-text='item.summary || item.message || "Activity"'></div>
                      <span class='rounded-full border px-2 py-1 text-[11px] uppercase tracking-[0.2em]' :class='signalBadgeClass(item.signal)' x-text='item.signal || "info"'></span>
                    </div>
                    <p class='mt-2 text-xs text-slate-400' x-text='item.timestamp || ""'></p>
                    <p class='mt-2 text-sm text-slate-300' x-text='item.raw_text || item.message || ""'></p>
                  </div>
                </template>
              </div>
            </section>

            <section x-show='selectedDetailTab === "actions"' class='rounded-[24px] border border-white/10 bg-white/5 p-4'>
              <h3 class='text-sm font-semibold uppercase tracking-[0.22em] text-slate-300'>Actions</h3>
              <p class='mt-2 text-sm text-slate-400'>Run the existing repo actions without leaving the selected issue.</p>
              <label class='mt-4 block'>
                <div class='text-[11px] uppercase tracking-[0.22em] text-slate-500'>Auth token</div>
                <input x-model='authToken' type='password' class='mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/50 px-3 py-2 text-sm text-white outline-none'>
              </label>
              <div class='mt-4 grid grid-cols-2 gap-3'>
                <button type='button' @click='triggerAction("status", selectedRepo)' class='rounded-2xl border border-white/10 bg-white/5 px-3 py-3 text-sm text-slate-100 transition hover:bg-white/10'>Status</button>
                <button type='button' @click='triggerAction("doctor", selectedRepo)' class='rounded-2xl border border-white/10 bg-white/5 px-3 py-3 text-sm text-slate-100 transition hover:bg-white/10'>Doctor</button>
                <button type='button' @click='triggerAction("pause", selectedRepo)' class='rounded-2xl border border-white/10 bg-white/5 px-3 py-3 text-sm text-slate-100 transition hover:bg-white/10'>Pause</button>
                <button type='button' @click='triggerAction("resume", selectedRepo)' class='rounded-2xl border border-white/10 bg-white/5 px-3 py-3 text-sm text-slate-100 transition hover:bg-white/10'>Resume</button>
                <button type='button' @click='triggerAction("once", selectedRepo)' class='rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-3 py-3 text-sm text-cyan-100 transition hover:bg-cyan-400/15'>Run once</button>
                <button type='button' @click='triggerAction("scan", selectedRepo, true)' class='rounded-2xl border border-white/10 bg-white/5 px-3 py-3 text-sm text-slate-100 transition hover:bg-white/10'>Scan dry-run</button>
              </div>
            </section>
          </div>
        </template>
      </aside>
    </section>

    <template x-if='commandPaletteOpen'>
      <div class='fixed inset-0 z-50'>
        <div class='absolute inset-0 bg-slate-950/70' @click='toggleCommandPalette(false)'></div>
        <div class='absolute left-1/2 top-20 w-full max-w-2xl -translate-x-1/2 rounded-[28px] border border-white/10 bg-slate-950/95 p-5 shadow-2xl'>
          <div class='flex items-center justify-between gap-3'>
            <div>
              <div class='text-[11px] uppercase tracking-[0.24em] text-slate-500'>Palette</div>
              <h3 class='mt-2 text-xl font-semibold text-white'>Command Palette</h3>
            </div>
            <button type='button' @click='toggleCommandPalette(false)' class='rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs text-slate-200'>Close</button>
          </div>
          <div class='mt-4 grid grid-cols-1 gap-3 md:grid-cols-2'>
            <div class='rounded-2xl border border-white/10 bg-white/5 p-4'>
              <div class='text-[11px] uppercase tracking-[0.22em] text-slate-500'>Views</div>
              <div class='mt-3 space-y-2'>
                <template x-for='view in queueViews' :key='`palette-${{view.id}}`'>
                  <button type='button' @click='selectView(view.id); toggleCommandPalette(false)' class='flex w-full items-center justify-between rounded-2xl border border-white/10 bg-slate-950/30 px-3 py-3 text-left text-sm text-white transition hover:bg-white/5'>
                    <span x-text='view.label'></span>
                    <span class='text-xs text-slate-400' x-text='view.count'></span>
                  </button>
                </template>
              </div>
            </div>
            <div class='rounded-2xl border border-white/10 bg-white/5 p-4'>
              <div class='text-[11px] uppercase tracking-[0.22em] text-slate-500'>Shortcuts</div>
              <div class='mt-3 space-y-3 text-sm text-slate-300'>
                <div><span class='font-mono text-cyan-100'>/</span> Focus search</div>
                <div><span class='font-mono text-cyan-100'>↑ ↓</span> Move queue selection</div>
                <div><span class='font-mono text-cyan-100'>Enter</span> Open selected issue</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </main>

  <script id='initial-data' type='application/json'>{initial}</script>
  <script>
    function dashboardApp() {{
      return {{
        rows: [],
        queueRows: [],
        queueViews: [],
        queueSummary: {{}},
        detailTabs: [
          {{ id: 'overview', label: 'Overview' }},
          {{ id: 'attempts', label: 'Attempts' }},
          {{ id: 'validation', label: 'Validation' }},
          {{ id: 'activity', label: 'Activity' }},
          {{ id: 'actions', label: 'Actions' }},
        ],
        selectedDetailTab: 'overview',
        selectedView: 'all',
        selectedIssueId: '',
        selectedRepo: '',
        selectedIssueDetail: null,
        commandPaletteOpen: false,
        showSystemHealth: false,
        authToken: '',
        repoFilter: '',
        searchText: '',
        generatedAt: '',
        refreshMs: 5000,
        themeMode: 'dark',

        get selectedViewLabel() {{
          const selected = this.queueViews.find((view) => view.id === this.selectedView);
          return selected ? selected.label : 'All Issues';
        }},

        get filteredQueueRows() {{
          const search = (this.searchText || '').trim().toLowerCase();
          return this.queueRows.filter((item) => {{
            if (this.selectedView !== 'all' && !(item.view_memberships || []).includes(this.selectedView)) return false;
            if (this.repoFilter && item.repo !== this.repoFilter) return false;
            if (!search) return true;
            const haystack = [
              item.issue_id,
              item.title,
              item.failure_summary,
              item.explanation_summary,
              item.repo,
              item.state,
              item.recommended_action,
            ].join(' ').toLowerCase();
            return haystack.includes(search);
          }});
        }},

        get lastUpdatedLabel() {{
          return this.generatedAt ? `Updated ${{this.generatedAt}}` : 'Waiting for data';
        }},

        initTheme() {{
          let mode = 'dark';
          try {{
            const stored = localStorage.getItem('flow-healer-theme');
            if (stored === 'light' || stored === 'dark') mode = stored;
          }} catch (_error) {{
            mode = 'dark';
          }}
          this.themeMode = mode;
          this.applyTheme();
        }},

        applyTheme() {{
          document.documentElement.setAttribute('data-theme', this.themeMode);
        }},

        toggleTheme() {{
          this.themeMode = this.themeMode === 'dark' ? 'light' : 'dark';
          this.applyTheme();
          try {{
            localStorage.setItem('flow-healer-theme', this.themeMode);
          }} catch (_error) {{
            console.warn('Theme preference could not be saved');
          }}
        }},

        trustBadgeClass(state) {{
          const lower = String(state || '').toLowerCase();
          if (lower === 'ready') return 'border-emerald-300/30 bg-emerald-400/10 text-emerald-100';
          if (lower === 'degraded') return 'border-amber-300/30 bg-amber-400/10 text-amber-100';
          if (lower === 'quarantined') return 'border-rose-300/30 bg-rose-400/10 text-rose-100';
          return 'border-white/10 bg-white/5 text-slate-200';
        }},

        formatTrustState(state) {{
          const lower = String(state || '').trim().toLowerCase();
          if (!lower) return 'Unknown';
          return lower.split('_').map((part) => part ? `${{part.charAt(0).toUpperCase()}}${{part.slice(1)}}` : '').join(' ');
        }},

        stateBadgeClass(state) {{
          const lower = String(state || '').toLowerCase();
          if (['pr_open', 'resolved'].includes(lower)) return 'border-emerald-300/30 bg-emerald-400/10 text-emerald-100';
          if (['running', 'claimed', 'verify_pending'].includes(lower)) return 'border-amber-300/30 bg-amber-400/10 text-amber-100';
          if (['blocked', 'failed', 'needs_clarification'].includes(lower)) return 'border-rose-300/30 bg-rose-400/10 text-rose-100';
          return 'border-white/10 bg-white/5 text-slate-200';
        }},

        statusDotClass(state) {{
          const lower = String(state || '').toLowerCase();
          if (['pr_open', 'resolved'].includes(lower)) return 'bg-emerald-300';
          if (['running', 'claimed', 'verify_pending'].includes(lower)) return 'bg-amber-300';
          if (['blocked', 'failed', 'needs_clarification'].includes(lower)) return 'bg-rose-300';
          return 'bg-cyan-300';
        }},

        signalBadgeClass(signal) {{
          const lower = String(signal || '').toLowerCase();
          if (['failure', 'error'].includes(lower)) return 'border-rose-300/30 bg-rose-400/10 text-rose-100';
          if (['running', 'pending'].includes(lower)) return 'border-amber-300/30 bg-amber-400/10 text-amber-100';
          if (['ok', 'completed'].includes(lower)) return 'border-emerald-300/30 bg-emerald-400/10 text-emerald-100';
          return 'border-white/10 bg-white/5 text-slate-200';
        }},

        async init() {{
          this.initTheme();
          try {{
            const script = document.getElementById('initial-data');
            if (script) {{
              const initial = JSON.parse(script.textContent || '{{}}');
              this.updateQueue(initial.queue || {{}});
              this.updateOverview(initial.overview || {{}});
              if (this.filteredQueueRows.length) {{
                const first = this.filteredQueueRows[0];
                await this.openIssueDetail(first.issue_id, first.repo, false);
              }}
            }}
          }} catch (error) {{
            console.error('Failed to parse initial payload', error);
          }}
          setInterval(() => this.refresh(), this.refreshMs);
        }},

        async refresh() {{
          await Promise.all([this.refreshQueue(), this.refreshOverview()]);
          if (this.selectedIssueId && this.selectedRepo) {{
            await this.openIssueDetail(this.selectedIssueId, this.selectedRepo, false);
          }}
        }},

        async refreshQueue() {{
          const response = await fetch('/api/queue', {{ cache: 'no-store' }});
          if (!response.ok) return;
          this.updateQueue(await response.json());
        }},

        async refreshOverview() {{
          const response = await fetch('/api/overview', {{ cache: 'no-store' }});
          if (!response.ok) return;
          this.updateOverview(await response.json());
        }},

        updateQueue(payload) {{
          this.queueRows = Array.isArray(payload.rows) ? payload.rows : [];
          this.queueViews = Array.isArray(payload.views) ? payload.views : [];
          this.queueSummary = payload.summary || {{}};
          this.generatedAt = payload.generated_at || '';
        }},

        updateOverview(payload) {{
          this.rows = Array.isArray(payload.rows) ? payload.rows : [];
        }},

        async openIssueDetail(issueId, repo, scroll = true) {{
          if (!issueId || !repo) return;
          this.selectedIssueId = issueId;
          this.selectedRepo = repo;
          const params = new URLSearchParams({{ repo, issue_id: issueId }});
          const response = await fetch(`/api/issue-detail?${{params.toString()}}`, {{ cache: 'no-store' }});
          if (!response.ok) return;
          this.selectedIssueDetail = await response.json();
          if (scroll) window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }},

        selectView(viewId) {{
          this.selectedView = viewId;
        }},

        selectNextIssue() {{
          if (!this.filteredQueueRows.length) return;
          const index = this.filteredQueueRows.findIndex((item) => item.issue_id === this.selectedIssueId && item.repo === this.selectedRepo);
          const nextIndex = index < 0 ? 0 : Math.min(this.filteredQueueRows.length - 1, index + 1);
          const next = this.filteredQueueRows[nextIndex];
          this.selectedIssueId = next.issue_id;
          this.selectedRepo = next.repo;
        }},

        selectPreviousIssue() {{
          if (!this.filteredQueueRows.length) return;
          const index = this.filteredQueueRows.findIndex((item) => item.issue_id === this.selectedIssueId && item.repo === this.selectedRepo);
          const nextIndex = index < 0 ? 0 : Math.max(0, index - 1);
          const next = this.filteredQueueRows[nextIndex];
          this.selectedIssueId = next.issue_id;
          this.selectedRepo = next.repo;
        }},

        openSelectedIssue() {{
          if (!this.selectedIssueId || !this.selectedRepo) return;
          this.openIssueDetail(this.selectedIssueId, this.selectedRepo);
        }},

        focusSearch() {{
          if (this.commandPaletteOpen) return;
          this.$refs.queueSearch && this.$refs.queueSearch.focus();
        }},

        toggleCommandPalette(force) {{
          if (typeof force === 'boolean') {{
            this.commandPaletteOpen = force;
            return;
          }}
          this.commandPaletteOpen = !this.commandPaletteOpen;
        }},

        closeOverlays() {{
          this.commandPaletteOpen = false;
        }},

        clearFilters() {{
          this.selectedView = 'all';
          this.repoFilter = '';
          this.searchText = '';
        }},

        triggerAction(command, repo, dryRun = false) {{
          if (!command || !repo) return;
          const form = document.createElement('form');
          form.method = 'post';
          form.action = '/action';
          const fields = {{ command, repo }};
          if (this.authToken) fields.auth_token = this.authToken;
          if (dryRun) fields.dry_run = 'true';
          Object.entries(fields).forEach(([key, value]) => {{
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = key;
            input.value = value;
            form.appendChild(input);
          }});
          document.body.appendChild(form);
          form.submit();
        }},
      }};
    }}
  </script>
</body>
</html>
"""


def _queue_row_from_issue(
    *,
    issue: dict[str, Any],
    repo_name: str,
    repo_row: dict[str, Any],
    explanation: dict[str, Any] | None,
) -> dict[str, Any]:
    issue_id = str(issue.get("issue_id") or "").strip()
    state = str(issue.get("state") or "queued").strip().lower()
    explanation = explanation or {}
    pr_number = int(issue.get("pr_number") or 0)
    memberships = {"all", state}
    if state in {"blocked", "failed", "needs_clarification", "pr_pending_approval"}:
        memberships.add("needs_review")
    return {
        "issue_id": issue_id,
        "repo": repo_name,
        "title": str(issue.get("title") or "").strip() or f"Issue #{issue_id}",
        "state": state,
        "state_label": state.replace("_", " "),
        "priority": int(issue.get("priority") or 100),
        "updated_at": str(issue.get("updated_at") or ""),
        "created_at": str(issue.get("created_at") or ""),
        "attempt_count": int(issue.get("attempt_count") or 0),
        "backoff_until": str(issue.get("backoff_until") or ""),
        "pr_number": pr_number,
        "pr_state": str(issue.get("pr_state") or ""),
        "pr_badge": f"#{pr_number}" if pr_number > 0 else "",
        "failure_summary": str(issue.get("last_failure_reason") or "").strip(),
        "failure_class": str(issue.get("last_failure_class") or "").strip(),
        "explanation_summary": str(explanation.get("summary") or "").strip(),
        "recommended_action": str(explanation.get("recommended_action") or "").strip(),
        "repo_trust_state": str((repo_row.get("trust") or {}).get("state") or ""),
        "view_memberships": sorted(memberships),
    }


def _queue_sort_key(row: dict[str, Any]) -> tuple[int, int, str, str]:
    state_order = {
        "running": 0,
        "claimed": 1,
        "verify_pending": 2,
        "queued": 3,
        "needs_clarification": 4,
        "blocked": 5,
        "failed": 6,
        "pr_pending_approval": 7,
        "pr_open": 8,
        "resolved": 9,
        "archived": 10,
    }
    return (
        state_order.get(str(row.get("state") or ""), 50),
        int(row.get("priority") or 100),
        str(row.get("updated_at") or ""),
        str(row.get("issue_id") or ""),
    )


def _build_views(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    definitions = [
        ("all", "All Issues"),
        ("queued", "Queued"),
        ("running", "Running"),
        ("blocked", "Blocked"),
        ("pr_open", "PR Open"),
        ("needs_review", "Needs Review"),
    ]
    return [
        {
            "id": view_id,
            "label": label,
            "count": len(rows) if view_id == "all" else sum(1 for row in rows if view_id in (row.get("view_memberships") or [])),
        }
        for view_id, label in definitions
    ]


def _build_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    def _count(*states: str) -> int:
        wanted = set(states)
        return sum(1 for row in rows if str(row.get("state") or "") in wanted)

    return {
        "total": len(rows),
        "queued": _count("queued"),
        "running": _count("running", "claimed", "verify_pending"),
        "blocked": _count("blocked", "failed"),
        "pr_open": _count("pr_open", "pr_pending_approval"),
        "needs_review": sum(1 for row in rows if "needs_review" in (row.get("view_memberships") or [])),
    }


def _now_label() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
