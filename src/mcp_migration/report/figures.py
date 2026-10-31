"""Figures for the manuscript, generated from the episode records.

Like ``stats``, nothing here is drawn by hand: every figure is a function of
``episodes.jsonl``, so refreshing a snapshot refreshes the plots. matplotlib is
an optional dependency, declared under the ``paper`` extra, because producing
the dataset does not need it.

Figures are sized for a single IEEE column and must survive being printed in
greyscale, so every series carries a line style and a marker in addition to its
colour. Colour alone never distinguishes two series.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp_migration.mine.classify import AuthorKind, StaticEra
from mcp_migration.mine.signals import PROTOCOL_REVISIONS
from mcp_migration.report.stats import EPISODE_KINDS

log = logging.getLogger(__name__)

# Okabe-Ito, reordered so that every adjacent pair clears a CVD separation of
# ΔE 8 (worst pair 9.6, protan). Assigned in this fixed order and never cycled.
PALETTE = ("#0072B2", "#CC79A7", "#E69F00", "#009E73", "#D55E00")
# Secondary encoding, so the figures still read in greyscale.
LINE_STYLES = ("-", "--", "-.", ":", (0, (3, 1, 1, 1, 1, 1)))
MARKERS = ("o", "s", "^", "D", "v")

# One IEEE column is 3.5in; leave a little room so nothing is clipped.
COLUMN_WIDTH_IN = 3.4
INK = "#1a1a1a"
MUTED = "#666666"
GRID = "#d8d8d8"


def _style() -> dict[str, Any]:
    """Recessive axes and small type, matching the manuscript's body size."""
    return {
        "font.size": 7,
        "axes.labelsize": 7,
        "axes.titlesize": 7,
        "xtick.labelsize": 6,
        "ytick.labelsize": 6,
        "legend.fontsize": 6,
        "axes.edgecolor": MUTED,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.4,
        "figure.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
    }


def _month(value: str) -> str:
    """Bin an ISO timestamp into a YYYY-MM bucket."""
    return datetime.fromisoformat(value).strftime("%Y-%m")


def _month_range(first: str, last: str) -> list[str]:
    """Every month from ``first`` to ``last`` inclusive, so gaps stay visible."""
    year, month = (int(p) for p in first.split("-"))
    end_year, end_month = (int(p) for p in last.split("-"))
    months: list[str] = []
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _thin_labels(months: Sequence[str], keep: int = 4) -> list[str]:
    """Label every ``keep``-th month, so the axis does not collide with itself."""
    return [m if i % keep == 0 else "" for i, m in enumerate(months)]


