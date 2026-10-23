import { bridge } from "../../../lib/api-proxy";

export const dynamic = "force-dynamic";
const handlers = bridge("notifications", { maxDepth: 1, root: true });
export const GET = handlers.GET;
export const POST = handlers.POST;
