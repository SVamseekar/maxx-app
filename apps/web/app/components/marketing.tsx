import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowUpRight } from "lucide-react";
import { RevealText } from "./ambient";

/** Building blocks for the explanatory pages. Server components: no state, no scripts. */

export function PageHero({ eyebrow, title, children, actions }: { eyebrow?: string; title: ReactNode; children?: ReactNode; actions?: ReactNode }) {
  return <header className="page-hero">{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{typeof title === "string" ? <RevealText lines={[title]} /> : title}</h1>{children && <p className="lede">{children}</p>}{actions && <div className="hero-actions">{actions}</div>}</header>;
}

export function Band({ id, title, intro, children, tone }: { id?: string; title?: ReactNode; intro?: ReactNode; children: ReactNode; tone?: "raised" }) {
  return <section id={id} className={`band ${tone === "raised" ? "band-raised" : ""}`} aria-labelledby={id ? `${id}-h` : undefined}>{title && <div className="band-head"><h2 id={id ? `${id}-h` : undefined}>{title}</h2>{intro && <p>{intro}</p>}</div>}{children}</section>;
}

export function Steps({ items, variant }: { items: { title: string; body: ReactNode; icon?: ReactNode }[]; variant?: "timeline" }) {
  return <ol className={`steps-grid ${variant === "timeline" ? "steps-timeline" : ""}`}>{items.map((item, index) => <li key={item.title}><span className="step-number" aria-hidden="true">{item.icon ?? index + 1}</span><h3>{item.title}</h3><p>{item.body}</p></li>)}</ol>;
}

export function Features({ items }: { items: { title: string; body: ReactNode; icon?: ReactNode }[] }) {
  return <div className="feature-grid">{items.map(item => <article key={item.title} className="fx-card">{item.icon && <span className="feature-icon" aria-hidden="true">{item.icon}</span>}<h3>{item.title}</h3><p>{item.body}</p></article>)}</div>;
}

export function Callout({ title, children, tone = "info" }: { title: string; children: ReactNode; tone?: "info" | "warn" }) {
  return <aside className={`callout callout-${tone}`}><strong>{title}</strong><p>{children}</p></aside>;
}

export function Faq({ items }: { items: { q: string; a: ReactNode }[] }) {
  return <div className="faq-list">{items.map(item => <details key={item.q}><summary>{item.q}</summary><div>{typeof item.a === "string" ? <p>{item.a}</p> : item.a}</div></details>)}</div>;
}

export function CtaRow({ children }: { children: ReactNode }) {
  return <div className="cta-row">{children}</div>;
}

export function ButtonLink({ href, children, primary }: { href: string; children: ReactNode; primary?: boolean }) {
  return <Link className={`button ${primary ? "primary" : ""}`} href={href}>{children}<ArrowUpRight size={15} aria-hidden="true" /></Link>;
}

export function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return <div className="table-wrap"><table><thead><tr>{head.map(cell => <th key={cell} scope="col">{cell}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{row.map((cell, i) => i === 0 ? <th key={i} scope="row">{cell}</th> : <td key={i} data-label={head[i] || undefined}>{cell}</td>)}</tr>)}</tbody></table></div>;
}
