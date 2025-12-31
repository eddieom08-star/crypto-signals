import { Redis } from '@upstash/redis'

export const redis = new Redis({
  url: process.env.UPSTASH_REDIS_REST_URL!,
  token: process.env.UPSTASH_REDIS_REST_TOKEN!,
})

export interface Signal {
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
  liquidity_score: number
  volume_ratio_score: number
  momentum_score: number
  buy_pressure_score: number
  trend_score: number
  entry_price: number
  stop_loss: number
  take_profit_1: number
  take_profit_2: number
  take_profit_3: number
  risk_reward_ratio: number
  security_warnings: string[]
  pop_factors: Record<string, number>
  telegram_sent: boolean
}

export interface Scan {
  timestamp: string
  symbol: string
  price_usd: number
  total_score: number
  pop_score: number
  signal_strength: string
  risk_level: string
  is_valid_signal: boolean
}

export interface BotStatus {
  status: string
  scan_count: number
  signals_sent: number
  errors_count: number
  last_scan: string | null
  watchlist_size: number
  watchlist: string[]
  updated_at: string
}

export async function getSignals(limit = 20): Promise<Signal[]> {
  try {
    const signals = await redis.lrange<Signal>('signals', 0, limit - 1)
    return signals || []
  } catch (error) {
    console.error('Failed to fetch signals:', error)
    return []
  }
}

export async function getScans(limit = 20): Promise<Scan[]> {
  try {
    const scans = await redis.lrange<Scan>('scans', 0, limit - 1)
    return scans || []
  } catch (error) {
    console.error('Failed to fetch scans:', error)
    return []
  }
}

export async function getBotStatus(): Promise<BotStatus | null> {
  try {
    const status = await redis.get<BotStatus>('bot_status')
    return status
  } catch (error) {
    console.error('Failed to fetch bot status:', error)
    return null
  }
}
