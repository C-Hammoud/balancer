import { Component, computed, input, signal } from '@angular/core';
import { DailyCount } from '../../../core/models';
import { barGeometry, BarGeom, dayLabel, linePoints, niceMax, pointsAttr } from './overview.helpers';

export interface ChartSeries {
  name: string;
  color: string;
  data: DailyCount[];
}

const W = 600;
const H = 120;
const LEFT = 30;
const BOTTOM = 20;
const TOP = 6;

/** Per-day counts as bars (one series) or lines (two series), with a hover tooltip. */
@Component({
  selector: 'app-trend-chart',
  standalone: true,
  template: `
    @if (series().length > 1) {
      <ul class="legend">
        @for (s of series(); track s.name) {
          <li><span class="swatch" [style.background]="s.color"></span>{{ s.name }}</li>
        }
      </ul>
    }
    <div class="chart" (mouseleave)="hover.set(null)">
      <svg [attr.viewBox]="'0 0 ' + (w + left) + ' ' + (h + top + bottom)" role="img" [attr.aria-label]="label()">
        <g [attr.transform]="'translate(' + left + ',' + top + ')'">
          <line class="grid" x1="0" [attr.x2]="w" y1="0" y2="0" />
          <line class="grid" x1="0" [attr.x2]="w" [attr.y1]="h / 2" [attr.y2]="h / 2" />
          <line class="axis" x1="0" [attr.x2]="w" [attr.y1]="h" [attr.y2]="h" />
          <text class="tick" x="-6" y="4" text-anchor="end">{{ max() }}</text>
          <text class="tick" x="-6" [attr.y]="h + 4" text-anchor="end">0</text>
          @for (t of ticks(); track t.x) {
            <text class="tick" [attr.x]="t.x" [attr.y]="h + 15" [attr.text-anchor]="t.anchor">{{ t.text }}</text>
          }

          @if (series().length === 1) {
            @for (b of bars(); track $index) {
              @if (b.height > 0) {
                <path [attr.d]="barPath(b)" [attr.fill]="series()[0].color" [class.dim]="hover() !== null && hover() !== $index" />
              }
            }
          } @else {
            @if (hover() !== null) {
              <line class="crosshair" [attr.x1]="cx(hover()!)" [attr.x2]="cx(hover()!)" y1="0" [attr.y2]="h" />
            }
            @for (s of lines(); track s.name) {
              <polyline [attr.points]="s.points" fill="none" [attr.stroke]="s.color" stroke-width="2"
                stroke-linejoin="round" stroke-linecap="round" />
              @if (hover() !== null) {
                <circle [attr.cx]="s.pts[hover()!].x" [attr.cy]="s.pts[hover()!].y" r="4"
                  [attr.fill]="s.color" stroke="#fff" stroke-width="2" />
              }
            }
          }

          @for (b of bars(); track $index) {
            <rect class="hit" [attr.x]="b.hitX" y="0" [attr.width]="b.hitWidth" [attr.height]="h"
              (mouseenter)="hover.set($index)" />
          }
        </g>
      </svg>
      @if (hover() !== null) {
        <div class="tip" [style.left.%]="tipLeft()" [class.flip]="tipLeft() > 70">
          <strong>{{ day(hover()!) }}</strong>
          @for (s of series(); track s.name) {
            <span>
              @if (series().length > 1) { <i class="swatch" [style.background]="s.color"></i> }
              {{ s.name }}: {{ countAt(s, hover()!) }}
            </span>
          }
        </div>
      }
    </div>
    <table class="sr-only">
      <caption>{{ label() }}</caption>
      <thead><tr><th>Day</th>@for (s of series(); track s.name) { <th>{{ s.name }}</th> }</tr></thead>
      <tbody>
        @for (d of firstData(); track d.date; let i = $index) {
          <tr><td>{{ d.date }}</td>@for (s of series(); track s.name) { <td>{{ countAt(s, i) }}</td> }</tr>
        }
      </tbody>
    </table>
  `,
  styles: `
    :host { display: block; }
    .legend { display: flex; gap: 1rem; list-style: none; margin: 0 0 0.35rem; padding: 0; font-size: 0.82rem; color: var(--muted); }
    .legend li { display: flex; align-items: center; gap: 0.35rem; }
    .swatch { display: inline-block; width: 0.7rem; height: 0.7rem; border-radius: 2px; }
    .chart { position: relative; }
    svg { display: block; width: 100%; height: auto; overflow: visible; }
    .grid { stroke: #eef2f1; stroke-width: 1; }
    .axis { stroke: #c9d5d4; stroke-width: 1; }
    .crosshair { stroke: #9fb0af; stroke-width: 1; stroke-dasharray: 3 3; }
    .tick { font-size: 11px; fill: var(--muted); }
    .hit { fill: transparent; cursor: crosshair; }
    path.dim { opacity: 0.45; }
    .tip {
      position: absolute; top: 0; transform: translateX(-50%); pointer-events: none;
      background: var(--ink); color: #fff; border-radius: 0.4rem; padding: 0.35rem 0.55rem;
      font-size: 0.78rem; display: grid; gap: 0.1rem; white-space: nowrap; z-index: 2;
    }
    .tip.flip { transform: translateX(-100%); }
    .tip .swatch { width: 0.55rem; height: 0.55rem; margin-right: 0.2rem; }
    .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  `,
})
export class TrendChartComponent {
  series = input.required<ChartSeries[]>();
  label = input('Chart');

  readonly w = W;
  readonly h = H;
  readonly left = LEFT;
  readonly top = TOP;
  readonly bottom = BOTTOM;
  hover = signal<number | null>(null);

  max = computed(() => niceMax(this.series().flatMap((s) => s.data.map((d) => d.count))));
  bars = computed(() => barGeometry(this.series()[0]?.data ?? [], W, H, this.max()));
  lines = computed(() =>
    this.series().map((s) => {
      const pts = linePoints(s.data, W, H, this.max());
      return { name: s.name, color: s.color, pts, points: pointsAttr(pts) };
    })
  );
  /** First, middle and last day under the axis. */
  ticks = computed(() => {
    const data = this.series()[0]?.data ?? [];
    if (!data.length) return [];
    const col = W / data.length;
    const idx = [...new Set([0, Math.floor((data.length - 1) / 2), data.length - 1])];
    return idx.map((i) => ({
      x: i === 0 ? 0 : i === data.length - 1 ? W : i * col + col / 2,
      anchor: i === 0 ? 'start' : i === data.length - 1 ? 'end' : 'middle',
      text: dayLabel(data[i].date),
    }));
  });

  firstData = computed(() => this.series()[0]?.data ?? []);

  countAt(s: ChartSeries, i: number): number {
    return s.data[i] ? s.data[i].count : 0;
  }

  cx(i: number): number {
    const n = this.series()[0]?.data.length || 1;
    return (i + 0.5) * (W / n);
  }

  tipLeft(): number {
    const i = this.hover();
    return i === null ? 0 : ((LEFT + this.cx(i)) / (W + LEFT)) * 100;
  }

  day(i: number): string {
    const d = this.series()[0]?.data[i];
    return d ? dayLabel(d.date) : '';
  }

  /** A bar with rounded top corners (radius up to 4px), square on the baseline. */
  barPath(b: BarGeom): string {
    const r = Math.min(4, b.width / 2, b.height);
    const { x, y, width: w, height: h } = b;
    return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
  }
}
