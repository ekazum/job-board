type Child = Node | string | null | undefined | false;

/**
 * Create an element with attributes and children. Strings become text nodes, never HTML,
 * so pasted posting text cannot inject markup. `false` attributes are skipped, `true` ones are set empty.
 */
export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attributes: Record<string, string | boolean> = {},
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value !== false) {
      node.setAttribute(name, value === true ? "" : value);
    }
  }
  for (const child of children) {
    if (child !== null && child !== undefined && child !== false) {
      node.append(child);
    }
  }
  return node;
}
