/**
 * Client-side technical indicator calculations
 * These mirror the backend TA-Lib calculations for chart visualization
 */

import { UTCTimestamp } from "lightweight-charts";

export interface CandleData {
  time: UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface LineData {
  time: UTCTimestamp;
  value: number;
}

export interface BollingerData {
  upper: LineData[];
  middle: LineData[];
  lower: LineData[];
}

export interface MACDData {
  macd: LineData[];
  signal: LineData[];
  histogram: LineData[];
}

export interface StochasticData {
  k: LineData[];
  d: LineData[];
}

export interface AroonData {
  up: LineData[];
  down: LineData[];
}

// ============================================
// PRICE OVERLAY INDICATORS
// ============================================

/**
 * Simple Moving Average
 */
export function calculateSMA(data: CandleData[], period: number): LineData[] {
  const result: LineData[] = [];
  for (let i = period - 1; i < data.length; i++) {
    let sum = 0;
    for (let j = 0; j < period; j++) {
      sum += data[i - j].close;
    }
    result.push({ time: data[i].time, value: sum / period });
  }
  return result;
}

/**
 * Exponential Moving Average
 */
export function calculateEMA(data: CandleData[], period: number): LineData[] {
  if (data.length < period) return [];
  const result: LineData[] = [];
  const k = 2 / (period + 1);

  // Initial EMA is SMA of first 'period' values
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += data[i].close;
  }
  let ema = sum / period;
  result.push({ time: data[period - 1].time, value: ema });

  // Calculate EMA for remaining values
  for (let i = period; i < data.length; i++) {
    ema = (data[i].close - ema) * k + ema;
    result.push({ time: data[i].time, value: ema });
  }
  return result;
}

/**
 * Double Exponential Moving Average
 */
export function calculateDEMA(data: CandleData[], period: number): LineData[] {
  const ema1 = calculateEMA(data, period);
  if (ema1.length === 0) return [];

  // Convert EMA results back to candle format for second EMA
  const emaCandles: CandleData[] = ema1.map((e) => ({
    time: e.time,
    open: e.value,
    high: e.value,
    low: e.value,
    close: e.value,
  }));

  const ema2 = calculateEMA(emaCandles, period);
  if (ema2.length === 0) return [];

  // DEMA = 2 * EMA1 - EMA2
  const result: LineData[] = [];
  const offset = ema1.length - ema2.length;
  for (let i = 0; i < ema2.length; i++) {
    const ema1Val = ema1[i + offset].value;
    const ema2Val = ema2[i].value;
    result.push({
      time: ema2[i].time,
      value: 2 * ema1Val - ema2Val,
    });
  }
  return result;
}

/**
 * Kaufman Adaptive Moving Average
 */
export function calculateKAMA(data: CandleData[], period: number): LineData[] {
  if (data.length < period + 1) return [];
  const result: LineData[] = [];

  const fastSC = 2 / (2 + 1); // Fast smoothing constant
  const slowSC = 2 / (30 + 1); // Slow smoothing constant

  // Start with SMA as initial KAMA
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += data[i].close;
  }
  let kama = sum / period;

  for (let i = period; i < data.length; i++) {
    // Calculate Efficiency Ratio (ER)
    const change = Math.abs(data[i].close - data[i - period].close);
    let volatility = 0;
    for (let j = 0; j < period; j++) {
      volatility += Math.abs(data[i - j].close - data[i - j - 1].close);
    }
    const er = volatility !== 0 ? change / volatility : 0;

    // Calculate Smoothing Constant (SC)
    const sc = Math.pow(er * (fastSC - slowSC) + slowSC, 2);

    // Calculate KAMA
    kama = kama + sc * (data[i].close - kama);
    result.push({ time: data[i].time, value: kama });
  }
  return result;
}

/**
 * Triangular Moving Average
 */
export function calculateTRIMA(data: CandleData[], period: number): LineData[] {
  // TRIMA is a double-smoothed SMA
  const sma1 = calculateSMA(data, Math.ceil(period / 2));
  if (sma1.length === 0) return [];

  const smaCandles: CandleData[] = sma1.map((s) => ({
    time: s.time,
    open: s.value,
    high: s.value,
    low: s.value,
    close: s.value,
  }));

  return calculateSMA(smaCandles, Math.floor(period / 2) + 1);
}

