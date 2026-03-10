"use client";

import { useEffect, useState } from "react";
import { Navigation } from "@/components/Navigation";
import { useTradingStore } from "@/lib/store";
import { automationPresets } from "@/lib/automationPresets";
import { Modal } from "@/components/Modal";
import {
  Play,
  Pause,
  Trash2,
  Plus,
  Zap,
  Target,
  Clock,
  Activity,
  AlertCircle,
  Pencil,
  Info,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { LogViewer } from "@/components/LogViewer";

export default function AutomationPage() {
  const { 
    automationRules, 
    fetchAutomationRules, 
    createAutomationRule, 
    deleteAutomationRule,
    updateAutomationRule,
    toggleAutomationRule,
    isLoading 
  } = useTradingStore();

  const [showNewRule, setShowNewRule] = useState(false);
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [presetSymbol, setPresetSymbol] = useState(
    automationPresets[0]?.symbol || "BTC/USDT"
  );
  const [isApplyingPresets, setIsApplyingPresets] = useState(false);
  const [newRule, setNewRule] = useState({
    name: "",
    symbol: "BTC/USDT",
    timeframe: "1h",
    side: "buy",
    signalType: "STRONG_BUY",
    amount: 100,
    amountType: "fixed",
    minScore: 10,
    stopLossPct: 2,
    takeProfitPct: 5,
    trailingStopPct: 0,
    onlyIfInPosition: true,
    reduceOnly: true,
    minProfitPct: 0.5,
    breakEvenAfterPct: 1.0,
    maxHoldBars: 72,
    cooldownMinutes: 60
  });

  const [customConditions, setCustomConditions] = useState<any[]>([]);
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [selectedRule, setSelectedRule] = useState<any | null>(null);

  useEffect(() => {
    fetchAutomationRules();
  }, [fetchAutomationRules]);

  const presetsForSymbol = automationPresets.filter(
    (preset) => preset.symbol === presetSymbol
  );

  const handleApplyPresetPack = async () => {
    if (presetsForSymbol.length === 0) {
      return;
    }

    setIsApplyingPresets(true);
    for (const preset of presetsForSymbol) {
      await createAutomationRule(preset as any);
    }
    await fetchAutomationRules();
    setIsApplyingPresets(false);
  };

  const handleLoadPresetIntoForm = () => {
    if (presetsForSymbol.length === 0) {
      return;
    }
    setShowNewRule(true);
    setNewRule({
      ...presetsForSymbol[0],
    } as any);
  };

  const addCondition = () => {
    setCustomConditions([...customConditions, { indicator: "RSI", op: "<", val: 30 }]);
  };

  const removeCondition = (index: number) => {
    setCustomConditions(customConditions.filter((_, i) => i !== index));
  };

  const updateCondition = (index: number, field: string, value: any) => {
    const updated = [...customConditions];
    updated[index] = { ...updated[index], [field]: value };
    setCustomConditions(updated);
  };

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    
    const ruleData = {
      ...newRule,
      conditions: customConditions.length > 0 
        ? JSON.stringify({ operator: "AND", rules: customConditions }) 
        : undefined
    };

    if (editingRuleId) {
      await updateAutomationRule(editingRuleId, ruleData as any);
    } else {
      await createAutomationRule(ruleData as any);
    }

    setShowNewRule(false);
    setEditingRuleId(null);
    setCustomConditions([]);
    setNewRule({
      name: "",
      symbol: "BTC/USDT",
      timeframe: "1h",
      side: "buy",
      signalType: "STRONG_BUY",
      amount: 100,
      amountType: "fixed",
      minScore: 10,
      stopLossPct: 2,
      takeProfitPct: 5,
      trailingStopPct: 0,
      onlyIfInPosition: true,
      reduceOnly: true,
      minProfitPct: 0.5,
      breakEvenAfterPct: 1.0,
      maxHoldBars: 72,
      cooldownMinutes: 60
    });
  };

  const handleEditRule = (rule: any) => {
    setShowNewRule(true);
    setEditingRuleId(rule.id);
    setNewRule({
      name: rule.name,
      symbol: rule.symbol,
      timeframe: rule.timeframe,
      side: rule.side,
      signalType: rule.signalType,
      amount: rule.amount,
      amountType: rule.amountType,
      minScore: rule.minScore ?? 0,
      stopLossPct: rule.stopLossPct ?? 0,
      takeProfitPct: rule.takeProfitPct ?? 0,
      trailingStopPct: rule.trailingStopPct ?? 0,
      onlyIfInPosition: rule.onlyIfInPosition ?? true,
      reduceOnly: rule.reduceOnly ?? true,
      minProfitPct: rule.minProfitPct ?? 0.5,
      breakEvenAfterPct: rule.breakEvenAfterPct ?? 1.0,
      maxHoldBars: rule.maxHoldBars ?? 72,
      cooldownMinutes: rule.cooldownMinutes ?? 60,
    });

    if (rule.conditions) {
      try {
        const parsed = JSON.parse(rule.conditions);
        setCustomConditions(parsed?.rules ?? []);
      } catch {
        setCustomConditions([]);
      }
    } else {
      setCustomConditions([]);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950">
      <Navigation />
      
      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-zinc-100 flex items-center gap-2">
              <Zap className="w-6 h-6 text-yellow-500" />
              Automation Rules
            </h1>
            <p className="text-zinc-500">Automate your trading strategies based on technical signals</p>
          </div>
          
          <div className="flex flex-col sm:flex-row sm:items-center gap-2">
            <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded-lg p-1">
              <button
                onClick={() => setViewMode("grid")}
                className={cn(
                  "px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
                  viewMode === "grid"
                    ? "bg-zinc-800 text-zinc-100"
                    : "text-zinc-500 hover:text-zinc-200"
                )}
              >
                Cards
              </button>
              <button
                onClick={() => setViewMode("list")}
                className={cn(
                  "px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
                  viewMode === "list"
                    ? "bg-zinc-800 text-zinc-100"
                    : "text-zinc-500 hover:text-zinc-200"
                )}
              >
                List
              </button>
            </div>
            <button 
              onClick={() => setShowNewRule(true)}
              className="flex items-center justify-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium transition-colors w-full sm:w-auto"
            >
              <Plus className="w-4 h-4" />
              New Rule
            </button>
          </div>
        </div>

        {/* Preset Packs */}
        <div className="card mb-6">
          <h3 className="card-header flex items-center gap-2">
            <Activity className="w-5 h-5" />
            Preset Packs
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-zinc-400">Coin</label>
              <select
                value={presetSymbol}
                onChange={(e) => setPresetSymbol(e.target.value)}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100"
              >
                {[...new Set(automationPresets.map((p) => p.symbol))].map((symbol) => (
                  <option key={symbol} value={symbol}>
                    {symbol}
                  </option>
                ))}
              </select>
            </div>
            <div className="md:col-span-2 flex items-end gap-3">
              <button
                onClick={handleApplyPresetPack}
                disabled={isApplyingPresets || presetsForSymbol.length === 0}
                className={cn(
                  "px-4 py-2 rounded-lg text-sm font-medium transition-colors",
                  isApplyingPresets || presetsForSymbol.length === 0
                    ? "bg-zinc-700 text-zinc-400 cursor-not-allowed"
                    : "bg-green-600 hover:bg-green-700 text-white"
                )}
              >
                {isApplyingPresets ? "Applying..." : `Create ${presetsForSymbol.length} Preset Rules`}
              </button>
              <button
                onClick={handleLoadPresetIntoForm}
                disabled={presetsForSymbol.length === 0}
                className={cn(
                  "px-4 py-2 rounded-lg text-sm font-medium transition-colors",
                  presetsForSymbol.length === 0
                    ? "bg-zinc-700 text-zinc-400 cursor-not-allowed"
                    : "bg-zinc-800 hover:bg-zinc-700 text-zinc-100"
                )}
              >
                Load First Preset into Form
              </button>
            </div>
          </div>
          <div className="mt-3 text-xs text-zinc-500">
            Creates a balanced set across multiple timeframes with buy entries and sell exits.
          </div>
        </div>

        {/* New Rule Form */}
        {showNewRule && (
          <div className="card mb-8 animate-in fade-in slide-in-from-top-4">
            <h3 className="card-header">
              {editingRuleId ? "Edit Automation Rule" : "Create New Automation Rule"}
            </h3>
            <form onSubmit={handleCreateRule} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-zinc-400">Rule Name</label>
                <input 
                  required
                  value={newRule.name}
                  onChange={e => setNewRule({...newRule, name: e.target.value})}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100"
                  placeholder="e.g. BTC Breakout"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-zinc-400">Trading Pair</label>
                <input 
                  required
                  value={newRule.symbol}
                  onChange={e => setNewRule({...newRule, symbol: e.target.value})}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-zinc-400">Timeframe</label>
                <select 
                  value={newRule.timeframe}
                  onChange={e => setNewRule({...newRule, timeframe: e.target.value})}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100"
                >
                  <option value="1m">1 minute</option>
                  <option value="5m">5 minutes</option>
                  <option value="15m">15 minutes</option>
                  <option value="1h">1 hour</option>
                  <option value="4h">4 hours</option>
                  <option value="1d">1 day</option>
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-zinc-400">Trade Side</label>
                <select 
                  value={newRule.side}
                  onChange={e => setNewRule({...newRule, side: e.target.value})}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100"
                >
                  <option value="buy">Buy</option>
                  <option value="sell">Sell</option>
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-zinc-400">Trigger Signal</label>
                <select 
                  value={newRule.signalType}
                  onChange={e => setNewRule({...newRule, signalType: e.target.value})}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100"
                >
                  <option value="STRONG_BUY">Strong Buy</option>
                  <option value="BUY">Buy</option>
                  <option value="SELL">Sell</option>
                  <option value="STRONG_SELL">Strong Sell</option>
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-zinc-400">Min Score (0-54)</label>
                <input
                  type="number"
                  value={newRule.minScore}
                  onChange={e => setNewRule({...newRule, minScore: parseInt(e.target.value)})}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-zinc-400">Amount Type</label>
                <select 
                  value={newRule.amountType}
                  onChange={e => setNewRule({...newRule, amountType: e.target.value})}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100"
                >
                  <option value="fixed">Fixed (Base Units)</option>
                  <option value="percent">Percent of Balance</option>
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-zinc-400">Trade Amount</label>
                <input 
                  type="number"
                  required
                  value={newRule.amount}
                  onChange={e => setNewRule({...newRule, amount: parseFloat(e.target.value)})}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100"
                  placeholder={newRule.amountType === "percent" ? "e.g. 5 (%)" : "e.g. 0.001"}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-zinc-400">Stop Loss (%)</label>
                <input 
                  type="number"
                  step="0.1"
                  value={newRule.stopLossPct}
                  onChange={e => setNewRule({...newRule, stopLossPct: parseFloat(e.target.value)})}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-zinc-400">Take Profit (%)</label>
                <input 
                  type="number"
                  step="0.1"
                  value={newRule.takeProfitPct}
                  onChange={e => setNewRule({...newRule, takeProfitPct: parseFloat(e.target.value)})}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-zinc-400">Trailing Stop (%)</label>
                <input 
                  type="number"
                  step="0.1"
                  value={newRule.trailingStopPct}
                  onChange={e => setNewRule({...newRule, trailingStopPct: parseFloat(e.target.value)})}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100"
                  placeholder="e.g. 1.5 (0 to disable)"
                />
              </div>

              {/* Exit Safeguards */}
              <div className="col-span-full border-t border-zinc-800 pt-4 mt-2">
                <h4 className="text-sm font-bold text-zinc-400 uppercase tracking-widest mb-3">Exit Safeguards</h4>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium text-zinc-400">Min Profit (%)</label>
                    <input
                      type="number"
                      step="0.1"
                      value={newRule.minProfitPct}
                      onChange={e => setNewRule({...newRule, minProfitPct: parseFloat(e.target.value)})}
                      className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium text-zinc-400">Break-even After (%)</label>
                    <input
                      type="number"
                      step="0.1"
                      value={newRule.breakEvenAfterPct}
                      onChange={e => setNewRule({...newRule, breakEvenAfterPct: parseFloat(e.target.value)})}
                      className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium text-zinc-400">Max Hold (Bars)</label>
                    <input
                      type="number"
                      value={newRule.maxHoldBars}
                      onChange={e => setNewRule({...newRule, maxHoldBars: parseInt(e.target.value)})}
                      className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100"
                    />
                  </div>
                  <label className="flex items-center gap-2 text-sm text-zinc-400">
                    <input
                      type="checkbox"
                      checked={newRule.onlyIfInPosition}
                      onChange={e => setNewRule({...newRule, onlyIfInPosition: e.target.checked})}
                      className="w-4 h-4 rounded border-zinc-600"
                    />
                    Only sell if in position
                  </label>
                  <label className="flex items-center gap-2 text-sm text-zinc-400">
                    <input
                      type="checkbox"
                      checked={newRule.reduceOnly}
                      onChange={e => setNewRule({...newRule, reduceOnly: e.target.checked})}
                      className="w-4 h-4 rounded border-zinc-600"
                    />
                    Reduce-only sells
                  </label>
                </div>
                <p className="mt-2 text-xs text-zinc-600">
                  Sell rules respect position size, minimum profit, and optional time-based exits.
                </p>
              </div>

              {/* Custom Conditions Section */}
              <div className="col-span-full border-t border-zinc-800 pt-4 mt-2">
                <div className="flex items-center justify-between mb-4">
                  <h4 className="text-sm font-bold text-zinc-400 uppercase tracking-widest">Custom Logic (Optional)</h4>
                  <button 
                    type="button" 
                    onClick={addCondition}
                    className="text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-2 py-1 rounded border border-zinc-700 transition-colors"
                  >
                    + Add Condition
                  </button>
                </div>

                <div className="space-y-3">
                  {customConditions.map((cond, i) => (
                    <div key={i} className="flex items-center gap-2 animate-in fade-in slide-in-from-left-2">
                      <select
                        value={cond.indicator}
                        onChange={e => updateCondition(i, "indicator", e.target.value)}
                        className="flex-1 bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-sm text-zinc-200"
                      >
                        <option value="RSI">RSI</option>
                        <option value="MACD">MACD</option>
                        <option value="EMA">EMA</option>
                        <option value="SMA">SMA</option>
                        <option value="ADX">ADX</option>
                        <option value="Bollinger Bands">Bollinger Bands</option>
                        <option value="Stochastic">Stochastic</option>
                        <option value="CCI">CCI</option>
                        <option value="MFI">MFI</option>
                        <option value="Aroon">Aroon</option>
                        <option value="APO">APO</option>
                        <option value="CMO">CMO</option>
                        <option value="DEMA">DEMA</option>
                        <option value="MESA">MESA</option>
                        <option value="KAMA">KAMA</option>
                        <option value="MOM">MOM</option>
                        <option value="PPO">PPO</option>
                        <option value="SAR">SAR</option>
                        <option value="TRIMA">TRIMA</option>
                        <option value="TRIX">TRIX</option>
                        <option value="T3">T3</option>
                        <option value="ROC">ROC</option>
                        <option value="WMA">WMA</option>
                        <option value="ATR">ATR</option>
                        <option value="OBV">OBV</option>
                        <option value="WILLR">WILLR</option>
                        <option value="ULTOSC">ULTOSC</option>
                      </select>
                      <select
                        value={cond.op}
                        onChange={e => updateCondition(i, "op", e.target.value)}
                        className="w-28 bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-sm text-zinc-200"
                      >
                        <option value="<">&lt;</option>
                        <option value=">">&gt;</option>
                        <option value="==">==</option>
                        <option value="crosses_above">crosses above</option>
                        <option value="crosses_below">crosses below</option>
                      </select>
                      <input 
                        type="number"
                        value={cond.val}
                        onChange={e => updateCondition(i, "val", parseFloat(e.target.value))}
                        className="w-24 bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 text-sm text-zinc-200"
                      />
                      <button 
                        type="button" 
                        onClick={() => removeCondition(i)}
                        className="p-1.5 text-zinc-500 hover:text-red-400 transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                  {customConditions.length === 0 && (
                    <p className="text-xs text-zinc-600 italic">No custom conditions defined. Rule will trigger based on the Signal Type above.</p>
                  )}
                </div>
              </div>

              <div className="col-span-full flex justify-end gap-3 mt-2">
                <button 
                  type="button"
                  onClick={() => {
                    setShowNewRule(false);
                    setEditingRuleId(null);
                    setCustomConditions([]);
                    setNewRule({
                      name: "",
                      symbol: "BTC/USDT",
                      timeframe: "1h",
                      side: "buy",
                      signalType: "STRONG_BUY",
                      amount: 100,
                      amountType: "fixed",
                      minScore: 10,
                      stopLossPct: 2,
                      takeProfitPct: 5,
                      trailingStopPct: 0,
                      onlyIfInPosition: true,
                      reduceOnly: true,
                      minProfitPct: 0.5,
                      breakEvenAfterPct: 1.0,
                      maxHoldBars: 72,
                      cooldownMinutes: 60,
                    });
                  }}
                  className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button 
                  type="submit"
                  className="px-6 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium transition-colors"
                >
                  {editingRuleId ? "Update Rule" : "Save Rule"}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Rules List */}
        {viewMode === "grid" ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {isLoading.automation ? (
              <div className="col-span-full py-12 flex flex-col items-center justify-center gap-4">
                <div className="w-8 h-8 border-2 border-green-500 border-t-transparent rounded-full animate-spin" />
                <p className="text-zinc-500">Loading automation rules...</p>
              </div>
            ) : automationRules.length === 0 ? (
              <div className="col-span-full py-20 bg-zinc-900/50 rounded-2xl border-2 border-dashed border-zinc-800 flex flex-col items-center justify-center gap-4">
                <Activity className="w-12 h-12 text-zinc-700" />
                <div className="text-center">
                  <h3 className="text-lg font-medium text-zinc-400">No automation rules yet</h3>
                  <p className="text-zinc-500">Create your first rule to start automated trading</p>
                </div>
              </div>
            ) : (
              automationRules.map(rule => (
                <div key={rule.id} className={cn(
                  "card transition-all group",
                  !rule.isActive && "opacity-60"
                )}>
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h3 className="text-lg font-bold text-zinc-100">{rule.name}</h3>
                      <p className="text-zinc-500 font-mono text-sm">{rule.symbol} • {rule.timeframe}</p>
                    </div>
                    <button 
                      onClick={() => toggleAutomationRule(rule.id, !rule.isActive)}
                      className={cn(
                        "w-10 h-10 rounded-full flex items-center justify-center transition-colors",
                        rule.isActive 
                          ? "bg-green-500/10 text-green-500 hover:bg-green-500/20" 
                          : "bg-zinc-800 text-zinc-500 hover:bg-zinc-700"
                      )}
                    >
                      {rule.isActive ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5" />}
                    </button>
                  </div>

                  <div className="space-y-3 mb-6">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-zinc-500 flex items-center gap-1.5">
                        <Target className="w-4 h-4" /> Condition
                      </span>
                      <span className={cn(
                        "font-medium",
                        rule.signalType.includes("BUY") ? "text-green-400" : "text-red-400"
                      )}>
                        {rule.signalType} (Score {rule.minScore})
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-zinc-500 flex items-center gap-1.5">
                        <Zap className="w-4 h-4" /> Amount
                      </span>
                      <span className="text-zinc-200 font-medium">
                        {rule.amountType === "percent"
                          ? `${rule.amount}%`
                          : `${rule.amount} ${rule.symbol.split('/')[0]}`}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-zinc-500 flex items-center gap-1.5">
                        <Clock className="w-4 h-4" /> Last Triggered
                      </span>
                      <span className="text-zinc-400">
                        {rule.lastTriggered === 0 ? "Never" : new Date(rule.lastTriggered * 1000).toLocaleString()}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-4 border-t border-zinc-800">
                    <span className={cn(
                      "flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full",
                      rule.isActive 
                        ? "bg-green-500/10 text-green-500" 
                        : "bg-zinc-800 text-zinc-500"
                    )}>
                      <Activity className="w-3 h-3" />
                      {rule.isActive ? "Active" : "Paused"}
                    </span>
                    
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setSelectedRule(rule)}
                        className="p-2 text-zinc-500 hover:text-zinc-100 hover:bg-zinc-800 rounded-lg transition-all"
                        title="View details"
                      >
                        <Info className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleEditRule(rule)}
                        className="p-2 text-zinc-500 hover:text-zinc-100 hover:bg-zinc-800 rounded-lg transition-all"
                        title="Edit rule"
                      >
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button 
                        onClick={() => {
                          if (confirm("Delete this rule?")) deleteAutomationRule(rule.id);
                        }}
                        className="p-2 text-zinc-500 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-all"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        ) : (
          <div className="card p-0 overflow-hidden">
            {isLoading.automation ? (
              <div className="py-12 flex flex-col items-center justify-center gap-4">
                <div className="w-8 h-8 border-2 border-green-500 border-t-transparent rounded-full animate-spin" />
                <p className="text-zinc-500">Loading automation rules...</p>
              </div>
            ) : automationRules.length === 0 ? (
              <div className="py-16 text-center text-zinc-500">
                <Activity className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>No automation rules yet</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[720px]">
                  <thead className="text-zinc-500 border-b border-zinc-800">
                    <tr>
                      <th className="py-3 px-4 text-left">Rule</th>
                      <th className="py-3 px-4 text-left">Symbol</th>
                      <th className="py-3 px-4 text-left hidden md:table-cell">Timeframe</th>
                      <th className="py-3 px-4 text-left hidden md:table-cell">Signal</th>
                      <th className="py-3 px-4 text-right hidden sm:table-cell">Amount</th>
                      <th className="py-3 px-4 text-right hidden lg:table-cell">Last Triggered</th>
                      <th className="py-3 px-4 text-right">Status</th>
                      <th className="py-3 px-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800">
                    {automationRules.map((rule) => (
                      <tr
                        key={rule.id}
                        className="text-zinc-300 hover:bg-zinc-900/50 transition-colors cursor-pointer"
                        onClick={() => setSelectedRule(rule)}
                      >
                        <td className="py-3 px-4 font-medium">{rule.name}</td>
                        <td className="py-3 px-4 font-mono">{rule.symbol}</td>
                        <td className="py-3 px-4 hidden md:table-cell">{rule.timeframe}</td>
                        <td className={cn(
                          "py-3 px-4",
                          rule.signalType.includes("BUY") ? "text-green-400" : "text-red-400"
                        , "hidden md:table-cell")}>
                          {rule.signalType} ({rule.minScore})
                        </td>
                        <td className="py-3 px-4 text-right font-mono hidden sm:table-cell">
                          {rule.amountType === "percent"
                            ? `${rule.amount}%`
                            : `${rule.amount} ${rule.symbol.split('/')[0]}`}
                        </td>
                        <td className="py-3 px-4 text-right text-zinc-500 hidden lg:table-cell">
                          {rule.lastTriggered === 0
                            ? "Never"
                            : new Date(rule.lastTriggered * 1000).toLocaleString()}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <span className={cn(
                            "inline-flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full",
                            rule.isActive 
                              ? "bg-green-500/10 text-green-500" 
                              : "bg-zinc-800 text-zinc-500"
                          )}>
                            <Activity className="w-3 h-3" />
                            {rule.isActive ? "Active" : "Paused"}
                          </span>
                        </td>
                        <td
                          className="py-3 px-4 text-right"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => toggleAutomationRule(rule.id, !rule.isActive)}
                              className="p-1.5 text-zinc-500 hover:text-zinc-100 hover:bg-zinc-800 rounded"
                              title={rule.isActive ? "Pause" : "Activate"}
                            >
                              {rule.isActive ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                            </button>
                            <button
                              onClick={() => handleEditRule(rule)}
                              className="p-1.5 text-zinc-500 hover:text-zinc-100 hover:bg-zinc-800 rounded"
                              title="Edit rule"
                            >
                              <Pencil className="w-4 h-4" />
                            </button>
                            <button 
                              onClick={() => {
                                if (confirm("Delete this rule?")) deleteAutomationRule(rule.id);
                              }}
                              className="p-1.5 text-zinc-500 hover:text-red-400 hover:bg-red-400/10 rounded"
                              title="Delete rule"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Execution Logs */}
        <div className="mt-12">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="w-5 h-5 text-zinc-400" />
            <h2 className="text-xl font-bold text-zinc-200">Execution Logs</h2>
          </div>
          <LogViewer />
        </div>

        {/* Info Box */}
        <div className="mt-12 p-4 bg-blue-900/20 border border-blue-900/30 rounded-xl flex gap-3">
          <AlertCircle className="w-5 h-5 text-blue-400 shrink-0" />
          <div className="text-sm text-blue-300/80">
            <p className="font-medium text-blue-300 mb-1">How Automation Works</p>
            <p>Automation rules run every minute on the server. When the technical scan for a pair matches your trigger condition (Signal + Min Score), the bot will execute a market order in your current trading mode (Paper or Live). A cooldown is applied after each trigger to prevent multiple entries in a single trend.</p>
          </div>
        </div>

        <Modal
          isOpen={!!selectedRule}
          onClose={() => setSelectedRule(null)}
          title={selectedRule ? `Rule Details • ${selectedRule.name}` : "Rule Details"}
        >
          {selectedRule && (
            <div className="space-y-4 text-sm">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-zinc-500">Symbol</p>
                  <p className="text-zinc-100 font-mono">{selectedRule.symbol}</p>
                </div>
                <div>
                  <p className="text-zinc-500">Timeframe</p>
                  <p className="text-zinc-100 font-mono">{selectedRule.timeframe}</p>
                </div>
                <div>
                  <p className="text-zinc-500">Side</p>
                  <p className="text-zinc-100 uppercase">{selectedRule.side}</p>
                </div>
                <div>
                  <p className="text-zinc-500">Signal</p>
                  <p className="text-zinc-100 uppercase">{selectedRule.signalType}</p>
                </div>
                <div>
                  <p className="text-zinc-500">Amount</p>
                  <p className="text-zinc-100">
                    {selectedRule.amountType === "percent"
                      ? `${selectedRule.amount}%`
                      : `${selectedRule.amount} ${selectedRule.symbol.split("/")[0]}`}
                  </p>
                </div>
                <div>
                  <p className="text-zinc-500">Min Score</p>
                  <p className="text-zinc-100">{selectedRule.minScore ?? "—"}</p>
                </div>
                <div>
                  <p className="text-zinc-500">Stop Loss %</p>
                  <p className="text-zinc-100">{selectedRule.stopLossPct ?? "—"}</p>
                </div>
                <div>
                  <p className="text-zinc-500">Take Profit %</p>
                  <p className="text-zinc-100">{selectedRule.takeProfitPct ?? "—"}</p>
                </div>
                <div>
                  <p className="text-zinc-500">Trailing Stop %</p>
                  <p className="text-zinc-100">{selectedRule.trailingStopPct ?? "—"}</p>
                </div>
                <div>
                  <p className="text-zinc-500">Cooldown (min)</p>
                  <p className="text-zinc-100">{selectedRule.cooldownMinutes ?? "—"}</p>
                </div>
                <div>
                  <p className="text-zinc-500">Only If In Position</p>
                  <p className="text-zinc-100">{selectedRule.onlyIfInPosition ? "Yes" : "No"}</p>
                </div>
                <div>
                  <p className="text-zinc-500">Reduce Only</p>
                  <p className="text-zinc-100">{selectedRule.reduceOnly ? "Yes" : "No"}</p>
                </div>
                <div>
                  <p className="text-zinc-500">Min Profit %</p>
                  <p className="text-zinc-100">{selectedRule.minProfitPct ?? "—"}</p>
                </div>
                <div>
                  <p className="text-zinc-500">Break-even After %</p>
                  <p className="text-zinc-100">{selectedRule.breakEvenAfterPct ?? "—"}</p>
                </div>
                <div>
                  <p className="text-zinc-500">Max Hold (bars)</p>
                  <p className="text-zinc-100">{selectedRule.maxHoldBars ?? "—"}</p>
                </div>
              </div>
              <div>
                <p className="text-zinc-500">Custom Conditions</p>
                <pre className="text-xs text-zinc-300 bg-zinc-900/60 border border-zinc-800 rounded-lg p-3 overflow-x-auto">
                  {selectedRule.conditions
                    ? (() => {
                        try {
                          return JSON.stringify(JSON.parse(selectedRule.conditions), null, 2);
                        } catch {
                          return selectedRule.conditions;
                        }
                      })()
                    : "—"}
                </pre>
              </div>
            </div>
          )}
        </Modal>
      </main>
    </div>
  );
}
