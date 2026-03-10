"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  ColorType,
  ISeriesApi,
  UTCTimestamp,
  SeriesMarker,
  IChartApi,
} from "lightweight-charts";
import { useTradingStore } from "@/lib/store";
import { Activity, Layers, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  calculateSMA,
  calculateEMA,
  calculateDEMA,
  calculateKAMA,
  calculateTRIMA,
  calculateWMA,
  calculateT3,
  calculateBollingerBands,
  calculateSAR,
  calculateRSI,
  calculateMACD,
  calculateStochastic,
  calculateADX,
  calculateCCI,
  calculateMFI,
  calculateAroon,
  calculateWILLR,
  calculateROC,
  calculateMOM,
  calculateATR,
  calculateOBV,
  calculateCMO,
  calculateAPO,
  calculatePPO,
  calculateTRIX,
  calculateULTOSC,
  CandleData,
  LineData,
} from "@/lib/indicators";

interface TradingChartProps {
  height?: number;
  showMarkers?: boolean;
  showIndicators?: boolean;
}

// Indicator configuration
const OVERLAY_INDICATORS = {
  sma20: { name: "SMA 20", color: "#3b82f6" },
  ema50: { name: "EMA 50", color: "#f59e0b" },
  dema20: { name: "DEMA 20", color: "#a855f7" },
  kama30: { name: "KAMA 30", color: "#ec4899" },
  trima30: { name: "TRIMA 30", color: "#06b6d4" },
  wma20: { name: "WMA 20", color: "#84cc16" },
  t3: { name: "T3", color: "#d97706" },
  bbUpper: { name: "BB Upper", color: "#6b7280" },
  bbMiddle: { name: "BB Middle", color: "#9ca3af" },
  bbLower: { name: "BB Lower", color: "#6b7280" },
  sar: { name: "SAR", color: "#facc15" },
};

const OSCILLATOR_INDICATORS = {
  rsi: { name: "RSI", range: [0, 100], levels: [30, 70] },
  macd: { name: "MACD", range: null, levels: [0] },
  stochastic: { name: "Stochastic", range: [0, 100], levels: [20, 80] },
  adx: { name: "ADX", range: [0, 100], levels: [25] },
  cci: { name: "CCI", range: null, levels: [-100, 100] },
  mfi: { name: "MFI", range: [0, 100], levels: [20, 80] },
  aroon: { name: "Aroon", range: [0, 100], levels: [30, 70] },
  willr: { name: "Williams %R", range: [-100, 0], levels: [-80, -20] },
  roc: { name: "ROC", range: null, levels: [0] },
  mom: { name: "Momentum", range: null, levels: [0] },
  atr: { name: "ATR", range: null, levels: [] },
  obv: { name: "OBV", range: null, levels: [] },
  cmo: { name: "CMO", range: [-100, 100], levels: [-50, 50] },
  apo: { name: "APO", range: null, levels: [0] },
  ppo: { name: "PPO", range: null, levels: [0] },
  trix: { name: "TRIX", range: null, levels: [0] },
  ultosc: { name: "Ultimate Osc", range: [0, 100], levels: [30, 70] },
};

