export type ClassValue = string | undefined | null | false;

export function clsx(...inputs: ClassValue[]) {
  return inputs.filter(Boolean).join(" ");
}