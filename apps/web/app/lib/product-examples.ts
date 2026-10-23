/** Editorial examples only. These are never used as merchant inventory or price evidence. */
export const PRODUCT_EXAMPLES = [
  { id: "sneaker", category: "Footwear", name: "Everyday runners", min: 100, max: 220, limit: 180, offer: 160, color: "#a95136" },
  { id: "camera", category: "Cameras", name: "A new perspective", min: 400, max: 800, limit: 700, offer: 620, color: "#617f91" },
  { id: "home", category: "Home", name: "Your everyday rituals", min: 80, max: 200, limit: 160, offer: 130, color: "#657349" },
] as const;
