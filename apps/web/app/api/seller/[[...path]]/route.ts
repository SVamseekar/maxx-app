import { bridge } from "../../../lib/api-proxy";

export const dynamic = "force-dynamic";
const handlers = bridge("seller", { maxDepth: 3, root: true });
export const GET = handlers.GET;
export const POST = handlers.POST;
