import type { Metadata } from "next";
import { notFound } from "next/navigation";
import DocView from "../../components/doc-view";
import { BY_SLUG, DOCS } from "../docs";

type Props = { params: Promise<{ slug: string }> };
export function generateStaticParams() { return DOCS.map(doc => ({ slug: doc.slug })); }
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const doc = BY_SLUG[(await params).slug];
  return doc ? { title: `${doc.title} · Maxx`, description: doc.summary, alternates: { canonical: `/legal/${doc.slug}` } } : {};
}
export default async function Legal({ params }: Props) {
  const doc = BY_SLUG[(await params).slug];
  if (!doc) notFound();
  return <DocView doc={doc} />;
}
