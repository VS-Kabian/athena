import { safeHref } from "@/lib/safeHref";

test("passes through absolute https/http URLs unchanged", () => {
  expect(safeHref("https://x.com")).toBe("https://x.com");
  expect(safeHref("http://x.com")).toBe("http://x.com");
});

test("rejects dangerous schemes", () => {
  expect(safeHref("javascript:alert(1)")).toBeUndefined();
  expect(safeHref("data:text/html,x")).toBeUndefined();
});

test("rejects missing/relative/protocol-relative URLs", () => {
  expect(safeHref(undefined)).toBeUndefined();
  expect(safeHref("")).toBeUndefined();
  expect(safeHref("//evil.com")).toBeUndefined();
  expect(safeHref("/relative/path")).toBeUndefined();
  expect(safeHref("not a url")).toBeUndefined();
});
