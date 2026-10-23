/** Countries Maxx supports for sellers and delivery. Codes are ISO 3166-1 alpha-2. */
export const COUNTRIES: Record<string, string> = {
  US: "United States", CA: "Canada", GB: "United Kingdom", IE: "Ireland", DE: "Germany", FR: "France", ES: "Spain", IT: "Italy", NL: "Netherlands", BE: "Belgium",
  AT: "Austria", PT: "Portugal", SE: "Sweden", DK: "Denmark", FI: "Finland", NO: "Norway", PL: "Poland", CZ: "Czechia", AU: "Australia", NZ: "New Zealand",
  IN: "India", SG: "Singapore", JP: "Japan", AE: "United Arab Emirates",
};
export const countryName = (code: string) => COUNTRIES[code] ?? code;
