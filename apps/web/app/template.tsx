import type { ReactNode } from "react";

/** Navigation never delays reading or shifts focus for a decorative entrance. */
export default function Template({ children }: { children: ReactNode }) {
  return <div className="page-content">{children}</div>;
}
