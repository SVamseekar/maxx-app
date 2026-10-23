export type Block = string | { list: string[] } | { note: string } | { table: { head: string[]; rows: string[][] } };
export type Section = { id: string; title: string; body: Block[] };
export type Doc = { slug: string; title: string; summary: string; audience: string; sections: Section[] };