/**
 * Weighted Moving Average
 */
export function calculateWMA(data: CandleData[], period: number): LineData[] {
  if (data.length < period) return [];
  const result: LineData[] = [];
  const divisor = (period * (period + 1)) / 2;

  for (let i = period - 1; i < data.length; i++) {
    let sum = 0;
    for (let j = 0; j < period; j++) {
      sum += data[i - j].close * (period - j);
    }
    result.push({ time: data[i].time, value: sum / divisor });
  }
  return result;
}

/**
 * Triple Exponential Moving Average (T3)
 */
export function calculateT3(
  data: CandleData[],
  period: number,
  vfactor: number = 0.7
): LineData[] {
  // T3 = c1*e6 + c2*e5 + c3*e4 + c4*e3
  // where c1 = -a^3, c2 = 3*a^2 + 3*a^3, c3 = -6*a^2 - 3*a - 3*a^3, c4 = 1 + 3*a + a^3 + 3*a^2
  // and a = vfactor

  const a = vfactor;
  const c1 = -a * a * a;
  const c2 = 3 * a * a + 3 * a * a * a;
  const c3 = -6 * a * a - 3 * a - 3 * a * a * a;
  const c4 = 1 + 3 * a + a * a * a + 3 * a * a;

  const ema1 = calculateEMA(data, period);
  if (ema1.length < period) return [];

  const toCandles = (arr: LineData[]): CandleData[] =>
    arr.map((e) => ({
      time: e.time,
      open: e.value,
      high: e.value,
      low: e.value,
      close: e.value,
    }));

  const ema2 = calculateEMA(toCandles(ema1), period);
  if (ema2.length < period) return [];
  const ema3 = calculateEMA(toCandles(ema2), period);
  if (ema3.length < period) return [];
  const ema4 = calculateEMA(toCandles(ema3), period);
  if (ema4.length < period) return [];
  const ema5 = calculateEMA(toCandles(ema4), period);
  if (ema5.length < period) return [];
  const ema6 = calculateEMA(toCandles(ema5), period);
  if (ema6.length === 0) return [];

  // Align all EMAs to shortest length
  const minLen = ema6.length;
  const result: LineData[] = [];

  for (let i = 0; i < minLen; i++) {
    const idx3 = ema3.length - minLen + i;
    const idx4 = ema4.length - minLen + i;
    const idx5 = ema5.length - minLen + i;
    const idx6 = i;

    const t3 =
      c1 * ema6[idx6].value +
      c2 * ema5[idx5].value +
      c3 * ema4[idx4].value +
      c4 * ema3[idx3].value;

    result.push({ time: ema6[idx6].time, value: t3 });
  }
  return result;
}

/**
 * Bollinger Bands
 */
export function calculateBollingerBands(
  data: CandleData[],
  period: number = 20,
  stdDev: number = 2
): BollingerData {
  const upper: LineData[] = [];
  const middle: LineData[] = [];
  const lower: LineData[] = [];

  for (let i = period - 1; i < data.length; i++) {
    let sum = 0;
    for (let j = 0; j < period; j++) {
      sum += data[i - j].close;
    }
    const sma = sum / period;

    // Calculate standard deviation
    let sqSum = 0;
    for (let j = 0; j < period; j++) {
      sqSum += Math.pow(data[i - j].close - sma, 2);
    }
    const std = Math.sqrt(sqSum / period);

    middle.push({ time: data[i].time, value: sma });
    upper.push({ time: data[i].time, value: sma + stdDev * std });
    lower.push({ time: data[i].time, value: sma - stdDev * std });
  }

  return { upper, middle, lower };
}

/**
 * Parabolic SAR
 */
