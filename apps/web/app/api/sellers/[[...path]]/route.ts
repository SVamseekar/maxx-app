import { bridge } from "../../../lib/api-proxy";

export const dynamic = "force-dynamic";
const handlers = bridge("sellers", { maxDepth: 2, root: false });
export const GET = handlers.GET;
export const POST = handlers.POST;