def _whole_months(months: Sequence[str], latest: str) -> list[str]:
    """Drop a trailing partial month.

    A snapshot taken mid-month otherwise ends every series on a sharp fall that
    is an artifact of when collection stopped, which reads as a real decline.
    """
    if not months:
        return []
    last = datetime.fromisoformat(latest)
    days_in_month = {1: 31, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
    if last.month == 2:
        leap = last.year % 4 == 0 and (last.year % 100 != 0 or last.year % 400 == 0)
        final_day = 29 if leap else 28
    else:
        final_day = days_in_month[last.month]
    if last.day < final_day and months[-1] == last.strftime("%Y-%m"):
        return list(months[:-1])
    return list(months)


def episodes_by_kind(episodes: Sequence[Mapping[str, Any]], out: Path) -> Path:
    """Monthly episode count per kind: when migration activity actually happens."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    per_kind: dict[str, Counter[str]] = {k: Counter() for k in EPISODE_KINDS}
    for episode in episodes:
        kind = str(episode["kind"])
        if kind in per_kind:
            per_kind[kind][_month(str(episode["start"]))] += 1
    seen = sorted({m for counts in per_kind.values() for m in counts})
    if not seen:
        raise ValueError("no episodes to plot")
    latest = max(str(e["start"]) for e in episodes)
    months = _whole_months(_month_range(seen[0], seen[-1]), latest)

    with plt.rc_context(_style()):
        fig, ax = plt.subplots(figsize=(COLUMN_WIDTH_IN, 1.45))
        for i, kind in enumerate(EPISODE_KINDS):
            ax.plot(
                months,
                [per_kind[kind].get(m, 0) for m in months],
                label=kind.replace("_", " "),
                color=PALETTE[i],
                linestyle=LINE_STYLES[i],
                marker=MARKERS[i],
                markersize=2.5,
                linewidth=1.1,
            )
        ax.set_xticks(range(len(months)))
        ax.set_xticklabels(_thin_labels(months), rotation=45, ha="right")
        ax.set_ylabel("episodes per month")
        # Above the axes: the v1-removal peak occupies the upper left, and an
        # inset legend crowds it.
        ax.legend(
            frameon=False,
            ncol=3,
            loc="lower left",
            bbox_to_anchor=(0, 1.0, 1, 0.12),
            mode="expand",
            borderaxespad=0,
            handletextpad=0.4,
            columnspacing=1.0,
        )
        ax.margins(x=0.01)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out)
        plt.close(fig)
    log.info("wrote %s", out)
    return out


def revision_adoption(episodes: Sequence[Mapping[str, Any]], out: Path) -> Path:
    """Cumulative repositories in which each revision literal has appeared.

    Counts a repository once, at the first episode that introduces the literal,
    so the curves show spread through the population rather than churn.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    first_seen: dict[str, dict[str, str]] = {r: {} for r in PROTOCOL_REVISIONS}
    for episode in sorted(episodes, key=lambda e: str(e["start"])):
        month, repo = _month(str(episode["start"])), str(episode["repo"])
        for revision in episode.get("revisions_added", []):
            bucket = first_seen.get(str(revision))
            if bucket is not None and repo not in bucket:
                bucket[repo] = month
    seen = sorted({m for b in first_seen.values() for m in b.values()})
    if not seen:
        raise ValueError("no revision adoptions to plot")
    latest = max(str(e["start"]) for e in episodes)
    months = _whole_months(_month_range(seen[0], seen[-1]), latest)

    with plt.rc_context(_style()):
        fig, ax = plt.subplots(figsize=(COLUMN_WIDTH_IN, 1.45))
        for i, revision in enumerate(PROTOCOL_REVISIONS):
            per_month = Counter(first_seen[revision].values())
            running, series = 0, []
            for month in months:
                running += per_month.get(month, 0)
                series.append(running)
            ax.plot(
                months,
                series,
                label=revision,
                color=PALETTE[i],
                linestyle=LINE_STYLES[i],
                marker=MARKERS[i],
                markersize=2.5,
                linewidth=1.1,
            )
        ax.set_xticks(range(len(months)))
        ax.set_xticklabels(_thin_labels(months), rotation=45, ha="right")
        ax.set_ylabel("repositories (cumulative)")
        ax.legend(frameon=False, loc="upper left")
        ax.margins(x=0.01)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out)
        plt.close(fig)
    log.info("wrote %s", out)
    return out


