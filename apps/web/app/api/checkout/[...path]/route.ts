import { bridge } from "../../../lib/api-proxy";

export const dynamic = "force-dynamic";
const handlers = bridge("checkout", { maxDepth: 3 });
export const GET = handlers.GET;
export const POST = handlers.POST;
