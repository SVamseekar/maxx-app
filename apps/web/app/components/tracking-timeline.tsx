"use client";
import { Check, CircleAlert, MapPin, Package, Truck } from "lucide-react";

type Event = { status: string; message: string; location: string; at: number };

export const TRACKING_LABEL: Record<string, string> = {
  pre_transit: "Label created", in_transit: "In transit", out_for_delivery: "Out for delivery", delivered: "Delivered",
  available_for_pickup: "Ready for pickup", return_to_sender: "Returning to sender", failure: "Delivery failed", unknown: "Waiting for the carrier", cancelled: "Cancelled", error: "Tracking error",
};
const TROUBLE = new Set(["return_to_sender", "failure", "cancelled", "error"]);

function when(seconds: number) {
  return new Date(seconds * 1000).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** The carrier's own events for a parcel, newest first. */
export default function TrackingTimeline({ events, status, estimated, simulated }: { events: Event[]; status: string; estimated?: number | null; simulated?: boolean }) {
  if (!events.length && !status) return null;
  const ordered = [...events].reverse();
  return <section className="tracking" aria-label="Carrier tracking">
    <header><span className={TROUBLE.has(status) ? "tracking-status trouble" : status === "delivered" ? "tracking-status done" : "tracking-status"}>{TROUBLE.has(status) ? <CircleAlert size={14} aria-hidden="true" /> : status === "delivered" ? <Check size={14} aria-hidden="true" /> : <Truck size={14} aria-hidden="true" />} {TRACKING_LABEL[status] ?? "Tracking"}</span>
      {estimated && status !== "delivered" && <span className="muted small">Expected by {new Date(estimated * 1000).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}</span>}
      {simulated && <span className="muted small">Simulated carrier</span>}</header>
    {ordered.length > 0 && <ol>{ordered.map((event, index) => <li key={`${event.status}-${event.at}-${index}`}><Package size={13} aria-hidden="true" /><div><strong>{TRACKING_LABEL[event.status] ?? event.status}</strong>{event.message && <span>{event.message}</span>}<small>{when(event.at)}{event.location && <> · <MapPin size={11} aria-hidden="true" /> {event.location}</>}</small></div></li>)}</ol>}
  </section>;
}