def author_kind_share(
    episodes: Sequence[Mapping[str, Any]], out: Path, min_episodes: int = 200
) -> Path:
    """Share of episodes per month carrying an agent trailer or a bot author.

    Plotted as a share rather than a count, so the curve is not simply the
    dataset's own growth. Months holding fewer than ``min_episodes`` episodes
    are dropped: early in the observation window a handful of episodes make the
    ratio swing between 0 and 100%, which reads as signal and is not.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    per: dict[str, Counter[str]] = defaultdict(Counter)
    for episode in episodes:
        month = _month(str(episode["start"]))
        kinds = set(episode.get("author_kinds", []))
        per[month]["total"] += 1
        if AuthorKind.AI_AGENT_ASSISTED in kinds:
            per[month]["agent"] += 1
        if AuthorKind.BOT in kinds:
            per[month]["bot"] += 1
    latest = max(str(e["start"]) for e in episodes)
    months = [m for m in _whole_months(sorted(per), latest) if per[m]["total"] >= min_episodes]
    if not months:
        raise ValueError("no months with enough episodes to plot")

    with plt.rc_context(_style()):
        fig, ax = plt.subplots(figsize=(COLUMN_WIDTH_IN, 1.45))
        for i, (key, label) in enumerate((("agent", "AI-agent trailer"), ("bot", "bot author"))):
            ax.plot(
                months,
                [100.0 * per[m][key] / per[m]["total"] for m in months],
                label=label,
                color=PALETTE[i],
                linestyle=LINE_STYLES[i],
                marker=MARKERS[i],
                markersize=2.5,
                linewidth=1.1,
            )
        ax.set_xticks(range(len(months)))
        ax.set_xticklabels(_thin_labels(months, keep=3), rotation=45, ha="right")
        ax.set_ylabel("% of episodes")
        ax.set_ylim(0, 60)
        ax.legend(frameon=False, loc="upper left")
        ax.margins(x=0.01)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out)
        plt.close(fig)
    log.info("wrote %s", out)
    return out


def kind_by_era(episodes: Sequence[Mapping[str, Any]], out: Path) -> Path:
    """Episode kind against the repository's end state.

    This cross-tabulation is also the sampling frame: the manual sample is
    stratified over exactly these cells.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Abbreviated so the rotated tick labels do not eat the figure's height.
    short = {
        "mixed_v1_v2": "mixed",
        "sdk_v2_modern_features": "v2 modern",
        "sdk_v2_default": "v2 default",
        "sdk_v1_pinned_below_2": "v1 pinned",
        "sdk_v1": "v1",
        "standalone_fastmcp": "fastmcp",
        "no_official_sdk": "no sdk",
    }
    eras = [e.value for e in StaticEra]
    grid: dict[tuple[str, str], int] = defaultdict(int)
    for episode in episodes:
        grid[(str(episode["kind"]), str(episode.get("head_static_era") or ""))] += 1
    matrix = [[grid.get((kind, era), 0) for era in eras] for kind in EPISODE_KINDS]
    largest = max((v for row in matrix for v in row), default=1) or 1

    with plt.rc_context(_style()):
        fig, ax = plt.subplots(figsize=(COLUMN_WIDTH_IN, 1.6))
        # Sequential magnitude: one hue, light to dark. Never a rainbow.
        ax.imshow(matrix, cmap="Blues", aspect="auto", vmin=0, vmax=largest)
        ax.set_xticks(range(len(eras)))
        ax.set_xticklabels([short[e] for e in eras], rotation=45, ha="right")
        ax.set_yticks(range(len(EPISODE_KINDS)))
        ax.set_yticklabels([k.replace("_", " ") for k in EPISODE_KINDS])
        ax.grid(False)
        for r, row in enumerate(matrix):
            for c, value in enumerate(row):
                # Direct labels: the cell value is never encoded by colour alone.
                ax.text(
                    c,
                    r,
                    f"{value:,}",
                    ha="center",
                    va="center",
                    fontsize=5,
                    color="white" if value > 0.55 * largest else INK,
                )
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out)
        plt.close(fig)
    log.info("wrote %s", out)
    return out


