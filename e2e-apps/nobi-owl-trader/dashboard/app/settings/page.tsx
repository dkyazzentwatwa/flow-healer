"use client";

import { useState, useEffect } from "react";
import { Navigation } from "@/components/Navigation";
import { useTradingStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import {
  Settings,
  Key,
  Server,
  Bell,
  Shield,
  Save,
  CheckCircle,
  AlertTriangle,
} from "lucide-react";

export default function SettingsPage() {
  const {
    isConnected,
    isPaperTrading,
    exchange,
    checkConnection,
    settings: storeSettings,
    updateSettings,
    riskLimits,
    updateRiskLimits,
    fetchRiskLimits,
  } = useTradingStore();

  const [form, setForm] = useState({
    apiUrl: storeSettings.apiUrl,
    notifications: storeSettings.enableNotifications,
    autoRefresh: storeSettings.enableAutoRefresh,
    refreshInterval: Math.max(5, Math.round(storeSettings.refreshInterval / 1000)),
    maxPositionSizePercent: riskLimits.maxPositionSizePercent,
    defaultTimeframe: storeSettings.timeframe,
  });

  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetchRiskLimits();
  }, [fetchRiskLimits]);

  useEffect(() => {
    setForm({
      apiUrl: storeSettings.apiUrl,
      notifications: storeSettings.enableNotifications,
      autoRefresh: storeSettings.enableAutoRefresh,
      refreshInterval: Math.max(5, Math.round(storeSettings.refreshInterval / 1000)),
      maxPositionSizePercent: riskLimits.maxPositionSizePercent,
      defaultTimeframe: storeSettings.timeframe,
    });
  }, [storeSettings, riskLimits]);

  const handleSave = () => {
    updateSettings({
      apiUrl: form.apiUrl,
      enableNotifications: form.notifications,
      enableAutoRefresh: form.autoRefresh,
      refreshInterval: form.refreshInterval * 1000,
      timeframe: form.defaultTimeframe as any,
    });
    updateRiskLimits({
      maxPositionSizePercent: form.maxPositionSizePercent,
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="min-h-screen bg-zinc-950">
      <Navigation />

      <main className="max-w-4xl mx-auto px-4 py-8">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-12 h-12 bg-zinc-800 rounded-xl flex items-center justify-center">
            <Settings className="w-6 h-6 text-zinc-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-zinc-100">Settings</h1>
            <p className="text-zinc-500">Configure your trading bot</p>
          </div>
        </div>

        {/* Connection Status Card */}
        <div className="card mb-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Server className="w-5 h-5 text-zinc-400" />
              <div>
                <h3 className="font-medium text-zinc-200">API Connection</h3>
                <p className="text-sm text-zinc-500">{form.apiUrl}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span
                className={cn(
                  "flex items-center gap-2 px-3 py-1.5 rounded-full text-sm",
                  isConnected
                    ? "bg-green-400/10 text-green-400"
                    : "bg-red-400/10 text-red-400"
                )}
              >
                {isConnected ? (
                  <CheckCircle className="w-4 h-4" />
                ) : (
                  <AlertTriangle className="w-4 h-4" />
                )}
                {isConnected ? "Connected" : "Disconnected"}
              </span>
              <button
                onClick={() => {
                  updateSettings({ apiUrl: form.apiUrl });
                  checkConnection();
                }}
                className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm transition-colors"
              >
                Test
              </button>
            </div>
          </div>
          {isConnected && (
            <div className="mt-4 pt-4 border-t border-zinc-800 flex gap-4 text-sm">
              <span className="text-zinc-500">
                Exchange: <span className="text-zinc-300 capitalize">{exchange}</span>
              </span>
              <span className="text-zinc-500">
                Mode:{" "}
                <span className={isPaperTrading ? "text-yellow-400" : "text-green-400"}>
                  {isPaperTrading ? "Paper Trading" : "Live Trading"}
                </span>
              </span>
            </div>
          )}
        </div>

        {/* Settings Sections */}
        <div className="space-y-6">
          {/* Trading Settings */}
          <div className="card">
            <h3 className="card-header flex items-center gap-2">
              <Shield className="w-5 h-5" />
              Trading Settings
            </h3>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <label className="font-medium text-zinc-200">Paper Trading Mode</label>
                  <p className="text-sm text-zinc-500">
                    Controlled by server configuration
                  </p>
                </div>
                <span
                  className={cn(
                    "px-3 py-1.5 rounded-full text-sm",
                    isPaperTrading
                      ? "bg-green-400/10 text-green-400"
                      : "bg-red-400/10 text-red-400"
                  )}
                >
                  {isPaperTrading ? "Enabled" : "Disabled"}
                </span>
              </div>

              <div>
                <label className="block font-medium text-zinc-200 mb-2">
                  Max Position Size (% of portfolio)
                </label>
                <input
                  type="number"
                  value={form.maxPositionSizePercent}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      maxPositionSizePercent: parseFloat(e.target.value) || 0,
                    })
                  }
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100 focus:outline-none focus:ring-2 focus:ring-green-500"
                />
                <p className="text-sm text-zinc-500 mt-1">
                  Maximum exposure per position
                </p>
              </div>

              <div>
                <label className="block font-medium text-zinc-200 mb-2">
                  Default Timeframe
                </label>
                <select
                  value={form.defaultTimeframe}
                  onChange={(e) =>
                    setForm({ ...form, defaultTimeframe: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100 focus:outline-none focus:ring-2 focus:ring-green-500"
                >
                  <option value="1m">1 minute</option>
                  <option value="5m">5 minutes</option>
                  <option value="15m">15 minutes</option>
                  <option value="1h">1 hour</option>
                  <option value="4h">4 hours</option>
                  <option value="1d">1 day</option>
                </select>
              </div>
            </div>
          </div>

          {/* Paper Balance Management */}
          {isPaperTrading && (
            <div className="card">
              <h3 className="card-header flex items-center gap-2">
                <Server className="w-5 h-5" />
                Paper Balance Management
              </h3>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block font-medium text-zinc-200 mb-2">
                      Currency (e.g. USDT)
                    </label>
                    <input
                      id="paper-currency"
                      type="text"
                      placeholder="USDT"
                      className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100 focus:outline-none focus:ring-2 focus:ring-green-500"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-zinc-200 mb-2">
                      Amount
                    </label>
                    <input
                      id="paper-amount"
                      type="number"
                      placeholder="10000"
                      className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100 focus:outline-none focus:ring-2 focus:ring-green-500"
                    />
                  </div>
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={() => {
                      const currency = (document.getElementById("paper-currency") as HTMLInputElement).value;
                      const amount = parseFloat((document.getElementById("paper-amount") as HTMLInputElement).value);
                      if (currency && !isNaN(amount)) {
                        useTradingStore.getState().setPaperBalance(currency, amount);
                      }
                    }}
                    className="flex-1 px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-zinc-100 rounded-lg transition-colors"
                  >
                    Set Balance
                  </button>
                  <button
                    onClick={() => {
                      if (confirm("Are you sure you want to reset all paper balances?")) {
                        useTradingStore.getState().resetPaperAccount();
                      }
                    }}
                    className="px-4 py-2 bg-red-900/30 hover:bg-red-900/50 text-red-400 border border-red-900/50 rounded-lg transition-colors"
                  >
                    Reset All
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* API Configuration */}
          <div className="card">
            <h3 className="card-header flex items-center gap-2">
              <Key className="w-5 h-5" />
              API Configuration
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block font-medium text-zinc-200 mb-2">
                  API Server URL
                </label>
                <input
                  type="text"
                  value={form.apiUrl}
                  onChange={(e) =>
                    setForm({ ...form, apiUrl: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
                />
              </div>

              <div className="p-4 bg-zinc-800/50 rounded-lg">
                <p className="text-sm text-zinc-400">
                  <strong className="text-zinc-300">Note:</strong> API keys are configured
                  on the server side via environment variables. Edit the{" "}
                  <code className="text-green-400">.env</code> file in the project root to
                  update your exchange credentials.
                </p>
              </div>
            </div>
          </div>

          {/* Notifications */}
          <div className="card">
            <h3 className="card-header flex items-center gap-2">
              <Bell className="w-5 h-5" />
              Notifications & Display
            </h3>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <label className="font-medium text-zinc-200">Enable Notifications</label>
                  <p className="text-sm text-zinc-500">
                    Show alerts for trade signals
                  </p>
                </div>
                <button
                  onClick={() =>
                    setForm({ ...form, notifications: !form.notifications })
                  }
                  className={cn(
                    "w-12 h-6 rounded-full transition-colors relative",
                    form.notifications ? "bg-green-600" : "bg-zinc-700"
                  )}
                >
                  <span
                    className={cn(
                      "absolute top-1 w-4 h-4 bg-white rounded-full transition-transform",
                      form.notifications ? "left-7" : "left-1"
                    )}
                  />
                </button>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <label className="font-medium text-zinc-200">Auto-Refresh Data</label>
                  <p className="text-sm text-zinc-500">
                    Automatically update prices and data
                  </p>
                </div>
                <button
                  onClick={() =>
                    setForm({ ...form, autoRefresh: !form.autoRefresh })
                  }
                  className={cn(
                    "w-12 h-6 rounded-full transition-colors relative",
                    form.autoRefresh ? "bg-green-600" : "bg-zinc-700"
                  )}
                >
                  <span
                    className={cn(
                      "absolute top-1 w-4 h-4 bg-white rounded-full transition-transform",
                      form.autoRefresh ? "left-7" : "left-1"
                    )}
                  />
                </button>
              </div>

              {form.autoRefresh && (
                <div>
                  <label className="block font-medium text-zinc-200 mb-2">
                    Refresh Interval (seconds)
                  </label>
                  <input
                    type="number"
                    min="5"
                    max="60"
                    value={form.refreshInterval}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        refreshInterval: parseInt(e.target.value) || 10,
                      })
                    }
                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-100 focus:outline-none focus:ring-2 focus:ring-green-500"
                  />
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Save Button */}
        <div className="mt-8 flex justify-end">
          <button
            onClick={handleSave}
            className={cn(
              "flex items-center gap-2 px-6 py-3 rounded-lg font-medium transition-all",
              saved
                ? "bg-green-600 text-white"
                : "bg-green-600 hover:bg-green-700 text-white"
            )}
          >
            {saved ? (
              <>
                <CheckCircle className="w-5 h-5" />
                Saved!
              </>
            ) : (
              <>
                <Save className="w-5 h-5" />
                Save Settings
              </>
            )}
          </button>
        </div>
      </main>
    </div>
  );
}