export function calculateSAR(
  data: CandleData[],
  acceleration: number = 0.02,
  maximum: number = 0.2
): LineData[] {
  if (data.length < 2) return [];
  const result: LineData[] = [];

  let isLong = data[1].close > data[0].close;
  let af = acceleration;
  let ep = isLong ? data[0].high : data[0].low;
  let sar = isLong ? data[0].low : data[0].high;

  for (let i = 1; i < data.length; i++) {
    const prevSar = sar;

    // Calculate new SAR
    sar = prevSar + af * (ep - prevSar);

    if (isLong) {
      // Ensure SAR is below prior two lows
      if (i >= 2) {
        sar = Math.min(sar, data[i - 1].low, data[i - 2].low);
      }

      // Check for reversal
      if (data[i].low < sar) {
        isLong = false;
        sar = ep;
        ep = data[i].low;
        af = acceleration;
      } else {
        // Update EP and AF
        if (data[i].high > ep) {
          ep = data[i].high;
          af = Math.min(af + acceleration, maximum);
        }
      }
    } else {
      // Ensure SAR is above prior two highs
      if (i >= 2) {
        sar = Math.max(sar, data[i - 1].high, data[i - 2].high);
      }

      // Check for reversal
      if (data[i].high > sar) {
        isLong = true;
        sar = ep;
        ep = data[i].high;
        af = acceleration;
      } else {
        // Update EP and AF
        if (data[i].low < ep) {
          ep = data[i].low;
          af = Math.min(af + acceleration, maximum);
        }
      }
    }

    result.push({ time: data[i].time, value: sar });
  }
  return result;
}

// ============================================
// OSCILLATOR INDICATORS
// ============================================

/**
 * Relative Strength Index
 */
export function calculateRSI(data: CandleData[], period: number = 14): LineData[] {
  if (data.length < period + 1) return [];
  const result: LineData[] = [];

  let gains = 0;
  let losses = 0;

  // Initial average gain/loss
  for (let i = 1; i <= period; i++) {
    const change = data[i].close - data[i - 1].close;
    if (change > 0) gains += change;
    else losses -= change;
  }

  let avgGain = gains / period;
  let avgLoss = losses / period;
  let rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
  result.push({ time: data[period].time, value: 100 - 100 / (1 + rs) });

  // Subsequent values using smoothing
  for (let i = period + 1; i < data.length; i++) {
    const change = data[i].close - data[i - 1].close;
    const currentGain = change > 0 ? change : 0;
    const currentLoss = change < 0 ? -change : 0;

    avgGain = (avgGain * (period - 1) + currentGain) / period;
    avgLoss = (avgLoss * (period - 1) + currentLoss) / period;

    rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    result.push({ time: data[i].time, value: 100 - 100 / (1 + rs) });
  }
  return result;
}

/**
 * MACD (Moving Average Convergence Divergence)
 */
export function calculateMACD(
  data: CandleData[],
  fastPeriod: number = 12,
  slowPeriod: number = 26,
  signalPeriod: number = 9
): MACDData {
  const emaFast = calculateEMA(data, fastPeriod);
  const emaSlow = calculateEMA(data, slowPeriod);

  // Calculate MACD line (fast EMA - slow EMA)
  const macdLine: LineData[] = [];
  const offset = emaFast.length - emaSlow.length;

  for (let i = 0; i < emaSlow.length; i++) {
    macdLine.push({
      time: emaSlow[i].time,
      value: emaFast[i + offset].value - emaSlow[i].value,
    });
  }

  // Calculate signal line (EMA of MACD)
  const macdCandles: CandleData[] = macdLine.map((m) => ({
    time: m.time,
    open: m.value,
    high: m.value,
    low: m.value,
    close: m.value,
  }));
  const signalLine = calculateEMA(macdCandles, signalPeriod);

  // Calculate histogram
  const histogram: LineData[] = [];
  const sigOffset = macdLine.length - signalLine.length;
  for (let i = 0; i < signalLine.length; i++) {
    histogram.push({
      time: signalLine[i].time,
      value: macdLine[i + sigOffset].value - signalLine[i].value,
    });
  }

  return {
    macd: macdLine.slice(sigOffset),
    signal: signalLine,
    histogram,
  };
}

/**
 * Stochastic Oscillator
 */
export function calculateStochastic(
  data: CandleData[],
  kPeriod: number = 14,
  dPeriod: number = 3
): StochasticData {
  if (data.length < kPeriod) return { k: [], d: [] };

  const kLine: LineData[] = [];

  for (let i = kPeriod - 1; i < data.length; i++) {
    let highest = data[i].high;
    let lowest = data[i].low;

    for (let j = 0; j < kPeriod; j++) {
      highest = Math.max(highest, data[i - j].high);
      lowest = Math.min(lowest, data[i - j].low);
    }

    const range = highest - lowest;
    const k = range === 0 ? 50 : ((data[i].close - lowest) / range) * 100;
    kLine.push({ time: data[i].time, value: k });
  }

  // %D is SMA of %K
  const kCandles: CandleData[] = kLine.map((k) => ({
    time: k.time,
    open: k.value,
    high: k.value,
    low: k.value,
    close: k.value,
  }));
  const dLine = calculateSMA(kCandles, dPeriod);

  return { k: kLine, d: dLine };
}