def migration_end_states(episodes: Sequence[Mapping[str, Any]], out: Path) -> Path:
    """Where migration episodes leave the repository.

    A magnitude across one categorical axis, so a bar rather than a pie or a
    stack, ordered by size and directly labelled. The two bars that still
    answer the legacy handshake are drawn in the darker tone, because the
    finding is how much of the population sits in them.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    counts = Counter(
        str(e.get("head_static_era") or "unknown") for e in episodes if e["kind"] == "migration"
    )
    if not counts:
        raise ValueError("no migration episodes to plot")
    total = sum(counts.values())
    short = {
        "sdk_v2_default": "v2 SDK, legacy default",
        "mixed_v1_v2": "both generations",
        "no_official_sdk": "no official SDK",
        "sdk_v2_modern_features": "v2 SDK + modern features",
        "sdk_v1": "still v1",
        "standalone_fastmcp": "standalone FastMCP",
        "sdk_v1_pinned_below_2": "pinned below 2",
    }
    still_legacy = {"sdk_v2_default", "mixed_v1_v2"}
    order = [k for k, _ in counts.most_common()][::-1]

    with plt.rc_context(_style()):
        fig, ax = plt.subplots(figsize=(COLUMN_WIDTH_IN, 1.5))
        values = [counts[k] for k in order]
        ax.barh(
            range(len(order)),
            values,
            color=[PALETTE[0] if k in still_legacy else "#b8cfe0" for k in order],
            height=0.68,
        )
        ax.set_yticks(range(len(order)))
        ax.set_yticklabels([short.get(k, k) for k in order])
        ax.set_xlabel("migration episodes")
        ax.xaxis.grid(True)
        ax.yaxis.grid(False)
        for i, v in enumerate(values):
            ax.text(
                v + total * 0.012,
                i,
                f"{v:,} ({100 * v / total:.0f}%)",
                va="center",
                fontsize=5.5,
            )
        ax.set_xlim(0, max(values) * 1.28)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out)
        plt.close(fig)
    log.info("wrote %s", out)
    return out


def technical_lag(profiles: Mapping[str, Mapping[str, Any]], out: Path) -> Path:
    """Share of each release's cohort that has adopted it, by days since release.

    Non-adopters stay in the denominator, so a curve's height is uptake in the
    cohort rather than among those who moved, and each curve stops where its
    window does. Revisions keep the colours they have in revision_adoption; the
    SDK major is not a revision, so it is drawn in ink with its own dash.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from mcp_migration.report.lag import SDK_V2

    if not profiles:
        raise ValueError("no technical lag to plot")
    horizon = 365
    with plt.rc_context(_style()):
        fig, ax = plt.subplots(figsize=(COLUMN_WIDTH_IN, 1.8))
        ax.axvline(30, color=MUTED, linewidth=0.6, linestyle=":")
        ax.text(
            31,
            0.98,
            "30 days",
            transform=ax.get_xaxis_transform(),
            va="top",
            ha="left",
            color=MUTED,
            fontsize=5.5,
        )
        for key, profile in profiles.items():
            style: Any
            if key == SDK_V2:
                color, style, marker, label = INK, (0, (5, 1.5)), "x", "SDK v2"
            else:
                i = PROTOCOL_REVISIONS.index(key)
                color, style, marker, label = PALETTE[i], LINE_STYLES[i], MARKERS[i], key
            window = min(int(profile["window_days"]), horizon)
            # Step from 0 at release, through each adoption day, to the window end.
            xs, ys, level = [0], [0.0], 0.0
            for day, pct in profile["curve"]:
                if day > window:
                    break
                xs += [day, day]
                ys += [level, pct]
                level = pct
            xs.append(window)
            ys.append(level)
            ax.plot(xs, ys, color=color, linestyle=style, linewidth=1.1, label=label)
            # One marker where the window ends, so a curve that stops early reads
            # as unobserved rather than flat. None for a window past the axis.
            if int(profile["window_days"]) <= horizon:
                ax.plot(
                    [window], [level], color=color, marker=marker, markersize=3.5, linestyle="none"
                )
        ax.set_xlim(0, horizon)
        ax.set_ylim(bottom=0)
        ax.set_xlabel("days since release")
        ax.set_ylabel("cohort adopted (%)")
        # Above the axes: inside, it covers the early days, where the curves differ.
        ax.legend(
            frameon=False,
            loc="lower left",
            bbox_to_anchor=(0, 1.0),
            ncol=3,
            handlelength=2.6,
            columnspacing=1.0,
            borderaxespad=0.2,
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, bbox_inches="tight")
        plt.close(fig)
    log.info("wrote %s", out)
    return out


def _plotted_n(row: Mapping[str, Any]) -> int:
    """The denominator of a language's bars: Python servers, else resolved repositories."""
    return int(row.get("server_import") or row.get("resolved", row["n"]))


