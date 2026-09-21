import { isGeneratorKind } from '@/lib/generators/kinds';
import { parseByok } from '@/lib/llm/byok';
import { generateStream } from '@/lib/llm/generate';
import { readJsonBody } from '@/lib/api/body-guard';
import { UnknownKindError } from '@/lib/llm/errors';
import { newRequestId } from '@/lib/utils/id';
import { withApiErrors } from '@/lib/api/with-api-errors';

export const runtime = 'nodejs';
export const maxDuration = 300;

type RouteContext = { params: Promise<{ kind: string }> };

async function postHandler(req: Request, { params }: RouteContext): Promise<Response> {
  const { kind } = await params;
  const requestId = newRequestId();
  if (!isGeneratorKind(kind)) {
    throw new UnknownKindError(kind);
  }
  const byok = parseByok(req.headers);
  const body: unknown = await readJsonBody(req);
  return generateStream({ kind, body, byok, requestId });
}

export const POST = withApiErrors(postHandler, () => 'generate');
