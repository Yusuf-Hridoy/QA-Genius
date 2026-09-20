import { NextResponse } from 'next/server';
import { isGeneratorKind } from '@/lib/generators/kinds';
import { parseByok } from '@/lib/llm/byok';
import { generateStream } from '@/lib/llm/generate';
import { UnknownKindError, AppError, mapProviderError } from '@/lib/llm/errors';
import { newRequestId } from '@/lib/utils/id';
import { log } from '@/lib/utils/log';
import { NO_STORE } from '@/lib/api/with-api-errors';

export const runtime = 'nodejs';
export const maxDuration = 300;

type RouteContext = { params: Promise<{ kind: string }> };

export async function POST(req: Request, { params }: RouteContext): Promise<Response> {
  const { kind } = await params;
  const requestId = newRequestId();

  try {
    if (!isGeneratorKind(kind)) {
      throw new UnknownKindError(kind);
    }
    const byok = parseByok(req.headers);
    const body: unknown = await req.json().catch(() => ({}));
    return await generateStream({ kind, body, byok, requestId });
  } catch (error) {
    const appError = error instanceof AppError ? error : mapProviderError(error);
    if (!(error instanceof AppError)) {
      log.error(`generate ${kind} ${requestId}`, error);
    }
    return NextResponse.json(appError.toJson(), { status: appError.status, headers: NO_STORE });
  }
}