def protocol_support(protocol: Mapping[str, Mapping[str, Any]], out: Path) -> Path:
    """Share of v2 repositories supporting the new revision, and with a selected
    feature marker detected, grouped by SDK language.

    Support in Python (and in repositories using both SDKs) is assigned by the
    SDK's documented design rather than detected, so those bars are drawn hatched
    and pale and named as such in the legend. Legacy support is not plotted:
    the classifier's call on legacy retirement was not reliable enough to report.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    languages = [lang for lang in ("python", "typescript", "both") if lang in protocol]
    if not languages:
        raise ValueError("no protocol dimensions to plot")
    labels = {"python": "Python", "typescript": "TypeScript", "both": "both SDKs"}
    assigned = {"python", "both"}  # support follows from the SDK, not detection
    width = 0.34
    with plt.rc_context(_style()):
        fig, ax = plt.subplots(figsize=(COLUMN_WIDTH_IN, 1.7))
        for j, key in enumerate(("pct_modern", "pct_features")):
            for i, lang in enumerate(languages):
                row = protocol[lang]
                if key == "pct_features" and row.get("pct_server_features") is not None:
                    key_used = "pct_server_features"  # Python servers, as in TypeScript
                else:
                    key_used = key
                y = float(row.get(key_used, row.get(key.replace("pct_", "pct_new_"))) or 0.0)
                sdk = key == "pct_modern" and lang in assigned
                ax.bar(
                    i + (j - 0.5) * width,
                    y,
                    width * 0.92,
                    color=PALETTE[j],
                    alpha=0.35 if sdk else 1.0,
                    hatch="////" if sdk else ("...." if j else ""),
                    edgecolor="white" if not sdk else PALETTE[j],
                    linewidth=0.4,
                )
                ax.text(
                    i + (j - 0.5) * width,
                    y + 1.5,
                    f"{y:.0f}",
                    ha="center",
                    va="bottom",
                    fontsize=5.5,
                    color=INK,
                )
        ax.set_xticks(range(len(languages)))
        ax.set_xticklabels(
            [f"{labels[lang]}\n(n={_plotted_n(protocol[lang]):,})" for lang in languages]
        )
        ax.set_ylim(0, 112)
        ax.set_yticks([0, 25, 50, 75, 100])
        ax.set_ylabel("v2 repositories (%)")
        ax.grid(axis="x", visible=False)
        handles = [
            Patch(facecolor=PALETTE[0], edgecolor="white", label="supports 2026-07-28 (detected)"),
            Patch(
                facecolor=PALETTE[0],
                alpha=0.35,
                hatch="////",
                edgecolor=PALETTE[0],
                label="assigned by SDK design",
            ),
            Patch(
                facecolor=PALETTE[1],
                hatch="....",
                edgecolor="white",
                label="selected feature marker detected",
            ),
        ]
        ax.legend(
            handles=handles,
            frameon=False,
            loc="lower left",
            bbox_to_anchor=(0, 1.0),
            ncol=2,
            handlelength=1.4,
            columnspacing=0.9,
            borderaxespad=0.2,
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, bbox_inches="tight")
        plt.close(fig)
    log.info("wrote %s", out)
    return out


# Rows of the deferral forest plot: (group heading or None, summary key, label).
FOREST_ROWS: tuple[tuple[str | None, str, str], ...] = (
    (None, "deferral", "primary (exposed)"),
    ("timing", "deferral_landmark", "landmark at day 1 (both groups)"),
    ("timing", "deferral_same_day_excluded", "drop same-day v2 (pinned only)"),
    ("event and sample", "deferral_code_only", "import events only"),
    ("event and sample", "deferral_no_bots", "no bot commits"),
    ("event and sample", "deferral_no_preexisting", "no rewritten ceiling"),
    ("event and sample", "deferral_dedup", "one repository per shared-commit group"),
    ("event and sample", "deferral_no_reuse", "each control used once"),
    ("event and sample", "deferral_corpus", "MCPCorpus only"),
    ("comparison group", "deferral_censor_controls", "censor controls that later pin"),
    ("comparison group", "deferral_unmatched", "controls not recently active"),
    ("comparison group", "deferral_all_v1", "any v1 repository"),
)
# The paper's selection, in the paper's order and without group headings;
# every row is in FOREST_ROWS, drawn in full for the artifact.
# Line breaks fall between phrases, so the larger type stays near column width.
FOREST_PAPER_ROWS: tuple[tuple[str | None, str, str], ...] = (
    (None, "deferral", "primary (exposed)"),
    (None, "deferral_landmark", "landmark at day 1\n(both groups)"),
    (None, "deferral_censor_controls", "censor controls\nthat later pin"),
    (None, "deferral_unmatched", "controls not\nrecently active"),
    (None, "deferral_all_v1", "any v1 repository"),
    (None, "deferral_dedup", "one repository per\nshared-commit group"),
    (None, "deferral_corpus", "MCPCorpus only"),
)


def deferral_forest(
    measurement: Mapping[str, Any],
    out: Path,
    rows_spec: Sequence[tuple[str | None, str, str]] = FOREST_ROWS,
    font: float = 7.0,
) -> Path:
    """Gap at day 30 (pinned minus controls) with its clustered 95% interval, per
    analysis, grouped by what each variant tests, with zero marked.

    The same numbers as the sensitivity table, drawn so that a reader sees at
    once which intervals cross zero. Beside each gap are the two shares it is
    the difference of, so a reader can tell which group moved; an analysis
    with fewer than 100 pinned repositories carries its size in its label.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows: list[tuple[str, float, float, float, float, float] | str] = []
    heading: str | None = None
    for group, key, label in rows_spec:
        block = measurement.get(key) or {}
        clustered = block.get("clustered_30") or {}
        gap = clustered.get("gap")
        if not gap:
            continue
        if group != heading and group is not None:
            rows.append(group)
        heading = group
        n_pinned = int((block.get("pinned") or {}).get("n") or 0)
        if 0 < n_pinned < 100:
            label = (
                f"{label}\n(n = {n_pinned})"
                if "\n" in "".join(spec[2] for spec in rows_spec)
                else f"{label} (n = {n_pinned})"
            )
        rows.append(
            (
                label,
                float(gap["pct"]),
                float(gap["ci_low"]),
                float(gap["ci_high"]),
                float(clustered["pinned"]["pct"]),
                float(clustered["controls"]["pct"]),
            )
        )
    if not rows:
        raise ValueError("no deferral analyses with intervals to plot")
    x_min, x_max = -15.0, 25.0
    # Drawn wider than a column and scaled down to fit it, so the type is set
    # larger than _style's to land near the other figures' size on the page.
    small = font - 0.5
    style = {**_style(), "xtick.labelsize": font, "ytick.labelsize": font, "axes.labelsize": font}
    row_height = 0.17 if font <= 7 else 0.36
    with plt.rc_context(style):
        width = 1.05 if font <= 7 else 1.25
        fig, ax = plt.subplots(figsize=(width, row_height * len(rows) + 0.45))
        labels: list[str] = []
        for i, row in enumerate(rows):
            y = len(rows) - 1 - i
            if isinstance(row, str):
                labels.append(row)
                continue
            label, pct, low, high, pinned_pct, control_pct = row
            labels.append(label)
            primary = label.startswith("primary")
            color = PALETTE[4] if primary else PALETTE[0]
            # Clip to the axis, with an arrow where an interval runs past it.
            lo, hi = max(low, x_min), min(high, x_max)
            ax.plot([lo, hi], [y, y], color=color, linewidth=1.1, solid_capstyle="butt")
            for end, edge, marker in ((low, x_min, "<"), (high, x_max, ">")):
                if (end < edge) if marker == "<" else (end > edge):
                    ax.plot(edge, y, marker=marker, markersize=3.5, color=color)
            ax.plot(pct, y, marker="D" if primary else "o", markersize=3.8, color=color)
            # Number columns at fixed offsets from the axis, in points, so
            # they cannot collide whatever the plot's width.
            for offset, text in (
                (5, f"{pinned_pct:.1f} vs {control_pct:.1f}"),
                (round(54 * font / 7), f"{pct:.1f} [{low:.1f}, {high:.1f}]".replace("-", "\u2212")),
            ):
                ax.annotate(
                    text,
                    xy=(1, y),
                    xycoords=("axes fraction", "data"),
                    xytext=(offset, 0),
                    textcoords="offset points",
                    ha="left",
                    va="center",
                    fontsize=small,
                    color=INK,
                    annotation_clip=False,
                )
        # Column headings over the numbers, above the top row.
        for offset, text in ((5, "shares (%)"), (round(54 * font / 7), "gap [95% CI]")):
            ax.annotate(
                text,
                xy=(1, len(rows) - 0.4),
                xycoords=("axes fraction", "data"),
                xytext=(offset, 3),
                textcoords="offset points",
                ha="left",
                va="bottom",
                fontsize=small,
                color=MUTED,
                style="italic",
                annotation_clip=False,
            )
        ax.set_xlim(x_min, x_max)
        ax.axvline(0, color=MUTED, linestyle="--", linewidth=0.7)
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels(list(reversed(labels)))
        for tick in ax.get_yticklabels():
            tick.set_linespacing(0.95)
        for tick, row in zip(ax.get_yticklabels(), reversed(rows), strict=True):
            if isinstance(row, str):
                tick.set_fontstyle("italic")
                tick.set_color(MUTED)
        ax.tick_params(axis="y", length=0)
        ax.set_ylim(-0.6, len(rows) - 0.4)
        ax.set_xticks([-10, 0, 10, 20])
        ax.set_xlabel("gap at day 30 (points)")
        ax.grid(axis="y", visible=False)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, bbox_inches="tight")
        plt.close(fig)
    log.info("wrote %s", out)
    return out


