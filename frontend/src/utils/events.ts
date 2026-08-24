export function emit<T>(
  target: EventTarget,
  type: string,
  detail: T,
): boolean {
  return target.dispatchEvent(
    new CustomEvent<T>(type, {
      bubbles: true,
      composed: true,
      detail,
    }),
  );
}