/**
 * Average Directional Index
 */
export function calculateADX(data: CandleData[], period: number = 14): LineData[] {
  if (data.length < period * 2) return [];
  const result: LineData[] = [];

  // Calculate True Range, +DM, -DM
  const tr: number[] = [];
  const plusDM: number[] = [];
  const minusDM: number[] = [];

  for (let i = 1; i < data.length; i++) {
    const high = data[i].high;
    const low = data[i].low;
    const prevClose = data[i - 1].close;
    const prevHigh = data[i - 1].high;
    const prevLow = data[i - 1].low;

    tr.push(Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose)));

    const upMove = high - prevHigh;
    const downMove = prevLow - low;

    plusDM.push(upMove > downMove && upMove > 0 ? upMove : 0);
    minusDM.push(downMove > upMove && downMove > 0 ? downMove : 0);
  }

  // Smooth TR, +DM, -DM
  let smoothTR = tr.slice(0, period).reduce((a, b) => a + b, 0);
  let smoothPlusDM = plusDM.slice(0, period).reduce((a, b) => a + b, 0);
  let smoothMinusDM = minusDM.slice(0, period).reduce((a, b) => a + b, 0);

  // Calculate +DI, -DI, DX
  const dx: number[] = [];

  for (let i = period; i < tr.length; i++) {
    smoothTR = smoothTR - smoothTR / period + tr[i];
    smoothPlusDM = smoothPlusDM - smoothPlusDM / period + plusDM[i];
    smoothMinusDM = smoothMinusDM - smoothMinusDM / period + minusDM[i];

    const plusDI = (smoothPlusDM / smoothTR) * 100;
    const minusDI = (smoothMinusDM / smoothTR) * 100;
    const diSum = plusDI + minusDI;
    dx.push(diSum === 0 ? 0 : (Math.abs(plusDI - minusDI) / diSum) * 100);
  }

  // Calculate ADX as smoothed DX
  let adx = dx.slice(0, period).reduce((a, b) => a + b, 0) / period;
  result.push({ time: data[period * 2].time, value: adx });

  for (let i = period; i < dx.length; i++) {
    adx = (adx * (period - 1) + dx[i]) / period;
    result.push({ time: data[i + period + 1].time, value: adx });
  }

  return result;
}

/**
 * Commodity Channel Index
 */
export function calculateCCI(data: CandleData[], period: number = 20): LineData[] {
  if (data.length < period) return [];
  const result: LineData[] = [];

  for (let i = period - 1; i < data.length; i++) {
    // Calculate typical price
    const tp: number[] = [];
    for (let j = 0; j < period; j++) {
      const d = data[i - j];
      tp.push((d.high + d.low + d.close) / 3);
    }

    const meanTP = tp.reduce((a, b) => a + b, 0) / period;
    const meanDev = tp.reduce((a, b) => a + Math.abs(b - meanTP), 0) / period;

    const cci = meanDev === 0 ? 0 : (tp[0] - meanTP) / (0.015 * meanDev);
    result.push({ time: data[i].time, value: cci });
  }
  return result;
}

/**
 * Money Flow Index
 */
export function calculateMFI(data: CandleData[], period: number = 14): LineData[] {
  if (data.length < period + 1 || !data[0].volume) return [];
  const result: LineData[] = [];

  // Calculate raw money flow
  const rawMF: { positive: number; negative: number }[] = [];

  for (let i = 1; i < data.length; i++) {
    const tp = (data[i].high + data[i].low + data[i].close) / 3;
    const prevTP = (data[i - 1].high + data[i - 1].low + data[i - 1].close) / 3;
    const mf = tp * (data[i].volume || 0);

    rawMF.push({
      positive: tp > prevTP ? mf : 0,
      negative: tp < prevTP ? mf : 0,
    });
  }

  // Calculate MFI
  for (let i = period - 1; i < rawMF.length; i++) {
    let positiveMF = 0;
    let negativeMF = 0;

    for (let j = 0; j < period; j++) {
      positiveMF += rawMF[i - j].positive;
      negativeMF += rawMF[i - j].negative;
    }

    const mfi = negativeMF === 0 ? 100 : 100 - 100 / (1 + positiveMF / negativeMF);
    result.push({ time: data[i + 1].time, value: mfi });
  }
  return result;
}