def deferral_curves(deferral: Mapping[str, Any], out: Path) -> Path:
    """Cumulative share moving to Python v2 after a deferring ceiling, against
    date-matched v1 controls, with numbers at risk beneath the axis.

    Kaplan-Meier step functions with their 95% bands; both clocks start on the
    pinning date, and each curve stops where its follow-up does.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cohorts = (
        ("pinned", "pinned", PALETTE[4], "--"),
        ("controls", "matched control entries", PALETTE[0], "-"),
    )
    with plt.rc_context(_style()):
        fig, ax = plt.subplots(figsize=(COLUMN_WIDTH_IN, 1.75))
        for key, label, color, style in cohorts:
            curve = (deferral.get(key) or {}).get("curve") or []
            if not curve:
                continue
            days = [0] + [int(p[0]) for p in curve]
            est = [0.0] + [float(p[1]) for p in curve]
            low = [0.0] + [float(p[2]) for p in curve]
            high = [0.0] + [float(p[3]) for p in curve]
            ax.step(
                days,
                est,
                where="post",
                color=color,
                linestyle=style,
                linewidth=1.2,
                label=f"{label} (n={int(deferral[key]['n']):,})",
            )
            ax.fill_between(days, low, high, step="post", color=color, alpha=0.15, linewidth=0)
        ax.set_xlim(0, 45)
        ax.set_ylim(bottom=0)
        ax.set_xlabel("days since the pinning date (controls: their matching date)")
        ax.set_ylabel("v2 adoption signal (%)")
        ax.legend(frameon=False, loc="upper left")
        # Numbers at risk beneath the axis, one row per cohort.
        rows = (
            ("pinned", deferral.get("risk_pinned") or []),
            ("controls", deferral.get("risk_controls") or []),
        )
        for k, (name, table) in enumerate(rows):
            y = -0.40 - 0.11 * k
            ax.text(
                -0.13,
                y,
                name,
                transform=ax.transAxes,
                ha="right",
                va="center",
                fontsize=5.5,
                color=MUTED,
            )
            for entry in table:
                if entry["day"] > 45:
                    continue
                ax.text(
                    entry["day"] / 45,
                    y,
                    f"{entry['at_risk']:,}",
                    transform=ax.transAxes,
                    ha="center",
                    va="center",
                    fontsize=5.5,
                    color=INK,
                )
        # Header row: the day each column of numbers at risk refers to.
        ax.text(
            -0.13,
            -0.29,
            "at risk on day",
            transform=ax.transAxes,
            ha="right",
            va="center",
            fontsize=5.5,
            color=MUTED,
            style="italic",
        )
        for entry in rows[0][1]:
            if entry["day"] <= 45:
                ax.text(
                    entry["day"] / 45,
                    -0.29,
                    str(entry["day"]),
                    transform=ax.transAxes,
                    ha="center",
                    va="center",
                    fontsize=5.5,
                    color=MUTED,
                    style="italic",
                )
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, bbox_inches="tight")
        plt.close(fig)
    log.info("wrote %s", out)
    return out


def build_all(
    episodes: Sequence[Mapping[str, Any]],
    out_dir: Path,
    lag: Mapping[str, Mapping[str, Any]] | None = None,
    measurement: Mapping[str, Any] | None = None,
) -> list[Path]:
    """Generate every manuscript figure into ``out_dir``."""
    extra = [technical_lag(lag, out_dir / "technical-lag.pdf")] if lag else []
    # RQ1 from application code where the scan exists, else the earlier view.
    protocol = (measurement or {}).get("protocol_app") or (measurement or {}).get("protocol")
    if protocol:
        extra.append(protocol_support(protocol, out_dir / "protocol-support.pdf"))
    if measurement and measurement.get("deferral"):
        extra.append(deferral_curves(measurement["deferral"], out_dir / "deferral.pdf"))
        # The paper's selection at a larger size, and every variant for the artifact.
        extra.append(
            deferral_forest(
                measurement, out_dir / "deferral-forest.pdf", FOREST_PAPER_ROWS, font=8.5
            )
        )
        extra.append(deferral_forest(measurement, out_dir / "deferral-forest-full.pdf"))
    return [
        *extra,
        episodes_by_kind(episodes, out_dir / "episodes-by-kind.pdf"),
        revision_adoption(episodes, out_dir / "revision-adoption.pdf"),
        kind_by_era(episodes, out_dir / "kind-by-era.pdf"),
        author_kind_share(episodes, out_dir / "author-kind-share.pdf"),
        migration_end_states(episodes, out_dir / "migration-end-states.pdf"),
    ]
