import { NextResponse } from 'next/server'
import { getSignals } from '@/lib/redis'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const limit = parseInt(searchParams.get('limit') || '20')

  const signals = await getSignals(limit)

  return NextResponse.json({ signals, count: signals.length })
}
