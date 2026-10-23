import { bridge } from "../../../lib/api-proxy";

export const dynamic = "force-dynamic";
const handlers = bridge("money", { maxDepth: 3, blocked: ["webhooks"] });
export const GET = handlers.GET;
export const POST = handlers.POST;
