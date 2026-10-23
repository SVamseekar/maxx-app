import { Working } from "./components/ui";
export default function Loading() {
  return <main id="main-content" className="route-loading" aria-busy="true"><Working label="Opening your next view" /><div className="skeleton-heading" /><div className="skeleton-line" /><div className="skeleton-layout"><div /><div /></div></main>;
}
