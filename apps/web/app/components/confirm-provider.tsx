"use client";

import { createContext, useContext, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { X } from "lucide-react";

type Confirm = (message: string) => Promise<boolean>;
const Confirmation = createContext<Confirm>(() => Promise.resolve(false));
export const useConfirm = () => useContext(Confirmation);

/** Native modal supplies inert background, Escape handling and focus containment. */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null);
  const resolve = useRef<((answer: boolean) => void) | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => { if (message !== null && !dialog.current?.open) dialog.current?.showModal(); }, [message]);
  useEffect(() => () => { resolve.current?.(false); }, []);
  function finish(answer: boolean) {
    const complete = resolve.current;
    resolve.current = null;
    dialog.current?.close();
    setMessage(null);
    complete?.(answer);
  }
  function confirm(message: string) {
    resolve.current?.(false);
    return new Promise<boolean>(done => { resolve.current = done; setMessage(message); });
  }
  return <Confirmation.Provider value={confirm}>{children}<dialog ref={dialog} className="confirm-dialog" aria-labelledby={`${id}-title`} aria-describedby={`${id}-body`} onCancel={event => { event.preventDefault(); finish(false); }} onClose={() => { if (resolve.current) finish(false); }}>
    <button type="button" className="icon-button confirm-close" onClick={() => finish(false)} aria-label="Cancel action"><X size={18} /></button>
    <span className="dialog-kicker">Please review</span><h2 id={`${id}-title`}>Confirm this action</h2><p id={`${id}-body`}>{message}</p>
    <div className="confirm-actions"><button type="button" autoFocus onClick={() => finish(false)}>Cancel</button><button type="button" className="button primary" onClick={() => finish(true)}>Confirm action</button></div>
  </dialog></Confirmation.Provider>;
}
