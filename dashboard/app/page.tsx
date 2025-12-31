'use client'

import { useEffect, useState } from 'react'

interface Signal {
  timestamp: string
  symbol: string
  address: string
  price_usd: number
  total_score: number
  pop_score: number
  pop_confidence: string
  expected_return: number
  max_drawdown: number
  signal_strength: string
  risk_level: string
  is_locked: boolean
  lock_percentage: number
  is_bundled: boolean
  bundle_percentage: number
  security_score: number
  bundle_penalty: number
  entry_price: number
  stop_loss: number
  take_profit_1: number
  take_profit_2: number
  take_profit_3: number
  risk_reward_ratio: number
  security_warnings: string[]
  telegram_sent: boolean
}

interface BotStatus {
  status: string
  scan_count: number
  signals_sent: number
  errors_count: number
  last_scan: string | null
  watchlist: string[]
  updated_at: string
}

interface Scan {
  timestamp: string
  symbol: string
  price_usd: number
  total_score: number
  pop_score: number
  signal_strength: string
  risk_level: string
  is_valid_signal: boolean
}

function formatPrice(price: number): string {
  if (price >= 1) return `$${price.toFixed(4)}`
  if (price >= 0.0001) return `$${price.toFixed(6)}`
  return `$${price.toFixed(10)}`
}

function formatTime(timestamp: string): string {
  return new Date(timestamp).toLocaleString()
}

function getRiskClass(risk: string): string {
  const classes: Record<string, string> = {
    LOW: 'text-green-400',
    MEDIUM: 'text-yellow-400',
    HIGH: 'text-orange-400',
    CRITICAL: 'text-red-400',
    UNKNOWN: 'text-gray-400',
  }
  return classes[risk] || 'text-gray-400'
}

function getSignalClass(strength: string): string {
  const classes: Record<string, string> = {
    STRONG: 'border-green-500 bg-green-500/10',
    MODERATE: 'border-yellow-500 bg-yellow-500/10',
    WEAK: 'border-red-500 bg-red-500/10',
    'NO SIGNAL': 'border-gray-500 bg-gray-500/10',
  }
  return classes[strength] || 'border-gray-500 bg-gray-500/10'
}

