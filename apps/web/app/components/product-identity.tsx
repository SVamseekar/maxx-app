import { Headphones, Smartphone, Laptop, Package, Watch, Wind } from "lucide-react";

/** Category illustration, not a claim that a stock photograph depicts the item. */
export default function ProductIdentity({ title }: { title: string }) {
  const key = title.toLowerCase();
  const category = /headphone|earbud|airpod|sony wh/.test(key) ? "Audio" : /phone|iphone|pixel|galaxy/.test(key) ? "Mobile" : /laptop|macbook|notebook/.test(key) ? "Computing" : /watch/.test(key) ? "Wearables" : /vacuum|dyson|cleaner/.test(key) ? "Home" : "Group purchase";
  const Icon = { Audio: Headphones, Mobile: Smartphone, Computing: Laptop, Wearables: Watch, Home: Wind, "Group purchase": Package }[category];
  return <div className="product-identity" data-category={category}><Icon size={44} strokeWidth={1.15} aria-hidden="true" /><span>{category}</span></div>;
}
