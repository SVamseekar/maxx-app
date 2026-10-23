"use client";
import { useEffect, useState } from "react";

export default function SectionNav({ items, label = "On this page" }: { items: { id: string; label: string }[]; label?: string }) {
  const [active, setActive] = useState(items[0]?.id ?? "");
  useEffect(() => {
    const observer = new IntersectionObserver(entries => {
      const visible = entries.filter(entry => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (visible[0]) setActive(visible[0].target.id);
    }, { rootMargin: "-100px 0px -55% 0px" });
    for (const item of items) { const element = document.getElementById(item.id); if (element) observer.observe(element); }
    return () => observer.disconnect();
  }, [items]);
  return <nav className="section-nav" aria-label={label}>{items.map(item => <a key={item.id} href={`#${item.id}`} aria-current={active === item.id ? "location" : undefined} onClick={() => setActive(item.id)}>{item.label}</a>)}</nav>;
}
