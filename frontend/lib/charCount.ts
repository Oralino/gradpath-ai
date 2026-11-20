// Length in Unicode code points, which is how Python's len() (and so the backend's max_length)
// counts. String.length counts UTF-16 units and would count an emoji as 2.
export function charCount(text: string): number {
  return [...text].length;
}
