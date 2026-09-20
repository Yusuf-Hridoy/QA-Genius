import { NextResponse } from 'next/server';
import { z } from 'zod';
import { PUBLIC_KINDS, REGISTRY } from '@/lib/generators/kinds';

export const runtime = 'nodejs';

const CACHE = { 'Cache-Control': 'public, max-age=300' } as const;

export async function GET(): Promise<Response> {
  const generators = PUBLIC_KINDS.map((kind) => {
    const def = REGISTRY[kind];
    return {
      kind: def.kind,
      title: def.title,
      description: def.description,
      tier: def.tier,
      requestSchema: z.toJSONSchema(def.requestSchema as z.ZodType),
      outputSchema: z.toJSONSchema(def.outputSchema as z.ZodType),
    };
  });
  return NextResponse.json(generators, { headers: CACHE });
}
