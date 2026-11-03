import { useTheme } from "./theme";

/**
 * Chart colours for each theme. They repeat the --xe-series-* and chart tokens of styles/tokens.css (a unit test
 * checks that both stay the same), because SVG attributes need real colour values, not CSS variables.
 *
 * The four series hues were checked with the data-visualisation palette validator on both surfaces: adjacent pairs
 * stay apart for the common colour-vision deficiencies. On the light surface series 3 and 4 have low contrast, so
 * every chart with more than one series has a legend and a table view, and values are never printed in a series
 * colour.
 */
export const CHART_COLORS = {
  light: {
    series: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"],
    seriesMuted: "#b8bdc8",
    grid: "#e8eaee",
    axis: "#c9cdd5",
    text: "#5f6577",
    ink: "#1e2230",
    surface: "#ffffff",
    brand: "#5b2c83",
  },
  dark: {
    series: ["#3987e5", "#d95926", "#199e70", "#c98500"],
    seriesMuted: "#4a4e5a",
    grid: "#262934",
    axis: "#3a3e4a",
    text: "#8e93a0",
    ink: "#e7e8ec",
    surface: "#191b22",
    brand: "#7a4ab3",
  },
} as const;

export type ChartColors = (typeof CHART_COLORS)[keyof typeof CHART_COLORS];

/** The chart colours of the theme in use. */
export function useChartColors(): ChartColors {
  return CHART_COLORS[useTheme().resolved];
}