export default function Dashboard() {
  const [signals, setSignals] = useState<Signal[]>([])
  const [status, setStatus] = useState<BotStatus | null>(null)
  const [scans, setScans] = useState<Scan[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedSignal, setSelectedSignal] = useState<Signal | null>(null)

  useEffect(() => {
    async function fetchData() {
      try {
        const [signalsRes, statusRes] = await Promise.all([
          fetch('/api/signals'),
          fetch('/api/status'),
        ])

        const signalsData = await signalsRes.json()
        const statusData = await statusRes.json()

        setSignals(signalsData.signals || [])
        setStatus(statusData.status)
        setScans(statusData.recent_scans || [])
      } catch (error) {
        console.error('Failed to fetch data:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 30000) // Refresh every 30s
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-xl">Loading dashboard...</div>
      </div>
    )
  }

  return (
    <main className="min-h-screen p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold">Crypto Signals Dashboard</h1>
          <div className="flex items-center gap-4">
            <span
              className={`px-3 py-1 rounded-full text-sm ${
                status?.status === 'running'
                  ? 'bg-green-500/20 text-green-400'
                  : 'bg-red-500/20 text-red-400'
              }`}
            >
              {status?.status || 'offline'}
            </span>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <div className="card">
            <div className="text-gray-400 text-sm">Total Scans</div>
            <div className="text-2xl font-bold">{status?.scan_count || 0}</div>
          </div>
          <div className="card">
            <div className="text-gray-400 text-sm">Signals Sent</div>
            <div className="text-2xl font-bold text-green-400">
              {status?.signals_sent || 0}
            </div>
          </div>
          <div className="card">
            <div className="text-gray-400 text-sm">Errors</div>
            <div className="text-2xl font-bold text-red-400">
              {status?.errors_count || 0}
            </div>
          </div>
          <div className="card">
            <div className="text-gray-400 text-sm">Last Scan</div>
            <div className="text-sm">
              {status?.last_scan ? formatTime(status.last_scan) : 'Never'}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Signals List */}
          <div className="lg:col-span-2">
            <h2 className="text-xl font-semibold mb-4">Recent Signals</h2>
            {signals.length === 0 ? (
              <div className="card text-center text-gray-400">
                No signals yet. Bot is scanning for opportunities...
              </div>
            ) : (
              <div className="space-y-4">
                {signals.map((signal, idx) => (
                  <div
                    key={idx}
                    className={`card cursor-pointer border-l-4 ${getSignalClass(
                      signal.signal_strength
                    )}`}
                    onClick={() => setSelectedSignal(signal)}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <span className="text-xl font-bold">${signal.symbol}</span>
                        <span
                          className={`px-2 py-0.5 rounded text-xs ${getSignalClass(
                            signal.signal_strength
                          )}`}
                        >
                          {signal.signal_strength}
                        </span>
                        {signal.telegram_sent && (
                          <span className="text-blue-400 text-xs">Sent</span>
                        )}
                      </div>
                      <div className="text-right">
                        <div className="font-mono">
                          {formatPrice(signal.price_usd)}
                        </div>
                        <div className="text-xs text-gray-400">
                          {formatTime(signal.timestamp)}
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-4 gap-4 text-sm">
                      <div>
                        <span className="text-gray-400">Score</span>
                        <div className="font-bold">{signal.total_score}/100</div>
                      </div>
                      <div>
                        <span className="text-gray-400">PoP</span>
                        <div className="font-bold">{signal.pop_score}%</div>
                      </div>
                      <div>
                        <span className="text-gray-400">Risk</span>
                        <div className={getRiskClass(signal.risk_level)}>
                          {signal.risk_level}
                        </div>
                      </div>
                      <div>
                        <span className="text-gray-400">R:R</span>
                        <div>1:{signal.risk_reward_ratio}</div>
                      </div>
                    </div>

                    <div className="mt-3 flex items-center gap-4 text-xs">
                      <span
                        className={signal.is_locked ? 'text-green-400' : 'text-red-400'}
                      >
                        {signal.is_locked
                          ? `Locked ${signal.lock_percentage.toFixed(0)}%`
                          : 'Not Locked'}
                      </span>
                      {signal.is_bundled && (
                        <span className="text-orange-400">
                          Bundled {signal.bundle_percentage.toFixed(0)}%
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent Scans */}
          <div>
            <h2 className="text-xl font-semibold mb-4">Recent Scans</h2>
            <div className="card">
              {scans.length === 0 ? (
                <div className="text-gray-400 text-center">No scans yet</div>
              ) : (
                <div className="space-y-3">
                  {scans.map((scan, idx) => (
                    <div
                      key={idx}
                      className={`p-3 rounded-lg border ${
                        scan.is_valid_signal
                          ? 'border-green-500/50 bg-green-500/5'
                          : 'border-gray-700 bg-gray-800/50'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold">${scan.symbol}</span>
                        <span className="text-sm font-mono">
                          {formatPrice(scan.price_usd)}
                        </span>
                      </div>
                      <div className="flex items-center justify-between mt-1 text-sm">
                        <span className="text-gray-400">
                          Score: {scan.total_score} | PoP: {scan.pop_score}%
                        </span>
                        <span className={getRiskClass(scan.risk_level)}>
                          {scan.risk_level}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Watchlist */}
            <h2 className="text-xl font-semibold mb-4 mt-8">Watchlist</h2>
            <div className="card">
              <div className="flex flex-wrap gap-2">
                {status?.watchlist?.map((symbol) => (
                  <span
                    key={symbol}
                    className="px-3 py-1 bg-gray-700 rounded-full text-sm"
                  >
                    ${symbol}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Signal Detail Modal */}
        {selectedSignal && (
          <div
            className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50"
            onClick={() => setSelectedSignal(null)}
          >
            <div
              className="card max-w-2xl w-full max-h-[90vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-2xl font-bold">${selectedSignal.symbol}</h3>
                <button
                  onClick={() => setSelectedSignal(null)}
                  className="text-gray-400 hover:text-white"
                >
                  Close
                </button>
              </div>

              <div className="grid grid-cols-2 gap-4 mb-6">
                <div>
                  <span className="text-gray-400">Entry Price</span>
                  <div className="text-xl font-mono">
                    {formatPrice(selectedSignal.entry_price)}
                  </div>
                </div>
                <div>
                  <span className="text-gray-400">Stop Loss</span>
                  <div className="text-xl font-mono text-red-400">
                    {formatPrice(selectedSignal.stop_loss)}
                  </div>
                </div>
              </div>

              <div className="mb-6">
                <span className="text-gray-400">Take Profit Levels</span>
                <div className="grid grid-cols-3 gap-4 mt-2">
                  <div className="p-3 bg-green-500/10 rounded border border-green-500/30">
                    <div className="text-xs text-gray-400">TP1</div>
                    <div className="font-mono text-green-400">
                      {formatPrice(selectedSignal.take_profit_1)}
                    </div>
                  </div>
                  <div className="p-3 bg-green-500/10 rounded border border-green-500/30">
                    <div className="text-xs text-gray-400">TP2</div>
                    <div className="font-mono text-green-400">
                      {formatPrice(selectedSignal.take_profit_2)}
                    </div>
                  </div>
                  <div className="p-3 bg-green-500/10 rounded border border-green-500/30">
                    <div className="text-xs text-gray-400">TP3</div>
                    <div className="font-mono text-green-400">
                      {formatPrice(selectedSignal.take_profit_3)}
                    </div>
                  </div>
                </div>
              </div>

              <div className="mb-6">
                <span className="text-gray-400">Analysis Scores</span>
                <div className="grid grid-cols-5 gap-2 mt-2 text-sm">
                  <div className="text-center p-2 bg-gray-700/50 rounded">
                    <div className="text-gray-400">Liquidity</div>
                    <div>{selectedSignal.security_score}/20</div>
                  </div>
                  <div className="text-center p-2 bg-gray-700/50 rounded">
                    <div className="text-gray-400">Security</div>
                    <div>+{selectedSignal.security_score}</div>
                  </div>
                  <div className="text-center p-2 bg-gray-700/50 rounded">
                    <div className="text-gray-400">PoP</div>
                    <div>{selectedSignal.pop_score}%</div>
                  </div>
                  <div className="text-center p-2 bg-gray-700/50 rounded">
                    <div className="text-gray-400">Expected</div>
                    <div className="text-green-400">
                      +{selectedSignal.expected_return}%
                    </div>
                  </div>
                  <div className="text-center p-2 bg-gray-700/50 rounded">
                    <div className="text-gray-400">Drawdown</div>
                    <div className="text-red-400">
                      -{selectedSignal.max_drawdown}%
                    </div>
                  </div>
                </div>
              </div>

              {selectedSignal.security_warnings.length > 0 && (
                <div className="mb-6">
                  <span className="text-gray-400">Security Warnings</span>
                  <div className="mt-2 space-y-1">
                    {selectedSignal.security_warnings.map((warning, idx) => (
                      <div key={idx} className="text-orange-400 text-sm">
                        {warning}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="text-xs text-gray-500 mt-4">
                Contract: {selectedSignal.address}
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