/**
 * Aroon Indicator
 */
export function calculateAroon(data: CandleData[], period: number = 25): AroonData {
  if (data.length < period + 1) return { up: [], down: [] };

  const up: LineData[] = [];
  const down: LineData[] = [];

  for (let i = period; i < data.length; i++) {
    let highestIdx = 0;
    let lowestIdx = 0;
    let highest = data[i - period].high;
    let lowest = data[i - period].low;

    for (let j = 0; j <= period; j++) {
      if (data[i - j].high >= highest) {
        highest = data[i - j].high;
        highestIdx = j;
      }
      if (data[i - j].low <= lowest) {
        lowest = data[i - j].low;
        lowestIdx = j;
      }
    }

    const aroonUp = ((period - highestIdx) / period) * 100;
    const aroonDown = ((period - lowestIdx) / period) * 100;

    up.push({ time: data[i].time, value: aroonUp });
    down.push({ time: data[i].time, value: aroonDown });
  }

  return { up, down };
}

/**
 * Williams %R
 */
export function calculateWILLR(data: CandleData[], period: number = 14): LineData[] {
  if (data.length < period) return [];
  const result: LineData[] = [];

  for (let i = period - 1; i < data.length; i++) {
    let highest = data[i].high;
    let lowest = data[i].low;

    for (let j = 0; j < period; j++) {
      highest = Math.max(highest, data[i - j].high);
      lowest = Math.min(lowest, data[i - j].low);
    }

    const range = highest - lowest;
    const willr = range === 0 ? -50 : ((highest - data[i].close) / range) * -100;
    result.push({ time: data[i].time, value: willr });
  }
  return result;
}

/**
 * Rate of Change
 */
export function calculateROC(data: CandleData[], period: number = 10): LineData[] {
  if (data.length <= period) return [];
  const result: LineData[] = [];

  for (let i = period; i < data.length; i++) {
    const roc = ((data[i].close - data[i - period].close) / data[i - period].close) * 100;
    result.push({ time: data[i].time, value: roc });
  }
  return result;
}

/**
 * Momentum
 */
export function calculateMOM(data: CandleData[], period: number = 10): LineData[] {
  if (data.length <= period) return [];
  const result: LineData[] = [];

  for (let i = period; i < data.length; i++) {
    const mom = data[i].close - data[i - period].close;
    result.push({ time: data[i].time, value: mom });
  }
  return result;
}

/**
 * Average True Range
 */
export function calculateATR(data: CandleData[], period: number = 14): LineData[] {
  if (data.length < period + 1) return [];
  const result: LineData[] = [];

  // Calculate True Range
  const tr: number[] = [];
  for (let i = 1; i < data.length; i++) {
    const high = data[i].high;
    const low = data[i].low;
    const prevClose = data[i - 1].close;
    tr.push(Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose)));
  }

  // Initial ATR is simple average
  let atr = tr.slice(0, period).reduce((a, b) => a + b, 0) / period;
  result.push({ time: data[period].time, value: atr });

  // Subsequent ATR using smoothing
  for (let i = period; i < tr.length; i++) {
    atr = (atr * (period - 1) + tr[i]) / period;
    result.push({ time: data[i + 1].time, value: atr });
  }
  return result;
}

/**
 * On Balance Volume
 */
export function calculateOBV(data: CandleData[]): LineData[] {
  if (data.length < 2 || !data[0].volume) return [];
  const result: LineData[] = [];
  let obv = 0;

  result.push({ time: data[0].time, value: obv });

  for (let i = 1; i < data.length; i++) {
    if (data[i].close > data[i - 1].close) {
      obv += data[i].volume || 0;
    } else if (data[i].close < data[i - 1].close) {
      obv -= data[i].volume || 0;
    }
    result.push({ time: data[i].time, value: obv });
  }
  return result;
}

/**
 * Chande Momentum Oscillator
 */
