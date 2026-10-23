/** WebAuthn glue: the server speaks base64url JSON, the browser API wants ArrayBuffers. */

export function b64uToBuffer(value: string): ArrayBuffer {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (value.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

export function bufferToB64u(buffer: ArrayBuffer | ArrayBufferView): string {
  const bytes = buffer instanceof ArrayBuffer ? new Uint8Array(buffer) : new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

type Descriptor = { id: string; type: "public-key"; transports?: AuthenticatorTransport[] };
export type CreationJSON = { challenge: string; rp: { id?: string; name: string }; user: { id: string; name: string; displayName: string }; pubKeyCredParams: PublicKeyCredentialParameters[]; excludeCredentials?: Descriptor[]; timeout?: number; attestation?: AttestationConveyancePreference; authenticatorSelection?: AuthenticatorSelectionCriteria };
export type RequestJSON = { challenge: string; rpId?: string; allowCredentials?: Descriptor[]; timeout?: number; userVerification?: UserVerificationRequirement };

const descriptor = (item: Descriptor): PublicKeyCredentialDescriptor => ({ ...item, id: b64uToBuffer(item.id) });

export function creationOptions(json: CreationJSON): PublicKeyCredentialCreationOptions {
  return { ...json, challenge: b64uToBuffer(json.challenge), user: { ...json.user, id: b64uToBuffer(json.user.id) }, excludeCredentials: json.excludeCredentials?.map(descriptor) };
}

export function requestOptions(json: RequestJSON): PublicKeyCredentialRequestOptions {
  return { ...json, challenge: b64uToBuffer(json.challenge), allowCredentials: json.allowCredentials?.map(descriptor) };
}

export function registrationToJSON(credential: PublicKeyCredential) {
  const response = credential.response as AuthenticatorAttestationResponse;
  return {
    id: credential.id, rawId: bufferToB64u(credential.rawId), type: credential.type,
    response: {
      clientDataJSON: bufferToB64u(response.clientDataJSON), attestationObject: bufferToB64u(response.attestationObject),
      transports: response.getTransports?.() ?? [],
    },
    clientExtensionResults: credential.getClientExtensionResults(),
    authenticatorAttachment: credential.authenticatorAttachment ?? undefined,
  };
}

export function assertionToJSON(credential: PublicKeyCredential) {
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id, rawId: bufferToB64u(credential.rawId), type: credential.type,
    response: {
      clientDataJSON: bufferToB64u(response.clientDataJSON), authenticatorData: bufferToB64u(response.authenticatorData),
      signature: bufferToB64u(response.signature), userHandle: response.userHandle ? bufferToB64u(response.userHandle) : undefined,
    },
    clientExtensionResults: credential.getClientExtensionResults(),
  };
}

export const passkeysSupported = () => typeof window !== "undefined" && "PublicKeyCredential" in window && typeof navigator.credentials?.create === "function";

export async function conditionalSupported(): Promise<boolean> {
  try { return passkeysSupported() && (await PublicKeyCredential.isConditionalMediationAvailable?.()) === true; } catch { return false; }
}

/** Translate the browser's terse WebAuthn errors into something a person can act on. */
export function passkeyErrorMessage(error: unknown): string | null {
  const name = (error as { name?: string } | null)?.name;
  if (name === "NotAllowedError" || name === "AbortError") return null; // cancelled or timed out: say nothing
  if (name === "InvalidStateError") return "This device already has a passkey for your account.";
  if (name === "NotSupportedError" || name === "SecurityError") return "Passkeys are not available in this browser or at this address.";
  return "Something went wrong with the passkey. Try again, or use another way to sign in.";
}

export async function createPasskey(json: CreationJSON) {
  const credential = (await navigator.credentials.create({ publicKey: creationOptions(json) })) as PublicKeyCredential | null;
  if (!credential) throw new DOMException("Cancelled", "NotAllowedError");
  return registrationToJSON(credential);
}

export async function getPasskey(json: RequestJSON, options: { conditional?: boolean; signal?: AbortSignal } = {}) {
  const credential = (await navigator.credentials.get({
    publicKey: requestOptions(json), signal: options.signal,
    ...(options.conditional ? { mediation: "conditional" as CredentialMediationRequirement } : {}),
  })) as PublicKeyCredential | null;
  if (!credential) throw new DOMException("Cancelled", "NotAllowedError");
  return assertionToJSON(credential);
}
