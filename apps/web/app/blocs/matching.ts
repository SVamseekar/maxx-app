type Match = {requires_confirmation:boolean;candidates:{product_key:string;confidence:number}[]};
export function canCreateMatch(result:Match|null,key:string,confirmed:boolean):boolean {
  if (confirmed) return true;
  const candidate=result?.candidates.find(c=>c.product_key===key);
  return !!candidate && candidate.confidence>=.8 && !result?.requires_confirmation;
}
