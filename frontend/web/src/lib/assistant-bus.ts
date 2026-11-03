/** Lets any button on the site open the help assistant (optionally with a first question). */
type Listener = (question?: string) => void;

const listeners = new Set<Listener>();

export function openAssistant(question?: string): void {
  listeners.forEach((l) => l(question));
}

export function onOpenAssistant(l: Listener): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}
