import { bridge } from "../../../lib/api-proxy";

export const dynamic = "force-dynamic";
const handlers = bridge("cases", { maxDepth: 3, root: false });
export const GET = handlers.GET;
export const POST = handlers.POST;