export function calculateCMO(data: CandleData[], period: number = 14): LineData[] {
  if (data.length < period + 1) return [];
  const result: LineData[] = [];

  for (let i = period; i < data.length; i++) {
    let sumUp = 0;
    let sumDown = 0;

    for (let j = 0; j < period; j++) {
      const change = data[i - j].close - data[i - j - 1].close;
      if (change > 0) sumUp += change;
      else sumDown -= change;
    }

    const cmo = sumUp + sumDown === 0 ? 0 : ((sumUp - sumDown) / (sumUp + sumDown)) * 100;
    result.push({ time: data[i].time, value: cmo });
  }
  return result;
}

/**
 * Absolute Price Oscillator
 */
export function calculateAPO(
  data: CandleData[],
  fastPeriod: number = 12,
  slowPeriod: number = 26
): LineData[] {
  const emaFast = calculateEMA(data, fastPeriod);
  const emaSlow = calculateEMA(data, slowPeriod);
  const result: LineData[] = [];

  const offset = emaFast.length - emaSlow.length;
  for (let i = 0; i < emaSlow.length; i++) {
    result.push({
      time: emaSlow[i].time,
      value: emaFast[i + offset].value - emaSlow[i].value,
    });
  }
  return result;
}

/**
 * Percentage Price Oscillator
 */
export function calculatePPO(
  data: CandleData[],
  fastPeriod: number = 12,
  slowPeriod: number = 26
): LineData[] {
  const emaFast = calculateEMA(data, fastPeriod);
  const emaSlow = calculateEMA(data, slowPeriod);
  const result: LineData[] = [];

  const offset = emaFast.length - emaSlow.length;
  for (let i = 0; i < emaSlow.length; i++) {
    const ppo = ((emaFast[i + offset].value - emaSlow[i].value) / emaSlow[i].value) * 100;
    result.push({ time: emaSlow[i].time, value: ppo });
  }
  return result;
}

/**
 * Triple Exponential Average (TRIX)
 */
export function calculateTRIX(data: CandleData[], period: number = 15): LineData[] {
  const ema1 = calculateEMA(data, period);
  if (ema1.length < period) return [];

  const toCandles = (arr: LineData[]): CandleData[] =>
    arr.map((e) => ({
      time: e.time,
      open: e.value,
      high: e.value,
      low: e.value,
      close: e.value,
    }));

  const ema2 = calculateEMA(toCandles(ema1), period);
  if (ema2.length < period) return [];
  const ema3 = calculateEMA(toCandles(ema2), period);
  if (ema3.length < 2) return [];

  const result: LineData[] = [];
  for (let i = 1; i < ema3.length; i++) {
    const trix = ((ema3[i].value - ema3[i - 1].value) / ema3[i - 1].value) * 100;
    result.push({ time: ema3[i].time, value: trix });
  }
  return result;
}

/**
 * Ultimate Oscillator
 */
export function calculateULTOSC(
  data: CandleData[],
  period1: number = 7,
  period2: number = 14,
  period3: number = 28
): LineData[] {
  if (data.length < period3 + 1) return [];
  const result: LineData[] = [];

  // Calculate buying pressure (BP) and true range (TR)
  const bp: number[] = [];
  const tr: number[] = [];

  for (let i = 1; i < data.length; i++) {
    const low = Math.min(data[i].low, data[i - 1].close);
    const high = Math.max(data[i].high, data[i - 1].close);
    bp.push(data[i].close - low);
    tr.push(high - low);
  }

  for (let i = period3 - 1; i < bp.length; i++) {
    let bp1 = 0, bp2 = 0, bp3 = 0;
    let tr1 = 0, tr2 = 0, tr3 = 0;

    for (let j = 0; j < period1; j++) {
      bp1 += bp[i - j];
      tr1 += tr[i - j];
    }
    for (let j = 0; j < period2; j++) {
      bp2 += bp[i - j];
      tr2 += tr[i - j];
    }
    for (let j = 0; j < period3; j++) {
      bp3 += bp[i - j];
      tr3 += tr[i - j];
    }

    const avg1 = tr1 === 0 ? 0 : bp1 / tr1;
    const avg2 = tr2 === 0 ? 0 : bp2 / tr2;
    const avg3 = tr3 === 0 ? 0 : bp3 / tr3;

    const ultosc = ((4 * avg1 + 2 * avg2 + avg3) / 7) * 100;
    result.push({ time: data[i + 1].time, value: ultosc });
  }
  return result;
}