export function TradingChart({
  height = 400,
  showMarkers = true,
  showIndicators = true,
}: TradingChartProps) {
  const toUtcSeconds = (value: number) =>
    Math.floor(value > 1e12 ? value / 1000 : value);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  // Overlay series refs
  const overlaySeriesRefs = useRef<Record<string, ISeriesApi<"Line"> | null>>({});

  // Oscillator chart refs
  const oscillatorContainerRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const oscillatorChartRefs = useRef<Record<string, IChartApi | null>>({});
  const oscillatorSeriesRefs = useRef<Record<string, ISeriesApi<"Line"> | ISeriesApi<"Histogram"> | null>>({});

  const {
    selectedSymbol,
    selectedTimeframe,
    historicalData,
    fetchHistoricalData,
    recentTrades,
    fetchRecentTrades,
  } = useTradingStore();

  const [isReady, setIsReady] = useState(false);
  const [showLayersMenu, setShowLayersMenu] = useState(false);
  const [expandedSection, setExpandedSection] = useState<"overlays" | "oscillators" | null>("overlays");

  // Toggle states
  const [overlayToggles, setOverlayToggles] = useState<Record<string, boolean>>({
    sma20: true,
    ema50: true,
    dema20: false,
    kama30: false,
    trima30: false,
    wma20: false,
    t3: false,
    bbUpper: false,
    bbMiddle: false,
    bbLower: false,
    sar: false,
  });

  const [oscillatorToggles, setOscillatorToggles] = useState<Record<string, boolean>>({
    rsi: false,
    macd: false,
    stochastic: false,
    adx: false,
    cci: false,
    mfi: false,
    aroon: false,
    willr: false,
    roc: false,
    mom: false,
    atr: false,
    obv: false,
    cmo: false,
    apo: false,
    ppo: false,
    trix: false,
    ultosc: false,
  });

  // Initialize Main Chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#a1a1aa",
      },
      grid: {
        vertLines: { color: "#18181b" },
        horzLines: { color: "#18181b" },
      },
      width: chartContainerRef.current.clientWidth,
      height: height,
      timeScale: {
        borderColor: "#27272a",
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: "#27272a",
      },
    });

    const candlestickSeries = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    candlestickSeriesRef.current = candlestickSeries;
    chartRef.current = chart;

    // Add overlay series
    if (showIndicators) {
      Object.entries(OVERLAY_INDICATORS).forEach(([key, config]) => {
        overlaySeriesRefs.current[key] = chart.addLineSeries({
          color: config.color,
          lineWidth: 1,
          crosshairMarkerVisible: key !== "sar",
          lastValueVisible: false,
          priceLineVisible: false,
        });
      });
    }

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
      // Resize oscillator charts
      Object.entries(oscillatorChartRefs.current).forEach(([key, oscChart]) => {
        const container = oscillatorContainerRefs.current[key];
        if (oscChart && container) {
          oscChart.applyOptions({ width: container.clientWidth });
        }
      });
    };

    window.addEventListener("resize", handleResize);
    setIsReady(true);

    return () => {
      window.removeEventListener("resize", handleResize);
      // Clean up oscillator charts
      Object.values(oscillatorChartRefs.current).forEach((c) => c?.remove());
      chart.remove();
    };
  }, [height, showIndicators]);

  // Fetch data
  useEffect(() => {
    if (isReady) {
      fetchHistoricalData(selectedSymbol, selectedTimeframe);
      if (showMarkers) fetchRecentTrades();
    }
  }, [selectedSymbol, selectedTimeframe, isReady, fetchHistoricalData, showMarkers, fetchRecentTrades]);

  // Update Main Chart Data
  useEffect(() => {
    if (!candlestickSeriesRef.current || !historicalData || !historicalData.candles.length) return;

    const candleData: CandleData[] = [...historicalData.candles]
      .sort((a, b) => a.time - b.time)
      .map((c) => ({
        time: toUtcSeconds(c.time) as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: c.volume,
      }));

    candlestickSeriesRef.current.setData(candleData);

    // Calculate and update overlay indicators
    if (showIndicators) {
      // SMA
      const smaData = calculateSMA(candleData, 20);
      overlaySeriesRefs.current.sma20?.setData(overlayToggles.sma20 ? smaData : []);

      // EMA
      const emaData = calculateEMA(candleData, 50);
      overlaySeriesRefs.current.ema50?.setData(overlayToggles.ema50 ? emaData : []);

      // DEMA
      const demaData = calculateDEMA(candleData, 20);
      overlaySeriesRefs.current.dema20?.setData(overlayToggles.dema20 ? demaData : []);

      // KAMA
      const kamaData = calculateKAMA(candleData, 30);
      overlaySeriesRefs.current.kama30?.setData(overlayToggles.kama30 ? kamaData : []);

      // TRIMA
      const trimaData = calculateTRIMA(candleData, 30);
      overlaySeriesRefs.current.trima30?.setData(overlayToggles.trima30 ? trimaData : []);

      // WMA
      const wmaData = calculateWMA(candleData, 20);
      overlaySeriesRefs.current.wma20?.setData(overlayToggles.wma20 ? wmaData : []);

      // T3
      const t3Data = calculateT3(candleData, 5, 0.7);
      overlaySeriesRefs.current.t3?.setData(overlayToggles.t3 ? t3Data : []);

      // Bollinger Bands
      const bbData = calculateBollingerBands(candleData, 20, 2);
      const showBB = overlayToggles.bbUpper || overlayToggles.bbMiddle || overlayToggles.bbLower;
      overlaySeriesRefs.current.bbUpper?.setData(overlayToggles.bbUpper ? bbData.upper : []);
      overlaySeriesRefs.current.bbMiddle?.setData(overlayToggles.bbMiddle ? bbData.middle : []);
      overlaySeriesRefs.current.bbLower?.setData(overlayToggles.bbLower ? bbData.lower : []);

      // SAR
      const sarData = calculateSAR(candleData, 0.02, 0.2);
      overlaySeriesRefs.current.sar?.setData(overlayToggles.sar ? sarData : []);
    }

    // Add Markers
    if (showMarkers && recentTrades.length > 0) {
      const markers: SeriesMarker<UTCTimestamp>[] = recentTrades
        .filter((t) => t.symbol === selectedSymbol)
        .map((t) => ({
          time: toUtcSeconds(t.timestamp) as UTCTimestamp,
          position: t.side === "buy" ? "belowBar" : "aboveBar",
          color: t.side === "buy" ? "#22c55e" : "#ef4444",
          shape: t.side === "buy" ? "arrowUp" : "arrowDown",
          text: t.side.toUpperCase(),
        }))
        .sort((a, b) => Number(a.time) - Number(b.time));

      candlestickSeriesRef.current.setMarkers(markers);
    }

    chartRef.current?.timeScale().fitContent();
  }, [historicalData, recentTrades, selectedSymbol, showMarkers, showIndicators, overlayToggles]);

  // Create/Update Oscillator Panes
  useEffect(() => {
    if (!historicalData || !historicalData.candles.length) return;

    const candleData: CandleData[] = [...historicalData.candles]
      .sort((a, b) => a.time - b.time)
      .map((c) => ({
        time: toUtcSeconds(c.time) as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: c.volume,
      }));

    Object.entries(oscillatorToggles).forEach(([key, enabled]) => {
      const container = oscillatorContainerRefs.current[key];

      if (enabled && container && !oscillatorChartRefs.current[key]) {
        // Create oscillator chart
        const oscChart = createChart(container, {
          layout: {
            background: { type: ColorType.Solid, color: "transparent" },
            textColor: "#a1a1aa",
          },
          grid: {
            vertLines: { color: "#18181b" },
            horzLines: { color: "#18181b" },
          },
          width: container.clientWidth,
          height: 100,
          timeScale: {
            visible: false,
          },
          rightPriceScale: {
            borderColor: "#27272a",
          },
        });

        oscillatorChartRefs.current[key] = oscChart;

        // Add series based on indicator type
        if (key === "macd") {
          const histSeries = oscChart.addHistogramSeries({
            color: "#3b82f6",
          });
          const macdData = calculateMACD(candleData, 12, 26, 9);
          histSeries.setData(macdData.histogram);
          oscillatorSeriesRefs.current[key] = histSeries;
        } else {
          const lineSeries = oscChart.addLineSeries({
            color: "#3b82f6",
            lineWidth: 1,
          });

          let data: LineData[] = [];
          switch (key) {
            case "rsi":
              data = calculateRSI(candleData, 14);
              break;
            case "stochastic":
              data = calculateStochastic(candleData, 14, 3).k;
              break;
            case "adx":
              data = calculateADX(candleData, 14);
              break;
            case "cci":
              data = calculateCCI(candleData, 20);
              break;
            case "mfi":
              data = calculateMFI(candleData, 14);
              break;
            case "aroon":
              data = calculateAroon(candleData, 25).up;
              break;
            case "willr":
              data = calculateWILLR(candleData, 14);
              break;
            case "roc":
              data = calculateROC(candleData, 10);
              break;
            case "mom":
              data = calculateMOM(candleData, 10);
              break;
            case "atr":
              data = calculateATR(candleData, 14);
              break;
            case "obv":
              data = calculateOBV(candleData);
              break;
            case "cmo":
              data = calculateCMO(candleData, 14);
              break;
            case "apo":
              data = calculateAPO(candleData, 12, 26);
              break;
            case "ppo":
              data = calculatePPO(candleData, 12, 26);
              break;
            case "trix":
              data = calculateTRIX(candleData, 15);
              break;
            case "ultosc":
              data = calculateULTOSC(candleData, 7, 14, 28);
              break;
            default:
              data = [];
          }

          lineSeries.setData(data);
          oscillatorSeriesRefs.current[key] = lineSeries;
        }

        oscChart.timeScale().fitContent();

        // Sync time scale with main chart
        if (chartRef.current) {
          chartRef.current.timeScale().subscribeVisibleLogicalRangeChange((range) => {
            if (range && oscillatorChartRefs.current[key]) {
              oscillatorChartRefs.current[key]?.timeScale().setVisibleLogicalRange(range);
            }
          });
        }
      } else if (!enabled && oscillatorChartRefs.current[key]) {
        // Remove oscillator chart
        oscillatorChartRefs.current[key]?.remove();
        oscillatorChartRefs.current[key] = null;
        oscillatorSeriesRefs.current[key] = null;
      }
    });
  }, [oscillatorToggles, historicalData]);

  const toggleOverlay = (key: string) => {
    setOverlayToggles((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const toggleOscillator = (key: string) => {
    setOscillatorToggles((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const activeOverlays = Object.entries(overlayToggles).filter(([_, v]) => v).length;
  const activeOscillators = Object.entries(oscillatorToggles).filter(([_, v]) => v).length;

  return (
    <div className="card p-0 overflow-hidden bg-zinc-950 border-zinc-800">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800 bg-zinc-900/50">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-green-500" />
          <span className="text-sm font-medium text-zinc-200">
            {selectedSymbol} Chart ({selectedTimeframe})
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-[10px] uppercase font-bold tracking-wider">
            {activeOverlays > 0 && (
              <span className="text-blue-400">{activeOverlays} overlays</span>
            )}
            {activeOscillators > 0 && (
              <span className="text-purple-400">{activeOscillators} oscillators</span>
            )}
          </div>
          <div className="relative">
            <button
              onClick={() => setShowLayersMenu(!showLayersMenu)}
              className={cn(
                "p-1.5 hover:bg-zinc-800 rounded transition-colors flex items-center gap-1",
                showLayersMenu && "bg-zinc-800"
              )}
            >
              <Layers className="w-4 h-4 text-zinc-400" />
              <span className="text-xs text-zinc-500">Indicators</span>
            </button>

            {/* Layers Menu */}
            {showLayersMenu && (
              <div className="absolute right-0 top-10 bg-zinc-900 border border-zinc-800 rounded-lg shadow-xl z-50 min-w-[220px] max-h-[500px] overflow-y-auto">
                {/* Overlays Section */}
                <div className="border-b border-zinc-800">
                  <button
                    onClick={() => setExpandedSection(expandedSection === "overlays" ? null : "overlays")}
                    className="w-full flex items-center justify-between px-3 py-2 hover:bg-zinc-800/50"
                  >
                    <span className="text-[10px] uppercase font-bold text-zinc-400 tracking-wider">
                      Price Overlays ({activeOverlays})
                    </span>
                    {expandedSection === "overlays" ? (
                      <ChevronUp className="w-3 h-3 text-zinc-500" />
                    ) : (
                      <ChevronDown className="w-3 h-3 text-zinc-500" />
                    )}
                  </button>
                  {expandedSection === "overlays" && (
                    <div className="pb-2">
                      {Object.entries(OVERLAY_INDICATORS).map(([key, config]) => (
                        <label
                          key={key}
                          className="flex items-center gap-2 px-3 py-1 hover:bg-zinc-800 cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={overlayToggles[key] || false}
                            onChange={() => toggleOverlay(key)}
                            className="w-3 h-3 rounded border-zinc-600"
                          />
                          <span
                            className="w-2 h-2 rounded-full"
                            style={{ backgroundColor: config.color }}
                          />
                          <span className="text-xs text-zinc-300">{config.name}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>

                {/* Oscillators Section */}
                <div>
                  <button
                    onClick={() => setExpandedSection(expandedSection === "oscillators" ? null : "oscillators")}
                    className="w-full flex items-center justify-between px-3 py-2 hover:bg-zinc-800/50"
                  >
                    <span className="text-[10px] uppercase font-bold text-zinc-400 tracking-wider">
                      Oscillators ({activeOscillators})
                    </span>
                    {expandedSection === "oscillators" ? (
                      <ChevronUp className="w-3 h-3 text-zinc-500" />
                    ) : (
                      <ChevronDown className="w-3 h-3 text-zinc-500" />
                    )}
                  </button>
                  {expandedSection === "oscillators" && (
                    <div className="pb-2">
                      {Object.entries(OSCILLATOR_INDICATORS).map(([key, config]) => (
                        <label
                          key={key}
                          className="flex items-center gap-2 px-3 py-1 hover:bg-zinc-800 cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={oscillatorToggles[key] || false}
                            onChange={() => toggleOscillator(key)}
                            className="w-3 h-3 rounded border-zinc-600"
                          />
                          <span className="text-xs text-zinc-300">{config.name}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Main Chart */}
      <div ref={chartContainerRef} className="w-full relative" style={{ height }} />

      {/* Oscillator Panes */}
      {Object.entries(OSCILLATOR_INDICATORS).map(([key, config]) => (
        oscillatorToggles[key] && (
          <div key={key} className="border-t border-zinc-800">
            <div className="px-3 py-1 bg-zinc-900/50 flex items-center justify-between">
              <span className="text-[10px] uppercase font-bold text-zinc-500 tracking-wider">
                {config.name}
              </span>
              <button
                onClick={() => toggleOscillator(key)}
                className="text-zinc-600 hover:text-zinc-400 text-xs"
              >
                &times;
              </button>
            </div>
            <div
              ref={(el) => { oscillatorContainerRefs.current[key] = el; }}
              className="w-full"
              style={{ height: 100 }}
            />
          </div>
        )
      ))}
    </div>
  );
}
