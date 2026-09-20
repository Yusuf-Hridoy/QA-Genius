import { NextResponse } from 'next/server';
import { PROVIDERS, PROVIDER_SELECT_ORDER } from '@/lib/llm/providers';

export const runtime = 'nodejs';

const CACHE = { 'Cache-Control': 'public, max-age=300' } as const;

export async function GET(): Promise<Response> {
  return NextResponse.json(
    PROVIDER_SELECT_ORDER.map((id) => PROVIDERS[id]),
    {
      headers: CACHE,
    },
  );
}
