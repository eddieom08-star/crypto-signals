import { NextResponse } from 'next/server'
import { getBotStatus, getScans } from '@/lib/redis'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export async function GET() {
  const [status, scans] = await Promise.all([
    getBotStatus(),
    getScans(10)
  ])

  return NextResponse.json({
    status: status || { status: 'offline', scan_count: 0, signals_sent: 0 },
    recent_scans: scans
  })
}
