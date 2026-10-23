import Image from "next/image";
import type { ReactNode } from "react";

/** Each editorial photograph has one assigned placement. Preserve its full composition. */
export default function EditorialImage({ kind, children }: { kind: "collective" | "fulfilment" | "scan" | "marketplace" | "detail"; children?: ReactNode }) {
  const asset = {
    collective: { src: "/artwork/collective-editorial.png", alt: "Illustrative headphones, camera and sneaker on limestone", width: 1536, height: 1024 },
    fulfilment: { src: "/artwork/fulfilment-editorial.png", alt: "Illustrative packing table with headphones, tissue and kraft parcels", width: 1536, height: 1024 },
    scan: { src: "/artwork/scan-editorial.png", alt: "Illustrative ivory headphones shown in full on stone", width: 1024, height: 1536 },
    marketplace: { src: "/artwork/shopping-still-life.webp", alt: "Illustrative phone, headphones and sneaker on dark stone", width: 1536, height: 1024 },
    detail: { src: "/artwork/headphones.webp", alt: "Illustrative black headphones on a stone surface", width: 1254, height: 1254 },
  }[kind];
  return <figure className={`editorial-image editorial-${kind}`}><Image src={asset.src} alt={asset.alt} width={asset.width} height={asset.height} sizes="(max-width: 800px) 90vw, 60vw" /><figcaption>{children && <span className="editorial-caption-title">{children}</span>}<span>Original illustrative artwork</span></figcaption></figure>;
}
