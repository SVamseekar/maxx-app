import { acceptableUse, cookies, privacy, terms } from "./docs-core";
import { consumerRights, payments, prohibited, refunds, sellerTerms } from "./docs-market";
import { accessibility, ai, imprint, noticeAndAction, security, subprocessors } from "./docs-trust";
import type { Doc } from "./types";

export const DOCS: Doc[] = [terms, privacy, cookies, acceptableUse, sellerTerms, prohibited, refunds, payments, consumerRights, ai, security, accessibility, noticeAndAction, subprocessors, imprint];
export const BY_SLUG: Record<string, Doc> = Object.fromEntries(DOCS.map(doc => [doc.slug, doc]));
